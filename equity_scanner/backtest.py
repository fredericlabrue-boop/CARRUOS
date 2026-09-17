"""Moteur de backtest : rejoue les regles sur l'historique, trade par trade.

HYPOTHESES, toutes explicites et toutes discutables :

  - Entree et sortie a la CLOTURE de la barre du signal. C'est coherent avec
    le mode operatoire reel (scan a 21h40, ordre avant la cloche) mais
    legerement optimiste : en pratique tu paies quelques points de base de
    plus.
  - Le veto resultats N'EST PAS applique retroactivement : le calendrier
    passe n'est pas disponible. Le backtest est donc optimiste d'exactement
    les trades qui auraient ete bloques par une publication.
  - Le stop se declenche sur CLOTURE, pas en intraday. Un gap sous le stop
    sort au cours d'ouverture reel de la barre suivante, sans protection.
    C'est volontaire : un stop intraday sur actions se fait sortir par le
    bruit et ne protege de toute facon pas des gaps.
  - Cout : 10 points de base par aller-retour (5 a l'entree, 5 a la sortie),
    spread et commission confondus.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .rules import (STOP_ATR_MULT, STOP_SWING_BUFFER, evaluate, market_regime_ok)

COUT_AR = 0.0010          # 10 bp par aller-retour
BE_ATR = 2.0              # gain latent avant remontee du stop au point mort
TRAIL_ATR = 4.0           # gain latent avant stop suiveur sur EMA20
MAX_BARRES = 120          # filet de securite : ~6 mois


@dataclass
class Trade:
    ticker: str
    entree_d: pd.Timestamp
    sortie_d: pd.Timestamp
    entree: float
    sortie: float
    stop0: float
    atr: float
    barres: int
    motif: str

    @property
    def risque(self) -> float:
        return self.entree - self.stop0

    @property
    def R(self) -> float:
        """Resultat en multiples de risque, net de couts. Sans dimension,
        donc comparable d'un titre a l'autre quel que soit le prix."""
        if self.risque <= 0:
            return 0.0
        brut = self.sortie - self.entree
        cout = self.entree * COUT_AR
        return (brut - cout) / self.risque

    @property
    def rendement(self) -> float:
        return (self.sortie - self.entree) / self.entree - COUT_AR


# ---------------------------------------------------------------------
# Frottements de marche.
#
# Le signal se calcule a la cloture de J, mais on ne peut pas acheter a
# cette cloture : l'ordre part a l'ouverture de J+1. Entre les deux, le
# prix a bouge. Ignorer ce decalage revient a se donner une information
# qu'on n'avait pas, et cela gonfle mecaniquement le resultat.
#
# COUTS : spread + commission, appliques a l'entree ET a la sortie.
# 0,10 % par cote est realiste sur des grandes capitalisations chez un
# courtier low-cost. SLIPPAGE : degradation supplementaire du prix
# obtenu, dans le sens defavorable des deux cotes.
# ---------------------------------------------------------------------

EXECUTION_J1 = True        # ordre passe a l'ouverture suivante
COUT_PAR_COTE = 0.0010     # spread + commission
SLIPPAGE = 0.0005          # degradation du prix obtenu


def _prix_entree(d: pd.DataFrame, i: int) -> tuple[float, int] | None:
    """Prix d'achat reel et barre a laquelle il est obtenu."""
    if not EXECUTION_J1:
        return float(d.iloc[i]["close"]), i
    if i + 1 >= len(d):
        return None                      # signal le dernier jour : non jouable
    o = float(d.iloc[i + 1]["open"])
    if not np.isfinite(o) or o <= 0:
        return None
    return o * (1 + COUT_PAR_COTE + SLIPPAGE), i + 1


def _prix_sortie(c: float) -> float:
    return c * (1 - COUT_PAR_COTE - SLIPPAGE)


def simule(d: pd.DataFrame, i: int, ticker: str, bo: pd.DataFrame) -> Trade | None:
    """Signal a la cloture de la barre i, execution a l'ouverture de i+1.

    Le stop et l'ATR sont ceux connus AU MOMENT DU SIGNAL : on ne peut
    pas dimensionner sur une information posterieure.
    """
    ligne = d.iloc[i]
    atr = float(ligne["atr14"])
    if not np.isfinite(atr) or atr <= 0:
        return None
    ex = _prix_entree(d, i)
    if ex is None:
        return None
    entree, i0 = ex

    fenetre = d.iloc[max(0, i - 9):i + 1]
    stop = min(float(fenetre["low"].min()) - STOP_SWING_BUFFER * atr,
               entree - STOP_ATR_MULT * atr)
    if stop >= entree:
        return None
    stop0 = stop
    sous_ema = 0

    for j in range(i0 + 1, min(i0 + 1 + MAX_BARRES, len(d))):
        r = d.iloc[j]
        c = float(r["close"])

        # 1. Stop (sur cloture). Un gap sous le stop sort au cours reel.
        if c <= stop:
            return Trade(ticker, d.index[i0], d.index[j], entree,
                         _prix_sortie(c), stop0, atr, j - i0, "stop")

        # 2. Regime : marche sous sa MM200 -> liquidation
        if not bool(bo["close"].iloc[j] > bo["sma200"].iloc[j]):
            return Trade(ticker, d.index[i0], d.index[j], entree,
                         _prix_sortie(c), stop0, atr, j - i0, "regime")

        # 3. Sortie tendance
        if c < float(r["sma50"]):
            return Trade(ticker, d.index[i0], d.index[j], entree,
                         _prix_sortie(c), stop0, atr, j - i0, "sma50")
        sous_ema = sous_ema + 1 if c < float(r["ema20"]) else 0
        if sous_ema >= 2:
            return Trade(ticker, d.index[i0], d.index[j], entree,
                         _prix_sortie(c), stop0, atr, j - i0, "ema20")

        # 4. Remontee du stop. Jamais vers le bas.
        gain = c - entree
        if gain >= TRAIL_ATR * atr and np.isfinite(r["ema20"]):
            stop = max(stop, float(r["ema20"]))
        elif gain >= BE_ATR * atr:
            stop = max(stop, entree)

    j = min(i0 + MAX_BARRES, len(d) - 1)
    return Trade(ticker, d.index[i0], d.index[j], entree,
                 _prix_sortie(float(d.iloc[j]["close"])), stop0, atr,
                 j - i0, "duree")


