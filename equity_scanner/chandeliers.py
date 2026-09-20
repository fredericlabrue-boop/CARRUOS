"""Lecture des chandeliers : des formes mesurees, et ce qui a suivi.

CE QUE CE MODULE NE FAIT PAS, ET POURQUOI
-----------------------------------------
Il ne dit pas qu'un marteau est haussier. Les manuels l'affirment ;
personne ici ne l'a verifie, et le projet ne publie pas ce qu'il n'a pas
mesure. Un nom de figure porte deja une direction — « etoile filante »,
« trois corbeaux noirs » — et c'est exactement le verdict directionnel
que le reste du programme refuse.

CE QU'IL FAIT
-------------
Deux choses, separees net :

  1. Il DETECTE la forme. Un harami est une relation geometrique entre
     deux bougies : le corps de la seconde tient entierement dans celui
     de la premiere. C'est verifiable a la regle, ce n'est pas une
     opinion. Les seuils sont ecrits ci-dessous, une fois, AVANT toute
     mesure.

  2. Il MESURE ce qui a suivi, sur CE titre, et le compare au TAUX DE
     BASE du titre. C'est la comparaison qui compte : « 56 % de hausses
     dans les dix seances apres un marteau » ne veut rien dire sur un
     titre qui monte 56 % du temps de toute facon. Le module affiche
     l'ecart au taux de base et l'intervalle de Wilson ; quand
     l'intervalle contient le taux de base, il ecrit que la figure est
     indiscernable du hasard sur ce titre.

Aucune figure n'entre dans une regle d'entree ou de sortie. Les treize
blocs de la specification ne bougent pas. C'est une aide a la LECTURE
d'un graphique, pas un signal.

    py -m equity_scanner.chandeliers NVDA
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

VERSION = "chandeliers-v1.0"

# --------------------------------------------------------------------
# Les seuils. Ecrits ICI, une fois, avant toute mesure.
#
# Les changer apres avoir regarde les resultats serait la meme peche que
# celle que le protocole interdit sur les parametres de strategie : avec
# huit seuils, on finit toujours par trouver une combinaison qui fait
# briller une figure. `test_moteur` les epingle.
# --------------------------------------------------------------------
SEUILS = {
    "doji_corps": 0.10,        # corps <= 10 % de l'etendue -> doji
    "petit_corps": 0.35,       # corps <= 35 % -> "petit corps"
    "grand_corps": 0.60,       # corps >= 60 % -> "grand corps"
    "marubozu": 0.90,          # corps >= 90 % -> presque pas d'ombre
    "ombre_longue": 2.0,       # l'ombre principale >= 2 x corps
    # L'ombre OPPOSEE se juge sur l'ETENDUE, pas sur le corps. Premiere
    # version : « <= 1 x corps ». Sur une etoile filante le corps fait
    # 3 % de l'etendue, donc la regle exigeait une ombre opposee de
    # moins de 3 % — aucune vraie bougie ne passait, et le detecteur ne
    # trouvait jamais ni etoile filante ni marteau inverse.
    "ombre_opposee": 0.15,     # <= 15 % de l'etendue
    "corps_tiers": 0.66,       # le corps dans le tiers haut (ou bas)
    "tendance_barres": 5,      # contexte : sur combien de barres
    "tendance_seuil": 0.02,    # +/- 2 % pour dire "apres une hausse"
    # Une barre plus etroite que 0,3 ATR est du bruit : tous les
    # rapports d'ombre y explosent et la figure ne veut rien dire.
    "etendue_mini_atr": 0.30,
    # Et un plancher ABSOLU, en part du cours : une seance ou le titre
    # n'a bouge que de deux centimes n'est pas un doji, c'est une
    # seance sans echange. Le garde-fou en ATR ne suffit pas — quand
    # toutes les barres recentes sont plates, l'ATR l'est aussi et le
    # rapport passe.
    "etendue_mini_pct": 0.0015,
}

# Les horizons auxquels on regarde ce qui a suivi. Fixes aussi.
HORIZONS = (1, 5, 10, 20)

# Occurrences en dessous desquelles on ne publie aucun taux : sous dix
# cas, l'intervalle de Wilson couvre a peu pres tout.
MINI_CAS = 10


def _mesures(d: pd.DataFrame) -> dict:
    """Les grandeurs de base de chaque bougie, en numpy.

    Tout le reste s'exprime avec celles-la. Les calculer une fois evite
    de les recalculer seize fois, une par figure.
    """
    o = d["open"].to_numpy(float)
    h = d["high"].to_numpy(float)
    b = d["low"].to_numpy(float)
    c = d["close"].to_numpy(float)
    etendue = h - b
    corps = np.abs(c - o)
    haut_corps = np.maximum(o, c)
    bas_corps = np.minimum(o, c)
    # Division protegee : une bougie plate a une etendue nulle.
    with np.errstate(divide="ignore", invalid="ignore"):
        part = np.where(etendue > 0, corps / etendue, 0.0)
    return {
        "o": o, "h": h, "b": b, "c": c,
        "etendue": etendue, "corps": corps,
        "haut_corps": haut_corps, "bas_corps": bas_corps,
        "part_corps": part,
        "verte": c > o, "rouge": c < o,
        "ombre_haute": h - haut_corps,
        "ombre_basse": bas_corps - b,
    }


def _contexte(c: np.ndarray, n: int, seuil: float) -> tuple:
    """Ce qui precede la bougie : hausse, baisse, ou ni l'un ni l'autre.

    Un marteau et un pendu ont EXACTEMENT la meme forme. Ce qui les
    distingue est ce qui precede. Sans contexte, les deux noms designent
    la meme chose et l'un des deux est faux.
    """
    prec = np.roll(c, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        var = np.where(prec > 0, c / prec - 1.0, 0.0)
    var[:n] = 0.0
    return var >= seuil, var <= -seuil


def _assez_large(m: dict, atr: np.ndarray | None, s: dict) -> np.ndarray:
    """Une bougie trop etroite ne porte aucune figure lisible.

    Deux garde-fous, parce qu'un seul ne suffit pas. Relatif a l'ATR :
    la barre doit etre d'une amplitude comparable a l'habitude du titre.
    Et absolu, en part du cours : quand toutes les barres recentes sont
    plates, l'ATR l'est aussi et le rapport passe alors que rien ne
    s'est echange.
    """
    ok = (m["etendue"] > 0) & (m["etendue"] >= s["etendue_mini_pct"] * m["c"])
    if atr is not None:
        ok &= m["etendue"] >= s["etendue_mini_atr"] * atr
    return ok


def figures(d: pd.DataFrame, seuils: dict | None = None) -> dict:
    """Detecte chaque figure. Rend un masque booleen par figure.

    Aucune interpretation ici : seulement de la geometrie. Le nom des
    figures est celui d'usage, parce que c'est celui des manuels que
    Frederic lira ailleurs — mais le nom ne vaut pas demonstration, et
    `suivi()` est la pour le rappeler en chiffres.
    """
    s = dict(SEUILS, **(seuils or {}))
    m = _mesures(d)
    n = len(d)
    atr = (d["atr14"].to_numpy(float)
           if "atr14" in d.columns else None)
    large = _assez_large(m, atr, s)
    hausse, baisse = _contexte(m["c"], int(s["tendance_barres"]),
                               s["tendance_seuil"])

    petit = m["part_corps"] <= s["petit_corps"]
    grand = m["part_corps"] >= s["grand_corps"]
    doji = m["part_corps"] <= s["doji_corps"]

    # Le corps est-il dans le tiers haut, ou dans le tiers bas ?
    # C'est ce qui fait la silhouette, autant que la longueur de l'ombre.
    with np.errstate(divide="ignore", invalid="ignore"):
        pos_bas = np.where(m["etendue"] > 0,
                           (m["bas_corps"] - m["b"]) / m["etendue"], 0.0)
        pos_haut = np.where(m["etendue"] > 0,
                            (m["h"] - m["haut_corps"]) / m["etendue"], 0.0)
    corps_en_haut = pos_bas >= s["corps_tiers"]
    corps_en_bas = pos_haut >= s["corps_tiers"]

    # Marteau : petit corps DANS LE TIERS HAUT, longue ombre basse, et
    # presque pas d'ombre haute. Pendu : la meme chose apres une hausse.
    forme_marteau = (petit & corps_en_haut
                     & (m["ombre_basse"] >= s["ombre_longue"] * m["corps"])
                     & (m["ombre_haute"] <= s["ombre_opposee"] * m["etendue"])
                     & large)
    # Etoile filante : longue ombre HAUTE, corps dans le tiers bas,
    # apres une hausse. Marteau inverse : la meme forme apres une baisse.
    forme_etoile = (petit & corps_en_bas
                    & (m["ombre_haute"] >= s["ombre_longue"] * m["corps"])
                    & (m["ombre_basse"] <= s["ombre_opposee"] * m["etendue"])
                    & large)

    def deux(prev, cur):
        """Masque d'une figure a deux bougies, aligne sur la SECONDE."""
        out = np.zeros(n, dtype=bool)
        if n >= 2:
            out[1:] = prev[:-1] & cur[1:]
        return out

    # --- figures a deux bougies -------------------------------------
    hc, bc = m["haut_corps"], m["bas_corps"]
    corps_dedans = np.zeros(n, dtype=bool)
    corps_dehors = np.zeros(n, dtype=bool)
    if n >= 2:
        corps_dedans[1:] = (hc[1:] <= hc[:-1]) & (bc[1:] >= bc[:-1])
        corps_dehors[1:] = (hc[1:] >= hc[:-1]) & (bc[1:] <= bc[:-1])
    grand_prec = np.zeros(n, dtype=bool)
    large_prec = np.zeros(n, dtype=bool)
    if n >= 2:
        grand_prec[1:] = grand[:-1]
        large_prec[1:] = large[:-1]

    rouge_prec = np.zeros(n, dtype=bool)
    verte_prec = np.zeros(n, dtype=bool)
    if n >= 2:
        rouge_prec[1:] = m["rouge"][:-1]
        verte_prec[1:] = m["verte"][:-1]

    # Penetrante / nuage noir : la seconde ouvre au-dela de la premiere
    # et clot au-dela de son milieu, sans la couvrir entierement.
    milieu = np.zeros(n)
    bas_prec = np.zeros(n)
    haut_prec = np.zeros(n)
    if n >= 2:
        milieu[1:] = (hc[:-1] + bc[:-1]) / 2.0
        bas_prec[1:] = bc[:-1]
        haut_prec[1:] = hc[:-1]

    fig = {
        "doji": doji & large,
        "marubozu_hausse": (m["part_corps"] >= s["marubozu"]) & m["verte"] & large,
        "marubozu_baisse": (m["part_corps"] >= s["marubozu"]) & m["rouge"] & large,
        "marteau": forme_marteau & baisse,
        "pendu": forme_marteau & hausse,
        "etoile_filante": forme_etoile & hausse,
        "marteau_inverse": forme_etoile & baisse,
        "harami_hausse": corps_dedans & grand_prec & large_prec & rouge_prec & m["verte"],
        "harami_baisse": corps_dedans & grand_prec & large_prec & verte_prec & m["rouge"],
        "avalement_hausse": corps_dehors & large & rouge_prec & m["verte"] & grand,
        "avalement_baisse": corps_dehors & large & verte_prec & m["rouge"] & grand,
        "penetrante": (rouge_prec & m["verte"] & large & large_prec
                       & (m["o"] < bas_prec) & (m["c"] > milieu)
                       & (m["c"] < haut_prec)),
        "nuage_noir": (verte_prec & m["rouge"] & large & large_prec
                       & (m["o"] > haut_prec) & (m["c"] < milieu)
                       & (m["c"] > bas_prec)),
    }

    # --- figures a trois bougies ------------------------------------
    if n >= 3:
        petit2 = np.zeros(n, dtype=bool)
        rouge1 = np.zeros(n, dtype=bool)
        verte1 = np.zeros(n, dtype=bool)
        grand1 = np.zeros(n, dtype=bool)
        milieu1 = np.zeros(n)
        petit2[2:] = petit[1:-1]
        rouge1[2:] = m["rouge"][:-2]
        verte1[2:] = m["verte"][:-2]
        grand1[2:] = grand[:-2]
        milieu1[2:] = (hc[:-2] + bc[:-2]) / 2.0
        fig["etoile_matin"] = (rouge1 & grand1 & petit2 & m["verte"] & grand
                               & (m["c"] > milieu1) & large)
        fig["etoile_soir"] = (verte1 & grand1 & petit2 & m["rouge"] & grand
                              & (m["c"] < milieu1) & large)
        # Trois soldats / trois corbeaux : trois grands corps de suite
        # dans le meme sens, chacun cloturant au-dela du precedent.
        vv = m["verte"] & grand & large
        rr = m["rouge"] & grand & large
        monte = np.zeros(n, dtype=bool)
        descend = np.zeros(n, dtype=bool)
        monte[1:] = m["c"][1:] > m["c"][:-1]
        descend[1:] = m["c"][1:] < m["c"][:-1]
        soldats = np.zeros(n, dtype=bool)
        corbeaux = np.zeros(n, dtype=bool)
        soldats[2:] = (vv[2:] & vv[1:-1] & vv[:-2]
                       & monte[2:] & monte[1:-1])
        corbeaux[2:] = (rr[2:] & rr[1:-1] & rr[:-2]
                        & descend[2:] & descend[1:-1])
        fig["trois_soldats"] = soldats
        fig["trois_corbeaux"] = corbeaux
    else:
        for k in ("etoile_matin", "etoile_soir", "trois_soldats",
                  "trois_corbeaux"):
            fig[k] = np.zeros(n, dtype=bool)

    return fig


