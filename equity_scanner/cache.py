"""Chargement des cours : cache disque et telechargements en parallele.

POURQUOI CE MODULE EXISTE

Le calcul n'a jamais ete le probleme. Enrichir un titre de 5 000 barres
prend 9 millisecondes ; 500 titres, moins de cinq secondes. Ce qui prenait
« 25 a 40 minutes » annoncees dans data.py, c'etait l'attente du reseau :
500 telechargements l'un APRES l'autre, chacun bloquant le suivant.

Deux corrections, aucune ruse :

  1. EN PARALLELE. Les telechargements attendent le reseau, pas le
     processeur : pendant qu'un fil attend, les autres travaillent. Huit
     fils ramenent l'attente a peu pres au huitieme. On ne monte pas plus
     haut : Yahoo limite le debit et repond par des erreurs si on insiste.

  2. SUR DISQUE. Un cours de cloture ne change plus apres la cloture. Le
     relancer dix fois dans la soiree, c'est telecharger dix fois la meme
     chose. Le cache garde la serie jusqu'a la cloture suivante ; la
     deuxieme passe de la journee ne touche plus le reseau du tout.

Ce que le module ne fait PAS : inventer une barre manquante, prolonger une
serie perimee, ou masquer une erreur de telechargement. Un titre qui ne se
charge pas ressort dans la liste des erreurs, avec son motif.
"""

from __future__ import annotations

import datetime as dt
import pickle
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

DOSSIER = Path(".bruce_cache") / "cours"
VERSION = 2                 # incremente si le format stocke change
FILS = 8                    # telechargements simultanes
FILS_MAX = 16
_VERROU = threading.Lock()
_MEMOIRE: dict[tuple, pd.DataFrame] = {}


# ---------------------------------------------------------------------
# Validite du cache
# ---------------------------------------------------------------------
def _cloture_utc(quand: dt.datetime) -> dt.datetime:
    """Derniere cloture US passee, en UTC.

    Les marches americains ferment a 21h00 UTC l'ete, 22h00 l'hiver ; on
    prend 22h00 pour ne jamais considerer comme definitive une bougie qui
    ne l'est pas encore. Avant cette heure, la reference est la veille.
    """
    jour = quand.date()
    if quand.hour < 22:
        jour = jour - dt.timedelta(days=1)
    return dt.datetime.combine(jour, dt.time(22, 0), dt.timezone.utc)


def _frais(horodatage: float, heures_max: float | None = None) -> bool:
    """Le fichier est-il encore valable ?"""
    ecrit = dt.datetime.fromtimestamp(horodatage, dt.timezone.utc)
    maintenant = dt.datetime.now(dt.timezone.utc)
    if heures_max is not None:
        return (maintenant - ecrit).total_seconds() < heures_max * 3600
    # Valable tant qu'aucune nouvelle cloture n'est intervenue depuis
    # l'ecriture.
    return ecrit >= _cloture_utc(maintenant)


def _fichier(ticker: str, annees: int, source: str) -> Path:
    sur = "".join(c if c.isalnum() or c in "-_." else "_" for c in ticker)
    return DOSSIER / f"{sur}-{annees}a-{source}-v{VERSION}.pkl"


# ---------------------------------------------------------------------
# Lecture / ecriture
# ---------------------------------------------------------------------
def _lit(f: Path, heures_max: float | None) -> pd.DataFrame | None:
    try:
        if not _frais(f.stat().st_mtime, heures_max):
            return None
        with f.open("rb") as fp:
            d = pickle.load(fp)
        if isinstance(d, pd.DataFrame) and not d.empty:
            return d
    except Exception:
        pass
    return None


