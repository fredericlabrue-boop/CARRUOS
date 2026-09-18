"""Derive post-annonce NEGATIVE — vente a decouvert. Hypothese n°3.

Specification : strategie-short-v1.md, empreinte SHA256
bc6a8d1798c38be9ca134c38b309e1d65a1b1108b8d92b6b99fe1a7c77aa175b

AUCUNE valeur de ce fichier ne doit etre modifiee apres le premier test.
Les constantes ci-dessous sont celles du document, recopiees telles
quelles. Si l'une d'elles change, ce n'est plus la meme hypothese : il
faut une nouvelle specification, une nouvelle empreinte et une nouvelle
ligne au registre.

VENDRE A DECOUVERT N'EST PAS ACHETER A L'ENVERS

Ce module ne retourne pas les signes d'une regle validee a l'achat. Il
met en oeuvre une specification ecrite pour la vente, avec ses propres
asymetries :

  - la perte n'est pas bornee : un titre qui double coute 100 % de la
    position, un titre qui quintuple en coute 400 % ;
  - la position GROSSIT quand elle a tort, donc le plafond de poids se
    verifie a chaque seance, pas seulement a l'entree ;
  - le marche derive a la hausse : il ne suffit pas d'avoir raison, il
    faut avoir assez raison pour couvrir cette derive ;
  - emprunter les titres se paie, au prorata du temps de detention.

CE QUE CE TEST SURESTIME, ET IL FAUT LE RETRANCHER A LA MAIN

Le dividende du au preteur n'est pas modelise : les donnees de cours
disponibles ne permettent pas de le reconstituer titre par titre. Sur
45 seances, un titre au rendement de 2 % coute environ 0,4 % de
dividende. Si l'esperance mesuree est inferieure a 0,4 point par trade,
l'avantage n'existe pas.

    py -m equity_scanner.short --univers us --csv short-us.csv
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import backtest as bt
from . import data as dl
from . import pead
from .indicators import enrich

# --------------------------------------------------------------- regles
# Recopiees de strategie-short-v1.md, etape 2. Gelees.
CAR3_MAX = -0.050         # E1 : reaction cumulee J-1..J+1, NEGATIVE
RVOL_ANNONCE = 2.0        # E2 : volume du jour d'annonce / moyenne 20 j
PRIX_MIN = 10.0           # E4
DOLLAR_VOL_MIN = 50e6     # E5 : plus severe qu'a l'achat, cf. emprunt
DELAI_EXEC = 3            # signal a la cloture de J+2, vente a l'ouverture J+3

MAX_BARRES = 45           # S1
STOP_ATR = 2.0            # S2 : stop AU-DESSUS de l'entree
AVANT_ANNONCE = 1         # S3 : rachat la veille de la publication suivante

RISQUE = 0.01
MAX_POS = 10              # effet de portefeuille, pas de titre
MAX_POIDS = 0.20          # 20 % du sleeve, verifie a chaque seance

# --------------------------------------------------------------- couts
EMPRUNT_AN = 0.020        # 2 % par an, au prorata temporis
EMPRUNT_DIFFICILE = 0.10  # 10 % par an : le cas qui decide, etape 6
SEANCES_AN = 252

# hors echantillon : un seul passage
OOS_DEBUT, OOS_FIN = "2024-01-01", "2026-12-31"
IN_DEBUT, IN_FIN = "2010-01-01", "2023-12-31"


@dataclass
class TradeCourt:
    """Une vente a decouvert. Les conventions de signe sont INVERSEES.

    `entree` est le prix AUQUEL ON A VENDU, net des frais : c'est ce
    qu'on encaisse. `sortie` est le prix auquel on a RACHETE, frais
    compris : c'est ce qu'on debourse. Le gain est donc entree moins
    sortie, et non l'inverse.

    On n'utilise pas backtest.Trade : sa propriete `risque` vaut
    entree - stop0, qui est NEGATIVE pour une vente puisque le stop est
    au-dessus. Elle rendrait un R de zero en silence. Mieux vaut une
    classe qui dit ce qu'elle fait.
    """
    ticker: str
    entree_d: pd.Timestamp
    sortie_d: pd.Timestamp
    entree: float             # prix de vente, encaisse
    sortie: float             # prix de rachat, debourse
    stop0: float              # AU-DESSUS de l'entree
    atr: float
    barres: int
    motif: str
    emprunt_an: float = EMPRUNT_AN
    sens: int = -1

    @property
    def risque(self) -> float:
        """Distance a l'arret, toujours positive."""
        return self.stop0 - self.entree

    @property
    def cout_emprunt(self) -> float:
        """Frais de pret, par titre, au prorata du temps de detention."""
        return self.entree * self.emprunt_an * self.barres / SEANCES_AN

    @property
    def R(self) -> float:
        """Resultat en multiples de risque, net de TOUS les couts."""
        if self.risque <= 0:
            return 0.0
        return (self.entree - self.sortie - self.cout_emprunt) / self.risque

    @property
    def rendement(self) -> float:
        if self.entree <= 0:
            return 0.0
        return (self.entree - self.sortie - self.cout_emprunt) / self.entree


