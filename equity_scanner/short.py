"""Derive post-annonce NEGATIVE — vente a decouvert. Hypothese n°3.

Specification : strategie-short-v1.md, empreinte SHA256
bc6a8d1798c38be9ca134c38b309e1d65a1b1108b8d92b6b99fe1a7c77aa175b

AUCUNE valeur de ce fichier ne doit etre modifiee apres le premier test.
Les constantes ci-dessous sont celles du document, recopiees telles
quelles. Si l'une d'elles change, ce n'est plus la meme hypothese : il
faut une nouvelle specification, une nouvelle empreinte et une nouvelle
ligne au registre.

VENDRE A DECOUVERT N'EST PAS ACHETER A L'ENVERS

Ce module ne retourne pas les signes d'une regle validee a l'achat. Il
met en oeuvre une specification ecrite pour la vente, avec ses propres
asymetries :

  - la perte n'est pas bornee : un titre qui double coute 100 % de la
    position, un titre qui quintuple en coute 400 % ;
  - la position GROSSIT quand elle a tort, donc le plafond de poids se
    verifie a chaque seance, pas seulement a l'entree ;
  - le marche derive a la hausse : il ne suffit pas d'avoir raison, il
    faut avoir assez raison pour couvrir cette derive ;
  - emprunter les titres se paie, au prorata du temps de detention.

CE QUE CE TEST SURESTIME, ET IL FAUT LE RETRANCHER A LA MAIN

Le dividende du au preteur n'est pas modelise : les donnees de cours
disponibles ne permettent pas de le reconstituer titre par titre. Sur
45 seances, un titre au rendement de 2 % coute environ 0,4 % de
dividende. Si l'esperance mesuree est inferieure a 0,4 point par trade,
l'avantage n'existe pas.

LA LECTURE DU TEXTE, ET LA PERIODE PARTAGEE

La facon dont ce moteur LIT la specification est ecrite a part, dans
strategie-short-v1-lecture.md, datee et hachee avant tout regard de
l'hypothese n°3 sur sa periode de validation. Cette periode avait deja
ete regardee par l'hypothese n°2 le 29/09/2026 : ce qu'il faut en
conclure est ecrit dans strategie-short-v1-amendement-1.md. Le passage
unique ne part pas tant que le proprietaire n'a pas valide les deux.

L'ancienne voie, qui calculait directement sur 2024-2026 sans rien
inscrire au registre, n'existe plus. Deux temps, comme a l'hypothese n°2 :

    py -m equity_scanner.short                      # preparation, puis le passage unique sur confirmation
    py -m equity_scanner.short --preparer           # la preparation seule, autant de fois qu'on veut
    py -m equity_scanner.short --valider-documents  # la note de lecture et l'amendement, une fois
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest as bt
from . import data as dl
from . import pead

# --------------------------------------------------------------- regles
# Recopiees de strategie-short-v1.md, etape 2. Gelees.
CAR3_MAX = -0.050         # E1 : reaction cumulee J-1..J+1, NEGATIVE
RVOL_ANNONCE = 2.0        # E2 : volume du jour d'annonce / moyenne 20 j
PRIX_MIN = 10.0           # E4
DOLLAR_VOL_MIN = 50e6     # E5 : plus severe qu'a l'achat, cf. emprunt
DELAI_EXEC = 3            # signal a la cloture de J+2, vente a l'ouverture J+3

MAX_BARRES = 45           # S1
STOP_ATR = 2.0            # S2 : stop AU-DESSUS de l'entree
AVANT_ANNONCE = 1         # S3 : rachat la veille de la publication suivante

RISQUE = 0.01
MAX_POS = 10              # effet de portefeuille, pas de titre
MAX_POIDS = 0.20          # 20 % du sleeve, verifie a chaque seance

# --------------------------------------------------------------- couts
EMPRUNT_AN = 0.020        # 2 % par an, au prorata temporis
EMPRUNT_DIFFICILE = 0.10  # 10 % par an : le cas qui decide, etape 6
SEANCES_AN = 252

# hors echantillon : un seul passage
OOS_DEBUT, OOS_FIN = "2024-01-01", "2026-12-31"
IN_DEBUT, IN_FIN = "2010-01-01", "2023-12-31"


@dataclass
class TradeCourt:
    """Une vente a decouvert. Les conventions de signe sont INVERSEES.

    `entree` est le prix AUQUEL ON A VENDU, net des frais : c'est ce
    qu'on encaisse. `sortie` est le prix auquel on a RACHETE, frais
    compris : c'est ce qu'on debourse. Le gain est donc entree moins
    sortie, et non l'inverse.

    On n'utilise pas backtest.Trade : sa propriete `risque` vaut
    entree - stop0, qui est NEGATIVE pour une vente puisque le stop est
    au-dessus. Elle rendrait un R de zero en silence. Mieux vaut une
    classe qui dit ce qu'elle fait.
    """
    ticker: str
    entree_d: pd.Timestamp
    sortie_d: pd.Timestamp
    entree: float             # prix de vente, encaisse
    sortie: float             # prix de rachat, debourse
    stop0: float              # AU-DESSUS de l'entree
    atr: float
    barres: int
    motif: str
    emprunt_an: float = EMPRUNT_AN
    sens: int = -1

    @property
    def risque(self) -> float:
        """Distance a l'arret, toujours positive."""
        return self.stop0 - self.entree

    @property
    def cout_emprunt(self) -> float:
        """Frais de pret, par titre, au prorata du temps de detention."""
        return self.entree * self.emprunt_an * self.barres / SEANCES_AN

    @property
    def R(self) -> float:
        """Resultat en multiples de risque, net de TOUS les couts."""
        if self.risque <= 0:
            return 0.0
        return (self.entree - self.sortie - self.cout_emprunt) / self.risque

    @property
    def rendement(self) -> float:
        if self.entree <= 0:
            return 0.0
        return (self.entree - self.sortie - self.cout_emprunt) / self.entree



# ------------------------------------------------ la lecture, pas les regles
# Rien ici n'entre dans l'empreinte des constantes (audit.parametres_short) :
# ce sont des choix de donnees et des lectures du texte, ecrits dans la
# note de lecture et haches avec elle.
RACINE = Path(__file__).resolve().parent.parent
SPECIFICATION = RACINE / "strategie-short-v1.md"
LECTURE = RACINE / "strategie-short-v1-lecture.md"
AMENDEMENT = RACINE / "strategie-short-v1-amendement-1.md"

UNIVERS = "us"
HYPOTHESE = "Dérive post-annonce négative"
TIRAGES, GRAINE = 1000, 7
TEMOINS_MIN = 20
DIVIDENDE_MIN = 0.004     # etape 3 : sous 0,4 point par trade, l'avantage n'existe pas
PFU = 0.30                # etape 7 : compte-titres ordinaire, au taux plein
CAPITAL = 10_000.0        # capital de depart du sleeve, celui du portefeuille simule

DOSSIER = Path.home() / ".carruos" / "strategie-3"
# L'ancienne voie directe — option S de Carruos.bat — ecrivait ses trades
# ici, apres avoir calcule sur 2024-2026 sans rien inscrire au registre.
TRACES = [RACINE / "short-us.csv"]

# Etape 6 : (libelle, spread + commission, glissement, emprunt annuel).
# La ligne 3 est celle de l'etape 3, ou se mesurent les cinq criteres ;
# la derniere decide.
COUTS = [
    ("sans aucun frais", 0.0, 0.0, 0.0),
    ("emprunt seul, 2 %/an", 0.0, 0.0, EMPRUNT_AN),
    ("réaliste : 2 %/an + 0,15 % par côté", 0.0010, 0.0005, EMPRUNT_AN),
    ("difficile à emprunter : 10 %/an + 0,30 % par côté", 0.0020, 0.0010,
     EMPRUNT_DIFFICILE),
]
LIGNE_CRITERES = 2
LIGNE_ELIMINATOIRE = 3

