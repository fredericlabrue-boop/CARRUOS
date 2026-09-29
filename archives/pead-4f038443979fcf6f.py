"""Derive post-annonce — moteur de test.

Hypothese n°2 du registre. Specification : derive-post-annonce-v1.md,
empreinte SHA256 f37d22bd76d253a4c686edb8fe1debb394490240593cc400a423a6f8fb428dee

AUCUNE valeur de ce fichier ne doit etre modifiee apres le premier test.
Les constantes ci-dessous sont celles du document, recopiees telles
quelles. Si l'une d'elles change, ce n'est plus la meme hypothese : il
faut une nouvelle specification, une nouvelle empreinte et une nouvelle
ligne au registre.

La facon dont ce moteur LIT la specification est ecrite a part, dans
derive-post-annonce-v1-lecture.md — datee et hachee avant tout regard sur
la periode de validation. Chaque ecart corrige y est explique.

    py -m equity_scanner.pead              # preparation, puis le passage unique sur confirmation
    py -m equity_scanner.pead --preparer   # la preparation seule, autant de fois qu'on veut
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import datetime as dt
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest as bt
from . import data as dl
from .indicators import enrich

# --------------------------------------------------------------- regles
CAR3_MIN = 0.050          # E1 : reaction cumulee J-1..J+1
RVOL_ANNONCE = 2.0        # E2 : volume du jour d'annonce / moyenne 20 j
PRIX_MIN = 10.0           # E4
DOLLAR_VOL_MIN = 20e6     # E5
DELAI_EXEC = 3            # signal a la cloture de J+2, achat a l'ouverture de J+3

MAX_BARRES = 45           # S1
STOP_ATR = 2.0            # S2
AVANT_ANNONCE = 1         # S3 : sortie la veille de la publication suivante

RISQUE = 0.01
MAX_POS = 10              # effet de portefeuille, pas de titre
MAX_POIDS = 0.25          # 25 % du sleeve par ligne, etape 2 du document

CACHE = Path(".bruce_cache") / "annonces"

# hors echantillon : un seul passage
OOS_DEBUT, OOS_FIN = "2024-01-01", "2026-12-31"
IN_DEBUT, IN_FIN = "2010-01-01", "2021-12-31"

# ------------------------------------------------ la lecture, pas les regles
# Rien ici n'entre dans l'empreinte des constantes : ce sont des faits de
# marche et des choix de donnees, ecrits dans la note de lecture.
RACINE = Path(__file__).resolve().parent.parent
SPECIFICATION = RACINE / "derive-post-annonce-v1.md"
LECTURE = RACINE / "derive-post-annonce-v1-lecture.md"

HEURE_CLOTURE = 16        # la cloture de New York : une annonce a 16 h ou apres
                          # ne peut etre echangee que la seance suivante
ANNEES_COURS = 8          # couvre la periode de conception (2019-2021) ET la validation
UNIVERS = "us"
HYPOTHESE = "Dérive post-annonce"
TIRAGES, GRAINE = 1000, 7
TEMOINS_MIN = 20

DOSSIER = Path.home() / ".carruos" / "strategie-2"
INSTANTANE = DOSSIER / "annonces.json"

# Les quatre lignes de l'etape 6 : (libelle, execution J+1, cout, glissement).
# La troisieme est celle des cinq criteres ; la quatrieme est eliminatoire.
COUTS = [
    ("clôture de J+2, sans frais (plafond irréaliste)", False, 0.0, 0.0),
    ("ouverture de J+3, sans frais", True, 0.0, 0.0),
    ("ouverture de J+3, 0,15 % par côté", True, 0.0010, 0.0005),
    ("ouverture de J+3, 0,30 % par côté", True, 0.0020, 0.0010),
]
LIGNE_CRITERES = 2
LIGNE_ELIMINATOIRE = 3

MOTIFS = {"stop": "stop touché", "regime": "marché passé sous sa MM200",
          "annonce": "veille de l'annonce suivante",
          "duree": f"{MAX_BARRES} séances écoulées"}

# Les conditions, en clair et avec leur seuil — lu sur les constantes,
# jamais recopie : un libelle qui dirait « 5 % » pendant que le moteur
# teste autre chose serait pire que pas de libelle.
LIBELLES = {
    "E1 surprise": f"E1 surprise : CAR3 ≥ +{CAR3_MIN * 100:.0f} %",
    "E2 volume": f"E2 volume ≥ {RVOL_ANNONCE:g} × l'habitude",
    "E3 pas de retractation": "E3 pas de rétractation le lendemain",
    "E4 prix": f"E4 prix ≥ {PRIX_MIN:g}",
    "E5 liquidite": f"E5 liquidité ≥ {DOLLAR_VOL_MIN / 1e6:g} M par jour",
    "E6 regime": "E6 indice au-dessus de sa MM200",
}

# Le passage unique ne part pas sur des donnees incompletes : un univers
# tronque brulerait la periode de validation pour rien. Ce sont des seuils
# de COMPLETUDE — ils ne regardent aucun rendement.
UNIVERS_MIN = 450         # le S&P 500 seul en compte plus de 500
PART_DATES_MIN = 0.90     # titres dont Yahoo a rendu les dates
PART_EXPLOITABLES_MIN = 0.80
# Sans l'heure, la lecture corrigee retombe sur la lecture litterale — le
# defaut meme que la note de lecture corrige. Une version ancienne de
# yfinance peut ne pas la rendre : on s'arrete plutot que de bruler la
# periode de validation avec.
PART_HEURES_MIN = 0.50

MOMENTS = {"apres_cloture": "après la clôture",
           "avant_ou_pendant": "avant l'ouverture ou pendant la séance",
           "hors_seance": "un jour sans séance",
           "inconnue": "heure inconnue (lecture littérale)"}


# ------------------------------------------------------- dates d'annonces
def _iso_new_york(x) -> str:
    t = pd.Timestamp(x)
    if t.tzinfo is not None:
        t = t.tz_convert("America/New_York").tz_localize(None)
    return t.isoformat()


def _normalise(x) -> dict:
    """Une annonce : {"date": jour du calendrier, "heure": heure de New York}.

    Accepte un dict deja forme, une chaine ISO ou un Timestamp. Minuit
    pile veut dire « heure non fournie » : on ne l'invente pas.
    """
    if isinstance(x, dict):
        return {"date": pd.Timestamp(x["date"]).normalize(),
                "heure": x.get("heure")}
    t = pd.Timestamp(x)
    if t.tzinfo is not None:
        t = t.tz_convert("America/New_York").tz_localize(None)
    heure = None if (t.hour, t.minute) == (0, 0) else int(t.hour)
    return {"date": t.normalize(), "heure": heure}


def annonces(ticker: str, journal=print) -> list[dict]:
    """Les publications du titre, avec leur HEURE.

    L'heure decide de la seance qui reagit : une publication apres la
    cloture ne s'echange que le lendemain. L'ancienne version jetait
    l'heure et prenait la date du calendrier (note de lecture, point 1).

    Un echec n'est pas mis en cache : un refus passager de Yahoo ne doit
    pas priver le titre de ses dates pour la journee.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{ticker.replace('/', '_')}.json"
    try:
        v = json.loads(f.read_text(encoding="utf-8"))
        if v.get("jour") == dt.date.today().isoformat() and "moments" in v:
            return [_normalise(x) for x in v["moments"]]
    except Exception:
        pass
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).get_earnings_dates(limit=40)
        moments = sorted({_iso_new_york(x) for x in df.index}) \
            if df is not None else []
    except Exception as exc:
        journal(f"    {ticker} : dates indisponibles ({type(exc).__name__})")
        return []
    if moments:
        try:
            f.write_text(json.dumps({"jour": dt.date.today().isoformat(),
                                     "moments": moments}), encoding="utf-8")
        except Exception:
            pass
    return [_normalise(x) for x in moments]


