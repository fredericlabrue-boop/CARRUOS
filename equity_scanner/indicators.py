"""Indicateurs techniques. Paramètres figés — ne pas optimiser."""

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def wilder(s: pd.Series, n: int) -> pd.Series:
    """Lissage de Wilder : alpha = 1/n. C'est ce que RSI et ATR utilisent,
    PAS une EMA de span n (alpha = 2/(n+1)). Se tromper ici décale le RSI
    de plusieurs points et fausse tout le backtest."""
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = wilder(gain, n)
    avg_loss = wilder(loss, n)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(avg_loss != 0.0, 100.0)


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    return pd.concat(
        [high - low, (high - prev).abs(), (low - prev).abs()], axis=1
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return wilder(true_range(high, low, close), n)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    width = (upper - lower) / mid
    return mid, upper, lower, width


def rvol(volume: pd.Series, n: int = 20) -> pd.Series:
    base = volume.rolling(n, min_periods=n).mean()
    return volume / base.replace(0.0, np.nan)


def rs_ratio(close: pd.Series, bench_close: pd.Series, n: int = 50):
    ratio = close / bench_close
    return ratio, sma(ratio, n)


def bars_since_high(high: pd.Series, lookback: int = 60) -> pd.Series:
    """Nombre de séances écoulées depuis le plus haut des `lookback` dernières.
    0 = le plus haut est aujourd'hui.

    Version par fenêtres glissantes numpy. Le `rolling().apply()` d'origine
    rappelait une fonction Python une fois par barre : sur un univers de
    500 titres × 5 000 barres, il représentait à lui seul 40 % du temps
    de calcul des indicateurs. Le résultat est identique, vérifié par test.
    """
    v = high.to_numpy(dtype=float)
    n = len(v)
    out = np.full(n, np.nan)
    if n >= lookback and lookback > 0:
        fen = np.lib.stride_tricks.sliding_window_view(v, lookback)
        # argmax renvoie la PREMIERE occurrence du maximum, comme np.argmax
        # dans la version d'origine : même convention en cas d'égalité.
        out[lookback - 1:] = (lookback - 1 - np.argmax(fen, axis=1)).astype(float)
        # Une fenêtre contenant un NaN n'a pas de plus haut défini.
        out[lookback - 1:][np.isnan(fen).any(axis=1)] = np.nan
    return pd.Series(out, index=high.index, name=high.name)


# Periodes de la strategie, en barres JOURNALIERES. Elles sont gelees :
# ce sont celles qui ont ete fixees avant le test, et elles ne bougent pas.
PERIODES = {"sma_longue": 200, "sma_moyenne": 50, "ema_courte": 20,
            "atr": 14, "rsi": 14, "macd": (12, 26, 9), "bb": (20, 2.0),
            "vol_ma": 20, "pente": 20, "haut": 60, "dollar_vol": 20}


def enrich(df: pd.DataFrame, bench_close: pd.Series | None = None,
           periodes: dict | None = None) -> pd.DataFrame:
    """Ajoute toutes les colonnes d'indicateurs. df doit contenir
    open/high/low/close/volume, index datetime croissant.

    `periodes` permet d'adapter les longueurs a une autre taille de
    bougie. Ce n'est PAS un reglage de performance : c'est une conversion
    de calendrier. Une SMA 200 sur bougies mensuelles couvrirait seize
    ans ; sur bougies hebdomadaires, 200 semaines font quatre ans. Pour
    lire le meme horizon reel, le nombre de barres doit suivre la taille
    de la barre. Les valeurs de la strategie, elles, restent celles de
    PERIODES et ne sont jamais recalculees.
    """
    P = dict(PERIODES, **(periodes or {}))
    d = df.copy()
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"]

    d["sma200"] = sma(c, P["sma_longue"])
    d["sma50"] = sma(c, P["sma_moyenne"])
    d["ema20"] = ema(c, P["ema_courte"])
    d["atr14"] = atr(h, l, c, P["atr"])
    d["rsi14"] = rsi(c, P["rsi"])
    d["macd"], d["macd_sig"], d["macd_hist"] = macd(c, *P["macd"])
    d["bb_mid"], d["bb_up"], d["bb_low"], d["bb_width"] = bollinger(
        c, P["bb"][0], P["bb"][1])
    d["vol_ma20"] = v.rolling(P["vol_ma"], min_periods=P["vol_ma"]).mean()
    # rvol et rs_ma50 suivent EUX AUSSI la conversion de calendrier. Les
    # laisser sur leurs valeurs par défaut (20 et 50 barres) donnait, en
    # hebdomadaire, un volume relatif calculé sur 20 SEMAINES face à des
    # moyennes converties sur 4 : deux horizons différents dans la même
    # ligne de règle.
    d["rvol"] = rvol(v, P["vol_ma"])
    d["sma50_slope20"] = d["sma50"] - d["sma50"].shift(P["pente"])
    d["bars_since_high60"] = bars_since_high(h, P["haut"])
    d["gap_pct"] = (d["open"] / c.shift(1) - 1.0).abs()
    d["dollar_vol20"] = (c * v).rolling(
        P["dollar_vol"], min_periods=P["dollar_vol"]).mean()

    if bench_close is not None:
        bench = bench_close.reindex(d.index).ffill()
        d["rs"], d["rs_ma50"] = rs_ratio(c, bench, P["sma_moyenne"])
        # 126 séances = six mois. Sur une autre taille de bougie, le
        # nombre de barres suit le même facteur de conversion que les
        # moyennes : 126 × (200 converti / 200 journalier).
        facteur = P["sma_longue"] / PERIODES["sma_longue"]
        n6m = max(2, round(126 * facteur))
        d["rs_6m"] = (c / c.shift(n6m)) / (bench / bench.shift(n6m))
    return d


def colonnes_manquantes(d: pd.DataFrame, avec_benchmark: bool = True) -> list[str]:
    """Colonnes qu'`enrich` aurait dû produire et qui manquent.

    Sert de garde-fou : une règle qui interroge une colonne absente doit
    refuser de conclure, jamais renvoyer « faux » en silence.
    """
    attendues = ["sma200", "sma50", "ema20", "atr14", "rsi14", "macd",
                 "macd_sig", "macd_hist", "bb_mid", "bb_up", "bb_low",
                 "bb_width", "vol_ma20", "rvol", "sma50_slope20",
                 "bars_since_high60", "gap_pct", "dollar_vol20"]
    if avec_benchmark:
        attendues += ["rs", "rs_ma50", "rs_6m"]
    return [c for c in attendues if c not in d.columns]
