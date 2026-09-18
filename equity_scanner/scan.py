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
        html_path=None, marche="us", fx=1.0, av_key=None, graph=0,
        fils=None, journal_audit=True):
    """Scan d'un univers.

    TROIS CHANGEMENTS par rapport a la version d'origine.

    1. UN SEUL telechargement par titre. `resolve.resoudre()` chargeait
       trois ans d'historique juste pour verifier qu'un ticker existe,
       puis `load(tk)` les rechargeait aussitot. Chaque titre etait donc
       telecharge DEUX FOIS, et un mnemonique europeen non qualifie
       jusqu'a vingt-deux fois. Tout passe maintenant par le cache.

    2. EN PARALLELE. Les telechargements attendent le reseau : les faire
       l'un apres l'autre, c'est attendre 500 fois de suite.

    3. CONTROLE QUALITE avant evaluation. Une serie trouee, perimee ou
       portant une division non ajustee ne produit plus de signal : elle
       ressort dans les erreurs, avec son motif.
    """
    from . import audit as ad
    from . import cache as ch
    from . import qualite as ql

    # --pause servait a espacer les appels quand ils partaient l'un apres
    # l'autre. Avec des telechargements simultanes, l'equivalent est de
    # n'en lancer qu'un a la fois.
    if pause:
        fils = 1
    bench_tk, bench_nom, ccy = INDICES[marche]
    sleeve_local = sleeve * fx

    bench_raw = ch.charge(bench_tk, annees=3, source=source)
    bench = enrich(bench_raw)
    bench_ok = market_regime_ok(bench)
    b = bench.iloc[-1]
    print(f"\n{bench_nom} ({bench_tk}) {b['close']:.2f} | MM200 {b['sma200']:.2f} "
          f"| régime {'RISK-ON' if bench_ok else 'RISK-OFF'}   ({bench.index[-1].date()})")

    # L'indice de reference subit le meme controle que les titres : un
    # regime calcule sur une serie perimee vaudrait moins que rien.
    rap_bench = ql.controle(bench_raw, ticker=bench_tk)
    if not rap_bench.utilisable:
        print(f"  DONNEES DE L'INDICE REFUSEES : {rap_bench.resume()}")
        print("  Aucun signal ne sera produit : le filtre de regime n'est "
              "pas calculable.")
        return [], [], [(bench_tk, rap_bench.resume())]

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

    # --- Resolution des tickers --------------------------------------
    resolus, errors = {}, []
    for brut_tk in tickers:
        try:
            tk, _ = rs.resoudre(brut_tk, lambda t: ch.charge(t, annees=3,
                                                             source=source),
                                av_key, journal=print)
        except Exception as exc:
            errors.append((brut_tk, f"{type(exc).__name__}: {str(exc)[:60]}"))
            continue
        if tk is None:
            errors.append((brut_tk, "ticker introuvable"))
            continue
        if tk.endswith(".L"):
            print(f"  ATTENTION {tk} : Londres cote en PENCE, pas en livres. "
                  f"Le calcul de position sera faux d'un facteur 100 "
                  f"sans --fx adapte.")
        resolus[tk] = brut_tk

    # --- Chargement en parallele -------------------------------------
    if verbose:
        print(f"  Chargement de {len(resolus)} titre(s)...")
    brutes, echecs = ch.charge_lot(list(resolus), annees=3, source=source,
                                   fils=fils or ch.FILS,
                                   journal=(print if verbose else None))
    errors += echecs

    # --- Evaluation ---------------------------------------------------
    signals, enrichies, rapports = [], {}, {}
    for tk, brut in sorted(brutes.items()):
        try:
            rap = ql.controle(brut, bench_raw, ticker=tk)
            if not rap.utilisable:
                errors.append((tk, rap.resume()))
                continue
            d = enrich(brut, bench_close=bench_raw["close"])
            if len(d) < 220:
                # Introduction recente : la SMA200 n'existe pas encore,
                # aucun verdict fiable. Le graphique reste calculable.
                errors.append((tk, f"cotee depuis {len(d)} seances seulement — "
                                   f"SMA200 indisponible avant 200"))
                continue
            jours = nw.seances_avant(cal.get(tk)) if cal else None
            sig = evaluate(d, tk, bench_ok, open_tickers=tuple(open_tickers),
                           n_open=len(open_tickers), days_to_earnings=jours)
            signals.append(sig)
            enrichies[tk] = d
            rapports[tk] = rap
        except Exception as e:
            errors.append((tk, str(e)[:70]))

    # Le veto « resultats inconnus » n'est leve que pour les titres dont
    # il est le dernier obstacle : quelques appels reseau au lieu de 500.
    signals = resout_resultats(signals, enrichies, bench_ok, open_tickers,
                               source, fils or 8, journal=print)
    if journal_audit:
        for sig in signals:
            ad.enregistre(sig, enrichies.get(sig.ticker), source="scan",
                          qualite={"alertes": rapports[sig.ticker].alertes
                                   if sig.ticker in rapports else []})

    # --- Graphiques ---------------------------------------------------
    for n, tk in enumerate(sorted(brutes), 1):
        if not graph or n > graph:
            break
        try:
            # Le graphique a besoin de BEAUCOUP plus d'historique que le
            # scan : une MM200 hebdomadaire reclame 200 semaines (~4 ans),
            # une MM200 mensuelle 200 mois (~17 ans).
            long_tk = ch.charge(tk, annees=20, source=source)
            long_bn = ch.charge(bench_tk, annees=20, source=source)
        except Exception:
            long_tk, long_bn = brutes[tk], bench_raw
        try:
            out = gr.render(long_tk, tk, long_bn, sleeve_local, ccy)
            print(f"  Graphique : {out}")
        except Exception as exc:
            print(f"  Graphique {tk} impossible ({type(exc).__name__}).")

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