def dates_annonces(ticker: str, journal=print) -> list[pd.Timestamp]:
    """Les seules dates du calendrier, sans l'heure. Garde pour
    `short.py`, dont la specification n'a pas encore ete relue."""
    return sorted({a["date"] for a in annonces(ticker, journal)})


def seance_de_reaction(index: pd.Index, date, heure) -> int | None:
    """La premiere seance dont les echanges peuvent refleter l'annonce.

    Apres la cloture : la suivante. Avant 16 h : le jour meme. Jour sans
    seance : la suivante. Heure inconnue : le jour du calendrier, faute
    de mieux — et c'est compte a part dans le rapport.
    """
    p = int(index.searchsorted(pd.Timestamp(date)))
    if p >= len(index):
        return None
    if (index[p] == pd.Timestamp(date) and heure is not None
            and heure >= HEURE_CLOTURE):
        p += 1
    return p if p < len(index) else None


def moment(index: pd.Index, date, heure) -> str:
    p = int(index.searchsorted(pd.Timestamp(date)))
    if p >= len(index) or index[p] != pd.Timestamp(date):
        return "hors_seance"
    if heure is None:
        return "inconnue"
    return "apres_cloture" if heure >= HEURE_CLOTURE else "avant_ou_pendant"


# ------------------------------------------------------------ evenements
def aligne(bo: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    """Indice de reference remis sur le calendrier du titre.

    Sans cela, toute lecture par position (`iloc[j]`) dans `bo` designe
    une date differente de celle du titre.
    """
    if len(bo.index) == len(index) and bool((bo.index == index).all()):
        return bo
    return bo.reindex(index).ffill()


def colonnes(d: pd.DataFrame, bo_aligne: pd.DataFrame) -> dict:
    """Les colonnes du moteur, lues une fois en numpy."""
    return {
        "open": d["open"].to_numpy(dtype=float),
        "close": d["close"].to_numpy(dtype=float),
        "atr14": d["atr14"].to_numpy(dtype=float),
        "regime": (bo_aligne["close"].to_numpy(dtype=float)
                   > bo_aligne["sma200"].to_numpy(dtype=float)),
    }


def evenements(d: pd.DataFrame, bench: pd.DataFrame, liste) -> list[dict]:
    """Pour chaque annonce : la seance de reaction J et les mesures.

    CAR3 = rendement du titre moins celui de l'indice, cumule de J-1 a
    J+1. On ne mesure pas la surprise comptable : on mesure ce que le
    marche en a fait.
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
    out, vues = [], set()
    for a in sorted((_normalise(x) for x in liste), key=lambda a: a["date"]):
        j = seance_de_reaction(idx, a["date"], a["heure"])
        if j is None or j <= 1 or j + DELAI_EXEC >= len(idx) or j in vues:
            continue
        vues.add(j)
        vm = volma[j] if np.isfinite(volma[j]) else 0.0
        out.append({
            "i": j, "date": idx[j], "annonce": a["date"], "heure": a["heure"],
            "moment": moment(idx, a["date"], a["heure"]),
            "car3": float(ab[j - 1:j + 2].sum()),
            "rvol": float(vol[j] / vm) if vm > 0 else 0.0,
            "suite": bool(close[j + 1] > close[j - 1]),
            "prix": float(close[j + 2]),
            "dvol": float(dvol[j + 2]) if np.isfinite(dvol[j + 2]) else 0.0,
        })
    return out


CONDITIONS = ("E1 surprise", "E2 volume", "E3 pas de retractation",
              "E4 prix", "E5 liquidite", "E6 regime")


def passe(ev: dict, marche_ok: bool) -> dict:
    """Les six conditions, une par une. On garde le detail pour pouvoir
    dire exactement ce qui a bloque."""
    return dict(zip(CONDITIONS, (
        ev["car3"] >= CAR3_MIN,
        ev["rvol"] >= RVOL_ANNONCE,
        ev["suite"],
        ev["prix"] >= PRIX_MIN,
        ev["dvol"] >= DOLLAR_VOL_MIN,
        marche_ok,
    )))


# --------------------------------------------------------------- moteur
def simule_pead(d, i_ann, ticker, bo, prochaine=None,
                col: dict | None = None) -> bt.Trade | None:
    """Achat a l'ouverture de J+3, sortie par la premiere condition
    atteinte. Aucun take-profit : couper la derive la ou elle produit
    son rendement serait l'erreur exacte de la v3.3 d'Alfred.

    `prochaine` est la DATE DU CALENDRIER de l'annonce suivante : on sort
    a la cloture de la derniere seance strictement avant elle.

    Une position que les donnees laissent ouverte revient avec le motif
    « ouvert » : ce n'est pas un trade, et les appelants l'ecartent.
    """
    if col is None:
        col = colonnes(d, aligne(bo, d.index))
    close, regime = col["close"], col["regime"]
    n = len(close)
    i = i_ann + DELAI_EXEC - 1                  # cloture de J+2 = signal
    if i >= n:
        return None
    atr = float(col["atr14"][i])
    if not np.isfinite(atr) or atr <= 0:
        return None
    if bt.EXECUTION_J1:
        if i + 1 >= n:
            return None
        px, i0 = float(col["open"][i + 1]), i + 1
    else:
        px, i0 = float(close[i]), i
    if not np.isfinite(px) or px <= 0:
        return None
    entree = px * (1 + bt.COUT_PAR_COTE + bt.SLIPPAGE)
    stop = entree - STOP_ATR * atr

    fin, motif = i0 + MAX_BARRES, "duree"                       # S1
    if prochaine is not None:                                   # S3
        # Une annonce posterieure a la derniere barre a sa veille au-dela
        # des donnees : elle ne peut pas fermer la position ICI. La prendre
        # pour la derniere barre fermerait comme si la regle avait joue.
        q = int(d.index.searchsorted(pd.Timestamp(prochaine)))
        if q < n and q - AVANT_ANNONCE < fin:
            fin, motif = q - AVANT_ANNONCE, "annonce"
    if fin <= i0:
        return None

    def sortie(j, m):
        return bt.Trade(ticker, d.index[i0], d.index[j], entree,
                        float(close[j]) * (1 - bt.COUT_PAR_COTE - bt.SLIPPAGE),
                        stop, atr, j - i0, m)

    for j in range(i0 + 1, min(fin, n - 1) + 1):
        if close[j] <= stop:                                    # S2
            return sortie(j, "stop")
        if not regime[j]:                                       # S4
            return sortie(j, "regime")
    if fin > n - 1:
        return sortie(n - 1, "ouvert")
    return sortie(fin, motif)


def _suivante(dates_triees: list, date) -> pd.Timestamp | None:
    k = bisect.bisect_right(dates_triees, pd.Timestamp(date))
    return dates_triees[k] if k < len(dates_triees) else None


def trades_ticker(d, ticker, bench, bo, liste, debut, fin,
                  simule: bool = True) -> tuple:
    """Rend (trades pris, annonces temoins, compte-rendu).

    `simule=False` compte sans rejouer : aucune sortie, aucun rendement.
    C'est ce que la preparation fait sur la periode de validation.

    Les temoins sont les annonces SANS surprise qui passent E4 et E6 :
    la population du controle par le hasard.

    `bo` est realigne sur le calendrier du titre. C'etait le defaut le plus
    couteux de la premiere version : des qu'un titre n'avait pas
    exactement le meme nombre de barres que SPY, le filtre de regime
    lisait une AUTRE DATE.
    """
    bo = aligne(bo, d.index)
    col = colonnes(d, bo)
    evs = evenements(d, bench, liste)
    dates_triees = sorted({_normalise(x)["date"] for x in liste})
    info = {"evenements": 0, "candidats": 0, "ouverts": 0,
            "conditions": {k: 0 for k in CONDITIONS},
            "moments": {k: 0 for k in MOMENTS}}
    pris, temoins = [], []
    d0, d1 = pd.Timestamp(debut), pd.Timestamp(fin)
    for ev in evs:
        if not (d0 <= ev["date"] <= d1):
            continue
        info["evenements"] += 1
        info["moments"][ev["moment"]] += 1
        marche_ok = bool(col["regime"][ev["i"] + DELAI_EXEC - 1])   # E6 a J+2
        cond = passe(ev, marche_ok)
        for k, v in cond.items():
            info["conditions"][k] += bool(v)
        proch = _suivante(dates_triees, ev["annonce"])
        if all(cond.values()):
            info["candidats"] += 1
            if not simule:
                continue
            t = simule_pead(d, ev["i"], ticker, bo, proch, col=col)
            if t is None:
                continue
            if t.motif == "ouvert":
                info["ouverts"] += 1
                continue
            pris.append(t)
        elif not cond["E1 surprise"] and cond["E4 prix"] and cond["E6 regime"]:
            temoins.append((ev, proch))
    return pris, temoins, info


# ------------------------------------------------ controle par le hasard
def z_contre_annonces_neutres(trades, temoins_par_tk, series, bo,
                              tirages=TIRAGES, graine=GRAINE) -> dict:
    """Le temoin n'est PAS une date au hasard : c'est une AUTRE annonce,
    sans surprise, rejouee avec exactement les memes sorties.

    Sinon on comparerait « acheter apres une surprise » a « acheter
    n'importe quand », ce qui melange l'effet cherche avec le simple fait
    d'acheter apres une publication.

    Chaque temoin est simule UNE fois : son resultat ne depend pas du
    tirage. On tire ensuite parmi ces resultats. La premiere version
    resimulait chaque temoin a chaque tirage — le meme calcul mille fois.
    """
    res = {"z": None, "reel": None, "temoin": None, "n_temoins": 0,
           "motif": ""}
    if not trades:
        res["motif"] = "aucun trade"
        return res
    res["reel"] = float(np.mean([t.rendement for t in trades]))
    rendements = []
    for tk in sorted(temoins_par_tk):
        lst = temoins_par_tk[tk]
        b = aligne(bo, series[tk].index)
        col = colonnes(series[tk], b)
        for ev, pr in lst:
            t = simule_pead(series[tk], ev["i"], tk, b, pr, col=col)
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
    # ddof=1 : meme convention que la Phase 0.
    mu, sd = float(moyennes.mean()), float(moyennes.std(ddof=1))
    res["temoin"] = mu
    res["z"] = (res["reel"] - mu) / sd if sd > 0 else 0.0
    return res


# ---------------------------------------------------------------- mesures
def _pf(rs):
    g = sum(x for x in rs if x > 0)
    p = -sum(x for x in rs if x < 0)
    return (g / p) if p > 0 else (float("inf") if g > 0 else 0.0)


def _wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    c = p + z * z / (2 * n)
    e = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - e) / den, (c + e) / den)


def mesures(trades, series: dict | None = None) -> dict:
    rs = [t.R for t in trades]
    pt = bt.portefeuille(trades, risque=RISQUE, max_pos=MAX_POS,
                         series=series, max_poids=MAX_POIDS)
    k = sum(1 for x in rs if x > 0)
    motifs = {}
    for t in trades:
        motifs[t.motif] = motifs.get(t.motif, 0) + 1
    return {"n": len(trades), "pf": _pf(rs),
            "ev": (sum(rs) / len(rs)) if rs else 0.0,
            "gagnants": k, "wilson": _wilson(k, len(rs)),
            "duree": float(np.mean([t.barres for t in trades])) if trades else 0.0,
            "dd": pt["dd"], "dd_source": pt["dd_source"],
            "pris": pt["pris"], "courbe": pt["courbe"],
            "rognees": pt.get("lignes_rognees", 0),
            "poids_max": pt.get("poids_max", 0.0),
            "motifs": motifs}


@contextlib.contextmanager
def conditions(j1: bool, cout: float, glissement: float):
    """Pose une ligne de la table des couts, et remet tout en place."""
    sauve = (bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE)
    bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE = j1, cout, glissement
    try:
        yield
    finally:
        bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE = sauve


# --------------------------------------------------------------- donnees
def _sha_fichier(f: Path) -> str:
    try:
        return hashlib.sha256(f.read_bytes()).hexdigest()
    except OSError:
        return ""


def empreintes() -> dict:
    """Tout ce qui identifie le test : le texte, sa lecture, les
    constantes, et le code qui a tourne."""
    from . import audit as ad
    return {"specification": _sha_fichier(SPECIFICATION),
            "lecture": _sha_fichier(LECTURE),
            "constantes": ad.empreinte_pead(),
            "moteur": _sha_fichier(Path(__file__))}


def collecte_annonces(tickers: list[str], journal=print,
                      fichier: Path | None = None) -> dict:
    """Releve les dates d'annonces de tout l'univers et les FIGE dans un
    instantane date. Le passage unique lit cet instantane, pas Yahoo le
    jour meme : ce qui a ete regarde reste reconstituable."""
    from concurrent.futures import ThreadPoolExecutor

    from . import cache as ch
    journal(f"  Relevé des dates d'annonces de {len(tickers)} titres…")
    with ThreadPoolExecutor(max_workers=ch.FILS) as pool:
        res = dict(zip(tickers, pool.map(
            lambda tk: annonces(tk, journal=lambda *_: None), tickers)))
    manquants = [tk for tk, v in res.items() if not v]
    if manquants:
        # Yahoo refuse parfois les rafales : une seconde passe, plus lente.
        journal(f"  {len(manquants)} titres sans réponse : seconde passe, "
                f"plus lente…")
        with ThreadPoolExecutor(max_workers=2) as pool:
            for tk, v in zip(manquants, pool.map(
                    lambda tk: annonces(tk, journal=lambda *_: None),
                    manquants)):
                res[tk] = v
    inst = {"collecte": dt.datetime.now().replace(microsecond=0).isoformat(),
            "univers": UNIVERS, "tickers": list(tickers),
            "annonces": {tk: [f"{a['date'].date()}T{a['heure']:02d}:00:00"
                              if a["heure"] is not None
                              else str(a["date"].date())
                              for a in v] for tk, v in res.items() if v},
            "sans_dates": sorted(tk for tk, v in res.items() if not v)}
    f = fichier or INSTANTANE
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(inst, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)
    return inst


def lit_instantane(fichier: Path | None = None) -> dict | None:
    try:
        return json.loads((fichier or INSTANTANE).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def charge_donnees(inst: dict, journal=print) -> dict:
    """Cours et controle qualite, pour les titres de l'instantane."""
    from . import cache as ch
    from . import qualite as ql
    tickers = inst["tickers"]
    journal(f"  Chargement de {ANNEES_COURS} ans de cours pour "
            f"{len(tickers)} titres…")
    bench_brut = ch.charge("SPY", annees=ANNEES_COURS)
    bo = enrich(bench_brut)
    brutes, echecs = ch.charge_lot(tickers, annees=ANNEES_COURS,
                                   journal=lambda *_: None)
    series, dates, ecartes = {}, {}, {}
    for tk, motif in echecs:
        ecartes[tk] = f"cours indisponibles ({motif})"
    # Dans l'ordre alphabetique, pas dans l'ordre d'arrivee des
    # telechargements paralleles : les tirages du temoin en dependent, et
    # un passage inscrit au registre doit se reproduire a l'identique.
    for tk in sorted(brutes):
        brut = brutes[tk]
        rap = ql.controle(brut, bench_brut, ticker=tk, exige_recent=False)
        if not rap.utilisable:
            ecartes[tk] = f"contrôle qualité : {rap.resume()}"
            continue
        liste = inst["annonces"].get(tk) or []
        if not liste:
            ecartes[tk] = "aucune date d'annonce"
            continue
        d = enrich(brut, bench_close=bench_brut["close"])
        if len(d) < 260:
            ecartes[tk] = f"historique trop court ({len(d)} séances)"
            continue
        series[tk], dates[tk] = d, liste
    return {"series": series, "dates": dates, "bench_brut": bench_brut,
            "bo": bo, "ecartes": ecartes, "instantane": inst}


# ------------------------------------------------------------------ rejeu
def rejeu(don: dict, debut: str, fin: str, simule: bool = True) -> tuple:
    trades, temoins = [], {}
    info = {"evenements": 0, "candidats": 0, "ouverts": 0,
            "conditions": {k: 0 for k in CONDITIONS},
            "moments": {k: 0 for k in MOMENTS}}
    for tk, d in don["series"].items():
        pr, tm, inf = trades_ticker(d, tk, don["bench_brut"], don["bo"],
                                    don["dates"][tk], debut, fin, simule)
        trades += pr
        if tm:
            temoins[tk] = tm
        for k in ("evenements", "candidats", "ouverts"):
            info[k] += inf[k]
        for k, v in inf["conditions"].items():
            info["conditions"][k] += v
        for k, v in inf["moments"].items():
            info["moments"][k] += v
    return trades, temoins, info


def evalue(don: dict, debut: str, fin: str, journal=print) -> dict:
    """Tout le test sur une periode : les cinq criteres a la ligne 3 des
    couts, le controle par le hasard, la table des couts, le comparatif."""
    _, j1, co, gl = COUTS[LIGNE_CRITERES]
    with conditions(j1, co, gl):
        trades, temoins, info = rejeu(don, debut, fin)
        m = mesures(trades, don["series"])
        journal(f"  {m['n']} trades. Contrôle contre les annonces neutres "
                f"({TIRAGES} tirages)…")
        z = z_contre_annonces_neutres(trades, temoins, don["series"], don["bo"])
    couts = []
    for lib, j1c, coc, glc in COUTS:
        with conditions(j1c, coc, glc):
            tr = rejeu(don, debut, fin)[0]
        rs = [x.R for x in tr]
        couts.append({"ligne": lib, "n": len(tr), "pf": _pf(rs),
                      "ev": (sum(rs) / len(rs)) if rs else 0.0})
    zv = z["z"]
    criteres = [
        ("trades", m["n"] >= 200, f"{m['n']}", "au moins 200"),
        ("profit factor", m["pf"] >= 1.15, _fr(m["pf"], ".2f"),
         "au moins 1,15"),
        ("espérance après coûts", m["ev"] > 0, _fr(m["ev"], "+.3f") + " R",
         "au-dessus de zéro"),
        ("z contre les annonces neutres", zv is not None and zv >= 2.0,
         "—" if zv is None else _fr(zv, "+.2f"), "au moins 2"),
        ("drawdown maximal", m["dd"] < 0.20, _pc(m["dd"]), "sous 20 %"),
    ]
    survit = couts[LIGNE_ELIMINATOIRE]["ev"] > 0
    technique = all(c[1] for c in criteres) and survit
    comparatif = None
    if technique:
        try:
            from . import cache as ch
            from . import comparatif as cp
            # `don["ref"]` : une reference fournie par les tests, sans reseau.
            ref = don.get("ref")
            if ref is None:
                ref = ch.charge("SMH", annees=ANNEES_COURS)["close"]
            c = m["courbe"]
            ref = ref[(ref.index >= c.index[0]) & (ref.index <= c.index[-1])]
            comparatif = cp.compare(c, ref, "SMH")
        except Exception as exc:
            comparatif = {"ok": False, "raison": f"{type(exc).__name__}: {exc}"}
    if not technique:
        verdict = "NO-GO"
    elif comparatif and comparatif.get("ok") and comparatif.get("verdict") == "GO":
        verdict = "GO"
    else:
        verdict = "GO technique, NON économique"
    return {"debut": debut, "fin": fin, "info": info, "m": m, "z": z,
            "couts": couts, "criteres": criteres, "survit": survit,
            "technique": technique, "comparatif": comparatif,
            "verdict": verdict, "trades": trades}


# ---------------------------------------------------------------- rapport
def _fr(x: float, fmt: str) -> str:
    """Un nombre a la francaise : virgule decimale. Le remplacement ne
    porte QUE sur le nombre, jamais sur la phrase qui l'entoure."""
    return format(x, fmt).replace(".", ",")


def _pc(x, dec=1):
    return _fr(x * 100, f".{dec}f") + " %"


def rapport(res: dict, don: dict, titre: str, entete: list[str]) -> list[str]:
    """Le rapport, en phrases. Chaque critere dit ce qu'il mesure."""
    L = ["", "  " + "=" * 66, f"  {titre}", "  " + "=" * 66]
    L += [f"  {x}" for x in entete]
    inst, info, m, z = don["instantane"], res["info"], res["m"], res["z"]

    L += ["", "  LES DONNÉES"]
    L.append(f"    {len(inst['tickers'])} titres dans l'univers (S&P 500 + "
             f"Nasdaq 100, composition du {inst['collecte'][:10]}), "
             f"{len(don['series'])} exploitables, {len(don['ecartes'])} écartés.")
    L.append(f"    {info['evenements']} publications dans la période, dont :")
    for k, lib in MOMENTS.items():
        L.append(f"      {info['moments'].get(k, 0):>6}  {lib}")
    avert = dl.avertissement(UNIVERS, res["debut"])
    if avert:
        L += ["", "    ⚠ " + avert]

    L += ["", "  LES SIX CONDITIONS D'ENTRÉE, UNE PAR UNE"]
    for k, v in info["conditions"].items():
        L.append(f"    {LIBELLES[k]:<40}{v:>6} sur {info['evenements']}")
    L.append(f"    {'toutes les six':<40}{info['candidats']:>6}")
    if info["ouverts"]:
        L.append(f"    dont {info['ouverts']} encore ouvertes à la fin des "
                 f"données : non comptées (ce ne sont pas des trades).")

    L += ["", "  LE RÉSULTAT (ouverture de J+3, 0,15 % de frais par côté)"]
    lo, hi = m["wilson"]
    L.append(f"    {m['n']} trades, durée moyenne {m['duree']:.0f} séances.")
    if m["n"]:
        L.append(f"    Gagnants : {m['gagnants']} sur {m['n']} — intervalle de "
                 f"Wilson {_pc(lo)} à {_pc(hi)}.")
        L.append("    Sorties : " + ", ".join(
            f"{MOTIFS.get(k, k)} {v}" for k, v in
            sorted(m["motifs"].items(), key=lambda x: -x[1])) + ".")
    if z["z"] is not None:
        L.append(f"    Rendement moyen par trade : {_pc(z['reel'], 2)}. Même "
                 f"calcul sur {z['n_temoins']} annonces SANS surprise, rejouées")
        L.append(f"    avec les mêmes sorties : {_pc(z['temoin'], 2)}. "
                 f"Écart en nombre d'écarts-types : z = {_fr(z['z'], '+.2f')}.")
    else:
        L.append(f"    Pas de contrôle par le hasard : {z['motif']}.")

    L += ["", "  LES CINQ CRITÈRES — tous obligatoires"]
    for nom, okc, val, seuil in res["criteres"]:
        L.append(f"    {'PASSE ' if okc else 'ÉCHOUE'}  {nom:<32}{val:>12}"
                 f"   ({seuil})")

    L += ["", "  SENSIBILITÉ AUX COÛTS — la dernière ligne est éliminatoire"]
    L.append(f"    {'hypothèse':<50}{'trades':>7}{'PF':>7}{'espérance':>12}")
    for c in res["couts"]:
        L.append(f"    {c['ligne']:<50}{c['n']:>7}{_fr(c['pf'], '>7.2f')}"
                 f"{_fr(c['ev'], '>+10.3f')} R")
    L.append(f"    Espérance à 0,30 % par côté : "
             f"{'positive — l’avantage survit' if res['survit'] else 'nulle ou négative — pas d’avantage'}.")

    if res["comparatif"] is not None:
        L += ["", "  LA BARRE ÉCONOMIQUE — battre SMH acheté et conservé, net"]
        cp_ = res["comparatif"]
        if cp_.get("ok"):
            L.append(f"    Rendement net du système {_pc(cp_['systeme']['tri_net'], 2)}"
                     f"/an, SMH {_pc(cp_['reference']['tri_net'], 2)}/an, "
                     f"sur {_fr(cp_['annees'], '.1f')} ans.")
        else:
            L.append(f"    Comparatif impossible : {cp_.get('raison')}.")

    crit = {c[0]: c[1] for c in res["criteres"]}
    if (crit["profit factor"] and crit["espérance après coûts"]
            and not crit["z contre les annonces neutres"]):
        L += ["",
              "  Profit factor et espérance passent, le z non : sur un marché "
              "qui monte, acheter",
              "  après n'importe quelle publication rapporte aussi. Le z "
              "compare aux annonces SANS",
              "  surprise, et c'est lui qui dit si la SURPRISE apporte quelque "
              "chose. Ici, non."]
    L += ["", "  " + "=" * 66]
    v = res["verdict"]
    if v == "NO-GO":
        L.append("  NO-GO. L'hypothèse est morte : elle ne se retouche pas, elle "
                 "ne s'assouplit pas.")
        if m["n"] < 200 and (z["z"] or 0) > 0:
            L.append("  Seule exception prévue par la spécification : moins de "
                     "200 trades avec un z positif.")
            L.append("  On peut alors élargir l'échantillon — plus d'historique "
                     "de dates — SANS toucher à une règle.")
    elif v == "GO":
        L.append("  GO. Les cinq critères passent, l'avantage survit aux coûts "
                 "défavorables, et bat SMH net.")
        L.append("  Déploiement plafonné à 25 % du portefeuille (étape 8).")
    else:
        L.append("  GO TECHNIQUE, NON ÉCONOMIQUE. Les critères passent, mais "
                 "SMH acheté et conservé fait mieux net.")
        L.append("  Il ne se déploie pas (étape 7).")
    L += ["  " + "=" * 66, ""]
    return L


def _entete(periode: str, emp: dict, inst: dict) -> list[str]:
    return [f"Période : {periode}",
            f"Date : {dt.datetime.now():%d/%m/%Y %H:%M}",
            f"Spécification : {SPECIFICATION.name}  {emp['specification'][:16]}…",
            f"Lecture : {LECTURE.name}  {emp['lecture'][:16]}…",
            f"Constantes gelées : {emp['constantes'][:16]}…",
            f"Code du moteur : pead.py  {emp['moteur'][:16]}…",
            f"Dates d'annonces relevées le {inst['collecte'][:10]}."]


# ------------------------------------------------------------ deux temps
def periode_validation() -> str:
    return f"{OOS_DEBUT[:4]}-{OOS_FIN[:4]}"


def prepare(journal=print, instantane: Path | None = None,
            tickers: list[str] | None = None) -> dict:
    """Tout ce qui precede le passage unique, repetable a volonte.

    Releve et fige les dates, charge les cours, compte ce qu'il y a a
    compter — sans jamais calculer un rendement sur 2024-2026 — et fait
    une REPETITION GENERALE sur la periode de conception, ou les regards
    sont illimites. Si quelque chose casse, c'est ici que ca doit casser.
    """
    journal("\n  STRATÉGIE 2 — DÉRIVE POST-ANNONCE : PRÉPARATION")
    journal("  Rien de ce qui suit ne regarde un rendement de la période de "
            "validation.\n")
    if tickers is None:
        tickers = dl.UNIVERS[UNIVERS][1]()
    inst = collecte_annonces(tickers, journal, instantane)
    n_dates = sum(len(v) for v in inst["annonces"].values())
    journal(f"  {len(inst['annonces'])} titres avec des dates, "
            f"{len(inst['sans_dates'])} sans ; {n_dates} publications.")
    par_an: dict = {}
    for v in inst["annonces"].values():
        for x in v:
            par_an[x[:4]] = par_an.get(x[:4], 0) + 1
    journal("  Publications par année : " + ", ".join(
        f"{a} : {par_an[a]}" for a in sorted(par_an)))
    h = part_heures(inst)
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

    # Le compte des candidats sur la periode de validation : combien de
    # trades le passage aura, AVANT d'en voir un seul resultat. C'est ce
    # qui dit a l'avance si le critere 1 (200 trades) est atteignable.
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
                "prévoit d'élargir l'échantillon, sans toucher aux règles.")

    emp = empreintes()
    journal("\n  RÉPÉTITION GÉNÉRALE sur la période de conception "
            f"({IN_DEBUT[:4]}-{IN_FIN[:4]}, regards illimités)")
    res = evalue(don, IN_DEBUT, IN_FIN, journal)
    lignes = rapport(res, don, "RÉPÉTITION — PÉRIODE DE CONCEPTION, RIEN N'Y EST JUGÉ",
                     _entete(f"{IN_DEBUT} → {IN_FIN} (données disponibles "
                             f"seulement)", emp, inst))
    for l in lignes:
        journal(l)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    (DOSSIER / f"repetition-{dt.date.today()}.txt").write_text(
        "\n".join(lignes), encoding="utf-8")
    return don