# Completude des donnees, comme a l'hypothese n°2 : aucun rendement
# n'est regarde pour decider de partir.
UNIVERS_MIN = 450
PART_DATES_MIN = 0.90
PART_EXPLOITABLES_MIN = 0.80
PART_HEURES_MIN = 0.50

CONDITIONS = ("E1 mauvaise surprise", "E2 volume", "E3 pas de rebond",
              "E4 prix", "E5 liquidite", "E6 titre sous sa SMA200")

# Les conditions en clair, lues sur les constantes, jamais recopiees.
LIBELLES = {
    "E1 mauvaise surprise":
        f"E1 mauvaise surprise : CAR3 ≤ −{abs(CAR3_MAX) * 100:.0f} %",
    "E2 volume": f"E2 volume ≥ {RVOL_ANNONCE:g} × l'habitude",
    "E3 pas de rebond": "E3 pas de rebond le lendemain",
    "E4 prix": f"E4 prix ≥ {PRIX_MIN:g} $",
    "E5 liquidite": f"E5 liquidité ≥ {DOLLAR_VOL_MIN / 1e6:g} M$ par jour",
    "E6 titre sous sa SMA200": "E6 titre sous sa SMA200",
}

MOTIFS = {"stop": "stop touché",
          "these morte": "thèse morte (clôture au-dessus de la SMA200)",
          "annonce": "veille de l'annonce suivante",
          "duree": f"{MAX_BARRES} séances écoulées"}

# Jamais un resultat de ce module sans ce rappel (CLAUDE.md).
RAPPEL_DIVIDENDE = ("Dividende dû au prêteur non modélisé : le résultat est "
                    "optimiste d'environ 0,3 à 0,4 point par trade.")
NOTE_SURVIVANT = ("Pour une vente à découvert, le sens de ce biais n'est pas "
                  "connu : manquent à la fois les faillites, qui auraient "
                  "rapporté, et les rachats avec prime, qui auraient coûté.")


# ------------------------------------------------------------ evenements
def colonnes(d: pd.DataFrame) -> dict:
    """Les colonnes du moteur, lues une fois en numpy."""
    n = len(d)

    def col(nom):
        return (d[nom].to_numpy(dtype=float) if nom in d
                else np.full(n, np.nan))
    return {"open": col("open"), "close": col("close"),
            "atr14": col("atr14"), "sma200": col("sma200")}


def evenements(d: pd.DataFrame, bench: pd.DataFrame, liste) -> list[dict]:
    """Pour chaque annonce : la seance de reaction J et les mesures.

    J est la premiere seance qui peut reagir (note de lecture, point 1) :
    apres 16 h, la suivante ; un jour sans seance, la suivante — jamais
    la precedente, ou personne ne connaissait encore l'annonce.
    """
    if d.empty or not liste:
        return []
    idx = d.index
    close = d["close"].to_numpy(dtype=float)
    vol = d["volume"].to_numpy(dtype=float)
    rt = d["close"].pct_change()
    rb = bench["close"].reindex(idx).ffill().pct_change()
    ab = (rt - rb).fillna(0.0).to_numpy(dtype=float)
    volma = d["volume"].rolling(20, min_periods=20).mean().to_numpy(dtype=float)
    dvol = (d["dollar_vol20"].to_numpy(dtype=float) if "dollar_vol20" in d
            else np.zeros(len(d)))
    sma = (d["sma200"].to_numpy(dtype=float) if "sma200" in d
           else np.full(len(d), np.nan))
    # La variante de robustesse (point 9) : SPY sous sa MM200 a J+2.
    bc = bench["close"]
    bas = (bc < bc.rolling(200, min_periods=200).mean()).astype(float)
    indice_bas = bas.reindex(idx).ffill().fillna(0.0).to_numpy() > 0.5
    out, vues = [], set()
    for a in sorted((pead._normalise(x) for x in liste),
                    key=lambda a: a["date"]):
        j = pead.seance_de_reaction(idx, a["date"], a["heure"])
        if j is None or j <= 1 or j + DELAI_EXEC >= len(idx) or j in vues:
            continue
        vues.add(j)
        vm = volma[j] if np.isfinite(volma[j]) else 0.0
        s2 = sma[j + 2]
        out.append({
            "i": j, "date": idx[j], "annonce": a["date"], "heure": a["heure"],
            "moment": pead.moment(idx, a["date"], a["heure"]),
            "car3": float(ab[j - 1:j + 2].sum()),
            "rvol": float(vol[j] / vm) if vm > 0 else 0.0,
            # E3 : le marche ne s'est PAS ravise a la hausse
            "suite": bool(close[j + 1] < close[j - 1]),
            "prix": float(close[j + 2]),
            "dvol": float(dvol[j + 2]) if np.isfinite(dvol[j + 2]) else 0.0,
            # E6 : le titre est deja en tendance baissiere, a J+2
            "sous_sma200": bool(np.isfinite(s2) and close[j + 2] < s2),
            "indice_sous_mm200": bool(indice_bas[j + 2]),
        })
    return out


def passe(ev: dict) -> dict:
    """Les six conditions, une par une, pour dire exactement ce qui bloque."""
    return dict(zip(CONDITIONS, (
        ev["car3"] <= CAR3_MAX,
        ev["rvol"] >= RVOL_ANNONCE,
        ev["suite"],
        ev["prix"] >= PRIX_MIN,
        ev["dvol"] >= DOLLAR_VOL_MIN,
        ev["sous_sma200"],
    )))


def est_temoin(ev: dict, cond: dict) -> bool:
    """Une annonce SANS surprise notable, vendable selon les memes regles
    (note de lecture, point 7) : |CAR3| sous le seuil de E1, et E4, E5,
    E6 remplies. Une bonne surprise n'en est pas une : vendre apres elle
    rendrait le temoin plus facile a battre."""
    return (abs(ev["car3"]) < abs(CAR3_MAX) and cond["E4 prix"]
            and cond["E5 liquidite"] and cond["E6 titre sous sa SMA200"])


# --------------------------------------------------------------- moteur
def simule_court(d, i_ann, ticker, prochaine=None,
                 emprunt_an: float = EMPRUNT_AN,
                 col: dict | None = None) -> TradeCourt | None:
    """Vente a l'ouverture de J+3, rachat a la premiere condition atteinte.

    S2 (stop) et S4 (these morte) se LISENT a la cloture et s'EXECUTENT a
    l'ouverture de la seance suivante — le texte : « Le stop est sur
    cloture […] Le stop sort alors au cours reel d'ouverture, pas au
    niveau souhaite. » La meme separation qu'a l'entree (condition a la
    cloture de J+2, vente a l'ouverture de J+3). Un ecart d'ouverture est
    donc compte en entier. La premiere cloture surveillee est celle du
    jour de la vente : « la premiere atteinte rachete ».

    S1 (duree) et S3 (veille de l'annonce suivante) sont connues d'avance
    et rachetent a la cloture de leur seance ; ce jour-la, elles passent
    avant un stop qui ne s'executerait que le lendemain.

    `prochaine` est la DATE DU CALENDRIER de l'annonce suivante : on
    rachete a la cloture de la derniere seance strictement avant elle.
    Une position que les donnees laissent ouverte revient avec le motif
    « ouvert » : ce n'est pas un trade, et les appelants l'ecartent.
    """
    if col is None:
        col = colonnes(d)
    close, sma = col["close"], col["sma200"]
    n = len(close)
    i = i_ann + DELAI_EXEC - 1              # cloture de J+2 = signal
    if i + 1 >= n:
        return None
    atr = float(col["atr14"][i])
    if not np.isfinite(atr) or atr <= 0:
        return None
    o = float(col["open"][i + 1])
    if not np.isfinite(o) or o <= 0:
        return None
    # On VEND : les frais reduisent ce qu'on encaisse.
    entree = o * (1 - bt.COUT_PAR_COTE - bt.SLIPPAGE)
    stop = entree + STOP_ATR * atr
    i0 = i + 1

    fin, motif = i0 + MAX_BARRES, "duree"                       # S1
    if prochaine is not None:                                   # S3
        # Une annonce posterieure a la derniere barre a sa veille au-dela
        # des donnees : elle ne peut pas fermer la position ICI.
        q = int(d.index.searchsorted(pd.Timestamp(prochaine)))
        if q < n and q - AVANT_ANNONCE < fin:
            fin, motif = q - AVANT_ANNONCE, "annonce"
    if fin <= i0:
        return None

    ouv = col["open"]

    def rachat(j, m, prix=None):
        """On RACHETE : les frais augmentent ce qu'on debourse."""
        p = float(close[j]) if prix is None else prix
        return TradeCourt(ticker, d.index[i0], d.index[j], entree,
                          p * (1 + bt.COUT_PAR_COTE + bt.SLIPPAGE),
                          stop, atr, j - i0, m, emprunt_an)

    # Les clotures qui precedent la sortie prevue : un declenchement y
    # rachete a l'ouverture suivante, qui existe encore dans les donnees.
    for j in range(i0, min(fin, n - 1)):
        s2 = close[j] >= stop                                   # S2
        s4 = bool(np.isfinite(sma[j]) and close[j] > sma[j])   # S4
        if s2 or s4:
            k = j + 1
            p = float(ouv[k]) if np.isfinite(ouv[k]) and ouv[k] > 0 \
                else float(close[k])
            return rachat(k, "stop" if s2 else "these morte", p)
    if fin > n - 1:
        return rachat(n - 1, "ouvert")
    return rachat(fin, motif)