VETO_RESULTATS = "RÉSULTATS INCONNUS"


def resout_resultats(signaux, series, bench_ok, open_tickers=(), source="yf",
                     fils=8, journal=None):
    """Leve le veto « resultats inconnus » pour les seuls titres concernes.

    LE PROBLEME. La regle est juste : une date de publication inconnue
    n'est pas une date sans risque, elle pose un veto. Mais aller
    chercher cette date pour les 500 titres d'un univers, c'est 500
    appels reseau pour une information qui ne change RIEN a 495 d'entre
    eux — ils sont deja recales par un bloc manquant.

    LA SOLUTION. On evalue d'abord tout le monde sans la date. Les seuls
    titres pour qui elle compte sont ceux dont les treize blocs passent
    et dont le veto resultats est le DERNIER obstacle. On va chercher la
    date pour ceux-la, une poignee, puis on les reevalue.

    Le veto reste entier : un titre dont la date reste introuvable le
    garde, et ne declenche pas.
    """
    if source != "yf":
        return signaux
    a_resoudre = [s.ticker for s in signaux
                  if all(s.blocks.values())
                  and all(VETO_RESULTATS in v for v in s.vetos)
                  and s.vetos]
    if not a_resoudre:
        return signaux
    if journal:
        journal(f"  {len(a_resoudre)} candidat(s) potentiel(s) : recherche "
                f"de la date de publication.")
    dates = dl.days_to_earnings_lot(a_resoudre, fils=fils)
    par_tk = {s.ticker: s for s in signaux}
    for tk, jours in dates.items():
        d = series.get(tk)
        if d is None:
            continue
        par_tk[tk] = evaluate(d, tk, bench_ok,
                              open_tickers=tuple(open_tickers),
                              n_open=len(open_tickers),
                              days_to_earnings=jours)
    return [par_tk.get(s.ticker, s) for s in signaux]


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
    p.add_argument("--pause", type=float, default=0.0,
                   help="ancien reglage d'espacement : force un seul "
                        "telechargement a la fois")
    p.add_argument("--fils", type=int, default=None,
                   help="telechargements simultanes (8 par defaut, 16 max)")
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
                              a.pause, a.html, a.marche, a.fx, a.av_key,
                              a.chart, fils=a.fils)
    df = report(fired, allsig, a.sleeve * a.fx, errs)
    if a.csv and not df.empty:
        df.to_csv(a.csv, index=False)
        print(f"→ {a.csv}")


if __name__ == "__main__":
    main()
