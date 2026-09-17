"""Règles du système « Repli en tendance » v1.0.

Toute valeur numérique ici est un PARAMÈTRE FIGÉ. Si tu les modifies pour
faire passer un backtest, tu fais du grid search déguisé et le z-score ne
veut plus rien dire. Change-les une fois, re-teste tout, et documente.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# --- paramètres figés -------------------------------------------------
PULLBACK_WINDOW = 10        # séances max depuis le plus haut 60j
RSI_ZONE = (40.0, 55.0)     # zone d'achat en tendance (pas 30 : cf. spec)
RSI_FLOOR = 40.0            # une clôture sous ce niveau invalide le repli
EMA_BAND_ATR = 0.5          # largeur de la zone de repli autour de l'EMA20
RVOL_MIN = 1.2
GAP_VETO = 0.05             # gap > 5 % sur 3 séances = mouvement news
GAP_LOOKBACK = 3
EARNINGS_BLACKOUT = 10      # séances
STOP_ATR_MULT = 1.5
STOP_SWING_BUFFER = 0.1     # × ATR sous le plus bas du repli
MIN_PRICE = 10.0
MIN_DOLLAR_VOL = 20_000_000.0
RISK_PER_TRADE = 0.01       # 1 % du sleeve
MAX_POSITIONS = 5
MAX_WEIGHT = 0.25           # 25 % du sleeve sur une ligne


@dataclass
class Signal:
    ticker: str
    date: pd.Timestamp
    fired: bool
    blocks: dict = field(default_factory=dict)
    vetos: list = field(default_factory=list)
    entry: float = np.nan
    stop: float = np.nan
    atr: float = np.nan
    rs_6m: float = np.nan
    risk_pct: float = np.nan

    @property
    def failed_blocks(self):
        return [k for k, v in self.blocks.items() if not v]


def market_regime_ok(bench: pd.DataFrame, i: int = -1) -> bool:
    """Bloc 1a — filtre marché. À lui seul, ce filtre supprime 2008 et 2022."""
    row = bench.iloc[i]
    return bool(row["close"] > row["sma200"])


def evaluate(
    d: pd.DataFrame,
    ticker: str,
    bench_ok: bool,
    i: int = -1,
    open_tickers: tuple = (),
    n_open: int = 0,
    days_to_earnings: int | None = None,
) -> Signal:
    """Évalue les 4 blocs sur la barre `i` (par défaut la dernière close).

    days_to_earnings=None signifie INCONNU, pas SANS RISQUE : le veto est
    alors levé en warning, jamais ignoré silencieusement.
    """
    n = len(d)
    if n == 0:
        raise ValueError("serie vide : aucune barre a evaluer")
    # Position ABSOLUE de la barre. Sans cette normalisation, un indice
    # positif plus petit que la fenetre produisait une borne de depart
    # negative : la tranche repartait de la FIN de la serie et rendait une
    # fenetre vide, donc un stop a NaN. Et i=0 faisait de `prev` la
    # derniere barre — le declencheur se comparait au futur.
    pos = i if i >= 0 else n + i
    if not 0 <= pos < n:
        raise IndexError(f"barre {i} hors de la serie ({n} barres)")
    if pos < 1:
        raise ValueError("la barre 0 n'a pas de veille : declencheur "
                         "non evaluable")
    row = d.iloc[pos]
    win = d.iloc[max(0, pos - PULLBACK_WINDOW + 1) : pos + 1]
    sig = Signal(ticker=ticker, date=d.index[pos], fired=False)

    # --- Bloc 1 : régime ---------------------------------------------
    sig.blocks["1a_marche_sma200"] = bench_ok
    sig.blocks["1b_titre_sma200"] = bool(row["close"] > row["sma200"])
    sig.blocks["1c_sma50_pente"] = bool(row["sma50_slope20"] > 0)
    # Sans benchmark, `rs` est absent : la force relative n'est pas
    # EVALUABLE. On la marque comme telle au lieu de la compter comme un
    # echec, et `fired` ne peut pas se declencher tant qu'elle manque.
    if "rs" in d.columns and "rs_ma50" in d.columns:
        sig.blocks["1d_force_relative"] = bool(
            row["rs"] > row["rs_ma50"])
    else:
        sig.blocks["1d_force_relative"] = False
        sig.vetos.append("FORCE RELATIVE NON CALCULEE — indice de reference "
                         "absent")
    # La LIGNE MACD reste au-dessus de zéro pendant un repli sain : c'est une
    # condition de régime. L'HISTOGRAMME, lui, passe négatif par construction
    # dès qu'il y a repli — exiger hist > 0 à l'entrée arrive 4 à 6 séances
    # après le point bas et tue le setup. Voir bloc 3.
    sig.blocks["1e_macd_ligne_positive"] = bool(row["macd"] > 0)

    # --- Bloc 2 : setup (le repli) -----------------------------------
    band = EMA_BAND_ATR * row["atr14"]
    in_band = bool(abs(row["close"] - row["ema20"]) <= band) or bool(
        (win["low"] <= win["bb_mid"]).any()
    )
    rsi_touched = bool(win["rsi14"].between(*RSI_ZONE).any())
    rsi_held = bool(win["rsi14"].min() >= RSI_FLOOR)
    sig.blocks["2a_zone_repli"] = in_band
    sig.blocks["2b_rsi_zone_40_55"] = rsi_touched
    sig.blocks["2c_rsi_jamais_sous_40"] = rsi_held
    sig.blocks["2d_repli_recent"] = bool(row["bars_since_high60"] <= PULLBACK_WINDOW)

    # --- Bloc 3 : déclencheur ----------------------------------------
    prev = d.iloc[pos - 1]
    sig.blocks["3a_macd_hist_retourne"] = bool(row["macd_hist"] > prev["macd_hist"])
    sig.blocks["3b_close_sup_ema20"] = bool(row["close"] > row["ema20"])
    sig.blocks["3c_close_sup_haut_veille"] = bool(row["close"] > prev["high"])

    # --- Bloc 4 : confirmation indépendante --------------------------
    sig.blocks["4a_rvol"] = bool(row["rvol"] >= RVOL_MIN)

    # --- Vetos --------------------------------------------------------
    if row["close"] < MIN_PRICE:
        sig.vetos.append("prix < 10 $")
    if row["dollar_vol20"] < MIN_DOLLAR_VOL:
        sig.vetos.append("volume dollar 20j < 20 M$")
    if bool((win["gap_pct"].tail(GAP_LOOKBACK) > GAP_VETO).any()):
        sig.vetos.append("gap > 5 % sur 3 séances")
    if ticker in open_tickers:
        sig.vetos.append("position déjà ouverte")
    if n_open >= MAX_POSITIONS:
        sig.vetos.append("5 positions déjà ouvertes")
    if days_to_earnings is None:
        sig.vetos.append("RÉSULTATS INCONNUS — à vérifier à la main")
    elif days_to_earnings < EARNINGS_BLACKOUT:
        sig.vetos.append(f"résultats dans {days_to_earnings} séances")

    sig.fired = all(sig.blocks.values()) and not sig.vetos

    # --- Niveaux ------------------------------------------------------
    sig.entry = float(row["close"])
    sig.atr = float(row["atr14"])
    if not np.isfinite(sig.atr) or sig.atr <= 0:
        sig.fired = False
        sig.vetos.append("ATR indisponible — niveaux non calculables")
        return sig
    swing_low = float(win["low"].min()) - STOP_SWING_BUFFER * sig.atr
    atr_stop = sig.entry - STOP_ATR_MULT * sig.atr
    sig.stop = float(min(swing_low, atr_stop))
    sig.risk_pct = (sig.entry - sig.stop) / sig.entry
    sig.rs_6m = float(row.get("rs_6m", np.nan))
    return sig


def position_size(sig: Signal, sleeve_eur: float) -> dict:
    """Taille = (1 % du sleeve) / (entrée − stop), plafonnée à 25 % du sleeve."""
    risk_unit = sig.entry - sig.stop
    if risk_unit <= 0:
        return {"shares": 0, "notional": 0.0, "capped": False}
    shares = int((RISK_PER_TRADE * sleeve_eur) // risk_unit)
    cap = int((MAX_WEIGHT * sleeve_eur) // sig.entry)
    capped = shares > cap
    shares = min(shares, cap)
    return {
        "shares": shares,
        "notional": round(shares * sig.entry, 2),
        "risk_eur": round(shares * risk_unit, 2),
        "capped": capped,
    }


def rank(signals: list) -> list:
    """Classement des candidats par force relative 6 mois vs benchmark.

    ATTENTION : ce tri est un DÉPARTAGE, pas un signal validé. Il ajoute un
    degré de liberté. Si tu t'en sers, il doit passer la Phase 0 comme le
    reste — sinon prends les signaux par ordre alphabétique, c'est plus
    honnête qu'un tri non testé.
    """
    return sorted(
        [s for s in signals if s.fired],
        key=lambda s: (-s.rs_6m if np.isfinite(s.rs_6m) else 0.0),
    )


# --- Sorties ----------------------------------------------------------
# Hierarchie de la spec v1.0. Le stop initial depend du prix d'entree et
# n'est donc evaluable que si l'on detient la position : il est traite
# ailleurs, pas ici.
def evaluate_exit(d, bench_ok: bool, i: int = -1) -> dict:
    """Signaux de sortie evaluables sans connaitre le prix d'entree."""
    row = d.iloc[i]
    prev = d.iloc[i - 1]
    sorties = {
        "marché sous sa MM200": not bench_ok,
        "2 clôtures sous l'EMA20": bool(row["close"] < row["ema20"]
                                        and prev["close"] < prev["ema20"]),
        "clôture sous la SMA50": bool(row["close"] < row["sma50"]),
        "MACD repassé négatif": bool(row["macd"] < 0),
    }
    return sorties