def _ecrit(f: Path, d: pd.DataFrame) -> None:
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        # Ecriture atomique : un fichier a moitie ecrit par un autre fil
        # produirait un cache corrompu lu comme valide.
        tmp = f.with_suffix(f".{threading.get_ident()}.tmp")
        with tmp.open("wb") as fp:
            pickle.dump(d, fp, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(f)
    except Exception:
        pass


# ---------------------------------------------------------------------
# Chargement unitaire
# ---------------------------------------------------------------------
def charge(ticker: str, annees: int = 3, source: str = "yf",
           heures_max: float | None = None,
           force: bool = False) -> pd.DataFrame:
    """Cours d'un titre, depuis le cache si possible.

    Meme contrat de sortie que data.load_yf : index datetime croissant,
    colonnes open/high/low/close/volume.
    """
    from . import data as dl

    cle = (ticker, annees, source)
    if not force:
        with _VERROU:
            d = _MEMOIRE.get(cle)
        if d is not None:
            return d
        d = _lit(_fichier(ticker, annees, source), heures_max)
        if d is not None:
            with _VERROU:
                _MEMOIRE[cle] = d
            return d

    d = dl.loader(source)(ticker, years=annees)
    if d is None or d.empty:
        raise ValueError(f"aucune donnee pour {ticker}")
    _ecrit(_fichier(ticker, annees, source), d)
    with _VERROU:
        _MEMOIRE[cle] = d
    return d


# ---------------------------------------------------------------------
# Chargement d'un univers
# ---------------------------------------------------------------------
def charge_lot(tickers, annees: int = 3, source: str = "yf",
               fils: int = FILS, journal=None, pas: int = 25,
               heures_max: float | None = None,
               force: bool = False) -> tuple[dict, list]:
    """Charge tout un univers en parallele.

    Rend ({ticker: DataFrame}, [(ticker, motif d'echec)]). Les echecs ne
    sont pas avales : chacun ressort avec son ticker et son motif, pour
    qu'un titre retire de la cote ou mal orthographie se voie.
    """
    tickers = list(dict.fromkeys(t for t in tickers if t))
    if not tickers:
        return {}, []
    fils = max(1, min(int(fils), FILS_MAX, len(tickers)))
    series: dict[str, pd.DataFrame] = {}
    erreurs: list[tuple[str, str]] = []
    debut = time.perf_counter()

    with ThreadPoolExecutor(max_workers=fils) as pool:
        # Le futur est associe a son ticker : as_completed rend les
        # resultats dans le desordre, et sans cette table une erreur ne
        # saurait plus de quel titre elle parle.
        futurs = {pool.submit(charge, tk, annees, source, heures_max,
                              force): tk for tk in tickers}
        for n, fut in enumerate(as_completed(futurs), 1):
            tk = futurs[fut]
            try:
                series[tk] = fut.result()
            except Exception as exc:
                erreurs.append((tk, f"{type(exc).__name__}: {str(exc)[:70]}"))
            if journal and pas and n % pas == 0:
                journal(f"    {n}/{len(tickers)} charges "
                        f"({time.perf_counter() - debut:.0f} s)")
    if journal:
        journal(f"    {len(series)} charges, {len(erreurs)} en echec, "
                f"{time.perf_counter() - debut:.0f} s")
    return series, sorted(erreurs)


# ---------------------------------------------------------------------
# Enrichissement memoise
# ---------------------------------------------------------------------
_ENRICHI: dict[tuple, pd.DataFrame] = {}


def enrichi(ticker: str, bench_close: pd.Series | None = None,
            annees: int = 3, source: str = "yf",
            periodes: dict | None = None) -> pd.DataFrame:
    """Serie enrichie, calculee une seule fois par processus.

    La page graphique, le scan et le controle des positions demandaient
    tous les trois le meme titre et recalculaient tous les trois les memes
    indicateurs.
    """
    from .indicators import enrich

    empreinte = None
    if bench_close is not None and len(bench_close):
        empreinte = (str(bench_close.index[0]), str(bench_close.index[-1]),
                     len(bench_close))
    cle = (ticker, annees, source, empreinte,
           tuple(sorted((periodes or {}).items())) if periodes else None)
    with _VERROU:
        d = _ENRICHI.get(cle)
    if d is not None:
        return d
    d = enrich(charge(ticker, annees, source), bench_close=bench_close,
               periodes=periodes)
    with _VERROU:
        _ENRICHI[cle] = d
    return d


# ---------------------------------------------------------------------
# Entretien
# ---------------------------------------------------------------------
def oublie() -> None:
    """Vide le cache memoire. Le disque n'est pas touche."""
    with _VERROU:
        _MEMOIRE.clear()
        _ENRICHI.clear()


def etat() -> dict:
    """Ce que contient le cache disque, sans rien y toucher."""
    try:
        fichiers = sorted(DOSSIER.glob("*.pkl"))
    except Exception:
        return {"fichiers": 0, "octets": 0, "frais": 0}
    octets = sum(f.stat().st_size for f in fichiers)
    frais = sum(1 for f in fichiers if _frais(f.stat().st_mtime, None))
    return {"fichiers": len(fichiers), "octets": octets, "frais": frais,
            "dossier": str(DOSSIER)}


def purge(jours: int = 30) -> int:
    """Supprime les series plus vieilles que `jours`. Rend le compte."""
    n = 0
    limite = time.time() - jours * 86400
    try:
        for f in DOSSIER.glob("*.pkl"):
            if f.stat().st_mtime < limite:
                f.unlink(missing_ok=True)
                n += 1
    except Exception:
        pass
    return n


def main() -> None:
    import argparse
    a = argparse.ArgumentParser(description="Cache des cours")
    a.add_argument("--etat", action="store_true")
    a.add_argument("--purge", type=int, nargs="?", const=30, default=None,
                   help="supprime les series plus vieilles que N jours")
    o = a.parse_args()
    if o.purge is not None:
        print(f"  {purge(o.purge)} serie(s) supprimee(s).")
    e = etat()
    print(f"\n  CACHE DES COURS  ({e.get('dossier', DOSSIER)})")
    print(f"    fichiers        {e['fichiers']}")
    print(f"    encore valables {e['frais']}")
    print(f"    taille          {e['octets'] / 1e6:.1f} Mo\n")


if __name__ == "__main__":
    main()