# ------------------------------------------------------------ evenements
def evenements(d: pd.DataFrame, bench: pd.DataFrame,
               dates: list) -> list[dict]:
    """Pour chaque annonce : la reaction du marche et les conditions.

    Meme mesure qu'a l'hypothese n°2 — CAR3, la reaction du marche — mais
    on cherche ici les reactions NEGATIVES.
    """
    if d.empty or not dates:
        return []
    idx = d.index
    rt = d["close"].pct_change()
    rb = bench["close"].reindex(idx).ffill().pct_change()
    ab = (rt - rb).fillna(0.0)
    volma = d["volume"].rolling(20, min_periods=20).mean()
    out = []
    for da in dates:
        pos = idx.searchsorted(da)
        if pos <= 1 or pos >= len(idx) - DELAI_EXEC - 1:
            continue
        j = pos if idx[pos] == da else pos - 1
        if j <= 1 or j + DELAI_EXEC >= len(idx):
            continue
        vm = float(volma.iloc[j]) if np.isfinite(volma.iloc[j]) else 0.0
        out.append({
            "i": j, "date": idx[j],
            "car3": float(ab.iloc[j - 1:j + 2].sum()),
            "rvol": float(d["volume"].iloc[j]) / vm if vm > 0 else 0.0,
            # E3 : le marche ne s'est PAS ravise a la hausse
            "suite": bool(d["close"].iloc[j + 1] < d["close"].iloc[j - 1]),
            "prix": float(d["close"].iloc[j + 2]),
            "dvol": float(d["dollar_vol20"].iloc[j + 2])
            if "dollar_vol20" in d else 0.0,
            # E6 : le titre est deja en tendance baissiere
            "sous_sma200": bool(d["close"].iloc[j + 2]
                                < d["sma200"].iloc[j + 2])
            if "sma200" in d else False,
        })
    return out


def passe(ev: dict) -> dict:
    """Les six conditions, une par une, pour dire exactement ce qui bloque."""
    return {
        "E1 mauvaise surprise": ev["car3"] <= CAR3_MAX,
        "E2 volume": ev["rvol"] >= RVOL_ANNONCE,
        "E3 pas de rebond": ev["suite"],
        "E4 prix": ev["prix"] >= PRIX_MIN,
        "E5 liquidite": ev["dvol"] >= DOLLAR_VOL_MIN,
        "E6 titre sous sa SMA200": ev["sous_sma200"],
    }


