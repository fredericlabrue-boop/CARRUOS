"""Validation sur données synthétiques. `python -m equity_scanner.test_rules`

Le principe est celui de la Phase 0 d'Alfred : on prouve d'abord que le code
fait ce qu'on croit, sur des séries dont on connaît la réponse. Un scanner
qu'on n'a pas cassé exprès est un scanner qu'on n'a pas testé.
"""

import numpy as np
import pandas as pd

from .indicators import atr, bars_since_high, enrich, rsi, wilder
from .rules import RSI_FLOOR, Signal, evaluate, market_regime_ok, position_size

IDX = lambda n: pd.bdate_range("2022-01-03", periods=n)


def series(closes, vol_mult=None, gap_at=None, gap=0.08):
    c = pd.Series(closes, dtype=float)
    o = c.shift(1).fillna(c.iloc[0])
    if gap_at is not None:
        o.iloc[gap_at] = c.iloc[gap_at - 1] * (1 + gap)
    v = np.full(len(c), 1_000_000.0)
    if vol_mult:
        for k, m in vol_mult.items():
            v[k] = 1_000_000.0 * m
    return pd.DataFrame(
        {"open": o.values, "high": (c * 1.004).values, "low": (c * 0.996).values,
         "close": c.values, "volume": v}, index=IDX(len(c)))


def trend(n=400, drift=0.0015, pull_len=4, pull_rate=-0.007, rebound=0.016, seed=1):
    rng = np.random.default_rng(seed)
    c = [100.0]
    for _ in range(n - pull_len - 2):
        c.append(c[-1] * (1 + drift + rng.normal(0, 0.004)))
    for _ in range(pull_len):
        c.append(c[-1] * (1 + pull_rate))
    c.append(c[-1] * (1 + rebound))
    return c


def bench_df(n=400, drift=0.0006, seed=7):
    rng = np.random.default_rng(seed)
    c = [400.0]
    for _ in range(n - 1):
        c.append(c[-1] * (1 + drift + rng.normal(0, 0.005)))
    return series(c)


def ok(name, cond):
    print(f"  {'PASS' if cond else 'ÉCHEC'}  {name}")
    assert cond, name


def main():
    print("\n— Indicateurs —")
    s = pd.Series(np.arange(1.0, 61.0))
    ok("wilder(14) != ema(span=14) (alpha 1/14 vs 2/15)",
       abs(wilder(s, 14).iloc[-1] - s.ewm(span=14, adjust=False).mean().iloc[-1]) > 0.5)
    ok("RSI d'une série monotone croissante = 100", abs(rsi(s).iloc[-1] - 100.0) < 1e-9)
    ok("RSI d'une série monotone décroissante = 0",
       abs(rsi(pd.Series(np.arange(60.0, 0.0, -1.0))).iloc[-1]) < 1e-9)
    ok("RSI borné 0-100", rsi(pd.Series(np.random.default_rng(3).normal(100, 5, 300)
                                        ).cumsum()).dropna().between(0, 100).all())
    h = pd.Series([1, 2, 9, 3, 4, 5.0])
    ok("bars_since_high : pic à 3 barres du bord",
       bars_since_high(h, 6).iloc[-1] == 3.0)
    tr = atr(pd.Series([10.0] * 30), pd.Series([9.0] * 30), pd.Series([9.5] * 30), 14)
    ok("ATR d'un range constant de 1.0 converge vers 1.0", abs(tr.iloc[-1] - 1.0) < 0.05)

    b = bench_df()
    be, bc = enrich(b), b["close"]
    print("\n— Cas positif —")
    d = enrich(series(trend(), vol_mult={-1: 1.9}), bench_close=bc)
    sig = evaluate(d, "GOOD", market_regime_ok(be), days_to_earnings=30)
    ok("le repli sain déclenche", sig.fired)
    ok("13 blocs évalués", len(sig.blocks) == 13)
    ok("stop sous l'entrée", sig.stop < sig.entry)
    ok("risque unitaire < 12 %", sig.risk_pct < 0.12)

    print("\n— Cas négatifs (chacun doit bloquer pour la BONNE raison) —")
    sig2 = evaluate(d, "GOOD", False, days_to_earnings=30)
    ok("marché RISK-OFF bloque", not sig2.fired and not sig2.blocks["1a_marche_sma200"])

    deep = enrich(series(trend(pull_len=7, pull_rate=-0.011), vol_mult={-1: 1.9}),
                  bench_close=bc)
    sd = evaluate(deep, "DEEP", True, days_to_earnings=30)
    ok(f"repli trop profond (RSI < {RSI_FLOOR:.0f}) rejeté",
       not sd.fired and not sd.blocks["2c_rsi_jamais_sous_40"])

    down = enrich(series(trend(drift=-0.0012, rebound=0.016), vol_mult={-1: 1.9}),
                  bench_close=bc)
    sdn = evaluate(down, "DOWN", True, days_to_earnings=30)
    ok("tendance baissière rejetée",
       not sdn.fired and not sdn.blocks["1b_titre_sma200"])

    flat = enrich(series(trend()), bench_close=bc)
    sf = evaluate(flat, "NOVOL", True, days_to_earnings=30)
    ok("RVOL 1.0 rejeté", not sf.fired and not sf.blocks["4a_rvol"])

    gp = enrich(series(trend(), vol_mult={-1: 1.9}, gap_at=-2), bench_close=bc)
    sg = evaluate(gp, "GAP", True, days_to_earnings=30)
    ok("gap > 5 % pose un veto",
       not sg.fired and any("gap" in v for v in sg.vetos))

    se = evaluate(d, "EARN", True, days_to_earnings=4)
    ok("résultats dans 4 séances → veto", not se.fired)
    su = evaluate(d, "UNK", True, days_to_earnings=None)
    ok("résultats INCONNUS → veto (jamais ignoré en silence)",
       not su.fired and any("INCONNUS" in v for v in su.vetos))
    so = evaluate(d, "GOOD", True, open_tickers=("GOOD",), n_open=1, days_to_earnings=30)
    ok("position déjà ouverte → veto", not so.fired)

    print("\n— Dimensionnement —")
    t = Signal("T", d.index[-1], True, entry=100.0, stop=95.0)
    ps = position_size(t, 10_000.0)
    ok("1 % de 10 000 € / 5 € de risque = 20 titres", ps["shares"] == 20)
    ok("risque effectif = 100 €", abs(ps["risk_eur"] - 100.0) < 1e-6)
    t2 = Signal("T", d.index[-1], True, entry=100.0, stop=99.5)
    ps2 = position_size(t2, 10_000.0)
    ok("stop serré → plafond 25 % appliqué (25 titres, pas 200)",
       ps2["shares"] == 25 and ps2["capped"])

    print("\nTous les tests passent.\n")


if __name__ == "__main__":
    main()