# --------------------------------------------------------------------
# Ce qui a suivi
# --------------------------------------------------------------------

def wilson(succes: int, total: int, z: float = 1.96) -> tuple:
    """Intervalle de Wilson. Jamais un taux seul : c'est la regle."""
    if total <= 0:
        return (0.0, 0.0, 100.0)
    p = succes / total
    den = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / den
    demi = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / den
    return (max(0.0, (centre - demi) * 100), p * 100,
            min(100.0, (centre + demi) * 100))


def _avance(c: np.ndarray, h: int) -> np.ndarray:
    """Rendement a h barres. NaN la ou l'avenir manque."""
    out = np.full(len(c), np.nan)
    if h < len(c):
        out[:-h] = c[h:] / c[:-h] - 1.0
    return out


def suivi(d: pd.DataFrame, masque: np.ndarray,
          horizons=HORIZONS) -> list[dict]:
    """Ce qui a suivi la figure, compare au taux de base du titre.

    La comparaison est le coeur du module. « 56 % de hausses » est un
    chiffre vide tant qu'on ne sait pas que le titre monte 54 % du temps
    quoi qu'il arrive.
    """
    c = d["close"].to_numpy(float)
    lignes = []
    for h in horizons:
        av = _avance(c, h)
        bon = np.isfinite(av)
        cas = masque & bon
        n = int(cas.sum())
        base_n = int(bon.sum())
        base_haut = int((av[bon] > 0).sum())
        base = base_haut / base_n * 100 if base_n else 0.0
        if n < MINI_CAS:
            lignes.append({"horizon": h, "n": n, "assez": False,
                           "base": round(base, 1)})
            continue
        haut = int((av[cas] > 0).sum())
        bas_ic, taux, haut_ic = wilson(haut, n)
        med = float(np.median(av[cas])) * 100
        med_base = float(np.median(av[bon])) * 100
        # Le point qui tranche : l'intervalle couvre-t-il le taux de base ?
        couvre = bas_ic <= base <= haut_ic
        lignes.append({
            "horizon": h, "n": n, "assez": True,
            "hausses": haut, "taux": round(taux, 1),
            "ic": (round(bas_ic, 1), round(haut_ic, 1)),
            "base": round(base, 1), "ecart": round(taux - base, 1),
            "median": round(med, 2), "median_base": round(med_base, 2),
            "indiscernable": bool(couvre),
        })
    return lignes


