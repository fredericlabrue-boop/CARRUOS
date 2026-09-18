"""Adaptateurs de données. Deux sources, même contrat de sortie :
un DataFrame index=datetime, colonnes open/high/low/close/volume, ordre croissant.

NOTE : ce module n'a PAS pu être testé ici (le conteneur n'a pas accès aux
fournisseurs de données). Le reste du paquet, lui, est testé sur données
synthétiques. Lance `python -m equity_scanner.data --selftest AAPL` chez toi
avant la première vraie passe.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[[c for c in COLS if c in df.columns]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.sort_index().dropna()


# --- yfinance ---------------------------------------------------------
def load_yf(ticker: str, years: int = 3) -> pd.DataFrame:
    import yfinance as yf

    start = dt.date.today() - dt.timedelta(days=int(years * 365.25))
    df = yf.download(ticker, start=start, progress=False, auto_adjust=False)
    if df is None or df.empty:
        raise ValueError(f"aucune donnée pour {ticker}")
    return _normalise(df)


def days_to_earnings_lot(tickers, fils: int = 8) -> dict:
    """Dates de resultats de plusieurs titres, en parallele.

    Un appel reseau par titre : les enchainer, c'est attendre autant de
    fois de suite. A n'appeler que sur les titres pour qui la reponse
    CHANGE quelque chose — voir `scan.resout_resultats()`.
    """
    from concurrent.futures import ThreadPoolExecutor

    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {}
    n = max(1, min(int(fils), 16, len(tickers)))
    with ThreadPoolExecutor(max_workers=n) as pool:
        return dict(zip(tickers, pool.map(days_to_earnings_yf, tickers)))


def days_to_earnings_yf(ticker: str) -> int | None:
    """Renvoie None si la date est introuvable. None = INCONNU, pas SANS RISQUE :
    rules.evaluate() pose alors un veto explicite."""
    try:
        import yfinance as yf

        cal = yf.Ticker(ticker).calendar
        d = None
        if isinstance(cal, dict):
            v = cal.get("Earnings Date")
            d = (v[0] if isinstance(v, (list, tuple)) and v else v)
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            d = cal.iloc[0, 0]
        if d is None:
            return None
        d = pd.Timestamp(d).tz_localize(None).date()
        return len(pd.bdate_range(dt.date.today(), d)) if d >= dt.date.today() else None
    except Exception:
        return None


# --- IBKR (ib_insync) -------------------------------------------------
def load_ibkr(ticker: str, years: int = 3, host="127.0.0.1", port=7497, cid=17):
    """Nécessite TWS ou IB Gateway lancé, API activée
    (Global Configuration → API → Settings → Enable ActiveX and Socket Clients).
    Port 7497 = paper, 7496 = live."""
    from ib_insync import IB, Stock, util

    ib = IB()
    ib.connect(host, port, clientId=cid, readonly=True)
    try:
        contract = Stock(ticker, "SMART", "USD")
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract, endDateTime="", durationStr=f"{years} Y",
            barSizeSetting="1 day", whatToShow="TRADES", useRTH=True,
        )
        return _normalise(util.df(bars).set_index("date"))
    finally:
        ib.disconnect()


LOADERS = {"yf": load_yf, "ibkr": load_ibkr}

_NOMS = {"yf": "load_yf", "ibkr": "load_ibkr"}


def loader(source: str = "yf"):
    """Fonction de chargement, resolue AU MOMENT DE L'APPEL.

    `LOADERS` fige la reference a l'import : une fois le module charge,
    remplacer `data.load_yf` — ce que font les tests pour travailler sur
    des series synthetiques, sans reseau — n'a plus aucun effet sur les
    appelants qui passent par la table. On resout donc par son nom.
    """
    import sys as _sys
    nom = _NOMS.get(source)
    if nom is None:
        raise ValueError(f"source inconnue : {source}")
    return getattr(_sys.modules[__name__], nom)


# --- Univers europeen ~180 grandes capitalisations -------------------
# Liste figee : Wikipedia change de structure et casse le parsing.
# Si un ticker renvoie une erreur au scan, signale-le, il sera retire.
_CAC = """MC OR TTE SAN SU AIR AI EL RMS BNP DG CS SAF KER ORA VIE LR CAP PUB
ACA GLE ML RI BN EN SGO VIV HO ERF DSY TEP ENGI EDEN ALO RNO CA STLAP URW"""
_DAX = """SAP SIE ALV DTE MRK BAS BAYN BMW MBG VOW3 ADS DBK MUV2 RWE DB1 IFX
HEN3 EOAN FRE HEI CON ZAL SY1 SRT3 PAH3 BEI MTX QIA 1COV DHL CBK RHM ENR P911
HNR1 BNR FME"""
_AEX = """ASML ADYEN HEIA INGA PHIA RAND KPN DSFIR AKZA WKL ABN AD MT NN AGN
PRX BESI ASM IMCD REN"""
_IBEX = """SAN BBVA ITX IBE REP TEF AENA FER AMS CLNX ACS ELE NTGY CABK MAP
GRF ENG COL SAB"""
_MIB = """ENEL ISP ENI UCG RACE G TIT PST MB SRG TRN BAMI LDO CPR MONC TEN
AMP BMED STLAM"""


def _suf(blob: str, suffixe: str) -> list[str]:
    return [x + suffixe for x in blob.split()]


def europe_tickers() -> list[str]:
    """~180 grandes capitalisations europeennes, 5 places."""
    return sorted(set(
        _suf(_CAC, ".PA") + _suf(_DAX, ".DE") + _suf(_AEX, ".AS")
        + _suf(_IBEX, ".MC") + _suf(_MIB, ".MI")))


def cac40_tickers_fige() -> list[str]:
    return sorted(_suf(_CAC, ".PA"))


# Wikipedia renvoie 403 a toute requete sans User-Agent. pandas.read_html
# appelle urllib avec son UA par defaut : il faut donc telecharger la page
# nous-memes, puis passer le HTML a pandas.
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _html(url: str, timeout: int = 25) -> str:
    import urllib.request
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _wiki(url: str, col: str, suffixe: str = "") -> list[str]:
    import io
    for tab in pd.read_html(io.StringIO(_html(url))):
        if col in tab.columns:
            s = tab[col].astype(str).str.strip()
            s = s.str.replace(".", "-", regex=False) if not suffixe else s
            return sorted({x + suffixe for x in s if x and x.lower() != "nan"})
    raise ValueError(f"colonne {col} introuvable sur {url}")


def cac40_tickers() -> list[str]:
    """CAC 40. yfinance veut le suffixe .PA pour Euronext Paris."""
    return _wiki("https://en.wikipedia.org/wiki/CAC_40", "Ticker")


def dax_tickers() -> list[str]:
    """DAX. Repli sur la liste figee si Wikipedia refuse."""
    try:
        return _wiki("https://en.wikipedia.org/wiki/DAX", "Ticker")
    except Exception:
        print("  Wikipedia indisponible. Repli sur la liste DAX figee.")
        return sorted(_suf(_DAX, ".DE"))


# Repli si Wikipedia est injoignable : 120 grandes capitalisations US tres
# liquides. Moins complet que le S&P 500, mais toujours exploitable.
_US = """AAPL MSFT NVDA GOOGL GOOG AMZN META AVGO TSLA BRK-B LLY JPM V UNH XOM
MA COST HD PG JNJ WMT ABBV NFLX CRM BAC ORCL MRK AMD KO PEP TMO LIN ACN CSCO
ADBE MCD ABT WFC PM DIS TXN GE CAT VZ INTU IBM QCOM DHR CMCSA NOW AMGN PFE
NEE UNP SPGI RTX AXP LOW UBER T HON BKNG COP ELV PGR ETN BSX SYK TJX VRTX
PLD MDT C BLK ADI MMC SCHW LMT CB ADP MU PANW REGN KLAC AMAT LRCX SBUX GILD
DE BA MDLZ ISRG SO CI ZTS INTC TMUS DUK CME EQIX SHW ITW APH MO NKE PYPL
ANET CRWD SNPS CDNS MRVL FTNT ORLY MCK NOC WM APD CSX PH ECL EMR"""


def us_tickers_fige() -> list[str]:
    return sorted(set(_US.split()))


def sp500_tickers() -> list[str]:
    """S&P 500 depuis Wikipedia, avec repli sur une liste figee.

    Attention pour un backtest : cette liste est la composition ACTUELLE.
    Fige un CSV date si tu veux eviter le biais du survivant.
    """
    import io
    try:
        for tab in pd.read_html(io.StringIO(
                _html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"))):
            if "Symbol" in tab.columns:
                return sorted(tab["Symbol"].astype(str).str.strip()
                              .str.replace(".", "-", regex=False).tolist())
        raise ValueError("colonne Symbol introuvable")
    except Exception as exc:
        print(f"  Wikipedia indisponible ({type(exc).__name__}). "
              f"Repli sur la liste figee de 120 grandes capitalisations US.")
        return us_tickers_fige()


# ---------------------------------------------------------------------
# Univers elargis
#
# "Toute la bourse" n'est pas realiste : la cote US compte plus de 5 000
# lignes, dont l'immense majorite est ecartee d'office par les vetos
# (prix sous 10, volume en dollars sous 20 M). Ces univers couvrent ce
# qui reste reellement negociable.
# ---------------------------------------------------------------------

def nasdaq100_tickers() -> list[str]:
    try:
        return _wiki("https://en.wikipedia.org/wiki/Nasdaq-100", "Ticker")
    except Exception:
        try:
            return _wiki("https://en.wikipedia.org/wiki/Nasdaq-100", "Symbol")
        except Exception as exc:
            print(f"  Nasdaq 100 indisponible ({type(exc).__name__}).")
            return []


def sp400_tickers() -> list[str]:
    """Moyennes capitalisations americaines."""
    try:
        return _wiki("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
                     "Symbol")
    except Exception as exc:
        print(f"  S&P 400 indisponible ({type(exc).__name__}).")
        return []


def us_large_tickers() -> list[str]:
    """S&P 500 + Nasdaq 100, dedoublonne. Environ 520 titres."""
    v = list(dict.fromkeys(sp500_tickers() + nasdaq100_tickers()))
    print(f"  Univers US large : {len(v)} titres.")
    return v


def us_total_tickers() -> list[str]:
    """S&P 500 + Nasdaq 100 + S&P 400. Environ 900 titres, 25 a 40 min."""
    v = list(dict.fromkeys(sp500_tickers() + nasdaq100_tickers()
                           + sp400_tickers()))
    print(f"  Univers US complet : {len(v)} titres. Compte 25 a 40 minutes.")
    return v


# Suffixe Yahoo par place de cotation, pour le STOXX 600
_PLACES = {"Paris": ".PA", "Amsterdam": ".AS", "Frankfurt": ".DE",
           "Xetra": ".DE", "Milan": ".MI", "Madrid": ".MC",
           "Brussels": ".BR", "Lisbon": ".LS", "Helsinki": ".HE",
           "Stockholm": ".ST", "Copenhagen": ".CO", "Oslo": ".OL",
           "London": ".L", "Zurich": ".SW", "Vienna": ".VI",
           "Dublin": ".IR", "Warsaw": ".WA"}


def stoxx600_tickers() -> list[str]:
    """STOXX Europe 600. Les tickers Wikipedia portent deja leur suffixe."""
    try:
        import io
        blob = _html("https://en.wikipedia.org/wiki/STOXX_Europe_600")
        for df in pd.read_html(io.StringIO(blob)):
            col = next((c for c in df.columns
                        if str(c).strip().lower() in ("ticker", "symbol")), None)
            if col is None or len(df) < 300:
                continue
            v = [str(x).strip().upper() for x in df[col].dropna()]
            v = [x for x in v if 1 < len(x) < 12 and x != "NAN"]
            if len(v) > 300:
                print(f"  STOXX Europe 600 : {len(v)} titres.")
                return v
        raise ValueError("table introuvable")
    except Exception as exc:
        print(f"  STOXX 600 indisponible ({type(exc).__name__}). "
              f"Repli sur la liste europeenne figee.")
        return europe_tickers()


def europe_total_tickers() -> list[str]:
    """STOXX 600 + CAC 40 + DAX + liste figee, dedoublonne."""
    v = list(dict.fromkeys(stoxx600_tickers() + cac40_tickers_fige()
                           + dax_tickers() + europe_tickers()))
    print(f"  Univers Europe complet : {len(v)} titres. "
          f"Compte 20 a 30 minutes.")
    return v


UNIVERS = {
    "sp500": ("S&P 500", sp500_tickers),
    "nasdaq100": ("Nasdaq 100", nasdaq100_tickers),
    "us": ("US large (S&P 500 + Nasdaq 100)", us_large_tickers),
    "us_total": ("US complet (+ moyennes capitalisations)", us_total_tickers),
    "cac40": ("CAC 40", cac40_tickers_fige),
    "dax": ("DAX", dax_tickers),
    "europe": ("Europe (liste figee)", europe_tickers),
    "stoxx600": ("STOXX Europe 600", stoxx600_tickers),
    "europe_total": ("Europe complet", europe_total_tickers),
}


# =====================================================================
# Univers historiques — chantier n°1 du registre : le biais du survivant
#
# Toutes les fonctions ci-dessus rendent la composition D'AUJOURD'HUI.
# Rejouer 2010-2021 sur la liste actuelle du S&P 500, c'est tester une
# strategie sur les seules societes qui ont SURVECU jusqu'en 2026 : les
# faillites, les rachats et les retraits de cote ont ete retires de
# l'echantillon apres coup. Le backtest ne peut alors pas perdre sur
# elles, et son resultat est mecaniquement flatte.
#
# Aucune ruse ne repare ca : il faut la vraie composition d'epoque. Ce
# que ce module apporte :
#
#   1. figer_univers()      enregistre la composition DU JOUR, datee.
#      Lancee une fois par trimestre, elle construit l'historique qui
#      manque. On ne peut pas remonter le temps, on peut arreter de le
#      perdre.
#   2. univers_a_la_date()  relit la composition connue la plus proche
#      AVANT une date donnee, et jamais apres.
#   3. avertissement()      dit en toutes lettres, dans le rapport, que
#      le resultat est flatte quand aucune composition d'epoque n'existe.
#
# Format du fichier : CSV a une colonne `ticker`, nomme
# `<cle>-AAAA-MM-JJ.csv` dans .bruce_cache/univers/.
# Un CSV recupere ailleurs (fournisseur, archive) se depose la et sera lu
# de la meme facon.
# =====================================================================

DOSSIER_UNIVERS = Path(".bruce_cache") / "univers"


def figer_univers(cle: str, tickers: list[str] | None = None,
                  date: str | None = None) -> Path:
    """Enregistre la composition d'un univers a une date. Rend le chemin."""
    if cle not in UNIVERS:
        raise ValueError(f"univers inconnu : {cle}")
    tickers = tickers if tickers is not None else UNIVERS[cle][1]()
    jour = date or dt.date.today().isoformat()
    DOSSIER_UNIVERS.mkdir(parents=True, exist_ok=True)
    f = DOSSIER_UNIVERS / f"{cle}-{jour}.csv"
    f.write_text("ticker\n" + "\n".join(sorted(set(tickers))) + "\n",
                 encoding="utf-8")
    return f


