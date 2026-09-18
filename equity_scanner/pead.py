"""Derive post-annonce — moteur de test.

Hypothese n°2 du registre. Specification : derive-post-annonce-v1.md,
empreinte SHA256 f37d22bd76d253a4c686edb8fe1debb394490240593cc400a423a6f8fb428dee

AUCUNE valeur de ce fichier ne doit etre modifiee apres le premier test.
Les constantes ci-dessous sont celles du document, recopiees telles
quelles. Si l'une d'elles change, ce n'est plus la meme hypothese : il
faut une nouvelle specification, une nouvelle empreinte et une nouvelle
ligne au registre.

    py -m equity_scanner.pead --univers us --csv pead.csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest as bt
from . import data as dl
from .indicators import enrich

# --------------------------------------------------------------- regles
CAR3_MIN = 0.050          # E1 : reaction cumulee J-1..J+1
RVOL_ANNONCE = 2.0        # E2 : volume du jour d'annonce / moyenne 20 j
PRIX_MIN = 10.0           # E4
DOLLAR_VOL_MIN = 20e6     # E5
DELAI_EXEC = 3            # signal a la cloture de J+2, achat a l'ouverture de J+3

MAX_BARRES = 45           # S1
STOP_ATR = 2.0            # S2
AVANT_ANNONCE = 1         # S3 : sortie la veille de la publication suivante

RISQUE = 0.01
MAX_POS = 10              # effet de portefeuille, pas de titre
MAX_POIDS = 0.25          # 25 % du sleeve par ligne, etape 2 du document

CACHE = Path(".bruce_cache") / "annonces"

# hors echantillon : un seul passage
OOS_DEBUT, OOS_FIN = "2024-01-01", "2026-12-31"
IN_DEBUT, IN_FIN = "2010-01-01", "2021-12-31"


# ------------------------------------------------------- dates d'annonces
def dates_annonces(ticker: str, journal=print) -> list[pd.Timestamp]:
    """Dates de publication. yfinance n'en donne que deux ans environ :
    c'est la voie A du document, assumee et documentee."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{ticker.replace('/', '_')}.json"
    try:
        v = json.loads(f.read_text(encoding="utf-8"))
        if v.get("jour") == dt.date.today().isoformat():
            return [pd.Timestamp(x) for x in v["dates"]]
    except Exception:
        pass
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).get_earnings_dates(limit=40)
        d = sorted({pd.Timestamp(x).tz_localize(None).normalize()
                    for x in df.index})
    except Exception as exc:
        journal(f"    {ticker} : dates indisponibles ({type(exc).__name__})")
        d = []
    try:
        f.write_text(json.dumps({"jour": dt.date.today().isoformat(),
                                 "dates": [str(x.date()) for x in d]}),
                     encoding="utf-8")
    except Exception:
        pass
    return d


