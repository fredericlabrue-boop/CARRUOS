"""« TLX a baisse de 25 % : est-ce qu'il va y avoir un rebond ? »

A QUOI CA REPOND

La question « va-t-il rebondir ? » demande l'avenir, et personne ne le
voit — ni ce programme, ni le modele de langage branche dessus, qui ne
voit meme pas les cours. Sa moitie mesurable, en revanche, se mesure : sur
tout l'historique de CE titre, chaque fois qu'il est tombe d'autant sous
son dernier sommet, qu'a-t-il fait ensuite ? Et a cote, ce que le titre
fait un jour quelconque — sans ce taux de base, « 60 % de hausses apres
une chute » ne dit rien sur un titre qui monte 60 % du temps.

COMMENT C'EST MESURE

* Un EPISODE commence le jour ou la cloture passe sous le dernier sommet
  de plus du seuil. Il faut un NOUVEAU sommet pour qu'un autre commence :
  une meme chute qui s'enfonce ne compte qu'une fois.
* Pour chaque episode, a 1, 3, 6 et 12 mois : le titre etait-il plus haut
  qu'au jour de l'episode, et avait-il retrouve son ancien sommet.
* Chaque proportion avec son intervalle de Wilson ; sous MINI_EPISODES,
  aucune n'est donnee. Une chute de 25 % arrive quelques fois en vingt
  ans : le plus souvent, la vraie reponse est « trop peu de cas ».

CE QUE LE TABLEAU NE PEUT PAS DIRE

Un titre encore cote aujourd'hui est, par construction, un titre qui
s'est releve de ses chutes passees. Ceux qui ne se sont pas releves ont
quitte la cote et ne sont dans aucune serie qu'on peut charger. Ce
tableau FLATTE donc le rebond — c'est ecrit a chaque affichage.

    py -m equity_scanner.rebond TLX.DE 25
"""

from __future__ import annotations

import math
import re
import sys

import numpy as np
import pandas as pd

# Les horizons, ecrits avant toute mesure : 1, 3, 6 et 12 mois de seances.
HORIZONS = (("1 mois", 21), ("3 mois", 63), ("6 mois", 126), ("1 an", 252))

# Sous ce nombre d'episodes, aucune proportion : a sept cas, un intervalle
# de Wilson couvre presque tout. Le meme seuil que SI JE GARDE…
MINI_EPISODES = 8

# Le seuil par defaut quand la question n'en donne pas et que le titre
# n'est pas en recul : une chute « de marche baissier ».
SEUIL_DEFAUT = 20
SEUIL_MINI, SEUIL_MAXI = 5, 90

RAPPEL_SURVIVANT = (
    "Un titre encore coté aujourd'hui est, par construction, un titre qui "
    "s'est relevé de ses chutes passées : ceux qui ne se sont pas relevés "
    "ont quitté la cote et ne sont dans aucune série. Ce tableau flatte "
    "donc le rebond.")
RAPPEL = (
    "Ce que ces chutes ont été SUIVIES de sur ce titre, pas ce que la "
    "chute d'aujourd'hui annonce. Aucune hypothèse n'a passé sa Phase 0 : "
    "ce n'est pas un avis.")
RAPPEL_GENERAL = (
    "« Est-ce bien d'acheter ce qui a chuté ? » ne se tranche pas en "
    "général : cela dépend du titre, de la profondeur de la chute, de la "
    "durée — et de ceux qui ne se sont jamais relevés, absents de toute "
    "série. Ce qui se mesure, c'est ce qu'un titre précis a fait après ses "
    "propres chutes. Posez la question sur un titre : « TLX.DE a baissé de "
    "25 %, rebond ? ».")


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def _cloture(d) -> pd.Series | None:
    if d is None:
        return None
    c = d["close"] if isinstance(d, pd.DataFrame) else d
    c = pd.Series(c, dtype=float).dropna()
    c = c[c > 0]
    return c if len(c) > 30 else None


def etat(d) -> dict | None:
    """Ou en est le titre : son recul sous le dernier sommet, et depuis
    quand. Un fait, sans aucune prevision."""
    c = _cloture(d)
    if c is None:
        return None
    sommet = c.cummax()
    i = int(np.flatnonzero(c.to_numpy() >= sommet.to_numpy())[-1])
    return {"cours": round(float(c.iloc[-1]), 4),
            "sommet": round(float(sommet.iloc[-1]), 4),
            "date_sommet": str(c.index[i].date()),
            "seances_depuis": int(len(c) - 1 - i),
            "recul_pct": round((float(c.iloc[-1]) / float(sommet.iloc[-1])
                                - 1) * 100, 1),
            "depuis": str(c.index[0].date())}


def seuil_de(question: str, e: dict | None) -> int:
    """Le seuil de chute : celui que la question NOMME (« baisse de 25 % »),
    sinon le recul actuel du titre arrondi aux 5 points inferieurs, sinon
    SEUIL_DEFAUT."""
    m = re.search(r"(\d{1,2}(?:[.,]\d+)?)\s*(?:%|pour ?cent|pourcent)",
                  question or "")
    if m:
        v = float(m.group(1).replace(",", "."))
        if SEUIL_MINI <= v <= SEUIL_MAXI:
            return int(round(v))
    if e and e.get("recul_pct") is not None and -e["recul_pct"] >= 10:
        return int(min(SEUIL_MAXI, 5 * math.floor(-e["recul_pct"] / 5)))
    return SEUIL_DEFAUT