def compositions(cle: str) -> list[tuple[str, Path]]:
    """Compositions figees disponibles pour cet univers, du plus ancien
    au plus recent. Rend [(date, chemin)]."""
    out = []
    try:
        for f in DOSSIER_UNIVERS.glob(f"{cle}-*.csv"):
            jour = f.stem[len(cle) + 1:]
            try:
                dt.date.fromisoformat(jour)
            except ValueError:
                continue
            out.append((jour, f))
    except Exception:
        return []
    return sorted(out)


def univers_a_la_date(cle: str, date: str) -> tuple[list[str], str]:
    """Composition connue la plus proche AVANT `date`.

    Rend (tickers, date_de_la_composition). Si rien n'a ete fige avant
    cette date, rend ([], "") — a l'appelant de dire qu'il se rabat sur
    la composition actuelle, et de le dire fort.
    """
    dispo = [(j, f) for j, f in compositions(cle) if j <= date]
    if not dispo:
        return [], ""
    jour, f = dispo[-1]
    lignes = [l.strip() for l in f.read_text(encoding="utf-8").splitlines()]
    tickers = [l for l in lignes[1:] if l and l.lower() != "nan"]
    return sorted(set(tickers)), jour


def avertissement(cle: str, debut: str) -> str:
    """Phrase a afficher dans tout rapport de backtest. Vide si une
    composition d'epoque couvre le debut de la periode testee."""
    _, jour = univers_a_la_date(cle, debut)
    if jour:
        return ""
    return (f"BIAIS DU SURVIVANT : aucune composition de « {cle} » figee "
            f"avant {debut}. Le test tourne sur la liste D'AUJOURD'HUI, "
            f"donc sur les seules societes qui ont survecu. Le resultat est "
            f"flatte d'un montant inconnu, et generalement de plusieurs "
            f"points par an. Lance `py -m equity_scanner.data --figer {cle}` "
            f"chaque trimestre pour cesser de perdre cette information.")


