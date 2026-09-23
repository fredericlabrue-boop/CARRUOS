"""Le carnet : ce que vous ecrivez, et ce que le programme a mesure ce
jour-la.

Deux choses distinctes vivent ici, et elles ne se melangent pas.

**Vos notes.** Du texte libre, date, rattachable a un titre. Le
programme n'y touche pas, ne les interprete pas, ne les resume pas.

**Vos releves.** Une photo datee de ce que CARRUOS mesurait a l'instant
ou vous l'avez prise : les 13 blocs d'un titre, vos positions, votre
liste. C'est la seule facon d'avoir un jour une reponse a « qu'est-ce
que je voyais quand j'ai achete ? » — parce qu'un releve pris apres
coup est reconstruit, donc faux.

Ou c'est range
---------------
`~/.carruos/carnet.json`, comme la cle Alpha Vantage, et pour la meme
raison : c'est le seul endroit qui survive a une mise a jour du
programme. Un carnet range a cote du code disparaitrait au premier
remplacement du dossier, et un carnet qui disparait est pire qu'un
carnet absent — on a cesse d'ecrire ailleurs en comptant dessus.

Ecriture par fichier temporaire puis remplacement : une coupure de
courant au milieu d'une sauvegarde laisse l'ancien carnet entier
plutot qu'un fichier a moitie ecrit.

Ce que le carnet ne fait pas
----------------------------
Il ne note rien tout seul, et il ne porte aucun jugement sur ce que
vous avez ecrit. « Vous aviez raison ce jour-la » demanderait de
comparer une intention a un resultat, donc de decider ce qui compte
comme reussite — ce n'est pas une mesure, c'est un avis, et le projet
n'en produit pas.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import uuid
from pathlib import Path

DOSSIER = Path.home() / ".carruos"
FICHIER = DOSSIER / "carnet.json"

# Un carnet qui grossit sans fin finit par ralentir l'ouverture de la
# page. Le plafond est large — a une note par jour il tient trente ans —
# et l'entree la plus ancienne part la premiere.
MAX_ENTREES = 12000

# Les genres d'entree. Le genre n'est PAS une etiquette libre : il dit
# qui a ecrit la ligne, et cette distinction est le fond du module.
GENRES = {
    "note": "NOTE",            # vous l'avez ecrite
    "releve": "RELEVÉ",        # le programme a mesure, vous avez fige
    "ordre": "ORDRE",          # un passage d'ordre que vous consignez
}


def _maintenant() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _vide() -> dict:
    return {"version": 1, "entrees": []}


def charge() -> dict:
    """Le carnet entier. Un fichier illisible ne fait pas tomber la page.

    Si le JSON est casse, on le met de cote sous `.abime` au lieu de
    l'ecraser : le contenu est peut-etre recuperable a la main, et
    l'ecraser en silence serait une perte definitive.
    """
    try:
        brut = FICHIER.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _vide()
    except OSError:
        return _vide()
    try:
        d = json.loads(brut)
    except ValueError:
        try:
            FICHIER.replace(FICHIER.with_suffix(".abime"))
        except OSError:
            pass
        return _vide()
    if not isinstance(d, dict) or not isinstance(d.get("entrees"), list):
        return _vide()
    return d


def _ecris(d: dict) -> None:
    """Ecriture atomique : temporaire, puis remplacement."""
    DOSSIER.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, FICHIER)
    try:
        os.chmod(FICHIER, 0o600)
    except OSError:
        pass


def ajoute(titre: str = "", texte: str = "", ticker: str = "",
           genre: str = "note", donnees: dict | None = None) -> dict:
    """Une entree de plus. Rend l'entree ecrite, avec son identifiant."""
    d = charge()
    e = {
        "id": uuid.uuid4().hex[:12],
        "date": _maintenant(),
        "genre": genre if genre in GENRES else "note",
        "ticker": (ticker or "").strip().upper(),
        "titre": (titre or "").strip(),
        "texte": texte or "",
    }
    if donnees:
        e["donnees"] = donnees
    d["entrees"].insert(0, e)
    del d["entrees"][MAX_ENTREES:]
    _ecris(d)
    return e


def modifie(ident: str, titre=None, texte=None, ticker=None) -> dict | None:
    """Corriger une note. La date de creation ne bouge pas ; une date de
    retouche s'ajoute — sinon on ne saurait plus si le texte est celui
    du jour de l'achat ou celui d'aujourd'hui, et c'est precisement ce
    qu'on cherchait a savoir."""
    d = charge()
    for e in d["entrees"]:
        if e.get("id") == ident:
            if titre is not None:
                e["titre"] = titre.strip()
            if texte is not None:
                e["texte"] = texte
            if ticker is not None:
                e["ticker"] = ticker.strip().upper()
            e["retouche"] = _maintenant()
            _ecris(d)
            return e
    return None


