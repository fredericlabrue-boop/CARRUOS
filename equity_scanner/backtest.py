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

from . import rules as R
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

    # La fenetre du plus bas de repli EST celle de la regle. Elle etait
    # ecrite « i - 9 » en dur : quand la Phase 0 decalait PULLBACK_WINDOW
    # de +-20 % pour tester la robustesse, le moteur continuait de placer
    # le stop sur 10 barres et le test de robustesse ne testait rien.
    fenetre = d.iloc[max(0, i - R.PULLBACK_WINDOW + 1):i + 1]
    stop = min(float(fenetre["low"].min()) - R.STOP_SWING_BUFFER * atr,
               entree - R.STOP_ATR_MULT * atr)
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
    # Les seuils sont lus sur le module `rules` a chaque appel : c'est ce
    # qui permet au test de robustesse de les decaler et d'etre reellement
    # pris en compte ici.
    W = R.PULLBACK_WINDOW
    c, h, l = d["close"], d["high"], d["low"]
    rsi, atr = d["rsi14"], d["atr14"]

    # Bloc 1 : regime
    # Une colonne absente n'est pas une condition fausse : c'est une
    # condition NON MESURABLE. Avant, « b &= ... if "rs" in d else False »
    # eteignait tous les signaux de la serie en silence — un titre enrichi
    # sans indice de reference rendait zero trade et la Phase 0 concluait
    # « NO-GO, 0 trade » sans jamais dire pourquoi.
    manquantes = [x for x in ("sma200", "sma50_slope20", "rs", "rs_ma50",
                              "macd", "ema20", "atr14", "rsi14", "bb_mid",
                              "macd_hist", "rvol", "bars_since_high60",
                              "gap_pct", "dollar_vol20") if x not in d.columns]
    if manquantes:
        raise ValueError(
            "colonnes d'indicateurs absentes : " + ", ".join(manquantes)
            + ". Enrichis la serie avec bench_close=... avant de rejouer "
              "les regles.")
    for col in ("close", "sma200"):
        if col not in bo.columns:
            raise ValueError(f"indice de reference sans colonne '{col}'")

    b = (bo["close"].to_numpy() > bo["sma200"].to_numpy())
    b &= (c > d["sma200"]).to_numpy()
    b &= (d["sma50_slope20"] > 0).to_numpy()
    b &= (d["rs"] > d["rs_ma50"]).to_numpy()
    b &= (d["macd"] > 0).to_numpy()

    # Bloc 2 : le repli
    bande = (c - d["ema20"]).abs() <= R.EMA_BAND_ATR * atr
    touche = (l <= d["bb_mid"]).rolling(W, min_periods=1).max().astype(bool)
    b &= (bande | touche).to_numpy()
    b &= rsi.between(*R.RSI_ZONE).rolling(W, min_periods=1).max().astype(bool).to_numpy()
    b &= (rsi.rolling(W, min_periods=1).min() >= R.RSI_FLOOR).to_numpy()
    b &= (d["bars_since_high60"] <= W).to_numpy()
    # bars_since_high vaut NaN tant que la fenetre de 60 barres n'est pas
    # pleine : NaN <= W rend False, ce qui est le comportement voulu.

    # Bloc 3 : le declencheur
    b &= (d["macd_hist"] > d["macd_hist"].shift(1)).to_numpy()
    b &= (c > d["ema20"]).to_numpy()
    b &= (c > h.shift(1)).to_numpy()

    # Bloc 4 : confirmation independante
    b &= (d["rvol"] >= R.RVOL_MIN).to_numpy()

    # Vetos evaluables sur historique (le veto resultats ne l'est pas)
    b &= (c >= R.MIN_PRICE).to_numpy()
    b &= (d["dollar_vol20"] >= R.MIN_DOLLAR_VOL).to_numpy()
    gap = (d["gap_pct"] > R.GAP_VETO).rolling(R.GAP_LOOKBACK, min_periods=1).max()
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
                 capital=10_000.0, series: dict | None = None) -> dict:
    """Reconstitue la courbe de capital en respectant les contraintes reelles :
    1 % de risque par trade, 5 positions simultanees au maximum.

    Un trade ecarte faute de place n'est pas compte comme perdu : il n'a
    simplement jamais existe. C'est ce que ferait le systeme en vrai.

    DEUX CORRECTIONS par rapport a la version d'origine.

    1. La taille de la ligne se calcule sur le capital du jour d'ENTREE,
       pas sur celui du jour de sortie. C'est la definition du risque
       fractionnaire fixe : on ne peut pas dimensionner une position avec
       un capital qu'on n'aura que plus tard.

    2. Le drawdown. L'ancienne courbe n'avait un point qu'aux dates de
       SORTIE, et deux sorties tombant le meme jour s'ecrasaient l'une
       l'autre dans un dictionnaire. Cinq lignes ouvertes pouvaient perdre
       30 % ensemble sans qu'un seul point de la courbe le montre : le
       critere « drawdown < 20 % » de la Phase 0 se prononcait sur une
       courbe aveugle aux pertes latentes.

       Si `series` est fourni ({ticker: DataFrame enrichi}), la courbe est
       valorisee CHAQUE SEANCE, positions ouvertes comprises : c'est le
       drawdown reellement vecu. Sans `series`, on retombe sur le
       drawdown realise et `dd_source` le dit franchement.
    """
    vide = {"courbe": pd.Series(dtype=float), "dd": 0.0, "dd_source": "aucune",
            "dd_realise": 0.0, "pris": 0, "ecartes": 0, "final": capital}
    if not trades:
        return vide

    # --- Selection : au plus `max_pos` lignes en meme temps -----------
    # Une ligne qui sort a la cloture de X est encore detenue a l'ouverture
    # de X : sa place n'est pas libre pour une entree datee de X.
    tri = sorted(trades, key=lambda t: (t.entree_d, t.ticker))
    fins: list[pd.Timestamp] = []
    retenus, ecartes = [], 0
    for t in tri:
        fins = [x for x in fins if x >= t.entree_d]
        if len(fins) >= max_pos:
            ecartes += 1
            continue
        fins.append(t.sortie_d)
        retenus.append(t)
    if not retenus:
        return dict(vide, ecartes=ecartes)

    # --- Capital realise, dans l'ordre chronologique ------------------
    evts = []
    for k, t in enumerate(retenus):
        evts.append((t.entree_d, 0, k))         # 0 = entree traitee avant sortie
        evts.append((t.sortie_d, 1, k))
    evts.sort()

    cap, engage, points = capital, {}, []
    for date, genre, k in evts:
        if genre == 0:
            engage[k] = cap * risque
        else:
            cap += engage.get(k, cap * risque) * retenus[k].R
            points.append((date, cap))

    debut = min(t.entree_d for t in retenus)
    realisee = pd.Series([v for _, v in points],
                         index=pd.DatetimeIndex([d for d, _ in points]))
    realisee = realisee.groupby(level=0).last().sort_index()
    if debut not in realisee.index:
        realisee = pd.concat(
            [pd.Series([capital], index=pd.DatetimeIndex([debut])), realisee]
        ).sort_index()
    dd_realise = _drawdown(realisee)

    courbe, dd, source = realisee, dd_realise, "sorties seulement"
    if series:
        q = _courbe_quotidienne(retenus, engage, realisee, series, capital)
        if q is not None and len(q) > 1:
            courbe, dd, source = q, _drawdown(q), "quotidienne"

    return {"courbe": courbe, "dd": dd, "dd_source": source,
            "dd_realise": dd_realise, "pris": len(retenus),
            "ecartes": ecartes, "final": float(cap)}


