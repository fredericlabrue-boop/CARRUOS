"""Phase 0 : le systeme a-t-il un edge mesurable ?

    py -m equity_scanner.phase0 --univers us --sleeve 8000
    py -m equity_scanner.phase0 --univers sp500 --csv resultats.csv

Cinq criteres. Les CINQ doivent passer, sinon NO-GO et rien ne bouge.

  1. >= 200 trades hors echantillon
  2. profit factor >= 1,15
  3. esperance positive apres couts
  4. z >= 2 contre des entrees aleatoires de meme duree
  5. drawdown maximum < 20 %

Le critere 4 est le plus important et le moins intuitif. Gagner de l'argent
ne prouve rien : sur un marche haussier, acheter n'importe quand en gagne
aussi. La question est de savoir si le SIGNAL fait mieux que le hasard a
duree de detention egale. C'est ce que mesure le z.

Aucun grid search. Les parametres sont figes avant le test. Sinon 78 125
combinaisons produisent ~3 900 faux positifs a z >= 2, et le critere ne veut
plus rien dire.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from . import backtest as bt
from . import data as dl
from .indicators import enrich

IN_DEBUT, IN_FIN = "2010-01-01", "2021-12-31"
OOS_DEBUT, OOS_FIN = "2022-01-01", "2026-12-31"
TIRAGES = 1000


# --- Statistiques -----------------------------------------------------
def profit_factor(rs: list[float]) -> float:
    g = sum(r for r in rs if r > 0)
    p = -sum(r for r in rs if r < 0)
    return float("inf") if p == 0 else g / p


def z_contre_hasard(trades, series: dict, graine=7) -> tuple:
    """Pour chaque trade reel (titre T, duree D), tire une entree au hasard
    sur T et detient exactement D barres. On refait l'ensemble 1000 fois pour
    obtenir la distribution nulle, puis on compare.

    Ce test neutralise le beta : si le systeme ne fait que capter la hausse
    du marche, le hasard capte la meme chose et z tombe a zero.
    """
    if not trades:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(graine)
    reel = float(np.mean([t.rendement for t in trades]))

    plan = []
    for t in trades:
        d = series.get(t.ticker)
        if d is None or len(d) < t.barres + 240:
            continue
        plan.append((d["close"].to_numpy(), t.barres))
    if len(plan) < 20:
        return reel, 0.0, 0.0

    moyennes = np.empty(TIRAGES)
    for k in range(TIRAGES):
        acc = np.empty(len(plan))
        for m, (px, dur) in enumerate(plan):
            i = rng.integers(220, len(px) - dur - 1)
            acc[m] = px[i + dur] / px[i] - 1.0 - bt.COUT_AR
        moyennes[k] = acc.mean()
    mu, sd = float(moyennes.mean()), float(moyennes.std(ddof=1))
    z = 0.0 if sd == 0 else (reel - mu) / sd
    return reel, mu, z


def mesures(trades, series) -> dict:
    rs = [t.R for t in trades]
    rends = [t.rendement for t in trades]
    pf = profit_factor(rs)
    gagnants = [r for r in rs if r > 0]
    pt = bt.portefeuille(trades)
    reel, nul, z = z_contre_hasard(trades, series)
    motifs = pd.Series([t.motif for t in trades]).value_counts().to_dict() if trades else {}
    return {
        "n": len(trades), "pf": pf,
        "ev_R": float(np.mean(rs)) if rs else 0.0,
        "ev_pct": float(np.mean(rends)) * 100 if rends else 0.0,
        "taux": len(gagnants) / len(rs) * 100 if rs else 0.0,
        "duree": float(np.mean([t.barres for t in trades])) if trades else 0.0,
        "dd": pt["dd"] * 100, "final": pt["final"],
        "pris": pt["pris"], "ecartes": pt["ecartes"],
        "z": z, "reel": reel * 100, "hasard": nul * 100, "motifs": motifs,
    }


def verdict(m: dict) -> tuple:
    c = [("trades OOS >= 200", m["n"] >= 200, f"{m['n']}"),
         ("profit factor >= 1,15", m["pf"] >= 1.15, f"{m['pf']:.2f}"),
         ("esperance > 0 apres couts", m["ev_R"] > 0, f"{m['ev_R']:+.3f} R"),
         ("z >= 2 contre le hasard", m["z"] >= 2.0, f"{m['z']:+.2f}"),
         ("drawdown < 20 %", m["dd"] < 20.0, f"{m['dd']:.1f} %")]
    return all(x[1] for x in c), c


# --- Robustesse -------------------------------------------------------
def robustesse(charge, tickers, bench, series) -> list:
    """Chaque parametre decale de +-20 %. Un systeme qui ne survit qu'aux
    valeurs exactes est du surapprentissage, pas un edge."""
    from . import rules as R
    tests = [("RSI plancher", "RSI_FLOOR", R.RSI_FLOOR),
             ("RVOL minimum", "RVOL_MIN", R.RVOL_MIN),
             ("fenetre de repli", "PULLBACK_WINDOW", R.PULLBACK_WINDOW),
             ("multiple ATR du stop", "STOP_ATR_MULT", R.STOP_ATR_MULT)]
    out = []
    for nom, attr, base in tests:
        for signe in (-0.2, 0.2):
            val = base * (1 + signe)
            if attr == "PULLBACK_WINDOW":
                val = max(3, int(round(val)))
            setattr(R, attr, val)
            if attr == "STOP_ATR_MULT":
                bt.STOP_ATR_MULT = val
            tr = []
            for tk in tickers:
                d = series.get(tk)
                if d is not None:
                    tr += bt.trades_ticker(d, tk, bench, OOS_DEBUT, OOS_FIN)
            pf = profit_factor([t.R for t in tr]) if tr else 0.0
            out.append((f"{nom} {signe:+.0%}", val, len(tr), pf, pf > 1.0))
            setattr(R, attr, base)
            if attr == "STOP_ATR_MULT":
                bt.STOP_ATR_MULT = base
    return out


# --- Execution --------------------------------------------------------
def charge_univers(tickers, bench_tk="SPY", ans=20, journal=print):
    bench_brut = dl.load_yf(bench_tk, years=ans)
    bench = enrich(bench_brut)
    series, rates = {}, []
    for n, tk in enumerate(tickers, 1):
        try:
            d = enrich(dl.load_yf(tk, years=ans), bench_close=bench_brut["close"])
            if len(d) >= 400:
                series[tk] = d
            else:
                rates.append(tk)
        except Exception:
            rates.append(tk)
        if n % 25 == 0:
            journal(f"    {n}/{len(tickers)} charges")
    return bench, series, rates


def tableau(titre, m, journal=print):
    journal(f"\n  {titre}")
    journal(f"    trades              {m['n']}")
    journal(f"    profit factor       {m['pf']:.2f}")
    journal(f"    esperance           {m['ev_R']:+.3f} R   ({m['ev_pct']:+.2f} %)")
    journal(f"    taux de reussite    {m['taux']:.1f} %")
    journal(f"    duree moyenne       {m['duree']:.0f} seances")
    journal(f"    rendement moyen     {m['reel']:+.2f} %  "
            f"contre {m['hasard']:+.2f} % au hasard")
    journal(f"    z                   {m['z']:+.2f}")
    journal(f"    drawdown max        {m['dd']:.1f} %")
    journal(f"    portefeuille        {m['pris']} pris, {m['ecartes']} ecartes "
            f"(5 positions max)")
    if m["motifs"]:
        journal(f"    sorties             " +
                ", ".join(f"{k} {v}" for k, v in m["motifs"].items()))


def lance(tickers, csv=None, journal=print):
    journal(f"\n  PHASE 0 — {len(tickers)} titres")
    journal(f"  in-sample {IN_DEBUT[:4]}-{IN_FIN[:4]}   "
            f"hors echantillon {OOS_DEBUT[:4]}-{OOS_FIN[:4]}")
    journal(f"  parametres FIGES, aucun grid search\n")
    journal("  Chargement...")
    bench, series, rates = charge_univers(tickers, journal=journal)
    journal(f"  {len(series)} titres exploitables"
            + (f", {len(rates)} ecartes" if rates else ""))

    journal("\n  Rejeu des regles...")
    tr_in, tr_oos = [], []
    for tk, d in series.items():
        tr_in += bt.trades_ticker(d, tk, bench, IN_DEBUT, IN_FIN)
        tr_oos += bt.trades_ticker(d, tk, bench, OOS_DEBUT, OOS_FIN)

    m_in, m_oos = mesures(tr_in, series), mesures(tr_oos, series)
    tableau("IN-SAMPLE (calibration, ne decide de rien)", m_in, journal)
    tableau("HORS ECHANTILLON (c'est lui qui decide)", m_oos, journal)

    ok, crit = verdict(m_oos)
    journal("\n  CRITERES GO/NO-GO")
    for nom, passe, val in crit:
        journal(f"    {'PASSE ' if passe else 'ECHOUE'}  {nom:<28} {val}")

    if ok:
        journal("\n  Robustesse (+-20 % sur chaque parametre)...")
        for nom, val, n, pf, bon in robustesse(None, list(series), bench, series):
            journal(f"    {'OK  ' if bon else 'NON '}  {nom:<26} "
                    f"valeur {val:<6} {n:4d} trades  PF {pf:.2f}")

    # L'audit avait raison : un avantage qui disparait des que les couts
    # montent n'est pas un avantage. On le mesure au lieu de l'esperer.
    journal("\n  SENSIBILITE AUX COUTS  (hors echantillon)")
    journal(f"    {'hypothese':<30}{'trades':>8}{'PF':>7}{'EV/trade':>10}")
    _j1, _c, _s = bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE
    for lib, j1, co, sl in [("cloture du jour, sans frais", False, 0.0, 0.0),
                            ("ouverture J+1, sans frais", True, 0.0, 0.0),
                            ("J+1 + 0,15 % par cote", True, 0.0010, 0.0005),
                            ("J+1 + 0,30 % par cote", True, 0.0020, 0.0010)]:
        bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE = j1, co, sl
        tr = []
        for tk, d in series.items():
            tr += bt.trades_ticker(d, tk, bench, OOS_DEBUT, OOS_FIN)
        rs = [x.R for x in tr]
        pfv = profit_factor(rs)
        ev = (sum(rs) / len(rs)) if rs else 0.0
        journal(f"    {lib:<30}{len(tr):>8}{pfv:>7.2f}{ev:>+10.3f}")
    bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE = _j1, _c, _s
    journal("    Si l'avantage ne survit pas a la derniere ligne, il n'existe pas.")

    journal("\n  " + "=" * 62)
    if ok:
        journal("  GO — les cinq criteres passent sur donnees hors echantillon.")
        journal("  Etape suivante : le comparatif contre SMH, net d'impot.")
        try:
            from . import comparatif as cp
            from . import data as dl
            courbe = bt.portefeuille(tr_oos)["courbe"]
            ref = dl.load_yf("SMH", years=20)["close"]
            ref = ref[(ref.index >= courbe.index[0])
                      & (ref.index <= courbe.index[-1])]
            cp.rapport(cp.compare(courbe, ref, "SMH"), journal)
        except Exception as exc:
            journal(f"  Comparatif indisponible ({type(exc).__name__}: {exc}).")
            journal("  Lance-le a part : py -m equity_scanner.comparatif")
    else:
        journal("  NO-GO — le systeme n'a pas demontre d'edge.")
        journal("  SMH ne bouge pas, le sleeve reste vide, la philosophie ne")
        journal("  change pas. C'est un resultat, pas un echec : tu viens")
        journal("  d'economiser le cout d'une strategie non validee.")
    journal("  " + "=" * 62 + "\n")

    if csv and tr_oos:
        pd.DataFrame([{
            "ticker": t.ticker, "entree": t.entree_d.date(),
            "sortie": t.sortie_d.date(), "prix_entree": round(t.entree, 2),
            "prix_sortie": round(t.sortie, 2), "stop": round(t.stop0, 2),
            "R": round(t.R, 3), "rendement_pct": round(t.rendement * 100, 2),
            "barres": t.barres, "motif": t.motif} for t in tr_oos]).to_csv(
            csv, index=False)
        journal(f"  Trades hors echantillon : {csv}\n")
    return ok, m_oos


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--univers", choices=["us", "sp500", "europe", "cac40"],
                   default="us")
    p.add_argument("--tickers", default="")
    p.add_argument("--csv", default=None)
    a = p.parse_args()
    tables = {"us": dl.us_tickers_fige, "sp500": dl.sp500_tickers,
              "europe": dl.europe_tickers, "cac40": dl.cac40_tickers_fige}
    tk = ([x.strip().upper() for x in a.tickers.split(",") if x.strip()]
          or tables[a.univers]())
    lance(tk, a.csv)


if __name__ == "__main__":
    main()