def signaux_vectorises(d: pd.DataFrame, bo: pd.DataFrame) -> np.ndarray:
    """Les 13 blocs calcules d'un coup sur toute la serie, en numpy.

    Strictement equivalent a un appel d'evaluate() par barre — l'egalite est
    verifiee par test — mais ~100x plus rapide. Indispensable : sans ca, un
    passage sur le S&P 500 prend des heures et la Phase 0 n'est jamais lancee.
    """
    from .rules import (EMA_BAND_ATR, GAP_LOOKBACK, GAP_VETO, MIN_DOLLAR_VOL,
                        MIN_PRICE, PULLBACK_WINDOW, RSI_FLOOR, RSI_ZONE, RVOL_MIN)
    W = PULLBACK_WINDOW
    c, h, l = d["close"], d["high"], d["low"]
    rsi, atr = d["rsi14"], d["atr14"]

    # Bloc 1 : regime
    b = (bo["close"].to_numpy() > bo["sma200"].to_numpy())
    b &= (c > d["sma200"]).to_numpy()
    b &= (d["sma50_slope20"] > 0).to_numpy()
    b &= (d["rs"] > d["rs_ma50"]).to_numpy() if "rs" in d else False
    b &= (d["macd"] > 0).to_numpy()

    # Bloc 2 : le repli
    bande = (c - d["ema20"]).abs() <= EMA_BAND_ATR * atr
    touche = (l <= d["bb_mid"]).rolling(W, min_periods=1).max().astype(bool)
    b &= (bande | touche).to_numpy()
    b &= rsi.between(*RSI_ZONE).rolling(W, min_periods=1).max().astype(bool).to_numpy()
    b &= (rsi.rolling(W, min_periods=1).min() >= RSI_FLOOR).to_numpy()
    b &= (d["bars_since_high60"] <= W).to_numpy()

    # Bloc 3 : le declencheur
    b &= (d["macd_hist"] > d["macd_hist"].shift(1)).to_numpy()
    b &= (c > d["ema20"]).to_numpy()
    b &= (c > h.shift(1)).to_numpy()

    # Bloc 4 : confirmation independante
    b &= (d["rvol"] >= RVOL_MIN).to_numpy()

    # Vetos evaluables sur historique (le veto resultats ne l'est pas)
    b &= (c >= MIN_PRICE).to_numpy()
    b &= (d["dollar_vol20"] >= MIN_DOLLAR_VOL).to_numpy()
    gap = (d["gap_pct"] > GAP_VETO).rolling(GAP_LOOKBACK, min_periods=1).max()
    b &= ~gap.fillna(0).astype(bool).to_numpy()
    return np.nan_to_num(b, nan=False).astype(bool)


def trades_ticker(d: pd.DataFrame, ticker: str, bench: pd.DataFrame,
                  debut=None, fin=None) -> list[Trade]:
    """Tous les trades d'un titre. Pas de chevauchement : on saute jusqu'a la
    sortie avant de rechercher un signal — le systeme ne detient qu'une
    position par titre."""
    bo = bench.reindex(d.index).ffill()
    sig = signaux_vectorises(d, bo)
    idx = d.index
    d0 = pd.Timestamp(debut) if debut else None
    d1 = pd.Timestamp(fin) if fin else None

    out, i, n = [], 220, len(d)
    while i < n:
        if not sig[i]:
            i += 1
            continue
        ts = idx[i]
        if (d0 is not None and ts < d0) or (d1 is not None and ts > d1):
            i += 1
            continue
        t = simule(d, i, ticker, bo)
        if t is None:
            i += 1
            continue
        out.append(t)
        i += t.barres + 1
    return out


def portefeuille(trades: list[Trade], risque=0.01, max_pos=5,
                 capital=10_000.0) -> dict:
    """Reconstitue la courbe de capital en respectant les contraintes reelles :
    1 % de risque par trade, 5 positions simultanees au maximum.

    Un trade ecarte faute de place n'est pas compte comme perdu : il n'a
    simplement jamais existe. C'est ce que ferait le systeme en vrai."""
    if not trades:
        return {"courbe": pd.Series(dtype=float), "dd": 0.0, "pris": 0,
                "ecartes": 0, "final": capital}

    tri = sorted(trades, key=lambda t: t.entree_d)
    evts, ouverts, pris, ecartes = [], [], 0, 0
    for t in tri:
        ouverts = [x for x in ouverts if x > t.entree_d]
        if len(ouverts) >= max_pos:
            ecartes += 1
            continue
        ouverts.append(t.sortie_d)
        pris += 1
        evts.append((t.sortie_d, t.R * risque))

    evts.sort()
    eq, cap = [], capital
    for ts, gain in evts:
        cap *= (1 + gain)
        eq.append((ts, cap))
    courbe = pd.Series(dict(eq)).sort_index()
    pic = courbe.cummax()
    dd = float(((courbe - pic) / pic).min()) if len(courbe) else 0.0
    return {"courbe": courbe, "dd": abs(dd), "pris": pris,
            "ecartes": ecartes, "final": float(cap)}