def _info_vide() -> dict:
    return {"evenements": 0, "candidats": 0, "ouverts": 0,
            "conditions": {k: 0 for k in CONDITIONS},
            "moments": {k: 0 for k in pead.MOMENTS},
            "premiere": None, "derniere": None, "indice_bas": []}


def trades_ticker(d, ticker, bench, liste, debut, fin,
                  emprunt_an: float = EMPRUNT_AN,
                  simule: bool = True) -> tuple:
    """Rend (trades pris, annonces temoins, compte-rendu).

    `simule=False` compte sans rejouer : aucune sortie, aucun rendement.
    C'est ce que la preparation fait sur la periode de validation.
    """
    col = colonnes(d)
    evs = evenements(d, bench, liste)
    # L'annonce suivante se lit dans la liste COMPLETE (point 3).
    dates_triees = sorted({pead._normalise(x)["date"] for x in liste})
    info = _info_vide()
    pris, temoins = [], []
    d0, d1 = pd.Timestamp(debut), pd.Timestamp(fin)
    for ev in evs:
        if not (d0 <= ev["date"] <= d1):
            continue
        info["evenements"] += 1
        pead._borne(info, ev["date"])
        info["moments"][ev["moment"]] += 1
        cond = passe(ev)
        for k, v in cond.items():
            info["conditions"][k] += bool(v)
        proch = pead._suivante(dates_triees, ev["annonce"])
        if all(cond.values()):
            info["candidats"] += 1
            if not simule:
                continue
            t = simule_court(d, ev["i"], ticker, proch, emprunt_an, col=col)
            if t is None:
                continue
            if t.motif == "ouvert":
                info["ouverts"] += 1
                continue
            pris.append(t)
            info["indice_bas"].append(ev["indice_sous_mm200"])
        elif est_temoin(ev, cond):
            temoins.append((ev, proch))
    return pris, temoins, info


# ------------------------------------------------ controle par le hasard
def z_contre_annonces_neutres(trades, temoins_par_tk, series,
                              tirages: int = TIRAGES, graine: int = GRAINE,
                              emprunt_an: float = EMPRUNT_AN) -> dict:
    """Le temoin est une AUTRE annonce, sans surprise notable, vendue a
    decouvert selon les memes regles.

    Sinon on comparerait « vendre apres une mauvaise surprise » a
    « vendre n'importe quand », ce qui melangerait l'effet cherche avec
    le simple fait de vendre a decouvert un marche qui monte.

    Chaque temoin est simule UNE fois, dans l'ordre alphabetique des
    titres, puis on tire parmi ces resultats : l'ancienne version
    resimulait chaque temoin a chaque tirage, et rendait z = 0 sans rien
    dire quand il n'y avait pas de temoins.
    """
    res = {"z": None, "reel": None, "temoin": None, "n_temoins": 0,
           "motif": ""}
    if not trades:
        res["motif"] = "aucun trade"
        return res
    res["reel"] = float(np.mean([t.rendement for t in trades]))
    rendements = []
    for tk in sorted(temoins_par_tk):
        col = colonnes(series[tk])
        for ev, pr in temoins_par_tk[tk]:
            t = simule_court(series[tk], ev["i"], tk, pr, emprunt_an, col=col)
            if t is not None and t.motif != "ouvert":
                rendements.append(t.rendement)
    r = np.array(rendements, dtype=float)
    res["n_temoins"] = len(r)
    if len(r) < TEMOINS_MIN:
        res["motif"] = (f"moins de {TEMOINS_MIN} annonces témoins simulables "
                        f"({len(r)})")
        return res
    rng = np.random.default_rng(graine)
    moyennes = r[rng.integers(0, len(r), size=(tirages, len(trades)))].mean(axis=1)
    mu, sd = float(moyennes.mean()), float(moyennes.std(ddof=1))
    res["temoin"] = mu
    res["z"] = (res["reel"] - mu) / sd if sd > 0 else 0.0
    return res


# ---------------------------------------------------------------- mesures
def _pf(rs):
    g = sum(x for x in rs if x > 0)
    p = -sum(x for x in rs if x < 0)
    return (g / p) if p > 0 else (float("inf") if g > 0 else 0.0)


def mesures(trades, series: dict | None = None) -> dict:
    rs = [t.R for t in trades]
    pt = bt.portefeuille(trades, risque=RISQUE, max_pos=MAX_POS,
                         capital=CAPITAL, series=series, max_poids=MAX_POIDS)
    k = sum(1 for x in rs if x > 0)
    motifs: dict = {}
    for t in trades:
        motifs[t.motif] = motifs.get(t.motif, 0) + 1
    return {"n": len(trades), "pf": _pf(rs),
            "ev": (sum(rs) / len(rs)) if rs else 0.0,
            "rendement": (float(np.mean([t.rendement for t in trades]))
                          if trades else 0.0),
            "gagnants": k, "wilson": pead._wilson(k, len(rs)),
            "duree": float(np.mean([t.barres for t in trades])) if trades else 0.0,
            "motifs": motifs,
            "emprunt": (float(np.mean([t.cout_emprunt / t.entree
                                       for t in trades])) * 100
                        if trades else 0.0),
            "dd": pt["dd"], "dd_source": pt["dd_source"],
            "pris": pt["pris"], "courbe": pt["courbe"], "final": pt["final"],
            "rognees": pt.get("lignes_rognees", 0),
            "poids_max": pt.get("poids_max", 0.0),
            "seances_au_dessus": pt.get("seances_au_dessus", 0),
            "lignes_au_dessus": pt.get("lignes_au_dessus", [])}


@contextlib.contextmanager
def _frais(cout: float, glissement: float):
    """Une ligne de la table des couts, le temps d'un rejeu."""
    sauve = (bt.COUT_PAR_COTE, bt.SLIPPAGE)
    bt.COUT_PAR_COTE, bt.SLIPPAGE = cout, glissement
    try:
        yield
    finally:
        bt.COUT_PAR_COTE, bt.SLIPPAGE = sauve


