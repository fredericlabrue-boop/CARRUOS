"""Adaptateurs de données. Deux sources, même contrat de sortie :
un DataFrame index=datetime, colonnes open/high/low/close/volume, ordre croissant.

NOTE : ce module n'a PAS pu être testé ici (le conteneur n'a pas accès aux
fournisseurs de données). Le reste du paquet, lui, est testé sur données
synthétiques. Lance `python -m equity_scanner.data --selftest AAPL` chez toi
avant la première vraie passe.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
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
    """S&P 500 depuis Wikipedia, ou la derniere liste chargee avec succes.

    Attention pour un backtest : cette liste est la composition ACTUELLE.
    Fige un CSV date si tu veux eviter le biais du survivant.

    L'ancien repli rendait la liste figee de 120 grandes capitalisations
    sous l'etiquette « S&P 500 » : un univers ampute sous un nom faux.
    Le repli est maintenant la derniere liste COMPLETE, datee ; sans elle,
    l'arret (`UniversIndisponible`). `us_tickers_fige()` reste disponible
    pour qui veut explicitement les 120.
    """
    return charge_composante("sp500")["tickers"]


# ---------------------------------------------------------------------
# Univers elargis
#
# "Toute la bourse" n'est pas realiste : la cote US compte plus de 5 000
# lignes, dont l'immense majorite est ecartee d'office par les vetos
# (prix sous 10, volume en dollars sous 20 M). Ces univers couvrent ce
# qui reste reellement negociable.
# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# Composantes des univers americains — chargees une par une, comptees,
# et jamais remplacees en silence.
#
# Le 29/09/2026, la preparation de l'hypothese n°2 a affiche « Nasdaq 100
# indisponible (ValueError) » puis 503 titres, sous l'etiquette « S&P 500
# + Nasdaq 100 ». Wikipedia avait deplace la table des composants de la
# page « Nasdaq-100 » vers « List of NASDAQ-100 companies » ; la fonction
# rendait une liste VIDE, et l'union ne contenait plus que le S&P 500.
#
# Trois regles, dans cet ordre :
#   1. chaque composante a ses adresses, essayees tour a tour, et un
#      nombre MINIMAL de lignes : une table tronquee n'est pas une liste ;
#   2. chaque liste chargee avec succes est gardee, datee
#      (`~/.carruos/univers/dernieres/`, qui survit aux mises a jour) ;
#   3. en cas d'echec, repli sur cette derniere liste, AVEC SA DATE, que le
#      rapport affiche. Sans elle : arret, `UniversIndisponible`.
# Jamais un univers ampute sous une etiquette fausse.
#
# Les minimums sont des seuils de COMPLETUDE de donnees : ils ne regardent
# aucun rendement et n'entrent dans aucune empreinte.
# ---------------------------------------------------------------------

_WP = "https://en.wikipedia.org/wiki/"

COMPOSANTES = {
    "sp500": {"nom": "S&P 500", "min": 480,
              "sources": [(_WP + "List_of_S%26P_500_companies", "Symbol")]},
    "nasdaq100": {"nom": "Nasdaq 100", "min": 95,
                  "sources": [(_WP + "List_of_NASDAQ-100_companies", "Ticker"),
                              (_WP + "List_of_NASDAQ-100_companies", "Symbol"),
                              (_WP + "Nasdaq-100", "Ticker"),
                              (_WP + "Nasdaq-100", "Symbol")]},
    "sp400": {"nom": "S&P 400", "min": 380,
              "sources": [(_WP + "List_of_S%26P_400_companies", "Symbol")]},
}

COMPOSEES = {"us": ("sp500", "nasdaq100"),
             "us_total": ("sp500", "nasdaq100", "sp400")}


class UniversIndisponible(RuntimeError):
    """Une composante n'a pu etre chargee, et aucune liste anterieure
    n'existe pour la remplacer. On s'arrete plutot que de tester un
    univers ampute sous le nom de l'univers complet."""


def _dossier_dernieres() -> Path:
    return DOSSIER_UNIVERS / "dernieres"


def _derniere(cle: str) -> dict | None:
    for dossier in (_dossier_dernieres(),
                    ANCIEN_DOSSIER_UNIVERS / "dernieres"):
        try:
            v = json.loads((dossier / f"{cle}.json")
                           .read_text(encoding="utf-8"))
            if v.get("tickers") and v.get("date"):
                return v
        except (OSError, ValueError, AttributeError):
            continue
    return None


def _garde_derniere(cle: str, tickers: list[str], source: str) -> None:
    f = _dossier_dernieres() / f"{cle}.json"
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"date": dt.date.today().isoformat(),
                                   "source": source, "tickers": tickers},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, f)
    except OSError as exc:
        print(f"  (liste {cle} non gardee : {exc})")