# --------------------------------------------------------------------
# Volume et prix — la place de l'"open interest" pour une action
# --------------------------------------------------------------------

def volume_prix(d: pd.DataFrame, horizons=HORIZONS) -> dict:
    """Les quatre etats du couple volume / prix, et ce qui a suivi.

    UNE ACTION N'A PAS D'OPEN INTEREST. C'est une notion de contrats a
    terme et d'options : le nombre de contrats ouverts non denoues. Une
    action existe en nombre fixe, il n'y a rien a ouvrir ni a denouer.
    Ce qui joue le meme role sur une action, c'est le VOLUME rapporte a
    son habitude — et c'est ce qu'on mesure ici.

    (L'open interest des OPTIONS d'une action existe, lui, et se lit
    ailleurs : voir `options.py`.)
    """
    if "rvol" in d.columns:
        rv = d["rvol"].to_numpy(float)
    else:
        v = d["volume"].to_numpy(float)
        moy = pd.Series(v).rolling(20).mean().to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            rv = np.where(moy > 0, v / moy, np.nan)
    c = d["close"].to_numpy(float)
    var = np.full(len(c), np.nan)
    var[1:] = c[1:] / c[:-1] - 1.0

    fort = rv >= 1.2
    faible = (rv < 1.2) & np.isfinite(rv)
    monte, baisse = var > 0, var < 0

    etats = {
        "hausse_volume_fort": monte & fort,
        "hausse_volume_faible": monte & faible,
        "baisse_volume_fort": baisse & fort,
        "baisse_volume_faible": baisse & faible,
    }
    return {k: suivi(d, np.nan_to_num(v, nan=False).astype(bool), horizons)
            for k, v in etats.items()}