def rejeu(don: dict, debut: str, fin: str, simule: bool = True,
          emprunt_an: float = EMPRUNT_AN) -> tuple:
    trades, temoins, info = [], {}, _info_vide()
    for tk in sorted(don["series"]):
        d = don["series"][tk]
        pr, tm, inf = trades_ticker(d, tk, don["bench_brut"],
                                    don["dates"][tk], debut, fin,
                                    emprunt_an, simule)
        trades += pr
        if tm:
            temoins[tk] = tm
        for k in ("evenements", "candidats", "ouverts"):
            info[k] += inf[k]
        for k, v in inf["conditions"].items():
            info["conditions"][k] += v
        for k, v in inf["moments"].items():
            info["moments"][k] += v
        pead._borne(info, inf["premiere"])
        pead._borne(info, inf["derniere"])
        info["indice_bas"] += inf["indice_bas"]
    return trades, temoins, info


def _coupe(don: dict, fin: str) -> dict:
    """Les donnees arretees a `fin`. La repetition sur 2010-2023 touche la
    periode de validation par son dernier jour : un trade ouvert en
    decembre 2023 serait rachete sur des cours de 2024. Coupees, ces
    positions restent « ouvertes » et ne comptent pas."""
    f = pd.Timestamp(fin)
    return {**don,
            "series": {tk: d.loc[:f] for tk, d in don["series"].items()},
            "bench_brut": don["bench_brut"].loc[:f]}


def verdict(criteres_ok: bool, survit: bool, dividende_ok: bool,
            economique_ok: bool) -> str:
    """Le verdict, dans l'ordre du texte. Tout ce qui n'est pas un
    critere passe ne peut que rejeter davantage."""
    if not (criteres_ok and survit and dividende_ok):
        return "NO-GO"
    if not economique_ok:
        return "GO technique, NON économique"
    return "GO sous réserve — six mois d'observation papier"


def economique(m: dict, debut: str, fin: str) -> dict:
    """Etape 7 : battre « ne rien faire », net de PFU. Le capital final,
    apres 30 % de PFU sur le gain, doit depasser le capital de depart."""
    c = m.get("courbe")
    if c is not None and len(c) > 1:
        annees = max((c.index[-1] - c.index[0]).days / 365.25, 1 / 365.25)
    else:
        annees = max((pd.Timestamp(fin) - pd.Timestamp(debut)).days / 365.25,
                     1 / 365.25)
    gain = (m.get("final", CAPITAL) - CAPITAL) / CAPITAL
    net = gain * (1 - PFU) if gain > 0 else gain
    tri = (1 + net) ** (1 / annees) - 1 if net > -1 else -1.0
    return {"ok": net > 0, "net": net, "tri_net": tri, "annees": annees}


def evalue(don: dict, debut: str, fin: str, journal=print,
           variante: bool = False) -> dict:
    """Tout le test sur une periode : les cinq criteres a la ligne
    realiste, le controle par le hasard, la table des couts, le
    dividende, la barre economique — et, au passage unique seulement, la
    variante avec filtre d'indice."""
    _, co, gl, emp = COUTS[LIGNE_CRITERES]
    with _frais(co, gl):
        trades, temoins, info = rejeu(don, debut, fin, emprunt_an=emp)
        m = mesures(trades, don["series"])
        journal(f"  {m['n']} trades. Contrôle contre les annonces neutres "
                f"({TIRAGES} tirages)…")
        z = z_contre_annonces_neutres(trades, temoins, don["series"],
                                      emprunt_an=emp)
    var = None
    if variante:
        vt = [t for t, b in zip(trades, info["indice_bas"]) if b]
        rs = [t.R for t in vt]
        var = {"n": len(vt), "pf": _pf(rs),
               "ev": (sum(rs) / len(rs)) if rs else 0.0,
               "rendement": (float(np.mean([t.rendement for t in vt]))
                             if vt else 0.0)}
    couts = []
    for lib, co_, gl_, emp_ in COUTS:
        with _frais(co_, gl_):
            tr = rejeu(don, debut, fin, emprunt_an=emp_)[0]
        rs = [x.R for x in tr]
        couts.append({"ligne": lib, "n": len(tr), "pf": _pf(rs),
                      "ev": (sum(rs) / len(rs)) if rs else 0.0})
    zv = z["z"]
    criteres = [
        ("trades", m["n"] >= 200, f"{m['n']}", "au moins 200"),
        ("profit factor", m["pf"] >= 1.15, pead._fr(m["pf"], ".2f"),
         "au moins 1,15"),
        ("espérance après coûts", m["ev"] > 0,
         pead._fr(m["ev"], "+.3f") + " R", "au-dessus de zéro"),
        ("z contre les annonces neutres", zv is not None and zv >= 2.0,
         "—" if zv is None else pead._fr(zv, "+.2f"), "au moins 2"),
        ("drawdown maximal", m["dd"] < 0.20, pead._pc(m["dd"]), "sous 20 %"),
    ]
    survit = couts[LIGNE_ELIMINATOIRE]["ev"] > 0
    dividende_ok = m["rendement"] >= DIVIDENDE_MIN
    eco = economique(m, debut, fin)
    v = verdict(all(c[1] for c in criteres), survit, dividende_ok, eco["ok"])
    return {"debut": debut, "fin": fin, "info": info, "m": m, "z": z,
            "couts": couts, "criteres": criteres, "survit": survit,
            "dividende_ok": dividende_ok, "economique": eco,
            "variante": var, "verdict": v, "trades": trades}


