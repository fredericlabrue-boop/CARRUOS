"""Scan quotidien.

    python -m equity_scanner.scan --sleeve 8000 --source yf
    python -m equity_scanner.scan --tickers AAPL,MSFT,AMD --verbose
    python -m equity_scanner.scan --universe sp500 --sleeve 8000 --csv sortie.csv

À lancer APRÈS la clôture US (22h ou 23h Paris). Toutes les règles sont
évaluées sur clôture — un scan en séance produit des signaux qui n'existent pas.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

import pandas as pd

from . import data as dl
from . import chart as gr
from . import news as nw
from . import resolve as rs
from .indicators import enrich
from . import dashboard
from .rules import MAX_POSITIONS, evaluate, market_regime_ok, position_size, rank

INDICES = {
    "us":     ("SPY",       "S&P 500",      "USD"),
    "europe": ("^STOXX",    "Stoxx 600",    "EUR"),
    "france": ("^FCHI",     "CAC 40",       "EUR"),
    "allemagne": ("^GDAXI", "DAX",          "EUR"),
}


def run(tickers, sleeve, source="yf", open_tickers=(), verbose=False, pause=0.0,
        html_path=None, marche="us", fx=1.0, av_key=None, graph=0):
    load = dl.LOADERS[source]
    bench_tk, bench_nom, ccy = INDICES[marche]
    sleeve_local = sleeve * fx

    bench_raw = load(bench_tk)
    bench = enrich(bench_raw)
    bench_ok = market_regime_ok(bench)
    b = bench.iloc[-1]
    print(f"\n{bench_nom} ({bench_tk}) {b['close']:.2f} | MM200 {b['sma200']:.2f} "
          f"| régime {'RISK-ON' if bench_ok else 'RISK-OFF'}   ({bench.index[-1].date()})")
    # Cloture US a 20h ou 21h UTC selon l'heure d'ete ; Europe a 15h30 ou 16h30.
    # On prend la borne haute pour etre certain que la bougie est definitive.
    now = dt.datetime.now(dt.timezone.utc)
    limite = 21 if marche == "us" else 17
    if bench.index[-1].date() == now.date() and now.hour < limite:
        h_paris = "22h" if marche == "us" else "17h30"
        print(f"  ATTENTION : la bougie du jour n'est pas terminee (cloture a {h_paris} "
              f"heure de Paris).\n  Le RVOL est sous-evalue et le MACD pas encore fige. "
              f"Signaux PROVISOIRES.\n  Creneau fiable : 20 minutes avant la cloture.")
    if fx == 1.0 and ccy != "EUR":
        print(f"  Note : sleeve pris pour {sleeve:.0f} {ccy}. Passe --fx 1.08 "
              f"pour convertir depuis l'euro.")

    if not bench_ok:
        print("\nMarché sous sa SMA200 → aucune entrée, et liquidation du sleeve "
              "sous 3 séances (règle de sortie 5). Scan interrompu.")
        if html_path:
            dashboard.render([], [], b, False, sleeve_local, bench.index[-1].date(),
                             html_path, bench_nom, ccy)
        return [], [], []

    # Calendrier des resultats : 1 seul appel pour tout le marche US, cache 24 h.
    cal = {}
    if av_key:
        try:
            cal = nw.earnings_map(av_key)
            print(f"  Calendrier des resultats : {len(cal)} societes chargees.")
        except Exception as exc:
            print(f"  Calendrier Alpha Vantage indisponible ({exc}). "
                  f"Repli sur yfinance.")

    signals, errors = [], []
    for n, brut_tk in enumerate(tickers, 1):
        tk = brut_tk
        try:
            # Traduit ISIN / mnemonique vers le ticker Yahoo. Un ticker deja
            # qualifie ("MC.PA", "AAPL") passe sans cout supplementaire.
            resolu, _ = rs.resoudre(brut_tk, load, av_key, journal=print)
            if resolu is None:
                errors.append((brut_tk, "ticker introuvable"))
                continue
            tk = resolu
            if tk.endswith(".L"):
                print(f"  ATTENTION {tk} : Londres cote en PENCE, pas en livres. "
                      f"Le calcul de position sera faux d'un facteur 100 "
                      f"sans --fx adapte.")
            brut = load(tk)
            d = enrich(brut, bench_close=bench_raw["close"])
            jeune = len(d) < 220
            if jeune:
                # Introduction recente (SPCX cote depuis juin 2026, par ex.).
                # La SMA200 n'existe pas encore : aucun verdict fiable.
                # On refuse le signal, mais on affiche quand meme le graphique :
                # bougies, EMA20, SMA50, RSI, MACD et Bollinger sont calculables.
                errors.append((tk, f"cotee depuis {len(d)} seances seulement — "
                                   f"SMA200 indisponible avant 200"))
            else:
                signals.append(evaluate(
                    d, tk, bench_ok,
                    open_tickers=tuple(open_tickers),
                    n_open=len(open_tickers),
                    days_to_earnings=(nw.seances_avant(cal.get(tk)) if cal
                                      else dl.days_to_earnings_yf(tk) if source == "yf"
                                      else None),
                ))
            if graph and n <= graph:
                # Le graphique a besoin de BEAUCOUP plus d'historique que le
                # scan : une MM200 hebdomadaire reclame 200 semaines (~4 ans),
                # une MM200 mensuelle 200 mois (~17 ans).
                try:
                    long_tk, long_bn = load(tk, years=20), load(bench_tk, years=20)
                except Exception:
                    long_tk, long_bn = brut, bench_raw
                out = gr.render(long_tk, tk, long_bn, sleeve_local, ccy)
                print(f"  Graphique : {out}")
        except Exception as e:
            msg = str(e)[:70]
            if av_key and ("donn" in msg or "index" in msg.lower()):
                for m in nw.chercher_symbole(av_key, tk)[:4]:
                    msg += f" | essaie {m['symbole']} ({m['nom'][:28]}, {m['region']})"
            errors.append((tk, msg))
        if verbose and n % 25 == 0:
            print(f"  … {n}/{len(tickers)}", file=sys.stderr)
        if pause:
            time.sleep(pause)

    fired = rank(signals)

    # Actualites : seulement pour les candidats retenus, pour tenir dans le quota.
    actus = {}
    if av_key and fired:
        for s in fired[:MAX_POSITIONS]:
            actus[s.ticker] = nw.news(av_key, s.ticker)

    if html_path:
        out = dashboard.render(fired, signals, b, bench_ok, sleeve_local,
                               bench.index[-1].date(), html_path, bench_nom, ccy,
                               actus, errors)
        print(f"\nTableau de bord : {out}")
    return fired, signals, errors


def report(fired, allsig, sleeve, errors=()):
    print(f"\n{len(fired)} candidat(s) sur {len(allsig)} titres analysés.")
    if errors:
        print(f"\n{len(errors)} titre(s) NON analysé(s) :")
        for tk, msg in errors[:15]:
            print(f"  {tk:12s} {msg}")
        if len(errors) > 15:
            print(f"  … et {len(errors) - 15} autres")
    if not fired:
        near = sorted(allsig, key=lambda s: len(s.failed_blocks))[:5]
        print("\nLes plus proches (bloc(s) manquant(s)) :")
        for s in near:
            print(f"  {s.ticker:6s} {', '.join(s.failed_blocks) or 'veto: ' + '; '.join(s.vetos)}")
        return pd.DataFrame()

    rows = []
    for s in fired[:MAX_POSITIONS]:
        ps = position_size(s, sleeve)
        rows.append({
            "ticker": s.ticker, "entrée": round(s.entry, 2), "stop": round(s.stop, 2),
            "risque %": f"{s.risk_pct * 100:.1f}", "ATR": round(s.atr, 2),
            "titres": ps["shares"], "montant": ps["notional"],
            "risque €": ps["risk_eur"], "RS 6m": round(s.rs_6m, 3),
            "plafonné": "oui" if ps["capped"] else "",
            "alerte": "; ".join(s.vetos),
        })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\nRisque total engagé : {df['risque €'].sum():.0f} € "
          f"({df['risque €'].sum() / sleeve * 100:.1f} % du sleeve)")
    print("\nCe sont des CANDIDATS, pas des ordres. Tant que la Phase 0 n'a pas "
          "rendu un GO, cette liste est une watchlist.")
    return df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sleeve", type=float, required=True, help="taille du sleeve en €")
    p.add_argument("--tickers", default="")
    p.add_argument("--universe",
                   choices=["sp500", "cac40", "dax", "europe"], default=None)
    p.add_argument("--marche", choices=list(INDICES), default="us",
                   help="indice de reference pour le regime et la force relative")
    p.add_argument("--fx", type=float, default=1.0,
                   help="taux EUR vers devise du titre (ex: 1.08 pour les US)")
    p.add_argument("--source", choices=["yf", "ibkr"], default="yf")
    p.add_argument("--open", default="", help="positions déjà ouvertes, séparées par ,")
    p.add_argument("--csv", default=None)
    p.add_argument("--html", nargs="?", const="dashboard.html", default=None,
                   help="genere et ouvre un tableau de bord HTML")
    p.add_argument("--pause", type=float, default=0.0, help="secondes entre 2 titres")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--chart", type=int, nargs="?", const=3, default=0,
                   help="ouvre un graphique interactif pour les N premiers titres")
    p.add_argument("--av-key", default=None,
                   help="cle Alpha Vantage : calendrier resultats + actualites")
    a = p.parse_args()

    univers = {k: f for k, (_, f) in dl.UNIVERS.items()}
    tickers = ([t.strip().upper() for t in a.tickers.split(",") if t.strip()]
               or (univers[a.universe]() if a.universe else []))
    if not tickers:
        p.error("passe --tickers ou --universe sp500")

    open_tk = tuple(t.strip().upper() for t in a.open.split(",") if t.strip())
    fired, allsig, errs = run(tickers, a.sleeve, a.source, open_tk, a.verbose,
                              a.pause, a.html, a.marche, a.fx, a.av_key, a.chart)
    df = report(fired, allsig, a.sleeve * a.fx, errs)
    if a.csv and not df.empty:
        df.to_csv(a.csv, index=False)
        print(f"→ {a.csv}")


if __name__ == "__main__":
    main()