# --------------------------------------------------------------- moteur
def simule_court(d, i_ann, ticker, prochaine=None,
                 emprunt_an: float = EMPRUNT_AN) -> TradeCourt | None:
    """Vente a l'ouverture de J+3, rachat a la premiere condition atteinte.

    Le stop est AU-DESSUS de l'entree et se declenche sur cloture. Il ne
    protege pas d'un ecart d'ouverture : une offre de rachat peut ouvrir
    40 % plus haut, et le rachat se fait alors au cours reel.
    """
    i = i_ann + DELAI_EXEC - 1              # cloture de J+2 = signal
    atr = float(d["atr14"].iloc[i]) if "atr14" in d else np.nan
    if not np.isfinite(atr) or atr <= 0 or i + 1 >= len(d):
        return None
    o = float(d["open"].iloc[i + 1])
    if not np.isfinite(o) or o <= 0:
        return None
    # On VEND : les frais reduisent ce qu'on encaisse.
    entree = o * (1 - bt.COUT_PAR_COTE - bt.SLIPPAGE)
    stop = entree + STOP_ATR * atr
    i0 = i + 1

    lim = len(d)
    if prochaine is not None:
        p = d.index.searchsorted(prochaine)
        lim = min(lim, max(i0 + 1, p - AVANT_ANNONCE))

    def rachat(c):
        """On RACHETE : les frais augmentent ce qu'on debourse."""
        return c * (1 + bt.COUT_PAR_COTE + bt.SLIPPAGE)

    for j in range(i0 + 1, min(i0 + 1 + MAX_BARRES, lim)):
        c = float(d["close"].iloc[j])
        if c >= stop:                                    # S2
            return TradeCourt(ticker, d.index[i0], d.index[j], entree,
                              rachat(c), stop, atr, j - i0, "stop",
                              emprunt_an)
        if "sma200" in d and c > float(d["sma200"].iloc[j]):   # S4
            return TradeCourt(ticker, d.index[i0], d.index[j], entree,
                              rachat(c), stop, atr, j - i0, "these morte",
                              emprunt_an)
    j = min(i0 + MAX_BARRES, lim - 1)
    if j <= i0:
        return None
    motif = "annonce" if (prochaine is not None and j < i0 + MAX_BARRES) else "duree"
    return TradeCourt(ticker, d.index[i0], d.index[j], entree,
                      rachat(float(d["close"].iloc[j])), stop, atr,
                      j - i0, motif, emprunt_an)


def trades_ticker(d, ticker, bench, dates, debut, fin,
                  emprunt_an: float = EMPRUNT_AN) -> tuple[list, list]:
    """Rend les trades pris et les annonces SANS surprise, qui serviront
    de population temoin au controle par le hasard."""
    evs = evenements(d, bench, dates)
    pris, temoins = [], []
    d0, d1 = pd.Timestamp(debut), pd.Timestamp(fin)
    for k, ev in enumerate(evs):
        if not (d0 <= ev["date"] <= d1):
            continue
        cond = passe(ev)
        proch = evs[k + 1]["date"] if k + 1 < len(evs) else None
        if all(cond.values()):
            t = simule_court(d, ev["i"], ticker, proch, emprunt_an)
            if t:
                pris.append(t)
        elif (not cond["E1 mauvaise surprise"] and cond["E4 prix"]
              and cond["E6 titre sous sa SMA200"]):
            temoins.append((ev, proch))
    return pris, temoins


# ------------------------------------------------ controle par le hasard
def z_contre_annonces_neutres(trades, temoins_par_tk, series,
                              tirages=1000, graine=7) -> tuple:
    """Le temoin est une AUTRE annonce, sans mauvaise surprise, vendue a
    decouvert selon les memes regles.

    Sinon on comparerait « vendre apres une mauvaise surprise » a
    « vendre n'importe quand », ce qui melangerait l'effet cherche avec
    le simple fait de vendre a decouvert un marche qui monte.
    """
    if not trades:
        return 0.0, 0.0, 0.0
    plat = [(tk, ev, pr) for tk, lst in temoins_par_tk.items()
            for ev, pr in lst]
    if len(plat) < 20:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(graine)
    reel = float(np.mean([t.rendement for t in trades]))
    n = len(trades)
    tirs = []
    for _ in range(tirages):
        ech = []
        for k in rng.integers(0, len(plat), n):
            tk, ev, pr = plat[int(k)]
            t = simule_court(series[tk], ev["i"], tk, pr)
            if t:
                ech.append(t.rendement)
        if ech:
            tirs.append(float(np.mean(ech)))
    if not tirs:
        return 0.0, 0.0, 0.0
    mu, sd = float(np.mean(tirs)), float(np.std(tirs, ddof=1))
    return ((reel - mu) / sd if sd > 0 else 0.0), reel, mu


# ---------------------------------------------------------------- mesures
def _pf(rs):
    g = sum(x for x in rs if x > 0)
    p = -sum(x for x in rs if x < 0)
    return (g / p) if p > 0 else (float("inf") if g > 0 else 0.0)


def mesures(trades, series: dict | None = None) -> dict:
    rs = [t.R for t in trades]
    pt = bt.portefeuille(trades, risque=RISQUE, max_pos=MAX_POS,
                         series=series)
    return {"n": len(trades), "pf": _pf(rs),
            "ev": (sum(rs) / len(rs)) if rs else 0.0,
            "reussite": (sum(1 for x in rs if x > 0) / len(rs)) if rs else 0.0,
            "duree": float(np.mean([t.barres for t in trades])) if trades else 0.0,
            "emprunt": (float(np.mean([t.cout_emprunt / t.entree
                                       for t in trades])) * 100
                        if trades else 0.0),
            "dd": pt["dd"], "dd_source": pt["dd_source"],
            "pris": pt["pris"], "courbe": pt["courbe"]}