def _pc(k: int, n: int) -> list:
    b, h = wilson(k, n)
    return [round(b * 100, 1), round(h * 100, 1)]


def apres_chute(d, seuil_pct: float) -> dict:
    """Chaque episode de chute de `seuil_pct` % sous le dernier sommet, et
    ce qui a suivi a chaque horizon, a cote du taux de base du titre."""
    c = _cloture(d)
    out = {"seuil": int(seuil_pct), "episodes": 0, "horizons": []}
    if c is None:
        out["erreur"] = "historique insuffisant"
        return out
    px = c.to_numpy()
    sommet = np.maximum.accumulate(px)
    recul = px / sommet - 1.0
    s = -abs(seuil_pct) / 100.0
    debuts, arme = [], True
    for t in range(1, len(px)):
        if px[t] >= sommet[t]:
            arme = True            # nouveau sommet : un autre episode peut venir
        elif arme and recul[t] <= s:
            debuts.append(t)
            arme = False
    out["episodes"] = len(debuts)
    out["depuis"] = str(c.index[0].date())
    out["dates"] = [str(c.index[t].date()) for t in debuts]
    for lib, h in HORIZONS:
        # Le taux de base : un jour quelconque, meme horizon.
        if len(px) > h:
            av = px[h:] / px[:-h] - 1.0
            base = float((av > 0).mean() * 100)
        else:
            base = None
        cas = [t for t in debuts if t + h < len(px)]
        n = len(cas)
        ligne = {"libelle": lib, "seances": h, "n": n,
                 "base_pct": None if base is None else round(base, 1)}
        if n:
            r = np.array([px[t + h] / px[t] - 1.0 for t in cas])
            k = int((r > 0).sum())
            revenu = int(sum(1 for t in cas
                             if px[t + 1:t + h + 1].max() >= sommet[t]))
            ligne.update({"hausses": k, "revenu_au_sommet": revenu,
                          "mediane": round(float(np.median(r)) * 100, 1),
                          "pire": round(float(r.min()) * 100, 1),
                          "meilleure": round(float(r.max()) * 100, 1)})
            if n >= MINI_EPISODES:
                w = _pc(k, n)
                ligne["wilson"] = w
                ligne["part"] = round(k / n * 100, 1)
                ligne["indiscernable"] = (base is not None
                                          and w[0] <= base <= w[1])
        out["horizons"].append(ligne)
    return out


def _n(x, dec=1) -> str:
    return f"{x:.{dec}f}".replace(".", ",").replace("-", "−")


def lignes(e: dict | None, m: dict | None) -> list[str]:
    """Les phrases du dossier. Chaque chiffre vient de `e` ou de `m`."""
    out = []
    if e:
        out.append(f"Aujourd'hui : {_n(e['recul_pct'])} % sous le dernier "
                   f"sommet ({_n(e['sommet'], 2)} le {e['date_sommet']}), "
                   f"{e['seances_depuis']} séances plus tard.")
    if not m:
        return out + ["La mesure des chutes passées n'a pas pu être faite."]
    if m.get("erreur"):
        return out + [f"Chutes passées : {m['erreur']}."]
    n = m["episodes"]
    out.append(f"Chutes de {m['seuil']} % ou plus sous un sommet, depuis "
               f"{m.get('depuis', '?')} : {n} épisode{'s' if n > 1 else ''}"
               + (f" ({', '.join(m['dates'][-6:])}"
                  + (" …" if n > 6 else "") + ")." if n else "."))
    if n == 0:
        return out + ["Aucune chute de cette profondeur sur l'historique "
                      "chargé : rien à comparer."]
    for h in m["horizons"]:
        if not h["n"]:
            out.append(f"  {h['libelle']} après : pas encore de recul "
                       f"suffisant pour le mesurer.")
            continue
        base = ("" if h["base_pct"] is None else
                f" ; un jour quelconque : {_n(h['base_pct'])} % de hausses")
        if h.get("wilson"):
            lecture = ("dans le bruit" if h.get("indiscernable")
                       else "écart net")
            out.append(f"  {h['libelle']} après : {h['hausses']} fois plus "
                       f"haut sur {h['n']} ({_n(h['wilson'][0])}–"
                       f"{_n(h['wilson'][1])} %){base} — {lecture}. "
                       f"Médiane {_n(h['mediane'])} %, pire "
                       f"{_n(h['pire'])} %, ancien sommet retrouvé "
                       f"{h['revenu_au_sommet']} fois.")
        else:
            out.append(f"  {h['libelle']} après : {h['hausses']} fois plus "
                       f"haut sur {h['n']} — trop peu de cas pour une "
                       f"proportion{base}. Pire {_n(h['pire'])} %, "
                       f"meilleure {_n(h['meilleure'])} %.")
    return out + ["", RAPPEL_SURVIVANT, RAPPEL]


def main(argv=None) -> None:
    a = list(sys.argv[1:] if argv is None else argv)
    if not a:
        print(__doc__)
        return
    from . import cache as ch
    d = ch.charge(a[0].upper(), annees=20)
    e = etat(d)
    s = int(a[1]) if len(a) > 1 else seuil_de("", e)
    print(f"\n  {a[0].upper()} — après une chute de {s} %\n")
    for x in lignes(e, apres_chute(d, s)):
        print("  " + x)


if __name__ == "__main__":
    main()