# --------------------------------------------------------------------
# Libelles et mise en forme
# --------------------------------------------------------------------

NOMS = {
    "doji": "Doji",
    "marubozu_hausse": "Marubozu haussier",
    "marubozu_baisse": "Marubozu baissier",
    "marteau": "Marteau",
    "pendu": "Pendu",
    "etoile_filante": "Étoile filante",
    "marteau_inverse": "Marteau inversé",
    "harami_hausse": "Harami haussier",
    "harami_baisse": "Harami baissier",
    "avalement_hausse": "Avalement haussier",
    "avalement_baisse": "Avalement baissier",
    "penetrante": "Pénétrante",
    "nuage_noir": "Nuage noir",
    "etoile_matin": "Étoile du matin",
    "etoile_soir": "Étoile du soir",
    "trois_soldats": "Trois soldats blancs",
    "trois_corbeaux": "Trois corbeaux noirs",
    "hausse_volume_fort": "Hausse, volume au-dessus de son habitude",
    "hausse_volume_faible": "Hausse, volume en dessous",
    "baisse_volume_fort": "Baisse, volume au-dessus de son habitude",
    "baisse_volume_faible": "Baisse, volume en dessous",
}

FORMES = {
    "doji": "corps ≤ 10 % de l'étendue : ouverture et clôture presque "
            "au même prix",
    "marubozu_hausse": "corps ≥ 90 % de l'étendue, clôture au-dessus de "
                       "l'ouverture : presque pas d'ombre",
    "marubozu_baisse": "corps ≥ 90 % de l'étendue, clôture en dessous",
    "marteau": "petit corps en haut, ombre basse ≥ 2 × le corps, "
               "après une baisse de 2 % sur 5 séances",
    "pendu": "la même forme que le marteau, mais après une hausse",
    "etoile_filante": "petit corps en bas, ombre haute ≥ 2 × le corps, "
                      "après une hausse",
    "marteau_inverse": "la même forme, mais après une baisse",
    "harami_hausse": "corps de la 2ᵉ bougie entièrement dans celui de la "
                     "1ʳᵉ ; 1ʳᵉ rouge et grande, 2ᵉ verte",
    "harami_baisse": "même emboîtement ; 1ʳᵉ verte et grande, 2ᵉ rouge",
    "avalement_hausse": "corps de la 2ᵉ bougie contenant celui de la 1ʳᵉ ; "
                        "1ʳᵉ rouge, 2ᵉ verte et grande",
    "avalement_baisse": "même englobement ; 1ʳᵉ verte, 2ᵉ rouge et grande",
    "penetrante": "2ᵉ bougie verte, ouvre sous le corps de la 1ʳᵉ (rouge) "
                  "et clôture au-dessus de son milieu",
    "nuage_noir": "2ᵉ bougie rouge, ouvre au-dessus du corps de la 1ʳᵉ "
                  "(verte) et clôture sous son milieu",
    "etoile_matin": "grande rouge, petit corps, puis grande verte "
                    "clôturant au-dessus du milieu de la 1ʳᵉ",
    "etoile_soir": "grande verte, petit corps, puis grande rouge "
                   "clôturant sous le milieu de la 1ʳᵉ",
    "trois_soldats": "trois grands corps verts de suite, chacun clôturant "
                     "au-dessus du précédent",
    "trois_corbeaux": "trois grands corps rouges de suite, chacun "
                      "clôturant sous le précédent",
}