def _main_univers() -> None:
    import argparse
    a = argparse.ArgumentParser(description="Univers et compositions figees")
    a.add_argument("--figer", metavar="CLE", default=None,
                   help="enregistre la composition du jour")
    a.add_argument("--liste", metavar="CLE", default=None,
                   help="montre les compositions figees disponibles")
    a.add_argument("--selftest", metavar="TICKER", default=None,
                   help="verifie qu'un ticker se charge chez le fournisseur")
    o = a.parse_args()
    if o.selftest:
        d = load_yf(o.selftest)
        print(f"\n  {o.selftest} : {len(d)} barres, "
              f"{d.index[0].date()} → {d.index[-1].date()}")
        print(d.tail(3).to_string(), "\n")
        return
    if o.figer:
        f = figer_univers(o.figer)
        n = len(f.read_text(encoding="utf-8").splitlines()) - 1
        print(f"\n  Composition de « {o.figer} » figee : {n} titres → {f}\n")
        return
    cle = o.liste or ""
    if cle:
        c = compositions(cle)
        print(f"\n  COMPOSITIONS FIGEES DE « {cle} » : {len(c)}")
        for jour, f in c:
            n = len(f.read_text(encoding="utf-8").splitlines()) - 1
            print(f"    {jour}   {n:>4} titres")
        if not c:
            print("    aucune. `--figer " + cle + "` en enregistre une.")
        print()
        return
    print("\n  UNIVERS DISPONIBLES")
    for k, (nom, _) in UNIVERS.items():
        c = compositions(k)
        print(f"    {k:<14}{nom:<44}{len(c)} composition(s) figee(s)")
    print()


if __name__ == "__main__":
    _main_univers()
