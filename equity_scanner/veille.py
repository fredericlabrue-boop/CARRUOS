"""La veille : rapprocher l'actualite de VOS lignes. Rien de plus.

Ce que ce module fait
---------------------
Une **jointure**. Il prend les actualites du jour et vos titres, et dit
lesquels se rencontrent. Trois niveaux, du plus factuel au moins
factuel, et chacun porte son etiquette a l'ecran.

1. **NOMME.** La source declare que cet article concerne ce titre. Ce
   n'est pas une interpretation : Alpha Vantage attache lui-meme une
   liste de tickers a chaque article. Si `TTE.PA` est dedans et que vous
   detenez `TTE.PA`, on vous le dit. Zero invention.

2. **MEME SECTEUR.** L'article porte un theme, et l'un de vos titres est
   **declare** dans le secteur correspondant. La table de correspondance
   est ecrite **avant** tout usage, juste en dessous, et affichee avec le
   resultat. C'est une correspondance de **noms**, pas une chaine de
   causes : dire que l'energie et `energy_transportation` designent la
   meme chose n'est pas dire qu'un article fera bouger un cours.

3. **MOT TROUVE.** Le titre de l'article contient un mot d'une liste
   ecrite d'avance — pays, institutions, mots de conflit. C'est un
   **appariement de chaines de caracteres**, et rien d'autre. « Iran »
   dans un titre veut dire que le mot y est. Il ne veut rien dire de
   plus, et surtout rien sur un cours.

Pourquoi ce niveau 3 existe, et ce qu'il ne faut pas en faire
------------------------------------------------------------
Alpha Vantage **n'etiquette pas la geopolitique**. Ses themes sont
economiques et sectoriels : il n'y a pas de sujet « conflit » ni
« sanctions ». Un rapprochement geopolitique ne peut donc pas s'appuyer
sur une declaration de la source — il faut aller chercher les mots
soi-meme, et c'est nettement plus faible.

C'est pour cela que ce niveau est le dernier, qu'il est nomme « mot
trouve » et pas « risque geopolitique », et qu'il ne produit aucun
compte agrege : additionner des occurrences de mots donnerait un nombre
qui ressemblerait a une mesure sans en etre une.

Ce que ce module refuse, et pourquoi
------------------------------------
**Un chiffrage du risque geopolitique.** C'est un interdit du projet,
et la raison tient en une phrase : personne ne sait convertir un
evenement en points de cours, et un nombre invente est plus dangereux
qu'une case vide parce qu'il se cite.

**Le score de sentiment du fournisseur.** Alpha Vantage en publie un.
C'est un score composite dont nous ignorons les poids ; le projet refuse
deja les siens, en importer un d'ailleurs serait pire puisqu'il ne
serait meme pas verifiable. Il n'entre pas dans la veille.

**Un classement des actualites par importance.** Il faudrait une echelle
d'importance, donc des poids, donc un score.

**Une direction.** « Cet evenement est bon pour vos lignes » suppose de
savoir ou va le cours. Le programme ne le sait pas, et une information
publique est deja dans les prix au moment ou vous la lisez.

Le secteur d'un titre est **declare** par la source de donnees, comme
dans `profil.py`, et le rapport le dit a chaque fois. Un titre mal
etiquete reste mal etiquete.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

# ---------------------------------------------------------------------
# La table de correspondance, ECRITE AVANT tout usage
# ---------------------------------------------------------------------
#
# A gauche les themes d'Alpha Vantage, a droite les secteurs tels que la
# source de donnees les nomme. C'est une correspondance de vocabulaire,
# etablie une fois, affichee avec le resultat pour qu'on puisse la
# contester.
#
# Elle est deliberement PAUVRE. Chaque theme ne pointe que vers les
# secteurs qu'il nomme explicitement. On pourrait la rendre plus riche —
# « l'energie touche les transports, qui touchent la distribution » —
# mais chaque maillon ajoute serait une supposition de notre part, et
# c'est exactement la pente a ne pas prendre.
#
# Les themes economiques generaux (`economy_macro`, `economy_monetary`,
# `economy_fiscal`, `financial_markets`) ne pointent vers RIEN : ils
# concernent tout le marche, donc les rattacher a un secteur
# particulier serait faux. Ils apparaissent quand meme dans la liste des
# actualites, simplement sans rapprochement sectoriel.
THEME_SECTEURS = {
    "energy_transportation": ("Energy", "Industrials", "Utilities"),
    "finance": ("Financial Services",),
    "life_sciences": ("Healthcare",),
    "manufacturing": ("Industrials", "Basic Materials"),
    "real_estate": ("Real Estate",),
    "retail_wholesale": ("Consumer Cyclical", "Consumer Defensive"),
    "technology": ("Technology", "Communication Services"),
    "blockchain": (),
    "earnings": (),
    "ipo": (),
    "mergers_and_acquisitions": (),
    "economy_fiscal": (),
    "economy_macro": (),
    "economy_monetary": (),
    "financial_markets": (),
}

# Le nom francais d'un secteur declare, pour l'affichage seulement.
SECTEURS_FR = {
    "Technology": "technologie",
    "Communication Services": "communication",
    "Financial Services": "finance",
    "Healthcare": "sante",
    "Consumer Cyclical": "consommation cyclique",
    "Consumer Defensive": "consommation de base",
    "Industrials": "industrie",
    "Basic Materials": "materiaux",
    "Energy": "energie",
    "Utilities": "services aux collectivites",
    "Real Estate": "immobilier",
}

# ---------------------------------------------------------------------
# Les mots, ECRITS AVANT tout usage
# ---------------------------------------------------------------------
#
# Chercher ces mots dans un titre est un appariement de chaines. Le
# resultat se verifie a l'oeil : le mot y est, ou il n'y est pas.
#
# La liste est volontairement courte et concrete. Une liste longue
# attraperait tout et ne distinguerait plus rien ; des mots vagues
# (« tension », « crise ») ressortiraient sur la moitie des titres de
# presse economique et ne vaudraient rien.
MOTS_GEO = {
    "pays": ("Russia", "Russian", "Ukraine", "China", "Chinese", "Taiwan",
             "Iran", "Israel", "Gaza", "Venezuela", "Saudi", "India",
             "Japan", "Korea", "Turkey", "Egypt", "Nigeria", "Libya"),
    "institutions": ("OPEC", "NATO", "OTAN", "European Union", "Brussels",
                     "Kremlin", "Pentagon", "White House", "Congress",
                     "Federal Reserve", "ECB", "IMF", "WTO"),
    "actions": ("sanction", "sanctions", "tariff", "tariffs", "embargo",
                "blockade", "strike", "strikes", "war", "conflict",
                "invasion", "ceasefire", "export ban", "import ban",
                "nationalis", "nationaliz", "coup", "election"),
    "chaines": ("supply chain", "shortage", "pipeline", "strait", "canal",
                "shipping", "freight", "semiconductor", "rare earth",
                "lithium", "uranium", "wheat", "grain"),
}

# Compile une fois. `\b` de part et d'autre pour qu'« Iran » ne sorte pas
# sur « Iranian » par hasard — ou plutot : pour qu'il en sorte, mais par
# le prefixe voulu et non par un fragment au milieu d'un autre mot.
_MOTIFS = {
    famille: re.compile(
        "|".join(r"\b" + re.escape(m) for m in mots), re.IGNORECASE)
    for famille, mots in MOTS_GEO.items() if mots
}

# Cache des secteurs declares : un appel reseau par titre, et le secteur
# d'une entreprise ne change pas d'une heure a l'autre.
CACHE = Path(".bruce_cache")
FICHIER_SECTEURS = CACHE / "secteurs.json"
AGE_SECTEURS = 30 * 24 * 3600          # un mois


def mots_trouves(titre: str) -> dict:
    """Les mots de la liste presents dans ce titre, par famille.

    Aucune ponderation, aucun total : un compte de mots ressemblerait a
    une mesure sans en etre une.
    """
    t = titre or ""
    out = {}
    for famille, motif in _MOTIFS.items():
        trouves = sorted({m.group(0) for m in motif.finditer(t)})
        if trouves:
            out[famille] = trouves
    return out


def _secteurs_caches() -> dict:
    try:
        d = json.loads(FICHIER_SECTEURS.read_text(encoding="utf-8"))
        if time.time() - d.get("quand", 0) < AGE_SECTEURS:
            return d.get("secteurs") or {}
    except Exception:
        pass
    return {}


def _range_secteurs(secteurs: dict) -> None:
    try:
        CACHE.mkdir(exist_ok=True)
        FICHIER_SECTEURS.write_text(
            json.dumps({"quand": time.time(), "secteurs": secteurs},
                       ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def secteurs(tickers) -> dict:
    """Le secteur DECLARE de chaque titre. `None` quand on ne l'a pas.

    C'est une declaration de la source de donnees, pas une mesure, et
    tout ce qui l'affiche doit le dire. Hors ligne ou quota epuise, la
    fonction rend simplement moins de lignes : le niveau 1 de la veille,
    lui, ne depend d'aucun de ces appels.
    """
    connus = _secteurs_caches()
    manquants = [t for t in tickers if t and t not in connus]
    if manquants:
        try:
            import yfinance as yf
            for t in manquants:
                try:
                    info = yf.Ticker(t).get_info() or {}
                    connus[t] = info.get("sector") or None
                except Exception:
                    connus[t] = None
            _range_secteurs(connus)
        except Exception:
            pass
    return {t: connus.get(t) for t in tickers}


def _joint(a: dict, ens: set, par_secteur: dict) -> dict:
    """Les trois niveaux, pour UN article. Le point unique de la logique.

    `rapproche()` et `decore()` s'en servent tous les deux : deux copies
    de cette regle finiraient par diverger, et l'ecran montrerait alors
    autre chose que le texte du majordome.
    """
    cites = sorted(t for t in (a.get("tickers") or []) if t in ens)
    touches: dict = {}
    for theme in (a.get("themes") or []):
        for s in THEME_SECTEURS.get(theme, ()):
            for t in par_secteur.get(s, []):
                if t not in cites:              # deja dit au niveau 1
                    touches.setdefault(s, set()).add(t)
    return {
        "titres": cites,
        "secteurs": {s: sorted(v) for s, v in sorted(touches.items())},
        "mots": mots_trouves(a.get("titre", "")),
    }


def _par_secteur(lignes, sect: dict) -> dict:
    out: dict = {}
    for t in lignes:
        s = sect.get(t)
        if s:
            out.setdefault(s, []).append(t)
    return out


def decore(actus, lignes, sect: dict | None = None) -> list[dict]:
    """Les actualites, chacune portant le rapprochement qui la concerne.

    L'ecran d'accueil affiche deja ces articles : le rapprochement s'y
    pose EN PLACE, sur l'article qu'on est en train de lire, plutot que
    dans une seconde liste a rapprocher de la premiere a la main.
    """
    lignes = [str(t).upper() for t in (lignes or []) if t]
    ens = set(lignes)
    sect = sect if sect is not None else (secteurs(lignes) if lignes else {})
    ps = _par_secteur(lignes, sect)
    out = []
    for a in actus or []:
        if a.get("erreur") or a.get("sans_cle"):
            out.append(dict(a))
            continue
        j = _joint(a, ens, ps)
        out.append({**a, "vous": j})
    return out


def rapproche(actus, lignes, sect: dict | None = None) -> dict:
    """La jointure. Trois niveaux, chacun etiquete par sa force.

    `actus` vient de `news.monde()`. `lignes` est la liste des titres du
    proprietaire — positions et MA LISTE confondues. `sect` permet de
    fournir les secteurs deja connus, pour ne pas rappeler le reseau.
    """
    lignes = [str(t).upper() for t in (lignes or []) if t]
    ens = set(lignes)
    sect = sect if sect is not None else (secteurs(lignes) if lignes else {})
    ps = _par_secteur(lignes, sect)

    nommes, sectoriels, geo = [], [], []
    for a in actus or []:
        if a.get("erreur"):
            continue
        base = {"titre": a.get("titre", ""), "source": a.get("source", ""),
                "quand": a.get("quand", ""), "url": a.get("url", "")}
        j = _joint(a, ens, ps)
        if j["titres"]:
            nommes.append({**base, "titres": j["titres"]})
        if j["secteurs"]:
            sectoriels.append({**base,
                               "themes": sorted(a.get("themes") or []),
                               "secteurs": j["secteurs"]})
        if j["mots"]:
            geo.append({**base, "mots": j["mots"]})

    return {
        "lignes": lignes,
        "secteurs": {t: s for t, s in sect.items() if s},
        "sans_secteur": sorted(t for t in lignes if not sect.get(t)),
        "nommes": nommes,
        "sectoriels": sectoriels,
        "geo": geo,
        "n_actus": len([a for a in (actus or []) if not a.get("erreur")]),
        "table": {k: list(v) for k, v in THEME_SECTEURS.items() if v},
        "rappel": RAPPEL,
        "rappel_secteur": RAPPEL_SECTEUR,
        "rappel_mots": RAPPEL_MOTS,
    }


RAPPEL = (
    "Ceci est un RAPPROCHEMENT, pas une analyse. Il dit quelles "
    "actualites rencontrent vos lignes ; il ne dit pas ce que le cours "
    "va faire, ni dans quel sens, ni quand. Une information publique "
    "est deja dans les prix au moment ou vous la lisez, et aucune "
    "regle du programme ne l'utilise.")

RAPPEL_SECTEUR = (
    "Le secteur d'un titre est DECLARE par la source de donnees, il "
    "n'est pas mesure. La correspondance entre un theme d'actualite et "
    "un secteur est une correspondance de NOMS, ecrite d'avance et "
    "affichee ci-dessous : elle ne dit pas qu'un article agit sur un "
    "cours.")

RAPPEL_MOTS = (
    "Un mot trouve est un mot trouve dans un titre — un appariement de "
    "chaines de caracteres, rien d'autre. Aucun total n'est calcule : "
    "compter des occurrences donnerait un nombre qui ressemblerait a "
    "une mesure sans en etre une. Le risque geopolitique n'est pas "
    "chiffre ici, et il ne le sera pas : personne ne sait convertir un "
    "evenement en points de cours, et un nombre invente est plus "
    "dangereux qu'une case vide parce qu'il se cite.")


def texte(r: dict) -> list[str]:
    """La veille en phrases. Aucun chiffre calcule ici : gabarits."""
    L = []
    if not r.get("lignes"):
        return ["Aucune ligne a rapprocher : ajoutez des positions ou "
                "collez des titres dans MA LISTE."]
    L.append(f"{r['n_actus']} actualites confrontees a "
             f"{len(r['lignes'])} de vos titres.")

    if r["nommes"]:
        L.append("")
        L.append("NOMMES PAR LA SOURCE — le fournisseur declare que "
                 "l'article porte sur ce titre :")
        for a in r["nommes"]:
            L.append(f"  • {', '.join(a['titres'])} — {a['titre']} "
                     f"({a['source']} {a['quand']})")
    else:
        L.append("")
        L.append("Aucune actualite ne nomme l'un de vos titres.")

    if r["sectoriels"]:
        L.append("")
        L.append("MEME SECTEUR DECLARE — correspondance de noms, "
                 "pas de causes :")
        for a in r["sectoriels"]:
            for s, ts in a["secteurs"].items():
                L.append(f"  • {SECTEURS_FR.get(s, s)} : "
                         f"{', '.join(ts)} — {a['titre']}")

    if r["geo"]:
        L.append("")
        L.append("MOTS TROUVES DANS LE TITRE — appariement de chaines :")
        for a in r["geo"]:
            mots = ", ".join(m for fam in a["mots"].values() for m in fam)
            L.append(f"  • {mots} — {a['titre']}")

    L.append("")
    L.append(r["rappel"])
    if r["sectoriels"]:
        L.append(r["rappel_secteur"])
    if r["geo"]:
        L.append(r["rappel_mots"])
    return L