def incomplet(don: dict) -> list[str]:
    """Les raisons de NE PAS lancer le passage unique. Vide : on peut."""
    inst = don["instantane"]
    n = len(inst["tickers"])
    out = []
    if n < UNIVERS_MIN:
        out.append(f"l'univers ne compte que {n} titres (au moins "
                   f"{UNIVERS_MIN} attendus) : la liste du S&P 500 n'a sans "
                   f"doute pas pu être lue sur Wikipédia")
    if n and len(inst["annonces"]) / n < PART_DATES_MIN:
        out.append(f"Yahoo n'a rendu les dates que de {len(inst['annonces'])} "
                   f"titres sur {n} : relancez la préparation plus tard, les "
                   f"dates déjà obtenues aujourd'hui sont gardées")
    if n and len(don["series"]) / n < PART_EXPLOITABLES_MIN:
        out.append(f"seulement {len(don['series'])} titres exploitables sur {n}")
    h = part_heures(inst)
    if h is not None and h < PART_HEURES_MIN:
        out.append(f"l'heure n'est connue que pour {h * 100:.0f} % des "
                   f"publications : mettez yfinance à jour (menu de "
                   f"Carruos.bat, option 2), puis relancez la préparation")
    return out


def part_heures(inst: dict) -> float | None:
    """La part des publications dont l'heure est connue."""
    tout = [x for v in inst["annonces"].values() for x in v]
    if not tout:
        return None
    return sum(1 for x in tout if "T" in x) / len(tout)