# ------------------------------------------------------------ evenements
def aligne(bo: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    """Indice de reference remis sur le calendrier du titre.

    Sans cela, toute lecture par position (`iloc[j]`) dans `bo` designe
    une date differente de celle du titre.
    """
    if len(bo.index) == len(index) and bool((bo.index == index).all()):
        return bo
    return bo.reindex(index).ffill()


def evenements(d: pd.DataFrame, bench: pd.DataFrame,
               dates: list[pd.Timestamp]) -> list[dict]:
    """Pour chaque annonce : la reaction du marche et les conditions.

    CAR3 = rendement du titre moins celui de l'indice, cumule de J-1 a
    J+1. On ne mesure pas la surprise comptable : on mesure ce que le
    marche en a fait.
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
        j = pos if idx[pos] == da else pos - 1      # jour de bourse de l'annonce
        if j <= 1 or j + DELAI_EXEC >= len(idx):
            continue
        car3 = float(ab.iloc[j - 1:j + 2].sum())
        vm = float(volma.iloc[j]) if np.isfinite(volma.iloc[j]) else 0.0
        rvol = float(d["volume"].iloc[j]) / vm if vm > 0 else 0.0
        out.append({
            "i": j, "date": idx[j], "car3": car3, "rvol": rvol,
            "suite": bool(d["close"].iloc[j + 1] > d["close"].iloc[j - 1]),
            "prix": float(d["close"].iloc[j + 2]),
            "dvol": float(d["dollar_vol20"].iloc[j + 2])
            if "dollar_vol20" in d else 0.0,
        })
    return out


def passe(ev: dict, marche_ok: bool) -> dict:
    """Les six conditions, une par une. On garde le detail pour pouvoir
    dire exactement ce qui a bloque."""
    return {
        "E1 surprise": ev["car3"] >= CAR3_MIN,
        "E2 volume": ev["rvol"] >= RVOL_ANNONCE,
        "E3 pas de retractation": ev["suite"],
        "E4 prix": ev["prix"] >= PRIX_MIN,
        "E5 liquidite": ev["dvol"] >= DOLLAR_VOL_MIN,
        "E6 regime": marche_ok,
    }


# --------------------------------------------------------------- moteur
def simule_pead(d, i_ann, ticker, bo, prochaine=None) -> bt.Trade | None:
    """Achat a l'ouverture de J+3, sortie par la premiere condition
    atteinte. Aucun take-profit : couper la derive la ou elle produit
    son rendement serait l'erreur exacte de la v3.3 d'Alfred.
    """
    i = i_ann + DELAI_EXEC - 1              # cloture de J+2 = signal
    atr = float(d["atr14"].iloc[i]) if "atr14" in d else np.nan
    if not np.isfinite(atr) or atr <= 0 or i + 1 >= len(d):
        return None
    o = float(d["open"].iloc[i + 1])
    if not np.isfinite(o) or o <= 0:
        return None
    entree = o * (1 + bt.COUT_PAR_COTE + bt.SLIPPAGE)
    stop = entree - STOP_ATR * atr
    if stop >= entree:
        return None
    i0 = i + 1

    lim = len(d)
    if prochaine is not None:
        p = d.index.searchsorted(prochaine)
        lim = min(lim, max(i0 + 1, p - AVANT_ANNONCE))

    for j in range(i0 + 1, min(i0 + 1 + MAX_BARRES, lim)):
        c = float(d["close"].iloc[j])
        if c <= stop:                                    # S2
            return bt.Trade(ticker, d.index[i0], d.index[j], entree,
                            c * (1 - bt.COUT_PAR_COTE - bt.SLIPPAGE),
                            stop, atr, j - i0, "stop")
        if not bool(bo["close"].iloc[j] > bo["sma200"].iloc[j]):   # S4
            return bt.Trade(ticker, d.index[i0], d.index[j], entree,
                            c * (1 - bt.COUT_PAR_COTE - bt.SLIPPAGE),
                            stop, atr, j - i0, "regime")
    j = min(i0 + MAX_BARRES, lim - 1)
    if j <= i0:
        return None
    motif = "annonce" if (prochaine is not None and j < i0 + MAX_BARRES) else "duree"
    return bt.Trade(ticker, d.index[i0], d.index[j], entree,
                    float(d["close"].iloc[j]) * (1 - bt.COUT_PAR_COTE - bt.SLIPPAGE),
                    stop, atr, j - i0, motif)


def trades_ticker(d, ticker, bench, bo, dates, debut, fin) -> tuple[list, list]:
    """Rend les trades pris et les evenements SANS surprise, qui serviront
    de population temoin au test du hasard.

    `bo` est realigne sur le calendrier du titre. C'etait le defaut le plus
    couteux du module : l'indice arrivait avec SON propre calendrier et on
    lisait dedans par position (`bo["close"].iloc[j]`, j venant du titre).
    Des qu'un titre n'avait pas exactement le meme nombre de barres que
    SPY — introduction plus tardive, jour ferie local, suspension de
    cotation — le filtre de regime lisait une AUTRE DATE. Sur un titre
    europeen, le decalage atteignait plusieurs semaines.
    """
    bo = aligne(bo, d.index)
    evs = evenements(d, bench, dates)
    pris, temoins = [], []
    d0, d1 = pd.Timestamp(debut), pd.Timestamp(fin)
    for k, ev in enumerate(evs):
        if not (d0 <= ev["date"] <= d1):
            continue
        marche_ok = bool(bo["close"].iloc[ev["i"]] > bo["sma200"].iloc[ev["i"]])
        cond = passe(ev, marche_ok)
        proch = evs[k + 1]["date"] if k + 1 < len(evs) else None
        if all(cond.values()):
            t = simule_pead(d, ev["i"], ticker, bo, proch)
            if t:
                pris.append(t)
        elif not cond["E1 surprise"] and cond["E4 prix"] and cond["E6 regime"]:
            temoins.append((ev, proch))
    return pris, temoins


# ------------------------------------------------ controle par le hasard
def z_contre_annonces_neutres(trades, temoins_par_tk, series, bo,
                              tirages=1000, graine=7) -> tuple:
    """Le temoin n'est PAS une date au hasard : c'est une AUTRE annonce,
    sans surprise.

    Sinon on comparerait "acheter apres une surprise" a "acheter n'importe
    quand", ce qui melange l'effet cherche avec le simple fait d'acheter
    apres une publication.
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
    # Chaque temoin est rejoue avec l'indice aligne sur le calendrier de
    # SON titre, exactement comme le trade reel auquel on le compare.
    aligne_par_tk = {tk: aligne(bo, series[tk].index) for tk in series}
    for _ in range(tirages):
        ech = []
        for k in rng.integers(0, len(plat), n):
            tk, ev, pr = plat[int(k)]
            t = simule_pead(series[tk], ev["i"], tk, aligne_par_tk[tk], pr)
            if t:
                ech.append(t.rendement)
        if ech:
            tirs.append(float(np.mean(ech)))
    if not tirs:
        return 0.0, 0.0, 0.0
    # ddof=1 : meme convention que la Phase 0, sinon les deux z ne sont
    # pas comparables entre eux.
    mu, sd = float(np.mean(tirs)), float(np.std(tirs, ddof=1))
    z = (reel - mu) / sd if sd > 0 else 0.0
    return z, reel, mu


# ---------------------------------------------------------------- rapport
def _pf(rs):
    g = sum(x for x in rs if x > 0)
    p = -sum(x for x in rs if x < 0)
    return (g / p) if p > 0 else (float("inf") if g > 0 else 0.0)


def mesures(trades, series: dict | None = None) -> dict:
    rs = [t.R for t in trades]
    pt = bt.portefeuille(trades, risque=RISQUE, max_pos=MAX_POS,
                         series=series, max_poids=MAX_POIDS)
    return {"n": len(trades), "pf": _pf(rs),
            "ev": (sum(rs) / len(rs)) if rs else 0.0,
            "reussite": (sum(1 for x in rs if x > 0) / len(rs)) if rs else 0.0,
            "duree": float(np.mean([t.barres for t in trades])) if trades else 0.0,
            "dd": pt["dd"], "dd_source": pt["dd_source"],
            "pris": pt["pris"], "courbe": pt["courbe"],
            "rognees": pt.get("lignes_rognees", 0),
            "poids_max": pt.get("poids_max", 0.0)}


def lance(tickers, csv=None, journal=print) -> dict:
    journal(f"\n  DERIVE POST-ANNONCE — {len(tickers)} titres")
    journal(f"  hors echantillon {OOS_DEBUT[:4]}-{OOS_FIN[:4]}")
    journal(f"  regles GELEES : CAR3 >= {CAR3_MIN:.1%}, RVOL >= {RVOL_ANNONCE}, "
            f"{MAX_BARRES} seances, stop {STOP_ATR} ATR\n")

    journal("  Chargement des cours et des dates d'annonces...")
    from . import cache as ch
    from . import qualite as ql
    from concurrent.futures import ThreadPoolExecutor

    bench_brut = ch.charge("SPY", annees=6)
    bo = enrich(bench_brut)

    # Cours en parallele, puis dates d'annonces en parallele. C'etait la
    # totalite du temps d'attente : deux appels reseau par titre, l'un
    # apres l'autre, sur plusieurs centaines de titres.
    brutes, echecs = ch.charge_lot(tickers, annees=6, journal=journal)
    sans = len(echecs)
    with ThreadPoolExecutor(max_workers=ch.FILS) as pool:
        annonces = dict(zip(brutes, pool.map(
            lambda tk: dates_annonces(tk, journal=lambda *_: None),
            list(brutes))))

    series, dates = {}, {}
    refuses = 0
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
        journal("  Aucune donnee. Verifie ta connexion et yfinance.")
        return {}

    tot = sum(len(v) for v in dates.values())
    journal(f"  {tot} annonces collectees "
            f"({tot / max(len(series), 1):.1f} par titre)\n")

    journal("  Rejeu des regles...")
    trades, temoins = [], {}
    for tk, d in series.items():
        pr, tm = trades_ticker(d, tk, bench_brut, bo, dates[tk],
                               OOS_DEBUT, OOS_FIN)
        trades += pr
        if tm:
            temoins[tk] = tm
    m = mesures(trades, series)
    journal(f"  {m['n']} trades, {sum(len(v) for v in temoins.values())} "
            f"annonces temoins (sans surprise)\n")

    journal("  Controle contre les annonces NEUTRES (1000 tirages)...")
    z, reel, mu = z_contre_annonces_neutres(trades, temoins, series, bo)

    journal("\n  RESULTATS HORS ECHANTILLON")
    journal(f"    {'trades':<26}{m['n']}")
    journal(f"    {'profit factor':<26}{m['pf']:.2f}")
    journal(f"    {'esperance par trade':<26}{m['ev']:+.3f} R")
    journal(f"    {'taux de reussite':<26}{m['reussite']:.0%}")
    journal(f"    {'duree moyenne':<26}{m['duree']:.0f} seances")
    journal(f"    {'plafond de poids':<26}{MAX_POIDS:.0%} par ligne  "
            f"({m.get('rognees', 0)} reduite(s) a l'entree, "
            f"max atteint {m.get('poids_max', 0):.1%})")
    journal(f"    {'drawdown':<26}{m['dd']:.1%}  "
            f"(valorisation {m.get('dd_source', '?')})")
    journal(f"    {'rendement reel':<26}{reel:+.3%}")
    journal(f"    {'annonces neutres':<26}{mu:+.3%}")
    journal(f"    {'score z':<26}{z:+.2f}")

    crit = [("trades >= 200", m["n"] >= 200, m["n"]),
            ("profit factor >= 1,15", m["pf"] >= 1.15, f"{m['pf']:.2f}"),
            ("esperance > 0", m["ev"] > 0, f"{m['ev']:+.3f}"),
            ("z >= 2", z >= 2.0, f"{z:+.2f}"),
            ("drawdown < 20 %", m["dd"] < 0.20, f"{m['dd']:.1%}")]
    journal("\n  CRITERES GO/NO-GO")
    for nom, ok, val in crit:
        journal(f"    {'PASSE ' if ok else 'ECHOUE'}  {nom:<26} {val}")
    go = all(o for _, o, _ in crit)

    journal("\n  SENSIBILITE AUX COUTS")
    journal(f"    {'hypothese':<30}{'trades':>8}{'PF':>7}{'EV':>9}")
    sauve = (bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE)
    for lib, co, sl in [("sans frais", 0.0, 0.0),
                        ("0,15 % par cote", 0.0010, 0.0005),
                        ("0,30 % par cote", 0.0020, 0.0010)]:
        bt.COUT_PAR_COTE, bt.SLIPPAGE = co, sl
        tr = []
        for tk, d in series.items():
            tr += trades_ticker(d, tk, bench_brut, bo, dates[tk],
                                OOS_DEBUT, OOS_FIN)[0]
        rs = [x.R for x in tr]
        journal(f"    {lib:<30}{len(tr):>8}{_pf(rs):>7.2f}"
                f"{(sum(rs) / len(rs) if rs else 0):>+9.3f}")
    bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE = sauve
    journal("    Si l'avantage ne survit pas a la derniere ligne, il n'existe pas.")

    journal("\n  " + "=" * 62)
    if go:
        journal("  GO — les cinq criteres passent.")
        journal("  Reste la barre economique : battre SMH net de PFU.")
        try:
            from . import comparatif as cp
            ref = dl.load_yf("SMH", years=6)["close"]
            c = m["courbe"]
            ref = ref[(ref.index >= c.index[0]) & (ref.index <= c.index[-1])]
            cp.rapport(cp.compare(c, ref, "SMH"), journal)
        except Exception as exc:
            journal(f"  Comparatif indisponible ({type(exc).__name__}).")
    else:
        journal("  NO-GO — l'hypothese est morte. Elle ne se retouche pas.")
        if m["n"] < 200 and z > 0:
            journal("  Exception prevue : moins de 200 trades avec z positif.")
            journal("  On peut elargir l'echantillon (historique de dates)")
            journal("  SANS toucher a une seule regle.")
    journal("  " + "=" * 62 + "\n")

    if csv and trades:
        pd.DataFrame([{"ticker": t.ticker, "entree": t.entree_d,
                       "sortie": t.sortie_d, "R": round(t.R, 3),
                       "barres": t.barres, "motif": t.motif}
                      for t in trades]).to_csv(csv, index=False)
        journal(f"  Detail des trades : {csv}\n")
    return {"go": go, "z": z, **{k: v for k, v in m.items() if k != "courbe"}}


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--univers", default="us")
    a.add_argument("--csv", default=None)
    o = a.parse_args()
    tables = {k: f for k, (_, f) in dl.UNIVERS.items()}
    if o.univers not in tables:
        a.error(f"univers inconnu. Choix : {', '.join(tables)}")
    lance(tables[o.univers](), csv=o.csv)


if __name__ == "__main__":
    main()