RAPPEL = (
    "Le nom d'une figure porte une direction que personne n'a vérifiée "
    "ici. Ce tableau ne dit pas ce qu'une figure annonce : il dit ce "
    "qu'elle a été suivie de, sur ce titre, et à combien cela diffère "
    "de ce que fait le titre un jour quelconque. Quand l'intervalle "
    "contient le taux de base, la figure est indiscernable du hasard.")


def lecture(d: pd.DataFrame, horizons=HORIZONS) -> dict:
    """Le tableau complet : chaque figure, ses occurrences, et la suite."""
    fig = figures(d)
    out = {"version": VERSION, "barres": len(d), "figures": [],
           "volume_prix": [], "rappel": RAPPEL,
           "derniere": str(d.index[-1].date()) if len(d) else "?"}
    for cle, masque in fig.items():
        n = int(masque.sum())
        # Ou en sommes-nous : la figure est-elle presente sur la
        # derniere bougie ? C'est la seule question du jour.
        out["figures"].append({
            "cle": cle, "nom": NOMS.get(cle, cle),
            "forme": FORMES.get(cle, ""),
            "n": n,
            "aujourdhui": bool(masque[-1]) if len(masque) else False,
            "suivi": suivi(d, masque, horizons) if n else [],
        })
    for cle, lignes in volume_prix(d, horizons).items():
        out["volume_prix"].append({"cle": cle, "nom": NOMS.get(cle, cle),
                                   "suivi": lignes})
    out["figures"].sort(key=lambda x: (not x["aujourdhui"], -x["n"]))

    # LE PIEGE DES COMPARAISONS MULTIPLES, chiffre sur place.
    # Dix-sept figures par quatre horizons font soixante-huit mesures
    # par titre. L'intervalle de Wilson est a 95 %, donc une mesure sur
    # vingt tombe a cote PAR CONSTRUCTION : environ trois « ecarts
    # nets » sont attendus sur chaque titre meme s'il n'y a rien a
    # trouver. Verifie sur douze univers de bruit pur : 4,5 % des
    # mesures ressortaient nettes, contre 5 % attendus.
    # Sans ce compte, Frederic lirait le premier ecart net comme une
    # decouverte. C'est exactement l'erreur que le protocole du projet
    # interdit sur les parametres de strategie.
    mesures = nets = 0
    for bloc in (out["figures"], out["volume_prix"]):
        for f in bloc:
            for x in f["suivi"]:
                if not x.get("assez"):
                    continue
                mesures += 1
                nets += bool(not x["indiscernable"])
    out["comptage"] = {
        "mesures": mesures, "nets": nets,
        "attendus_par_hasard": round(mesures * 0.05, 1),
        "phrase": (
            f"{mesures} mesures sur ce titre, dont {nets} affichent un "
            f"écart net. Environ {mesures * 0.05:.0f} sont attendues par "
            f"le seul hasard : l'intervalle est à 95 %, donc une mesure "
            f"sur vingt tombe à côté par construction. Un écart net "
            f"isolé ne vaut rien. Ce qui compterait, ce serait la même "
            f"figure nette sur plusieurs horizons À LA FOIS, et sur "
            f"plusieurs titres."),
    }
    return out