# ---------------------------------------------------------------- rapport
def rapport(res: dict, don: dict, titre: str, entete: list[str],
            repetition: bool = False) -> list[str]:
    """Le rapport, en phrases. Le rappel du dividende en tete et en pied.

    `repetition=True` : la periode de conception. Son verdict est
    INDICATIF — seul le passage unique juge l'hypothese."""
    from . import registre as rg
    fr, pc = pead._fr, pead._pc
    L = ["", "  " + "=" * 66, f"  {titre}", "  " + "=" * 66]
    L += [f"  {x}" for x in entete]
    L += ["", f"  ⚠ {RAPPEL_DIVIDENDE}"]
    inst, info, m, z = don["instantane"], res["info"], res["m"], res["z"]

    L += ["", "  LES DONNÉES"]
    L += pead._composantes(inst, don)
    L += pead._couverture(res, don)
    L.append(f"    {info['evenements']} publications dans la période, dont :")
    for k, lib in pead.MOMENTS.items():
        L.append(f"      {info['moments'].get(k, 0):>6}  {lib}")
    # L'avertissement generique dit « flatte » : c'est vrai a l'achat, pas
    # ici. Meme condition, phrase propre a la vente (lecture, point 8).
    if dl.avertissement(UNIVERS, res["debut"]):
        L += ["", f"    ⚠ BIAIS DU SURVIVANT : aucune composition de "
                  f"« {UNIVERS} » figée avant {res['debut']}. Le test tourne "
                  f"sur la liste D'AUJOURD'HUI, donc sur les seules sociétés "
                  f"qui ont survécu. {NOTE_SURVIVANT} Lancez `py -m "
                  f"equity_scanner.data --figer {UNIVERS}` chaque trimestre "
                  f"pour cesser de perdre cette information."]

    L += ["", "  LES SIX CONDITIONS D'ENTRÉE, UNE PAR UNE"]
    for k, v in info["conditions"].items():
        L.append(f"    {LIBELLES[k]:<44}{v:>6} sur {info['evenements']}")
    L.append(f"    {'toutes les six':<44}{info['candidats']:>6}")
    if info["ouverts"]:
        L.append(f"    dont {info['ouverts']} encore ouvertes à la fin des "
                 f"données : non comptées (ce ne sont pas des trades).")

    L += ["", "  LE RÉSULTAT (vente à l'ouverture de J+3, emprunt 2 %/an, "
              "0,15 % par côté)"]
    lo, hi = m["wilson"]
    L.append(f"    {m['n']} trades, durée moyenne {m['duree']:.0f} séances, "
             f"emprunt moyen {fr(m['emprunt'], '.2f')} % du notionnel.")
    if m["n"]:
        L.append(f"    Gagnants : {m['gagnants']} sur {m['n']} — intervalle de "
                 f"Wilson {pc(lo)} à {pc(hi)}.")
        L.append("    Rachats : " + ", ".join(
            f"{MOTIFS.get(k, k)} {v}" for k, v in
            sorted(m["motifs"].items(), key=lambda x: -x[1])) + ".")
    if z["z"] is not None:
        L.append(f"    Rendement moyen par trade : {pc(z['reel'], 2)}. Même "
                 f"calcul sur {z['n_temoins']} annonces SANS surprise notable,")
        L.append(f"    vendues avec les mêmes règles : {pc(z['temoin'], 2)}. "
                 f"Écart en nombre d'écarts-types : z = {fr(z['z'], '+.2f')}.")
    else:
        L.append(f"    Pas de contrôle par le hasard : {z['motif']}.")

    L += ["", "  LES CINQ CRITÈRES — tous obligatoires"]
    for nom, okc, val, seuil in res["criteres"]:
        L.append(f"    {'PASSE ' if okc else 'ÉCHOUE'}  {nom:<32}{val:>12}"
                 f"   ({seuil})")

    L += ["", "  LE DIVIDENDE DÛ AU PRÊTEUR — étape 3"]
    L.append(f"    {'PASSE ' if res['dividende_ok'] else 'ÉCHOUE'}  "
             f"{'rendement moyen par trade':<32}{pc(m['rendement'], 2):>12}"
             f"   (au moins {fr(DIVIDENDE_MIN * 100, '.1f')} point)")
    L.append("    Le dividende non modélisé coûte environ 0,4 point par trade "
             "sur 45 séances : en dessous,")
    L.append("    « l'avantage n'existe pas ».")

    L += ["", "  LE POIDS PAR LIGNE — mesuré à chaque séance, jamais corrigé"]
    L.append(f"    Plafond {pc(MAX_POIDS, 0)} du sleeve ; lignes réduites à "
             f"l'entrée : {m['rognees']} ; poids le plus élevé atteint : "
             f"{pc(m['poids_max'])}.")
    if m["seances_au_dessus"]:
        L.append(f"    {m['seances_au_dessus']} séances au-dessus du plafond. "
                 f"La spécification ne dit pas quel ordre passer : mesuré, "
                 f"pas corrigé.")

    L += ["", "  SENSIBILITÉ AUX COÛTS — la dernière ligne décide"]
    L.append(f"    {'hypothèse':<52}{'trades':>7}{'PF':>7}{'espérance':>12}")
    for c in res["couts"]:
        L.append(f"    {c['ligne']:<52}{c['n']:>7}{fr(c['pf'], '>7.2f')}"
                 f"{fr(c['ev'], '>+10.3f')} R")
    L.append("    Espérance à la dernière ligne : "
             + ("positive — l'avantage survit à un titre difficile à "
                "emprunter." if res["survit"] else
                "nulle ou négative — l'hypothèse ne tiendrait que sur des "
                "titres faciles à emprunter."))

    if res.get("variante") is not None:
        vr = res["variante"]
        L += ["", "  LA VARIANTE AVEC FILTRE D'INDICE — robustesse, une seule "
                  "fois, hors verdict"]
        L.append(f"    Les mêmes trades, gardés seulement quand SPY était sous "
                 f"sa MM200 à J+2 : {vr['n']} trades,")
        L.append(f"    profit factor {fr(vr['pf'], '.2f')}, espérance "
                 f"{fr(vr['ev'], '+.3f')} R, rendement moyen "
                 f"{pc(vr['rendement'], 2)}.")
        L.append("    Le verdict se prononce sur les règles gelées, pas sur "
                 "cette variante.")

    eco = res["economique"]
    L += ["", "  LA BARRE ÉCONOMIQUE — battre « ne rien faire », net de PFU "
              "(étape 7)"]
    L.append(f"    Rendement du sleeve net de {pc(PFU, 0)} de PFU : "
             f"{pc(eco['net'], 1)} sur {fr(eco['annees'], '.1f')} ans, soit "
             f"{pc(eco['tri_net'], 2)} par an. "
             + ("Au-dessus de zéro." if eco["ok"] else "Pas au-dessus de zéro."))

    L += ["", "  " + "=" * 66]
    v = res["verdict"]
    if repetition:
        L.append(f"  {v.upper()} SUR LA RÉPÉTITION — verdict indicatif. Seul le "
                 f"passage unique juge l'hypothèse.")
        L.append("  La période de conception sert à vérifier le code : ce "
                 "verdict ne condamne ni ne valide rien.")
        if v == "NO-GO":
            L.append("  Lancer le passage unique malgré lui demandera de "
                     f"taper {rg.PHRASE_FORCEE}.")
    elif v == "NO-GO":
        L.append("  NO-GO. L'hypothèse est morte : elle ne se retouche pas, ne se "
                 "re-teste pas avec des")
        L.append("  seuils ajustés, et ne revient pas sous un autre nom.")
        if m["n"] < 200 and (z["z"] or 0) > 0:
            L.append("  Seule exception prévue : moins de 200 trades avec un z "
                     "positif. On peut alors")
            L.append("  élargir l'univers de titres, SANS toucher à une règle.")
    elif v.startswith("GO technique"):
        L.append("  GO TECHNIQUE, NON ÉCONOMIQUE. Les critères passent, mais le "
                 "sleeve ne bat pas")
        L.append("  « ne rien faire » net de PFU. Il ne se déploie pas.")
    else:
        L.append("  GO SOUS RÉSERVE. Les cinq critères passent, l'avantage "
                 "survit à la dernière ligne")
        L.append("  des coûts, dépasse 0,4 point par trade et bat « ne rien "
                 "faire » net de PFU.")
        L.append("  Étape 8 : SIX MOIS D'OBSERVATION PAPIER avant tout ordre "
                 "réel. Aucune exception :")
        L.append("  la perte d'une vente à découvert n'est pas bornée.")
    L.append(f"  {RAPPEL_DIVIDENDE}")
    L += ["  " + "=" * 66, ""]
    return L


def _sha_fichier(f: Path) -> str:
    try:
        return hashlib.sha256(f.read_bytes()).hexdigest()
    except OSError:
        return ""


def empreintes() -> dict:
    """Tout ce qui identifie le test : le texte, sa lecture, l'amendement,
    les constantes, et le code qui a tourne."""
    from . import audit as ad
    return {"specification": _sha_fichier(SPECIFICATION),
            "lecture": _sha_fichier(LECTURE),
            "amendement": _sha_fichier(AMENDEMENT),
            "constantes": ad.empreinte_short(),
            "moteur": _sha_fichier(Path(__file__))}


def _entete(periode: str, emp: dict, inst: dict) -> list[str]:
    return [f"Période : {periode}",
            f"Date : {dt.datetime.now():%d/%m/%Y %H:%M}",
            f"Spécification : {SPECIFICATION.name}  {emp['specification'][:16]}…",
            f"Lecture : {LECTURE.name}  {emp['lecture'][:16]}…",
            f"Amendement : {AMENDEMENT.name}  {emp['amendement'][:16]}…",
            f"Constantes gelées : {emp['constantes'][:16]}…",
            f"Code du moteur : short.py  {emp['moteur'][:16]}…",
            f"Dates d'annonces relevées le {inst['collecte'][:10]}."]


# ------------------------------------------------------------ deux temps
def periode_validation() -> str:
    return f"{OOS_DEBUT[:4]}-{OOS_FIN[:4]}"


def charge_donnees(inst: dict, journal=print) -> dict:
    """Cours et controle qualite, depuis le debut de SA periode de
    conception, prechauffage compris — le moteur n'en chargeait que 6 ans."""
    return pead.charge_donnees(inst, journal, debut=IN_DEBUT)