def charge_composante(cle: str, repli: bool = True, journal=print) -> dict:
    """Une composante : {cle, nom, tickers, source, date, motif}.

    `source` vaut « direct » (chargee a l'instant) ou « repli » (la
    derniere liste chargee avec succes, du `date` indique). `motif` dit
    pourquoi le chargement direct a echoue. `repli=False` : pas de
    repli, l'echec leve — c'est ce que fait `figer_univers()`, qui
    daterait sinon d'aujourd'hui une liste plus ancienne.
    """
    c = COMPOSANTES[cle]
    motifs = []
    for url, col in c["sources"]:
        try:
            v = _wiki(url, col)
        except Exception as exc:
            motifs.append(f"{url.rsplit('/', 1)[-1]} [{col}] : "
                          f"{type(exc).__name__}: {exc}")
            continue
        if len(v) < c["min"]:
            motifs.append(f"{url.rsplit('/', 1)[-1]} [{col}] : table de "
                          f"{len(v)} lignes, au moins {c['min']} attendues")
            continue
        _garde_derniere(cle, v, url)
        return {"cle": cle, "nom": c["nom"], "tickers": v,
                "source": "direct", "date": dt.date.today().isoformat(),
                "motif": ""}
    motif = " ; ".join(motifs)
    der = _derniere(cle) if repli else None
    if der:
        journal(f"  {c['nom']} : chargement impossible — REPLI sur la liste "
                f"du {der['date']} ({len(der['tickers'])} titres).")
        return {"cle": cle, "nom": c["nom"], "tickers": list(der["tickers"]),
                "source": "repli", "date": der["date"], "motif": motif}
    if repli:
        raise UniversIndisponible(
            f"{c['nom']} : chargement impossible, et aucune liste n'a "
            f"jamais été chargée avec succès sur ce poste pour s'y replier. "
            f"Rien n'est lancé : un univers amputé de cette composante "
            f"serait testé sous un nom qui n'est pas le sien. "
            f"Vérifiez la connexion à Wikipédia, puis relancez. Détail : "
            f"{motif}")
    raise UniversIndisponible(
        f"{c['nom']} : chargement impossible ({motif}). Une liste de repli "
        f"ne peut pas être figée sous la date du jour.")


def univers_detaille(cle: str, repli: bool = True,
                     journal=print) -> tuple[list[str], list[dict]]:
    """Un univers compose : (tickers dedoublonnes, detail par composante).

    Chaque composante porte son nombre REEL de titres, sa source et sa
    date — c'est ce que les rapports affichent. Leve
    `UniversIndisponible` si une composante manque sans repli possible.
    """
    comps = [charge_composante(k, repli=repli, journal=journal)
             for k in COMPOSEES[cle]]
    tickers = list(dict.fromkeys(t for c in comps for t in c["tickers"]))
    for c in comps:
        journal(f"    {c['nom']:<12}{len(c['tickers']):>5} titres  "
                + (f"chargé le {c['date']}" if c["source"] == "direct"
                   else f"REPLI sur la liste du {c['date']}"))
    return tickers, comps


def resume_composantes(comps: list[dict]) -> list[dict]:
    """Le detail sans les listes : ce qu'un instantane ou un rapport garde."""
    return [{k: v for k, v in c.items() if k != "tickers"}
            | {"n": len(c["tickers"])} for c in comps]


def nasdaq100_tickers() -> list[str]:
    return charge_composante("nasdaq100")["tickers"]


def sp400_tickers() -> list[str]:
    """Moyennes capitalisations americaines."""
    return charge_composante("sp400")["tickers"]


def us_large_tickers() -> list[str]:
    """S&P 500 + Nasdaq 100, dedoublonne. Environ 520 titres."""
    v, _ = univers_detaille("us")
    print(f"  Univers US large : {len(v)} titres.")
    return v


def us_total_tickers() -> list[str]:
    """S&P 500 + Nasdaq 100 + S&P 400. Environ 900 titres, 25 a 40 min."""
    v, _ = univers_detaille("us_total")
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
# Profondeur des cours
#
# La preparation de l'hypothese n°2 chargeait un nombre FIXE d'annees (8).
# Le 29/09/2026, cela faisait commencer les cours fin 2018 : la
# « repetition generale 2010-2021 » n'a couvert que 2019-2021, sans que le
# rapport le dise. La profondeur se calcule donc depuis le DEBUT de la
# periode de conception, prechauffage des indicateurs compris.
#
# Un nombre ENTIER d'annees, arrondi au-dessus : le cache nomme ses
# fichiers d'apres lui, et une profondeur au jour pres retelechargerait
# tout l'univers chaque matin.
# =====================================================================

# Le plus long des indicateurs lus par les regles est la SMA 200 (regime
# E6, `indicators.PERIODES`) ; 260 seances est aussi l'historique minimal
# en dessous duquel un titre est ecarte. Une annee boursiere de 252
# seances fait 365,25 jours de calendrier.
PRECHAUFFAGE_SEANCES = 260