def texte(r: dict, largeur: int = 78) -> str:
    L = [f"\n  LECTURE DES CHANDELIERS — {r['barres']} bougies, "
         f"dernière le {r['derniere']}", ""]
    presentes = [f for f in r["figures"] if f["aujourdhui"]]
    if presentes:
        L.append("  SUR LA DERNIÈRE BOUGIE :")
        for f in presentes:
            L.append(f"    · {f['nom']}")
            L.append(f"        {f['forme']}")
        L.append("")
    else:
        L += ["  Aucune figure répertoriée sur la dernière bougie.", ""]

    L.append("  CE QUI A SUIVI, SUR CE TITRE")
    L.append(f"    {'figure':<24}{'cas':>5} {'horizon':>8} "
             f"{'hausses':>9} {'base':>7} {'écart':>7}")
    for f in r["figures"]:
        if not f["n"]:
            continue
        prem = True
        for s in f["suivi"]:
            if not s["assez"]:
                continue
            nom = f["nom"] if prem else ""
            cas = str(f["n"]) if prem else ""
            prem = False
            marque = "  indiscernable" if s["indiscernable"] else "  ÉCART NET"
            L.append(f"    {nom:<24}{cas:>5} {s['horizon']:>6} b "
                     f"{s['taux']:>7.1f} % {s['base']:>6.1f} % "
                     f"{s['ecart']:>+6.1f} pt{marque}")
        if prem:
            L.append(f"    {f['nom']:<24}{f['n']:>5}   moins de "
                     f"{MINI_CAS} cas exploitables")
    L.append("")
    L.append("  VOLUME ET PRIX  (une action n'a pas d'open interest)")
    for v in r["volume_prix"]:
        prem = True
        for s in v["suivi"]:
            if not s["assez"]:
                continue
            nom = v["nom"] if prem else ""
            prem = False
            marque = "  indiscernable" if s["indiscernable"] else "  ÉCART NET"
            L.append(f"    {nom:<42} {s['horizon']:>3} b "
                     f"{s['taux']:>6.1f} % base {s['base']:>5.1f} % "
                     f"{s['ecart']:>+5.1f} pt{marque}")
    L.append("")
    if r.get("comptage"):
        for ligne in _plie(r["comptage"]["phrase"], largeur):
            L.append("  " + ligne)
        L.append("")
    for ligne in _plie(r["rappel"], largeur):
        L.append("  " + ligne)
    return "\n".join(L + [""])


def _plie(texte: str, largeur: int) -> list[str]:
    mots, ligne, out = texte.split(), "", []
    for m in mots:
        if len(ligne) + len(m) + 1 > largeur:
            out.append(ligne)
            ligne = m
        else:
            ligne = (ligne + " " + m).strip()
    if ligne:
        out.append(ligne)
    return out


def rapport(ticker: str, annees: int = 10) -> dict:
    from . import cache as ch
    from .indicators import enrich
    d = enrich(ch.charge(ticker, annees=annees))
    r = lecture(d)
    r["ticker"] = ticker
    return r


def main() -> None:
    p = argparse.ArgumentParser(
        description="Lecture des chandeliers : formes mesurées, suite mesurée")
    p.add_argument("ticker")
    p.add_argument("--annees", type=int, default=10)
    a = p.parse_args()
    print(texte(rapport(a.ticker.upper(), a.annees)))


if __name__ == "__main__":
    main()
