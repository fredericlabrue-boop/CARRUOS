"""Controle qualite des donnees. Chantier n°2 du registre, marque bloquant.

LE PRINCIPE, ET IL N'EST PAS NEGOCIABLE

Refuser de produire un signal plutot que de completer silencieusement.

Un trou dans une serie ne se devine pas. Une barre manquante comblee par
la precedente fabrique une seance qui n'a jamais eu lieu : le RVOL de
cette seance est faux, l'ATR est sous-estime, le RSI derive. Le signal qui
en sort a l'air normal — c'est precisement ce qui le rend dangereux.

CE QUE CE MODULE N'EST PAS

Ce n'est pas un parametre de strategie. Aucun seuil d'ici n'entre dans la
definition d'un signal : ils decident seulement si les donnees permettent
de se prononcer. Un controle plus severe n'invente aucun trade, il en
supprime. Le sens de l'erreur est donc toujours le meme : vers le refus.
Les valeurs gelees de `indicators.PERIODES` et de `pead.py` ne sont ni
lues ni touchees ici.

CE QU'ON VERIFIE

  structure    colonnes presentes, index croissant, sans doublon
  coherence    high >= low, close dans [low, high], prix et volume positifs
  trous        seances ouvrees absentes du calendrier
  cotation     volume nul repete, seances plates repetees
  divisions    saut de prix sans rapport avec un mouvement de marche
  fraicheur    derniere barre trop ancienne pour decider ce soir
  synchronie   calendrier decroche de celui de l'indice de reference

    py -m equity_scanner.qualite AAPL MC.PA
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]

# --- seuils de refus --------------------------------------------------
# Ce ne sont pas des reglages de performance : ce sont les limites au-dela
# desquelles on considere qu'on ne SAIT PAS, donc qu'on ne dit rien.
TROUS_MAX = 0.02           # 2 % de seances ouvrees manquantes
TROU_CONSECUTIF_MAX = 5    # une semaine de cotation absente
SAUT_SUSPECT = 0.35        # |ln(C/C-1)| : division ou regroupement probable
SAUT_VS_INDICE = 0.25      # saut du titre net du mouvement de l'indice
PLATES_MAX = 5             # seances consecutives a cours strictement egal
VOLUME_NUL_MAX = 3         # seances consecutives sans echange
FRAICHEUR_MAX = 5          # seances ouvrees depuis la derniere barre
DESYNC_MAX = 5             # seances d'ecart avec la derniere barre de l'indice
COMMUN_MIN = 0.90          # part des dates du titre presentes dans l'indice
HISTOIRE_MIN = 220         # barres necessaires a une SMA200 plus sa pente

BLOQUANT, ALERTE = "bloquant", "alerte"


@dataclass
class Rapport:
    """Verdict sur une serie. `utilisable` est la seule chose qui decide."""
    ticker: str = ""
    barres: int = 0
    debut: str = ""
    fin: str = ""
    anomalies: list = field(default_factory=list)   # (gravite, message)

    @property
    def bloquants(self) -> list:
        return [m for g, m in self.anomalies if g == BLOQUANT]

    @property
    def alertes(self) -> list:
        return [m for g, m in self.anomalies if g == ALERTE]

    @property
    def utilisable(self) -> bool:
        return not self.bloquants

    def resume(self) -> str:
        if self.bloquants:
            return self.bloquants[0]
        if self.alertes:
            return f"utilisable, {len(self.alertes)} alerte(s)"
        return "donnees saines"

    def texte(self) -> str:
        L = [f"\n  {self.ticker or 'serie'} — {self.barres} barres "
             f"({self.debut} → {self.fin})"]
        if not self.anomalies:
            L.append("    donnees saines : aucune anomalie detectee.")
        for g, m in self.anomalies:
            L.append(f"    {'REFUS ' if g == BLOQUANT else 'alerte'}  {m}")
        L.append(f"    -> {'EXPLOITABLE' if self.utilisable else 'REFUSE'}")
        return "\n".join(L)

    def dict(self) -> dict:
        return {"ticker": self.ticker, "barres": self.barres,
                "debut": self.debut, "fin": self.fin,
                "utilisable": self.utilisable,
                "bloquants": self.bloquants, "alertes": self.alertes}


# ---------------------------------------------------------------------
def _seances_ouvrees(debut, fin) -> int:
    return len(pd.bdate_range(debut, fin))


def controle(d: pd.DataFrame, bench: pd.DataFrame | None = None,
             ticker: str = "", exige_recent: bool = True,
             aujourdhui: dt.date | None = None) -> Rapport:
    """Passe une serie brute au crible. Ne modifie rien, ne comble rien.

    `exige_recent=False` pour un backtest : on rejoue le passe, la
    fraicheur n'a pas de sens. `True` pour un scan du soir, ou une serie
    arretee il y a trois semaines produirait un signal sur des cours morts.
    """
    r = Rapport(ticker=ticker)
    if d is None or not isinstance(d, pd.DataFrame) or d.empty:
        r.anomalies.append((BLOQUANT, "serie vide"))
        return r

    r.barres = len(d)
    r.debut, r.fin = str(d.index[0].date()), str(d.index[-1].date())

    # --- structure ----------------------------------------------------
    manquantes = [c for c in COLS if c not in d.columns]
    if manquantes:
        r.anomalies.append((BLOQUANT, f"colonnes absentes : {', '.join(manquantes)}"))
        return r
    if not isinstance(d.index, pd.DatetimeIndex):
        r.anomalies.append((BLOQUANT, "index non temporel"))
        return r
    if not d.index.is_monotonic_increasing:
        r.anomalies.append((BLOQUANT, "index non croissant"))
    n_doublons = int(d.index.duplicated().sum())
    if n_doublons:
        r.anomalies.append((BLOQUANT, f"{n_doublons} date(s) en double"))
    if r.barres < HISTOIRE_MIN:
        r.anomalies.append((BLOQUANT, f"historique de {r.barres} barres : "
                                      f"la SMA200 et sa pente en demandent "
                                      f"{HISTOIRE_MIN}"))

    o, h, l, c, v = (d[x] for x in COLS)

    # --- coherence des barres ----------------------------------------
    n_nan = int(d[COLS].isna().any(axis=1).sum())
    if n_nan:
        r.anomalies.append((BLOQUANT, f"{n_nan} barre(s) incompletes (NaN)"))
    n_neg = int(((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)).sum())
    if n_neg:
        r.anomalies.append((BLOQUANT, f"{n_neg} barre(s) a prix nul ou negatif"))
    n_inv = int((h < l).sum())
    if n_inv:
        r.anomalies.append((BLOQUANT, f"{n_inv} barre(s) avec plus haut < plus bas"))
    hors = int(((c > h * 1.0001) | (c < l * 0.9999)
                | (o > h * 1.0001) | (o < l * 0.9999)).sum())
    if hors:
        r.anomalies.append((BLOQUANT, f"{hors} barre(s) dont l'ouverture ou la "
                                      f"cloture sort du range du jour"))
    if int((v < 0).sum()):
        r.anomalies.append((BLOQUANT, "volume negatif"))

    # --- trous dans le calendrier ------------------------------------
    attendues = _seances_ouvrees(d.index[0], d.index[-1])
    if attendues > 0:
        # Les jours feries different d'une place a l'autre : on tolere ce
        # qu'un calendrier national retire normalement (une dizaine par an,
        # soit environ 4 %), et on ne bloque que le trou franc.
        part = 1 - r.barres / attendues
        if part > TROUS_MAX + 0.04:
            r.anomalies.append(
                (BLOQUANT, f"{part:.1%} des seances ouvrees absentes "
                           f"({attendues - r.barres} barres manquantes)"))
        elif part > TROUS_MAX:
            r.anomalies.append(
                (ALERTE, f"{part:.1%} des seances ouvrees absentes"))
    pires = _plus_long_trou(d.index)
    if pires > TROU_CONSECUTIF_MAX:
        r.anomalies.append((BLOQUANT, f"interruption de cotation de {pires} "
                                      f"seances ouvrees consecutives"))

    # --- cotation reelle ---------------------------------------------
    nuls = _plus_longue_serie(v.to_numpy() == 0)
    if nuls > VOLUME_NUL_MAX:
        r.anomalies.append((BLOQUANT, f"{nuls} seances consecutives sans "
                                      f"aucun echange"))
    plates = _plus_longue_serie(c.diff().to_numpy() == 0)
    if plates > PLATES_MAX:
        r.anomalies.append((ALERTE, f"{plates} seances consecutives au meme "
                                    f"cours exact : cotation figee ou "
                                    f"donnee recopiee"))

    # --- divisions et regroupements non ajustes ----------------------
    lr = np.log(c / c.shift(1)).replace([np.inf, -np.inf], np.nan)
    suspects = lr.abs() > SAUT_SUSPECT
    if bench is not None and "close" in bench.columns:
        lb = np.log(bench["close"].reindex(d.index).ffill()
                    / bench["close"].reindex(d.index).ffill().shift(1))
        # Un krach fait bouger l'indice aussi. Ce qui trahit une division,
        # c'est un saut du titre que le marche n'accompagne pas.
        suspects &= (lr - lb).abs() > SAUT_VS_INDICE
    n_sauts = int(suspects.fillna(False).sum())
    if n_sauts:
        dates = ", ".join(str(x.date()) for x in d.index[suspects.fillna(False)][:3])
        r.anomalies.append((BLOQUANT, f"{n_sauts} saut(s) de prix sans "
                                      f"contrepartie de marche ({dates}) : "
                                      f"division ou regroupement non ajuste"))

    # --- fraicheur et synchronie -------------------------------------
    jour = aujourdhui or dt.date.today()
    if exige_recent:
        retard = max(0, _seances_ouvrees(d.index[-1].date(), jour) - 1)
        if retard > FRAICHEUR_MAX:
            r.anomalies.append((BLOQUANT, f"derniere barre au {r.fin}, soit "
                                          f"{retard} seances de retard"))
        elif retard > 1:
            r.anomalies.append((ALERTE, f"derniere barre au {r.fin} "
                                        f"({retard} seances de retard)"))

    if bench is not None and len(bench):
        ecart = abs(_seances_ouvrees(min(d.index[-1], bench.index[-1]),
                                     max(d.index[-1], bench.index[-1])) - 1)
        if ecart > DESYNC_MAX:
            r.anomalies.append(
                (BLOQUANT, f"decrochage de {ecart} seances avec l'indice "
                           f"(titre {r.fin}, indice {bench.index[-1].date()})"))
        recent = d.index[d.index >= bench.index[0]]
        if len(recent):
            commun = float(recent.isin(bench.index).mean())
            if commun < COMMUN_MIN:
                r.anomalies.append(
                    (ALERTE, f"{1 - commun:.0%} des seances du titre sont "
                             f"absentes du calendrier de l'indice"))
    return r


def _plus_long_trou(index: pd.DatetimeIndex) -> int:
    """Plus longue suite de seances ouvrees sans aucune barre."""
    if len(index) < 2:
        return 0
    pire = 0
    for a, b in zip(index[:-1], index[1:]):
        manque = _seances_ouvrees(a, b) - 2
        if manque > pire:
            pire = manque
    return max(0, pire)


def _plus_longue_serie(masque) -> int:
    """Plus longue suite de True consecutifs."""
    m = np.asarray(masque, dtype=bool)
    if not m.any():
        return 0
    pire = courant = 0
    for x in m:
        courant = courant + 1 if x else 0
        pire = max(pire, courant)
    return pire


# ---------------------------------------------------------------------
def filtre(series: dict, bench: pd.DataFrame | None = None,
           exige_recent: bool = True) -> tuple[dict, list]:
    """Separe les series exploitables des series refusees.

    Rend ({ticker: serie}, [(ticker, motif)]). Le motif est toujours dit :
    un titre qui disparait d'un scan sans explication est un bug qu'on ne
    voit jamais.
    """
    gardees, refusees = {}, []
    for tk, d in series.items():
        r = controle(d, bench, ticker=tk, exige_recent=exige_recent)
        if r.utilisable:
            gardees[tk] = d
        else:
            refusees.append((tk, r.resume()))
    return gardees, sorted(refusees)


def main() -> None:
    import argparse
    from . import cache as ch

    a = argparse.ArgumentParser(description="Controle qualite d'une serie")
    a.add_argument("tickers", nargs="*", default=["AAPL"])
    a.add_argument("--indice", default="SPY")
    a.add_argument("--annees", type=int, default=3)
    o = a.parse_args()

    try:
        bench = ch.charge(o.indice, annees=o.annees)
    except Exception as exc:
        print(f"  Indice {o.indice} indisponible ({type(exc).__name__}).")
        bench = None
    for tk in (o.tickers or ["AAPL"]):
        try:
            print(controle(ch.charge(tk, annees=o.annees), bench,
                           ticker=tk).texte())
        except Exception as exc:
            print(f"\n  {tk} : chargement impossible "
                  f"({type(exc).__name__}: {exc})")
    print()


if __name__ == "__main__":
    main()