def annees_de_cours(debut: str, seances: int = PRECHAUFFAGE_SEANCES,
                    aujourdhui: dt.date | None = None) -> int:
    """Nombre d'annees de cours a charger pour que les indicateurs soient
    chauds des `debut` : de `debut` moins `seances` seances jusqu'a
    aujourd'hui, arrondi a l'annee superieure."""
    jour = aujourdhui or dt.date.today()
    depart = (dt.date.fromisoformat(debut)
              - dt.timedelta(days=seances * 365.25 / 252))
    return max(1, math.ceil((jour - depart).days / 365.25))


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
# `<cle>-AAAA-MM-JJ.csv` dans ~/.carruos/univers/.
# Un CSV recupere ailleurs (fournisseur, archive) se depose la et sera lu
# de la meme facon.
#
# Pourquoi ~/.carruos/ et plus .bruce_cache/ : `.bruce_cache` vit a cote
# du programme et n'est pas livre dans l'archive. Une mise a jour
# installee dans un nouveau dossier repartait donc sans aucune
# composition figee — alors que tout l'interet est de les accumuler,
# trimestre apres trimestre, pendant des annees. C'est la meme lecon que
# la cle Alpha Vantage. L'ancien dossier reste LU : ce qui y a ete fige
# n'est pas perdu.
# =====================================================================

DOSSIER_UNIVERS = Path.home() / ".carruos" / "univers"
ANCIEN_DOSSIER_UNIVERS = Path(".bruce_cache") / "univers"


def figer_univers(cle: str, tickers: list[str] | None = None,
                  date: str | None = None) -> Path:
    """Enregistre la composition d'un univers a une date. Rend le chemin."""
    return figer_detaille(cle, tickers, date)[0]


def figer_detaille(cle: str, tickers: list[str] | None = None,
                   date: str | None = None,
                   journal=print) -> tuple[Path, list[dict]]:
    """Comme `figer_univers()`, et rend aussi le detail par composante.

    Un univers compose (« us ») est charge SANS repli : une liste de
    repli date d'un autre jour, la figer sous la date du jour serait
    ecrire une composition fausse. Chaque composante est figee aussi sous
    sa propre cle (« sp500 », « nasdaq100 »), a la meme date.
    """
    if cle not in UNIVERS:
        raise ValueError(f"univers inconnu : {cle}")
    comps: list[dict] = []
    if tickers is None and cle in COMPOSEES:
        tickers, comps = univers_detaille(cle, repli=False, journal=journal)
    elif tickers is None and cle in COMPOSANTES:
        comps = [charge_composante(cle, repli=False, journal=journal)]
        tickers = comps[0]["tickers"]
    tickers = tickers if tickers is not None else UNIVERS[cle][1]()
    jour = date or dt.date.today().isoformat()
    if len(comps) > 1:
        for c in comps:
            _ecrit_composition(c["cle"], c["tickers"], jour)
    return _ecrit_composition(cle, tickers, jour), comps


def _ecrit_composition(cle: str, tickers: list[str], jour: str) -> Path:
    DOSSIER_UNIVERS.mkdir(parents=True, exist_ok=True)
    f = DOSSIER_UNIVERS / f"{cle}-{jour}.csv"
    f.write_text("ticker\n" + "\n".join(sorted(set(tickers))) + "\n",
                 encoding="utf-8")
    return f


def compositions(cle: str) -> list[tuple[str, Path]]:
    """Compositions figees disponibles pour cet univers, du plus ancien
    au plus recent. Rend [(date, chemin)]. Une date figee aux deux
    endroits est lue dans ~/.carruos/, jamais deux fois."""
    par_jour: dict[str, Path] = {}
    for dossier in (ANCIEN_DOSSIER_UNIVERS, DOSSIER_UNIVERS):
        try:
            for f in dossier.glob(f"{cle}-*.csv"):
                jour = f.stem[len(cle) + 1:]
                try:
                    dt.date.fromisoformat(jour)
                except ValueError:
                    continue
                par_jour[jour] = f
        except Exception:
            continue
    return sorted(par_jour.items())


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
    return (f"BIAIS DU SURVIVANT : aucune composition de « {cle} » figée "
            f"avant {debut}. Le test tourne sur la liste D'AUJOURD'HUI, "
            f"donc sur les seules sociétés qui ont survécu. Le résultat est "
            f"flatté d'un montant inconnu, et généralement de plusieurs "
            f"points par an. Lancez `py -m equity_scanner.data --figer {cle}` "
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
        try:
            f, comps = figer_detaille(o.figer, journal=lambda *_: None)
        except UniversIndisponible as exc:
            print(f"\n  RIEN N'EST FIGÉ. {exc}\n")
            raise SystemExit(1)
        n = len(f.read_text(encoding="utf-8").splitlines()) - 1
        print(f"\n  Composition de « {o.figer} » figee : {n} titres → {f}")
        if comps:
            print("  Par composante :")
            for c in comps:
                print(f"    {c['nom']:<12}{len(c['tickers']):>5} titres")
            brut = sum(len(c["tickers"]) for c in comps)
            print(f"    {'dedoublonne':<12}{n:>5} titres "
                  f"({brut - n} en commun)")
        print()
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