def valide(don: dict, journal=print, second_regard: str = "",
           etat: Path | None = None, md: Path | None = None,
           dossier: Path | None = None, controle: bool = True) -> dict:
    """LE passage unique sur la periode de validation.

    Inscrit au registre AVANT de calculer ; ferme l'inscription AVANT
    d'afficher. Refuse un second passage, sauf demande explicite dont le
    motif est ecrit au registre, en toutes lettres, comme second regard.
    """
    from . import registre as rg
    periode = periode_validation()
    deja = rg.deja_regardee(HYPOTHESE, periode, etat)
    if deja and not second_regard:
        journal(f"\n  La période {periode} a déjà été regardée pour cette "
                f"hypothèse, le {deja['fin'][:10]} : {deja['resultat']}"
                + (f", z = {_fr(deja['z'], '+.2f')}"
                   if deja.get("z") is not None else "") + ".")
        rap = (deja.get("details") or {}).get("rapport")
        if rap:
            journal(f"  Le rapport : {rap}")
        journal("  La période de validation est un consommable : un second "
                "passage serait contaminé.")
        return {"refuse": True, "precedent": deja}
    manques = incomplet(don) if controle else []
    if manques:
        journal("\n  Le passage unique NE PART PAS : les données sont "
                "incomplètes, et une période")
        journal("  de validation brûlée sur un univers tronqué serait perdue "
                "pour de bon.")
        for m_ in manques:
            journal(f"    - {m_}")
        journal("  Rien n'a été regardé, rien n'est inscrit.\n")
        return {"refuse": True, "incomplet": manques}
    emp = empreintes()
    inst = don["instantane"]
    sha_inst = hashlib.sha256(json.dumps(inst, sort_keys=True).encode()).hexdigest()
    ident = rg.ouvre(HYPOTHESE, periode, "US large", emp["constantes"],
                     details={**emp, "instantane": sha_inst,
                              "collecte": inst["collecte"],
                              "titres": len(don["series"])},
                     motif=second_regard, etat=etat, md=md)
    journal(f"\n  Inscrit au registre avant le calcul. Passage sur "
            f"{OOS_DEBUT} → {OOS_FIN}…")
    res = evalue(don, OOS_DEBUT, OOS_FIN, journal)
    lignes = rapport(res, don, "STRATÉGIE 2 — LE PASSAGE UNIQUE",
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
                      "drawdown": round(res["m"]["dd"], 4)},
             etat=etat, md=md)
    f_rap.write_text("\n".join(lignes), encoding="utf-8")
    if res["trades"]:
        pd.DataFrame([{"ticker": t.ticker, "entree": t.entree_d.date(),
                       "sortie": t.sortie_d.date(), "R": round(t.R, 3),
                       "rendement": round(t.rendement, 4), "seances": t.barres,
                       "motif": MOTIFS.get(t.motif, t.motif)}
                      for t in res["trades"]]).to_csv(f_csv, index=False)
    for l in lignes:
        journal(l)
    journal(f"  Rapport : {f_rap}")
    if res["trades"]:
        journal(f"  Détail des trades : {f_csv}")
    journal(f"  Registre : {rg.MD if md is None else md}\n")
    return res


