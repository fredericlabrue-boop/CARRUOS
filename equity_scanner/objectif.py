"""Un objectif chiffre, traite par l'arithmetique.

« Objectif 50 000 euros le plus rapidement possible, et je ne veux pas
qu'on me dise que c'est impossible. »

L'arithmetique ne dit jamais impossible. Elle dit **ce que ca demande**.
C'est une reponse beaucoup plus utile qu'un refus, et beaucoup plus
utile aussi qu'un encouragement : elle se verifie.

Trois leviers, et trois seulement
---------------------------------
Pour aller d'un capital a une cible, il n'existe que trois leviers :

1. le **capital de depart** ;
2. le **versement** regulier ;
3. le **taux** de croissance, et le **temps** qu'on lui laisse.

Ce module fixe deux leviers et resout le troisieme. Il repond donc a :

- « avec ce que je verse, quel taux faut-il pour y etre en trois ans ? »
- « a ce taux-la, combien de temps ? »
- « a ce taux-la, combien faut-il verser par mois ? »

Chacune de ces reponses est exacte : c'est une equation, pas une
prevision.

La seule chose que ce module n'invente pas
------------------------------------------
Le taux. Il ne le devine pas, il ne le propose pas, il ne l'estime pas.
Quand il calcule un taux EXIGE, il dit bien que c'est ce que
l'arithmetique reclame — pas ce que quoi que ce soit va rendre.

Et il confronte ce taux exige a un fait mesurable : **sur l'historique
d'un instrument donne, quelle part des periodes de meme duree ont
effectivement atteint ce taux ?** C'est un taux de base, avec son
intervalle de Wilson, comme partout ailleurs dans ce programme. Ce n'est
pas une probabilite que ca se reproduise ; c'est la frequence avec
laquelle c'est arrive. La distinction est tout le sujet.

Aucune esperance de gain n'est affichee ici, et il n'y en aura pas tant
qu'aucune hypothese n'aura passe sa Phase 0 : sans avantage demontre,
un gain espere vaut zero, pas un petit nombre optimiste.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .strategie import PFU

# Plafond de recherche : cent ans. Au-dela, la reponse utile n'est pas
# un nombre d'annees, c'est « les leviers actuels n'y menent pas ».
MOIS_MAX = 1200

# Bornes de la recherche de taux. -95 %/an a +1000 %/an : assez large
# pour que la borne ne soit jamais la reponse, assez etroite pour que la
# dichotomie converge vite.
TAUX_MIN, TAUX_MAX = -0.95, 10.0


def _mensuel(taux_annuel: float) -> float:
    """Taux mensuel equivalent, capitalise.

    (1 + m)^12 = 1 + a. Diviser par douze serait faux, et l'erreur
    grandit avec le taux : a 20 %/an, la difference sur dix ans depasse
    un an d'ecart sur la date d'arrivee.
    """
    return (1.0 + taux_annuel) ** (1.0 / 12.0) - 1.0


def valeur(capital: float, versement: float, taux_annuel: float,
           mois: int) -> float:
    """Ce que devient le capital apres `mois` versements mensuels.

    Le versement est fait en DEBUT de mois, donc il travaille le mois
    meme. C'est la convention d'un virement programme, et elle change le
    resultat de facon non negligeable sur une longue duree.
    """
    m = _mensuel(taux_annuel)
    v = float(capital)
    for _ in range(int(mois)):
        v = (v + versement) * (1.0 + m)
    return v


def duree(capital: float, versement: float, taux_annuel: float,
          cible: float) -> int | None:
    """Combien de mois pour atteindre la cible. None si on n'y va pas.

    None n'est pas « impossible » : c'est « pas avec ces trois leviers-la
    en moins de cent ans ». Les leviers se changent, et c'est justement
    ce que `plan()` met en face.
    """
    if capital >= cible:
        return 0
    m = _mensuel(taux_annuel)
    v = float(capital)
    for k in range(1, MOIS_MAX + 1):
        v = (v + versement) * (1.0 + m)
        if v >= cible:
            return k
        # Capital qui fond et versement nul : la suite ne remontera pas.
        if versement <= 0 and m <= 0 and v < capital:
            return None
    return None


def taux_exige(capital: float, versement: float, cible: float,
               mois: int) -> float | None:
    """Le taux annuel qu'il faut pour y etre dans `mois` mois.

    Resolu par dichotomie : la valeur finale croit avec le taux, donc la
    solution est unique. Pas de formule fermee des qu'il y a des
    versements ET une capitalisation mensuelle.
    """
    mois = int(mois)
    if mois <= 0:
        return None
    if valeur(capital, versement, TAUX_MAX, mois) < cible:
        return None                      # meme a +1000 %/an, on n'y est pas
    if valeur(capital, versement, TAUX_MIN, mois) >= cible:
        return TAUX_MIN                  # les versements seuls y suffisent
    lo, hi = TAUX_MIN, TAUX_MAX
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if valeur(capital, versement, mid, mois) < cible:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def apres_impot(brut: float, verse: float, impot: float = PFU) -> float:
    """Ce qui reste d'une valeur brute une fois le gain impose.

    Le prelevement forfaitaire porte sur le GAIN, pas sur le capital :
    `verse` est tout ce qui est sorti de la poche (capital de depart plus
    versements). Une moins-value ne cree pas d'impot negatif, d'ou le
    plancher a zero.
    """
    gain = max(0.0, brut - verse)
    return brut - gain * impot


def taux_exige_net(capital: float, versement: float, cible: float,
                   mois: int, impot: float = PFU) -> float | None:
    """Le taux qu'il faut pour que la cible soit atteinte APRES impot.

    Ce n'est pas le taux brut divise par (1 - impot) : l'impot frappe le
    gain une fois, a la sortie, pas chaque annee. Sur une longue duree
    l'ecart entre les deux facons de compter est grand, et le raccourci
    surestime l'effort demande. Donc on resout la vraie equation, par la
    meme dichotomie que `taux_exige` — la valeur nette croit elle aussi
    avec le taux.

    Sans enveloppe fiscale (PEA, assurance-vie) l'hypothese est celle du
    compte-titres ordinaire : un seul denouement, taxe a la fin. Une
    ligne revendue tous les six mois paierait plus que cela ; ce chiffre
    est donc un plancher, et il est presente comme tel.
    """
    mois = int(mois)
    if mois <= 0:
        return None
    verse = float(capital) + float(versement) * mois

    def net(taux):
        return apres_impot(valeur(capital, versement, taux, mois), verse,
                           impot)

    if net(TAUX_MAX) < cible:
        return None
    if net(TAUX_MIN) >= cible:
        return TAUX_MIN
    lo, hi = TAUX_MIN, TAUX_MAX
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if net(mid) < cible:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def versement_exige(capital: float, taux_annuel: float, cible: float,
                    mois: int) -> float | None:
    """Le versement mensuel qu'il faut, a taux donne et date donnee.

    Formule fermee : la valeur finale est affine en versement, donc une
    division suffit. Pas de dichotomie la ou l'algebre repond.
    """
    mois = int(mois)
    if mois <= 0:
        return None
    m = _mensuel(taux_annuel)
    sans = valeur(capital, 0.0, taux_annuel, mois)
    par_euro = valeur(0.0, 1.0, taux_annuel, mois)
    if par_euro <= 0:
        return None
    manque = cible - sans
    return max(0.0, manque / par_euro)


# ---------------------------------------------------------------------
# Le taux exige, confronte a ce qui s'est REELLEMENT passe
# ---------------------------------------------------------------------

def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de Wilson. Jamais un pourcentage nu dans ce programme."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    e = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - e) / d, (c + e) / d)


def frequence_historique(close: pd.Series, taux_annuel: float,
                         mois: int) -> dict:
    """Sur cet historique, quelle part des periodes de `mois` mois ont
    atteint au moins ce taux annualise ?

    Fenetres glissantes, donc largement recouvrantes : deux fenetres
    voisines partagent presque toutes leurs seances. Le nombre de
    fenetres INDEPENDANTES est bien plus petit, et c'est lui qui porte
    l'information — d'ou `n_independantes`, qui sert a lire l'intervalle
    sans se croire plus precis qu'on ne l'est.

    Ce n'est pas une probabilite que ca se reproduise. C'est la
    frequence avec laquelle c'est arrive sur le passe disponible, qui
    est court, qui n'est pas l'avenir, et qui ne contient qu'un seul
    tirage de l'histoire.
    """
    c = close.dropna()
    n_barres = max(1, int(round(mois * 21)))     # ~21 seances par mois
    if len(c) < n_barres + 30:
        return {"assez": False, "n": 0, "sur": int(len(c)),
                "besoin": n_barres + 30}
    debut = c.values[:-n_barres]
    fin = c.values[n_barres:]
    ans = n_barres / 252.0
    with np.errstate(all="ignore"):
        croiss = (fin / debut) ** (1.0 / ans) - 1.0
    croiss = croiss[np.isfinite(croiss)]
    n = int(len(croiss))
    k = int((croiss >= taux_annuel).sum())
    lo, hi = _wilson(k, n)
    return {
        "assez": True, "k": k, "n": n,
        "part": k / n if n else None,
        "wilson": (lo, hi),
        "n_independantes": max(1, n // n_barres),
        "median": float(np.median(croiss)) if n else None,
        "mois": mois, "taux": taux_annuel,
    }


# ---------------------------------------------------------------------
# Le plan
# ---------------------------------------------------------------------

def plan(cible: float, capital: float, versement: float = 0.0,
         mois: int | None = None, taux: float | None = None,
         impot: float = PFU) -> dict:
    """Les trois leviers, chiffres, pour une cible donnee.

    `mois` : l'echeance voulue. `taux` : le taux POSE EN HYPOTHESE.
    L'un des deux suffit ; les deux ensemble donnent en plus l'ecart
    entre ce que l'hypothese produit et ce que l'echeance reclame.

    Rien ici n'est un conseil, et rien n'est refuse. Chaque ligne est
    une equation resolue.
    """
    out: dict = {"cible": float(cible), "capital": float(capital),
                 "versement": float(versement), "impot": impot,
                 "mois_vise": mois, "taux_pose": taux}

    manque = float(cible) - float(capital)
    out["manque"] = manque
    if manque <= 0:
        out["deja"] = True
        return out
    out["deja"] = False

    # Levier 1 : sans aucune croissance. Le plancher absolu, et le seul
    # chiffre du lot qui ne depende d'aucune hypothese.
    out["sans_croissance"] = {
        "mois": (math.ceil(manque / versement) if versement > 0 else None),
        "versement_pour_mois": (manque / mois if mois else None),
    }

    if mois:
        t = taux_exige(capital, versement, cible, mois)
        out["taux_exige"] = t
        out["taux_exige_net_impot"] = taux_exige_net(
            capital, versement, cible, mois, impot)
        out["versement_exige"] = {}
        for hyp in (0.04, 0.07, 0.10, 0.15):
            out["versement_exige"][hyp] = versement_exige(
                capital, hyp, cible, mois)

    if taux is not None:
        d = duree(capital, versement, taux, cible)
        out["duree_au_taux_pose"] = d
        out["annees_au_taux_pose"] = (None if d is None else round(d / 12, 1))

    # Les durees a quelques taux poses, pour voir la forme de la courbe.
    out["durees"] = {hyp: duree(capital, versement, hyp, cible)
                     for hyp in (0.0, 0.04, 0.07, 0.10, 0.15, 0.25)}
    return out


RAPPEL = (
    "Ces nombres sont des equations resolues, pas des previsions. Le "
    "taux exige est ce que l'arithmetique reclame pour tenir la date — "
    "il ne dit pas qu'un placement le rendra. Aucune hypothese du "
    "programme n'a passe sa Phase 0, donc aucun gain espere n'est "
    "affiche ici : sans avantage demontre, il vaut zero, pas un petit "
    "nombre optimiste.")

RAPPEL_FREQUENCE = (
    "La frequence historique compte des fenetres glissantes, qui se "
    "recouvrent presque entierement. Le nombre de periodes reellement "
    "independantes est bien plus petit, et c'est lui qui porte "
    "l'information. Une frequence passee n'est pas une probabilite "
    "future : l'historique disponible est court, et il ne contient "
    "qu'un seul deroulement de l'histoire.")


def texte(p: dict) -> list[str]:
    """Le plan en phrases. Aucun chiffre calcule ici : gabarits remplis."""
    def eur(x):
        return "—" if x is None else f"{x:,.0f} €".replace(",", " ")

    def pc(x):
        return "—" if x is None else f"{x * 100:.1f} %".replace(".", ",")

    def dur(m):
        if m is None:
            return "hors d'atteinte avec ces leviers en moins de cent ans"
        if m == 0:
            return "deja atteint"
        a, r = divmod(int(m), 12)
        if a and r:
            return f"{a} ans et {r} mois"
        return f"{a} ans" if a else f"{r} mois"

    if p.get("deja"):
        return [f"La cible de {eur(p['cible'])} est deja atteinte."]

    out = [f"Cible {eur(p['cible'])}, capital {eur(p['capital'])}, "
           f"versement {eur(p['versement'])} par mois. "
           f"Il manque {eur(p['manque'])}."]

    sc = p.get("sans_croissance") or {}
    if sc.get("mois") is not None:
        out.append(f"Sans aucune croissance, par les seuls versements : "
                   f"{dur(sc['mois'])}. C'est le seul chiffre de cette "
                   f"page qui ne depende d'aucune hypothese.")
    elif sc.get("versement_pour_mois") is not None:
        out.append(f"Sans aucune croissance, tenir la date demanderait "
                   f"{eur(sc['versement_pour_mois'])} par mois.")

    if p.get("mois_vise"):
        t = p.get("taux_exige")
        if t is None:
            out.append(f"Pour y etre en {dur(p['mois_vise'])}, aucun taux "
                       f"atteignable ne suffit avec ce capital et ce "
                       f"versement : c'est le versement qu'il faut bouger.")
        else:
            out.append(f"Pour y etre en {dur(p['mois_vise'])} avec ce "
                       f"versement, l'arithmetique reclame {pc(t)} par an. "
                       f"Elle ne dit pas ou le trouver.")
            ti = p.get("taux_exige_net_impot")
            if ti is not None:
                out.append(f"Et {pc(ti)} par an si les {eur(p['cible'])} "
                           f"doivent rester APRES le prelevement "
                           f"forfaitaire de {pc(p['impot'])} sur le gain — "
                           f"un seul denouement a la fin, donc un "
                           f"plancher : revendre souvent coute plus.")
        ve = p.get("versement_exige") or {}
        for hyp in sorted(ve):
            if ve[hyp] is not None:
                out.append(f"  — a {pc(hyp)} par an : {eur(ve[hyp])} "
                           f"par mois suffiraient.")

    if p.get("taux_pose") is not None:
        out.append(f"A {pc(p['taux_pose'])} par an — votre hypothese — : "
                   f"{dur(p.get('duree_au_taux_pose'))}.")

    out.append(RAPPEL)
    return out