def supprime(ident: str) -> bool:
    d = charge()
    avant = len(d["entrees"])
    d["entrees"] = [e for e in d["entrees"] if e.get("id") != ident]
    if len(d["entrees"]) == avant:
        return False
    _ecris(d)
    return True


def entrees(ticker: str = "", genre: str = "", q: str = "",
            limite: int = 300) -> list[dict]:
    """Les entrees, filtrees. Recherche insensible a la casse sur le
    titre et le texte — pas sur les donnees d'un releve, qui sont des
    chiffres et ne se cherchent pas au mot."""
    d = charge()
    tk = (ticker or "").strip().upper()
    mot = (q or "").strip().lower()
    out = []
    for e in d["entrees"]:
        if tk and e.get("ticker") != tk:
            continue
        if genre and e.get("genre") != genre:
            continue
        if mot and mot not in (e.get("titre", "") + " "
                               + e.get("texte", "")).lower():
            continue
        out.append(e)
        if len(out) >= limite:
            break
    return out


def tickers() -> list[str]:
    """Les titres qui ont au moins une entree, du plus recent au plus
    ancien. Sert a proposer un filtre sans le taper."""
    vus, out = set(), []
    for e in charge()["entrees"]:
        t = e.get("ticker")
        if t and t not in vus:
            vus.add(t)
            out.append(t)
    return out


def compte() -> dict:
    """Combien d'entrees, par genre. Affiche en tete de la page."""
    d = charge()["entrees"]
    return {"total": len(d),
            **{g: sum(1 for e in d if e.get("genre") == g) for g in GENRES}}


# ---------------------------------------------------------------------
# Les releves
# ---------------------------------------------------------------------
#
# Un releve fige des FAITS deja calcules ailleurs. Ce module ne mesure
# rien lui-meme : il recoit un dictionnaire et l'ecrit. C'est le meme
# contrat que `dossier.py` — si un chiffre n'a pas ete calcule par le
# moteur, il ne peut pas apparaitre dans un releve.

def releve(ticker: str, faits: dict, titre: str = "") -> dict:
    """Fige l'etat mesure d'un titre, date.

    `faits` vient de `dossier.constitue()` ou de `interet.mesures()`.
    On ne garde que des types simples : un objet pandas rendrait le
    carnet illisible par une autre version du programme.
    """
    return ajoute(titre=titre or f"Relevé {ticker.upper()}",
                  ticker=ticker, genre="releve",
                  donnees=_simplifie(faits))


def _simplifie(x, prof: int = 0):
    """Ne garde que ce qui se relit dans dix ans : nombres, chaines,
    booleens, listes et dictionnaires de ceux-la. Tout le reste devient
    son texte. Profondeur bornee : une structure qui se contient
    elle-meme ne doit pas bloquer la sauvegarde."""
    if prof > 6:
        return str(x)
    if x is None or isinstance(x, (bool, int, str)):
        return x
    if isinstance(x, float):
        return None if x != x or x in (float("inf"), float("-inf")) else x
    if isinstance(x, dict):
        return {str(k): _simplifie(v, prof + 1) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_simplifie(v, prof + 1) for v in x]
    return str(x)


# ---------------------------------------------------------------------
# Sortie lisible hors du programme
# ---------------------------------------------------------------------

def markdown(ticker: str = "") -> str:
    """Le carnet en texte, pour l'emporter ailleurs.

    Un carnet enferme dans un format proprietaire est un carnet qu'on
    perd le jour ou le programme ne demarre plus.
    """
    lignes = ["# Carnet CARRUOS", ""]
    for e in entrees(ticker=ticker, limite=MAX_ENTREES):
        jour = e.get("date", "")[:16].replace("T", " ")
        tete = f"## {jour} — {GENRES.get(e.get('genre'), 'NOTE')}"
        if e.get("ticker"):
            tete += f" — {e['ticker']}"
        lignes.append(tete)
        if e.get("titre"):
            lignes.append(f"**{e['titre']}**")
        if e.get("texte"):
            lignes += ["", e["texte"]]
        if e.get("donnees"):
            lignes += ["", "```json",
                       json.dumps(e["donnees"], ensure_ascii=False, indent=1),
                       "```"]
        lignes.append("")
    return "\n".join(lignes)