def prepare(journal=print, instantane: Path | None = None,
            tickers: list[str] | None = None) -> dict:
    """Tout ce qui precede le passage unique, repetable a volonte.

    Releve et fige les dates, charge les cours, compte ce qu'il y a a
    compter sur 2024-2026 — sans jamais y calculer un rendement — et fait
    une REPETITION GENERALE sur 2010-2023, donnees coupees au 31/12/2023.
    """
    journal("\n  STRATÉGIE 3 — DÉRIVE POST-ANNONCE NÉGATIVE, VENTE À DÉCOUVERT : "
            "PRÉPARATION")
    journal("  Rien de ce qui suit ne regarde un rendement de la période de "
            "validation.")
    journal(f"  {RAPPEL_DIVIDENDE}\n")
    comps = None
    if tickers is None:
        journal("  Univers US large, composante par composante :")
        try:
            tickers, comps = dl.univers_detaille(UNIVERS, journal=journal)
        except dl.UniversIndisponible as exc:
            journal(f"\n  LA PRÉPARATION S'ARRÊTE, rien n'est relevé. {exc}\n")
            return {}
        journal(f"  {len(tickers)} titres après dédoublonnage.")
    inst = pead.collecte_annonces(
        tickers, journal, instantane or (DOSSIER / "annonces.json"),
        composantes=dl.resume_composantes(comps) if comps else None)
    n_dates = sum(len(v) for v in inst["annonces"].values())
    journal(f"  {len(inst['annonces'])} titres avec des dates, "
            f"{len(inst['sans_dates'])} sans ; {n_dates} publications.")
    par_an: dict = {}
    for v in inst["annonces"].values():
        for x in v:
            par_an[x[:4]] = par_an.get(x[:4], 0) + 1
    journal("  Publications par année : " + ", ".join(
        f"{a} : {par_an[a]}" for a in sorted(par_an)))
    h = pead.part_heures(inst)
    if h is not None:
        journal(f"  Heure de publication connue pour {h * 100:.0f} % d'entre "
                f"elles.")
    if not inst["annonces"]:
        journal("\n  Aucune date d'annonce. Vérifiez la connexion, puis :"
                "\n    py -m pip install --upgrade yfinance lxml beautifulsoup4\n")
        return {}
    don = charge_donnees(inst, journal)
    journal(f"  {len(don['series'])} titres exploitables, "
            f"{len(don['ecartes'])} écartés.")
    motifs: dict = {}
    for mo in don["ecartes"].values():
        cle = mo.split(" (")[0].split(" :")[0]
        motifs[cle] = motifs.get(cle, 0) + 1
    for k, v in sorted(motifs.items(), key=lambda x: -x[1]):
        journal(f"      {v:>5}  {k}")
    if not don["series"]:
        return {}

    # Combien de trades le passage aura, AVANT d'en voir un seul resultat.
    _, _, info = rejeu(don, OOS_DEBUT, OOS_FIN, simule=False)
    journal(f"\n  PÉRIODE DE VALIDATION {periode_validation()} — des comptes, "
            f"aucun rendement")
    journal(f"    {info['evenements']} publications, dont "
            f"{info['moments']['apres_cloture']} après la clôture et "
            f"{info['moments']['inconnue']} d'heure inconnue.")
    journal(f"    Au plus {info['candidats']} trades (les six conditions) ; les "
            f"positions encore ouvertes à la fin des données en seront retirées.")
    if info["candidats"] < 200:
        journal("    ⚠ Moins de 200 : le critère 1 échouera. La spécification "
                "prévoit d'élargir l'univers, sans toucher aux règles.")

    emp = empreintes()
    journal("\n  RÉPÉTITION GÉNÉRALE sur la période de conception "
            f"({IN_DEBUT[:4]}-{IN_FIN[:4]}, regards illimités, données "
            f"coupées au {IN_FIN})")
    coupe = _coupe(don, IN_FIN)
    res = evalue(coupe, IN_DEBUT, IN_FIN, journal)
    lignes = rapport(res, coupe,
                     "RÉPÉTITION — PÉRIODE DE CONCEPTION, RIEN N'Y EST JUGÉ",
                     _entete(f"{IN_DEBUT} → {IN_FIN} (données disponibles "
                             f"seulement)", emp, inst), repetition=True)
    for l in lignes:
        journal(l)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    (DOSSIER / f"repetition-{dt.date.today()}.txt").write_text(
        "\n".join(lignes), encoding="utf-8")
    don["repetition"] = {
        "verdict": res["verdict"],
        "echecs": [c[0] for c in res["criteres"] if not c[1]]
        + ([] if res["survit"] else ["espérance à la dernière ligne des coûts"])
        + ([] if res["dividende_ok"] else ["0,4 point par trade"])}
    return don


def incomplet(don: dict) -> list[str]:
    """Les raisons de donnees de NE PAS lancer le passage. Vide : on peut."""
    inst = don["instantane"]
    n = len(inst["tickers"])
    out = []
    if n < UNIVERS_MIN:
        out.append(f"l'univers ne compte que {n} titres (au moins "
                   f"{UNIVERS_MIN} attendus)")
    if n and len(inst["annonces"]) / n < PART_DATES_MIN:
        out.append(f"Yahoo n'a rendu les dates que de {len(inst['annonces'])} "
                   f"titres sur {n} : relancez la préparation plus tard")
    if n and len(don["series"]) / n < PART_EXPLOITABLES_MIN:
        out.append(f"seulement {len(don['series'])} titres exploitables sur {n}")
    h = pead.part_heures(inst)
    if h is not None and h < PART_HEURES_MIN:
        out.append(f"l'heure n'est connue que pour {h * 100:.0f} % des "
                   f"publications : mettez yfinance à jour, puis relancez la "
                   f"préparation")
    return out


def _fichier_validation(fichier: Path | None) -> Path:
    return fichier or (DOSSIER / "documents-valides.json")