def main() -> None:
    a = argparse.ArgumentParser(
        description="Stratégie 2 : préparation, puis le passage unique")
    a.add_argument("--preparer", action="store_true",
                   help="la préparation seule (répétable)")
    a.add_argument("--valider", action="store_true",
                   help="le passage unique, sans question (après préparation)")
    a.add_argument("--second-regard", default="", metavar="MOTIF",
                   help="refaire un passage déjà fait ; le motif est écrit "
                        "au registre comme SECOND REGARD")
    # Garde pour l'ancien menu de Carruos.bat : seul l'univers de la
    # specification est accepte.
    a.add_argument("--univers", default=UNIVERS)
    a.add_argument("--csv", default=None, help=argparse.SUPPRESS)
    o = a.parse_args()
    if o.univers != UNIVERS:
        a.error("la spécification porte sur l'univers US large (--univers us)")

    from . import registre as rg
    deja = rg.deja_regardee(HYPOTHESE, periode_validation())
    if deja and not o.second_regard and not o.preparer:
        # Deja regardee : on le dit tout de suite, sans rien recharger.
        valide({}, controle=False)
        print("  La préparation reste possible, pour la répétition générale :"
              "\n    py -m equity_scanner.pead --preparer\n")
        return
    don = prepare()
    if not don or o.preparer:
        return
    manques = incomplet(don)
    if manques:
        valide(don)          # dit pourquoi il ne part pas
        return
    if not o.valider:
        if not sys.stdin.isatty():
            print("  Préparation terminée. Pour le passage unique : "
                  "py -m equity_scanner.pead --valider")
            return
        print("  La préparation est faite. Le passage unique regarde "
              f"{periode_validation()} UNE fois, et le résultat")
        print("  s'inscrit au registre quel qu'il soit.")
        try:
            rep = input("  Tapez OUI pour le lancer, ou Entrée pour "
                        "vous arrêter là : ").strip()
        except EOFError:
            rep = ""
        if rep != "OUI":
            print("  Rien n'a été regardé. Relancez quand vous voulez.\n")
            return
    valide(don, second_regard=o.second_regard)


if __name__ == "__main__":
    main()