def _drawdown(courbe: pd.Series) -> float:
    """Pire recul depuis un sommet, en part du sommet. Toujours positif."""
    if len(courbe) < 2:
        return 0.0
    pic = courbe.cummax()
    return abs(float(((courbe - pic) / pic).min()))


def _courbe_quotidienne(retenus, engage: dict, realisee: pd.Series,
                        series: dict, capital: float) -> pd.Series | None:
    """Capital valorise a chaque seance, pertes latentes comprises.

    A une date donnee : capital DEJA REALISE, plus la valeur courante de
    chaque ligne encore ouverte. Une ligne vaut son gain du moment en
    multiples de risque (R) multiplie par la somme engagee a son entree.
    C'est ce qu'afficherait le releve du courtier ce jour-la.

    Le jour de la sortie, le gain est deja compte dans le capital realise :
    la part latente s'arrete donc la veille, sans double comptage.
    """
    utiles = [t for t in retenus if t.ticker in series and t.risque > 0]
    if not utiles:
        return None
    calendrier = None
    for t in utiles:
        idx = series[t.ticker].index
        calendrier = idx if calendrier is None else calendrier.union(idx)
    debut = min(t.entree_d for t in retenus)
    fin = max(t.sortie_d for t in retenus)
    calendrier = calendrier[(calendrier >= debut) & (calendrier <= fin)]
    if len(calendrier) < 2:
        return None

    base = realisee.reindex(calendrier).ffill()
    base = base.fillna(capital)
    latent = pd.Series(0.0, index=calendrier)
    for k, t in enumerate(retenus):
        if t.ticker not in series or t.risque <= 0:
            continue
        c = series[t.ticker]["close"]
        seg = c[(c.index >= t.entree_d) & (c.index < t.sortie_d)]
        if seg.empty:
            continue
        r = ((seg - t.entree) / t.risque).reindex(calendrier)
        latent = latent.add(r.fillna(0.0) * engage.get(k, capital * 0.01),
                            fill_value=0.0)
    return (base + latent).dropna()