def lance(tickers, csv=None, journal=print, univers: str = "") -> dict:
    from . import audit as ad
    from . import cache as ch
    from . import qualite as ql
    from concurrent.futures import ThreadPoolExecutor

    if isinstance(tickers, str):
        raise TypeError("lance() attend une LISTE de tickers")
    tickers = list(tickers)

    journal(f"\n  DERIVE POST-ANNONCE NEGATIVE — {len(tickers)} titres")
    journal(f"  VENTE A DECOUVERT — hors echantillon "
            f"{OOS_DEBUT[:4]}-{OOS_FIN[:4]}, un seul passage")
    journal(f"  regles GELEES : CAR3 <= {CAR3_MAX:.1%}, RVOL >= "
            f"{RVOL_ANNONCE}, {MAX_BARRES} seances, stop +{STOP_ATR} ATR")
    journal(f"  emprunt {EMPRUNT_AN:.1%}/an au prorata  ·  "
            f"empreinte {ad.empreinte()[:16]}…")
    journal("")
    journal("  RAPPEL : le dividende du au preteur n'est pas modelise.")
    journal("  Le resultat ci-dessous est optimiste d'environ 0,3 a 0,4")
    journal("  point par trade. Retranchez-le avant de conclure.\n")

    journal("  Chargement des cours et des dates d'annonces...")
    bench_brut = ch.charge("SPY", annees=6)
    brutes, echecs = ch.charge_lot(tickers, annees=6, journal=journal)
    sans = len(echecs)
    with ThreadPoolExecutor(max_workers=ch.FILS) as pool:
        annonces = dict(zip(brutes, pool.map(
            lambda tk: pead.dates_annonces(tk, journal=lambda *_: None),
            list(brutes))))

    series, dates, refuses = {}, {}, 0
    for tk, brut in brutes.items():
        rap = ql.controle(brut, bench_brut, ticker=tk, exige_recent=False)
        if not rap.utilisable:
            refuses += 1
            sans += 1
            continue
        d = enrich(brut, bench_close=bench_brut["close"])
        da = annonces.get(tk) or []
        if len(d) < 260 or not da:
            sans += 1
            continue
        series[tk], dates[tk] = d, da
    journal(f"  {len(series)} titres exploitables, {sans} ecartes"
            + (f" dont {refuses} par le controle qualite" if refuses else ""))
    if not series:
        journal("  Aucune donnee exploitable.")
        return {}

    tot = sum(len(v) for v in dates.values())
    journal(f"  {tot} annonces collectees "
            f"({tot / max(len(series), 1):.1f} par titre)\n")

    journal("  Rejeu des regles...")
    trades, temoins = [], {}
    for tk, d in series.items():
        pr, tm = trades_ticker(d, tk, bench_brut, dates[tk],
                               OOS_DEBUT, OOS_FIN)
        trades += pr
        if tm:
            temoins[tk] = tm
    m = mesures(trades, series)
    journal(f"  {m['n']} trades, {sum(len(v) for v in temoins.values())} "
            f"annonces temoins (sans mauvaise surprise)\n")

    journal("  Controle contre les annonces NEUTRES (1000 tirages)...")
    z, reel, mu = z_contre_annonces_neutres(trades, temoins, series)

    journal("\n  RESULTATS HORS ECHANTILLON")
    journal(f"    {'trades':<28}{m['n']}")
    journal(f"    {'profit factor':<28}{m['pf']:.2f}")
    journal(f"    {'esperance par trade':<28}{m['ev']:+.3f} R")
    journal(f"    {'taux de reussite':<28}{m['reussite']:.0%}")
    journal(f"    {'duree moyenne':<28}{m['duree']:.0f} seances")
    journal(f"    {'cout d emprunt moyen':<28}{m['emprunt']:.2f} % du notionnel")
    journal(f"    {'drawdown':<28}{m['dd']:.1%}  "
            f"(valorisation {m['dd_source']})")
    journal(f"    {'rendement reel':<28}{reel:+.3%}")
    journal(f"    {'annonces neutres':<28}{mu:+.3%}")
    journal(f"    {'score z':<28}{z:+.2f}")

    crit = [("trades >= 200", m["n"] >= 200, m["n"]),
            ("profit factor >= 1,15", m["pf"] >= 1.15, f"{m['pf']:.2f}"),
            ("esperance > 0", m["ev"] > 0, f"{m['ev']:+.3f}"),
            ("z >= 2", z >= 2.0, f"{z:+.2f}"),
            ("drawdown < 20 %", m["dd"] < 0.20, f"{m['dd']:.1%}")]
    journal("\n  CRITERES GO/NO-GO")
    for nom, ok, val in crit:
        journal(f"    {'PASSE ' if ok else 'ECHOUE'}  {nom:<26} {val}")
    go = all(o for _, o, _ in crit)

    # --- Etape 6 : la sensibilite aux couts DECIDE ---------------------
    journal("\n  SENSIBILITE AUX COUTS  (etape 6 de la specification)")
    journal(f"    {'hypothese':<30}{'trades':>8}{'PF':>7}{'EV':>9}")
    sauve = (bt.COUT_PAR_COTE, bt.SLIPPAGE)
    cas = [("sans aucun frais", 0.0, 0.0, 0.0),
           ("emprunt seul, 2 %/an", 0.0, 0.0, EMPRUNT_AN),
           ("realiste : 2 %/an + 0,15 %", 0.0010, 0.0005, EMPRUNT_AN),
           ("difficile a emprunter, 10 %/an", 0.0020, 0.0010,
            EMPRUNT_DIFFICILE)]
    for lib, co, sl, emp in cas:
        bt.COUT_PAR_COTE, bt.SLIPPAGE = co, sl
        tr = []
        for tk, d in series.items():
            tr += trades_ticker(d, tk, bench_brut, dates[tk],
                                OOS_DEBUT, OOS_FIN, emp)[0]
        rs = [x.R for x in tr]
        journal(f"    {lib:<30}{len(tr):>8}{_pf(rs):>7.2f}"
                f"{(sum(rs) / len(rs) if rs else 0):>+9.3f}")
    bt.COUT_PAR_COTE, bt.SLIPPAGE = sauve
    journal("    La DERNIERE ligne decide. Si l'avantage disparait a 10 %")
    journal("    d'emprunt annuel, l'hypothese ne tient que sur des titres")
    journal("    faciles a emprunter — et ce sont rarement ceux qui baissent.")

    journal("\n  " + "=" * 62)
    if go:
        journal("  GO SOUS RESERVE — les cinq criteres passent.")
        journal("  Retranchez 0,3 a 0,4 point par trade pour le dividende")
        journal("  du au preteur, non modelise. Si l'esperance devient")
        journal("  negative apres cette soustraction, c'est un NO-GO.")
        journal("  Puis six mois d'observation papier avant tout ordre :")
        journal("  la perte non bornee impose cette etape.")
    else:
        journal("  NO-GO — l'hypothese est morte. Elle ne se retouche pas,")
        journal("  ne se re-teste pas avec des seuils ajustes, et ne")
        journal("  revient pas sous un autre nom.")
    journal("  " + "=" * 62 + "\n")

    if csv and trades:
        pd.DataFrame([{"ticker": t.ticker, "entree": t.entree_d,
                       "sortie": t.sortie_d, "prix_vente": round(t.entree, 2),
                       "prix_rachat": round(t.sortie, 2),
                       "stop": round(t.stop0, 2), "R": round(t.R, 3),
                       "emprunt": round(t.cout_emprunt, 4),
                       "barres": t.barres, "motif": t.motif}
                      for t in trades]).to_csv(csv, index=False)
        journal(f"  Detail des trades : {csv}\n")
    return {"go": go, "z": z, **{k: v for k, v in m.items() if k != "courbe"}}


def main() -> None:
    a = argparse.ArgumentParser(
        description="Derive post-annonce negative, vente a decouvert")
    a.add_argument("--univers", default="us")
    a.add_argument("--csv", default=None)
    o = a.parse_args()
    tables = {k: f for k, (_, f) in dl.UNIVERS.items()}
    if o.univers not in tables:
        a.error(f"univers inconnu. Choix : {', '.join(tables)}")
    lance(tables[o.univers](), csv=o.csv, univers=o.univers)


if __name__ == "__main__":
    main()