def documents_valides(fichier: Path | None = None) -> dict | None:
    """La validation du proprietaire, si elle porte sur les textes
    ACTUELS de la note de lecture et de l'amendement. Un texte modifie
    apres la validation la rend caduque."""
    try:
        v = json.loads(_fichier_validation(fichier).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    emp = empreintes()
    if (isinstance(v, dict) and v.get("date") and emp["lecture"]
            and emp["amendement"] and v.get("lecture") == emp["lecture"]
            and v.get("amendement") == emp["amendement"]):
        return v
    return None


def valide_documents(saisie=input, journal=print,
                     fichier: Path | None = None) -> bool:
    """La validation, par le proprietaire, de la note de lecture et de
    l'amendement n°1. Deux reponses exactes : la declaration de n'avoir
    jamais lance l'ancienne voie directe, puis JE VALIDE."""
    emp = empreintes()

    def demande(q):
        try:
            return (saisie(q) or "").strip()
        except EOFError:
            return ""
    journal("\n  HYPOTHÈSE N°3 — DEUX DOCUMENTS À VALIDER AVANT LE PASSAGE UNIQUE")
    journal(f"    {LECTURE.name:<40}{emp['lecture'][:16]}…")
    journal(f"    {AMENDEMENT.name:<40}{emp['amendement'][:16]}…")
    journal("  Ils sont à côté du programme : lisez-les en entier avant de "
            "répondre.")
    journal("  L'amendement garde 2024-2026 comme période de validation : "
            "l'hypothèse n°2 l'a regardée")
    journal("  le 29/09/2026, mais la n°3 avait gelé ses règles le "
            "18/09/2026, et le protocole consomme")
    journal("  une période PAR hypothèse. Il ne vaut que si la n°3 ne l'a "
            "jamais regardée elle-même.")
    traces = [f for f in TRACES if f.exists()]
    if traces:
        journal(f"\n  Une trace de l'ancienne voie directe existe : "
                f"{traces[0]}. Rien n'est validé :")
        journal("  si elle a tourné, la période est brûlée pour cette "
                "hypothèse (amendement, points 4 et 6).\n")
        return False
    r1 = demande("\n  Avez-vous déjà lancé l'option S de Carruos.bat, ou "
                 "« py -m equity_scanner.short »,\n  avant le 30 septembre "
                 "2026 ? Tapez OUI ou NON : ")
    if r1 != "NON":
        if r1 == "OUI":
            journal("\n  Alors l'hypothèse n°3 a déjà regardé 2024-2026 : la "
                    "période est brûlée POUR ELLE.")
            journal("  L'amendement ne s'applique pas. La seule voie honnête "
                    "est une période vierge —")
            journal("  une spécification v1.1 et une nouvelle empreinte "
                    "(amendement, point 6). Rien n'est validé.\n")
        else:
            journal("  Réponse non reconnue (OUI ou NON). Rien n'est validé.\n")
        return False
    r2 = demande("  Tapez JE VALIDE pour valider les deux documents, ou "
                 "Entrée pour vous arrêter : ")
    if r2 != "JE VALIDE":
        journal("  Rien n'est validé.\n")
        return False
    entree = {"date": dt.datetime.now().replace(microsecond=0).isoformat(),
              "lecture": emp["lecture"], "amendement": emp["amendement"],
              "declaration": "l'ancienne voie directe n'a jamais été lancée "
                             "avant le 30/09/2026"}
    f = _fichier_validation(fichier)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(entree, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, f)
    journal(f"\n  Validé le {entree['date'][:10]}, pour ces deux textes "
            f"exactement. S'ils changent, la validation")
    journal(f"  ne vaudra plus. Gardée dans {f}.\n")
    return True


def bloquants(don: dict, etat: Path | None = None,
              validation: Path | None = None,
              controle: bool = True) -> list[str]:
    """Tout ce qui empeche le passage unique de partir. Vide : il peut."""
    from . import registre as rg
    periode = periode_validation()
    out = []
    ab = rg.abandonnee(HYPOTHESE, etat)
    if ab:
        out.append(f"l'hypothèse a été ABANDONNÉE le {ab['fin'][:10]}, avant "
                   f"son passage : {ab.get('motif', '')}. La relancer serait "
                   f"une résurrection choisie après coup")
    for f in TRACES:
        if f.exists():
            out.append(f"une trace de l'ancienne voie directe existe ({f}) : "
                       f"elle calculait sur {periode} sans rien inscrire. Si "
                       f"elle a tourné, la période est brûlée pour cette "
                       f"hypothèse (amendement, point 4). Si ce fichier vient "
                       f"d'ailleurs, déplacez-le et relancez")
    autres = rg.autres_regards(HYPOTHESE, periode, etat)
    if documents_valides(validation) is None:
        if autres:
            noms = ", ".join(sorted({f"« {e['hypothese']} » le "
                                     f"{e['fin'][:10]}" for e in autres}))
            out.append(f"la période {periode} a déjà été regardée par "
                       f"l'hypothèse {noms}. Le passage ne part pas sans "
                       f"l'amendement n°1 validé : py -m equity_scanner.short "
                       f"--valider-documents")
        else:
            out.append("la note de lecture et l'amendement n°1 ne sont pas "
                       "validés : py -m equity_scanner.short "
                       "--valider-documents")
    if controle:
        out += incomplet(don)
    return out


def valide(don: dict, journal=print, second_regard: str = "",
           etat: Path | None = None, md: Path | None = None,
           dossier: Path | None = None, controle: bool = True,
           validation: Path | None = None) -> dict:
    """LE passage unique sur la periode de validation.

    Inscrit au registre AVANT de calculer ; ferme l'inscription AVANT
    d'afficher. Refuse un second passage, sauf demande explicite ecrite
    au registre comme second regard. Refuse de partir tant qu'un
    `bloquants()` reste."""
    from . import registre as rg
    periode = periode_validation()
    deja = rg.deja_regardee(HYPOTHESE, periode, etat)
    if deja and not second_regard:
        journal(f"\n  La période {periode} a déjà été regardée pour cette "
                f"hypothèse, le {deja['fin'][:10]} : {deja['resultat']}"
                + (f", z = {pead._fr(deja['z'], '+.2f')}"
                   if deja.get("z") is not None else "") + ".")
        rap = (deja.get("details") or {}).get("rapport")
        if rap:
            journal(f"  Le rapport : {rap}")
        journal("  La période de validation est un consommable : un second "
                "passage serait contaminé.")
        return {"refuse": True, "precedent": deja}
    b = bloquants(don, etat, validation, controle)
    if b:
        journal("\n  Le passage unique NE PART PAS. Rien n'a été regardé, "
                "rien n'est inscrit :")
        for m_ in b:
            journal(f"    - {m_}")
        journal("")
        return {"refuse": True, "bloquants": b}
    emp = empreintes()
    inst = don["instantane"]
    sha_inst = hashlib.sha256(json.dumps(inst, sort_keys=True).encode()).hexdigest()
    autres = rg.autres_regards(HYPOTHESE, periode, etat)
    val = documents_valides(validation) or {}
    ident = rg.ouvre(HYPOTHESE, periode, "US large", emp["constantes"],
                     details={**emp, "instantane": sha_inst,
                              "collecte": inst["collecte"],
                              "titres": len(don["series"]),
                              "periode_partagee": sorted(
                                  {e["hypothese"] for e in autres}),
                              "documents_valides": val.get("date")},
                     motif=second_regard, etat=etat, md=md)
    journal(f"\n  Inscrit au registre avant le calcul. Passage sur "
            f"{OOS_DEBUT} → {OOS_FIN}…")
    res = evalue(don, OOS_DEBUT, OOS_FIN, journal, variante=True)
    lignes = rapport(res, don, "STRATÉGIE 3 — LE PASSAGE UNIQUE",
                     _entete(f"{OOS_DEBUT} → {OOS_FIN}", emp, inst))
    rep = dossier or DOSSIER
    rep.mkdir(parents=True, exist_ok=True)
    stamp = f"{dt.datetime.now():%Y-%m-%d-%H%M}"
    f_rap = rep / f"validation-{stamp}.txt"
    f_csv = rep / f"validation-{stamp}-trades.csv"
    rg.ferme(ident, res["verdict"], res["z"]["z"],
             details={"rapport": str(f_rap), "trades": res["m"]["n"],
                      "pf": round(res["m"]["pf"], 3),
                      "esperance_R": round(res["m"]["ev"], 4),
                      "rendement_moyen": round(res["m"]["rendement"], 5),
                      "drawdown": round(res["m"]["dd"], 4),
                      "variante_indice": (res["variante"] or {}).get("n")},
             etat=etat, md=md)
    f_rap.write_text("\n".join(lignes), encoding="utf-8")
    if res["trades"]:
        pd.DataFrame([{"ticker": t.ticker, "vente": t.entree_d.date(),
                       "rachat": t.sortie_d.date(),
                       "prix_vente": round(t.entree, 2),
                       "prix_rachat": round(t.sortie, 2),
                       "stop": round(t.stop0, 2), "R": round(t.R, 3),
                       "rendement": round(t.rendement, 4),
                       "emprunt": round(t.cout_emprunt, 4),
                       "seances": t.barres,
                       "motif": MOTIFS.get(t.motif, t.motif)}
                      for t in res["trades"]]).to_csv(f_csv, index=False)
    for l in lignes:
        journal(l)
    journal(f"  Rapport : {f_rap}")
    if res["trades"]:
        journal(f"  Détail des trades : {f_csv}")
    journal(f"  Registre : {rg.MD if md is None else md}\n")
    return {**res, "lignes": lignes}


# ------------------------------------------------------------ l'abandon
PHRASE_ABANDON = "ABANDONNER"


def _criteres_du_rapport(texte: str) -> list[str]:
    """Les lignes des cinq criteres, recopiees du rapport tel qu'il a ete
    ecrit : l'abandon cite ce qui l'a motive, sans rien recalculer."""
    out, dedans = [], False
    for l in texte.splitlines():
        if "LES CINQ CRITÈRES" in l:
            dedans = True
            continue
        if dedans:
            if not l.strip():
                break
            out.append(l.strip())
    return out


def abandon(saisie=input, journal=print, etat: Path | None = None,
            md: Path | None = None, dossier: Path | None = None) -> dict:
    """Inscrit au registre l'abandon de l'hypothese AVANT son passage
    unique, sur la foi de la derniere repetition generale.

    Rien de 2024-2026 n'est regarde. Refuse si le passage a deja eu lieu
    (son resultat est la, il ne s'efface pas), ou si aucune repetition
    n'a ete ecrite (un abandon cite ce qui l'a motive)."""
    from . import audit as ad
    from . import registre as rg
    periode = periode_validation()
    deja = rg.deja_regardee(HYPOTHESE, periode, etat)
    if deja:
        journal(f"\n  Le passage unique a déjà eu lieu le {deja['fin'][:10]} : "
                f"{deja['resultat']}. Il est au registre ; il ne s'abandonne "
                f"pas après coup.\n")
        return {"ok": False, "motif": "passage deja fait"}
    ab = rg.abandonnee(HYPOTHESE, etat)
    if ab:
        journal(f"\n  Déjà inscrite comme abandonnée le {ab['fin'][:10]} : "
                f"{ab.get('motif', '')}.\n")
        return {"ok": True, "entree": ab, "deja": True}
    rep = dossier or DOSSIER
    rapports = sorted(rep.glob("repetition-*.txt")) if rep.exists() else []
    if not rapports:
        journal("\n  Aucune répétition générale n'a été écrite : un abandon "
                "cite ce qui l'a motivé.\n  Lancez d'abord la préparation "
                "(Tester-strategie-3.bat, choix 3).\n")
        return {"ok": False, "motif": "aucune repetition"}
    f = rapports[-1]
    texte = f.read_text(encoding="utf-8")
    verdict = ("NO-GO" if "NO-GO SUR LA RÉPÉTITION" in texte else
               "GO" if "SUR LA RÉPÉTITION" in texte else "inconnu")
    criteres = _criteres_du_rapport(texte)
    journal(f"\n  HYPOTHÈSE N°3 — ABANDON AVANT LE PASSAGE UNIQUE")
    journal(f"  Répétition générale : {f.name} — verdict {verdict}.")
    for l in criteres:
        journal(f"    {l}")
    journal(f"  Le passage unique sur {periode} ne sera jamais lancé : "
            f"l'hypothèse est fermée, et c'est")
    journal("  inscrit au registre comme un échec. Rien de la période de "
            "validation n'est regardé.")
    try:
        r = (saisie(f"  Tapez {PHRASE_ABANDON} pour l'inscrire, ou Entrée "
                    f"pour vous arrêter : ") or "").strip()
    except EOFError:
        r = ""
    if r != PHRASE_ABANDON:
        journal("  Rien n'est inscrit.\n")
        return {"ok": False, "motif": "non confirme"}
    motif = (f"répétition 2010-2023 {verdict}, passage unique {periode} "
             f"non lancé")
    e = rg.abandonne(
        HYPOTHESE, "US large", ad.empreinte_short(), motif,
        details={"repetition": str(f),
                 "repetition_sha256": _sha_fichier(f),
                 "verdict_repetition": verdict, "criteres": criteres,
                 **empreintes()},
        etat=etat, md=md)
    journal(f"\n  Inscrit au registre le {e['fin'][:10]} : {e['resultat']}.")
    journal(f"  Registre : {rg.MD if md is None else md}\n")
    return {"ok": True, "entree": e}


def main() -> None:
    from . import registre as rg
    a = argparse.ArgumentParser(
        description="Stratégie 3 : préparation, puis le passage unique")
    a.add_argument("--preparer", action="store_true",
                   help="la préparation seule (répétable)")
    a.add_argument("--valider", action="store_true",
                   help="le passage unique, sans question (après préparation)")
    a.add_argument("--valider-documents", action="store_true",
                   help="valider la note de lecture et l'amendement n°1")
    a.add_argument("--abandonner", action="store_true",
                   help="inscrire l'abandon avant le passage unique, sur la "
                        "foi de la dernière répétition")
    a.add_argument("--second-regard", default="", metavar="MOTIF",
                   help="refaire un passage déjà fait ; le motif est écrit "
                        "au registre comme SECOND REGARD")
    # Garde pour l'ancien menu de Carruos.bat : seul l'univers de la
    # lecture est accepte, et --csv ne sert plus (le detail des trades
    # est ecrit a cote du rapport).
    a.add_argument("--univers", default=UNIVERS)
    a.add_argument("--csv", default=None, help=argparse.SUPPRESS)
    o = a.parse_args()
    if o.univers != UNIVERS:
        a.error("la note de lecture fixe l'univers US large (--univers us)")
    if o.valider_documents:
        valide_documents()
        return
    if o.abandonner:
        abandon()
        return
    ab = rg.abandonnee(HYPOTHESE)
    if ab and not o.preparer:
        print(f"\n  L'hypothèse n°3 a été ABANDONNÉE le {ab['fin'][:10]}, "
              f"avant son passage unique :\n  {ab.get('motif', '')}. Elle est "
              f"fermée ; la préparation reste possible pour relire la "
              f"répétition :\n    py -m equity_scanner.short --preparer\n")
        return

    periode = periode_validation()
    deja = rg.deja_regardee(HYPOTHESE, periode)
    if deja and not o.second_regard and not o.preparer:
        valide({}, controle=False)
        print("  La préparation reste possible, pour la répétition générale :"
              "\n    py -m equity_scanner.short --preparer\n")
        return
    don = prepare()
    if not don or o.preparer:
        return
    if bloquants(don):
        valide(don)          # dit pourquoi il ne part pas
        return
    rep_ = don.get("repetition") or {}
    verdict_ = rep_.get("verdict")
    phrase = rg.phrase_de_lancement(verdict_)
    forcee = phrase != rg.PHRASE_SIMPLE
    if forcee:
        echecs = ", ".join(rep_.get("echecs") or []) or "verdict inconnu"
        print(f"  ⚠ LA RÉPÉTITION GÉNÉRALE A ÉCHOUÉ : "
              f"{verdict_ or 'aucun verdict'} sur la période de conception "
              f"({echecs}).")
        print("  Ce verdict est indicatif — seul le passage unique juge — "
              "mais lancer malgré lui")
        print(f"  consomme la période {periode} pour une hypothèse que ses "
              f"propres données de")
        print("  conception n'ont pas soutenue.")
        print(f"  Un simple OUI ne suffit plus : pour le lancer malgré tout, "
              f"tapez {phrase}.")
    if o.valider and forcee:
        print(f"  --valider ne suffit pas après une répétition "
              f"{verdict_ or 'sans verdict'} : lancez sans --valider")
        print(f"  et tapez {phrase}. Rien n'a été regardé.\n")
        return
    if not o.valider:
        if not sys.stdin.isatty():
            print("  Préparation terminée. Pour le passage unique : "
                  + ("py -m equity_scanner.short --valider" if not forcee else
                     f"py -m equity_scanner.short, puis tapez {phrase}"))
            return
        print(f"  La préparation est faite. Le passage unique regarde "
              f"{periode} UNE fois, et le résultat")
        print("  s'inscrit au registre quel qu'il soit.")
        print(f"  {RAPPEL_DIVIDENDE}")
        try:
            rep = input(f"  Tapez {phrase} pour le lancer, ou Entrée pour "
                        "vous arrêter là : ").strip()
        except EOFError:
            rep = ""
        if not rg.lancement_accepte(rep, verdict_):
            print("  Rien n'a été regardé. Relancez quand vous voulez.\n")
            return
    valide(don, second_regard=o.second_regard)


if __name__ == "__main__":
    main()
