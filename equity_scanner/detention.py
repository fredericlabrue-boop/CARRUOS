"""« Si je garde ce titre deux mois, qu'est-ce que ca a donne ? »

A QUOI CA REPOND

Frederic : « Tesla, j'aimerais garder deux mois : tu me conseilles quoi ?
Est-ce que c'est bien ? » et « celui-la c'est plutot une semaine, celui-la
plutot un an ». La premiere moitie de chaque question a une reponse
MESURABLE, et ce module la donne : sur tout l'historique du titre, chaque
periode de cette duree, ce qu'elle a rendu, a cote de ce qu'a rendu
l'indice sur les memes dates.

Ce qu'il ne donne pas : « c'est bien », « c'est un titre a une semaine ».
Ce serait choisir, apres coup, la duree qui a le mieux marche sur un passe
connu — la peche que le protocole interdit, et cinq horizons compares
donnent cinq chances d'en voir un briller par hasard. Aucune hypothese du
programme n'a passe sa Phase 0 ; un avis serait une opinion deguisee. Le
tableau est dans un ordre FIXE, du plus court au plus long, et n'est
jamais trie sur ce qu'il affiche.

COMMENT C'EST MESURE

* Des periodes qui ne se CHEVAUCHENT PAS, comptees a rebours depuis la
  derniere seance : vingt ans ne font que quatre periodes de cinq ans, et
  le tableau le dit au lieu de faire semblant d'en avoir mille. La part
  des periodes en hausse porte son intervalle de Wilson ; sous
  MINI_PERIODES, elle n'est pas donnee.
* Sur les clotures, comme tout le programme.
* Le recul INTERNE : de combien le titre est descendu sous le prix
  d'achat, au pire, avant la fin de la periode. C'est ce qu'il faut
  supporter sans vendre pour avoir le resultat de la derniere colonne.
* Contre l'indice (SPY ou ^STOXX selon la place) sur exactement les memes
  dates : une periode en hausse dans un marche qui monte plus vite n'est
  pas la meme chose qu'une periode qui bat le marche.
* « Achete lundi, vendu vendredi » : de l'OUVERTURE de la premiere seance
  de la semaine a la CLOTURE de la derniere, contre le taux de base du
  titre — la semaine prise de cloture a cloture. Quand l'intervalle de
  Wilson contient le taux de base, c'est dit : indiscernable du hasard.

    py -m equity_scanner.detention TSLA 2 mois
"""

from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

# L'ordre est celui des durees, jamais celui des resultats.
HORIZONS = (("1 semaine", 5), ("1 mois", 21), ("3 mois", 63),
            ("1 an", 252), ("5 ans", 1260))

# Seances par unite : 5 par semaine, 21 par mois, 252 par an.
UNITES = {"jours": 1, "semaines": 5, "mois": 21, "ans": 252}

# En dessous, la part des periodes en hausse n'est pas donnee : a sept
# periodes, un intervalle de Wilson couvre presque tout de 0 a 100 %.
MINI_PERIODES = 8

RAPPEL = ("Ce que ces durées ont DONNÉ sur ce titre, pas ce qu'elles vont "
          "donner. Aucune n'est « la bonne » : choisir celle qui a le "
          "mieux marché ici serait ajuster sur un passé connu, et cinq "
          "durées comparées donnent cinq chances d'en voir une briller par "
          "hasard. Aucune hypothèse n'a passé sa Phase 0 : ce n'est pas un "
          "avis.")

RAPPEL_BIEN = ("« Est-ce bien ? » n'a pas de réponse mesurable. Ce qui se "
               "mesure : combien de fois cette durée a fini en hausse, de "
               "combien, ce qu'il a fallu supporter en chemin, et si elle a "
               "fait mieux que l'indice sur les mêmes dates.")


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def _wpc(k: int, n: int) -> list:
    """L'intervalle de Wilson EN POURCENTS, tel qu'il s'affiche : le
    dossier du majordome doit porter les nombres que ses phrases citent."""
    a, b = wilson(k, n)
    return [round(a * 100, 1), round(b * 100, 1)]


def seances(duree: float, unite: str) -> int:
    """« 2 mois » -> 42 seances. Au moins une seance."""
    return max(1, int(round(float(duree) * UNITES.get(unite, 21))))


def libelle(s: int) -> str:
    for nom, h in HORIZONS:
        if h == s:
            return nom
    if s % 252 == 0:
        return f"{s // 252} an" + ("s" if s // 252 > 1 else "")
    if s % 21 == 0:
        return f"{s // 21} mois"
    if s % 5 == 0:
        return f"{s // 5} semaine" + ("s" if s // 5 > 1 else "")
    return f"{s} séance" + ("s" if s > 1 else "")


def _cloture(d) -> pd.Series | None:
    if d is None or "close" not in getattr(d, "columns", []):
        return None
    c = d["close"].dropna().astype(float)
    c = c[c > 0]
    return c if len(c) >= 30 else None


def _bornes(n: int, h: int) -> list[tuple[int, int]]:
    """Les periodes de h seances, sans chevauchement, comptees a rebours
    depuis la derniere seance. (depart, fin) en positions."""
    out, fin = [], n - 1
    while fin - h >= 0:
        out.append((fin - h, fin))
        fin -= h
    return out[::-1]


def mesure(d, h: int, bench=None, objectif: float | None = None) -> dict:
    """Toutes les periodes de h seances de l'historique, et ce qu'elles
    ont donne. Un dictionnaire de faits, sans verdict."""
    c = _cloture(d)
    base = {"seances": int(h), "libelle": libelle(int(h)), "periodes": 0}
    if c is None:
        return {**base, "erreur": "historique insuffisant"}
    bornes = _bornes(len(c), int(h))
    n = len(bornes)
    base["periodes"] = n
    base["depuis"] = str(c.index[0].date()) if n else ""
    if n == 0:
        return {**base, "erreur": f"moins de {h} séances d'historique"}
    px = c.to_numpy()
    var = np.array([(px[f] / px[a] - 1.0) * 100.0 for a, f in bornes])
    # Sous le prix d'achat, au pire : zero si le titre n'y est jamais
    # repasse — un « recul » positif ne voudrait rien dire.
    recul = np.minimum(0.0, np.array(
        [(px[a + 1:f + 1].min() / px[a] - 1.0) * 100.0 for a, f in bornes]))
    k = int((var > 0).sum())
    out = {**base,
           "hausses": k,
           "part": k / n if n >= MINI_PERIODES else None,
           "wilson": _wpc(k, n) if n >= MINI_PERIODES else None,
           "mediane": float(np.median(var)),
           "moyenne": float(var.mean()),
           "dispersion": float(var.std(ddof=1)) if n > 1 else None,
           "pire": float(var.min()), "meilleure": float(var.max()),
           "recul_median": float(np.median(recul)),
           "recul_pire": float(recul.min()),
           "derniere": {"du": str(c.index[bornes[-1][0]].date()),
                        "au": str(c.index[bornes[-1][1]].date()),
                        "variation": float(var[-1])}}

    # L'indice, sur exactement les memes dates.
    b = _cloture(bench)
    if b is not None:
        bi = b.reindex(c.index).ffill()
        paires = [(a, f) for a, f in bornes
                  if pd.notna(bi.iloc[a]) and pd.notna(bi.iloc[f])]
        if paires:
            vb = np.array([(bi.iloc[f] / bi.iloc[a] - 1.0) * 100.0
                           for a, f in paires])
            vt = np.array([(px[f] / px[a] - 1.0) * 100.0 for a, f in paires])
            kb = int((vt > vb).sum())
            nb = len(paires)
            out["indice"] = {
                "periodes": nb,
                "mediane": float(np.median(vb)),
                "hausses": int((vb > 0).sum()),
                "battu": kb,
                "part_battu": kb / nb if nb >= MINI_PERIODES else None,
                "wilson_battu": (_wpc(kb, nb)
                                 if nb >= MINI_PERIODES else None),
            }

    # Un objectif, s'il est donne : touche a un moment de la periode ?
    if objectif is not None:
        try:
            obj = float(objectif)
        except (TypeError, ValueError):
            obj = None
        if obj is not None and obj != 0:
            touche, delais = 0, []
            for a, f in bornes:
                seuil = px[a] * (1 + obj / 100.0)
                chemin = px[a + 1:f + 1]
                ok = (chemin >= seuil) if obj > 0 else (chemin <= seuil)
                if ok.any():
                    touche += 1
                    delais.append(int(np.argmax(ok)) + 1)
            out["objectif"] = {
                "cible": obj, "touche": touche,
                "part": touche / n if n >= MINI_PERIODES else None,
                "wilson": (_wpc(touche, n)
                           if n >= MINI_PERIODES else None),
                "seances_medianes": (float(np.median(delais))
                                     if delais else None)}
    return out


def lundi_vendredi(d) -> dict:
    """Achete a l'ouverture de la premiere seance de la semaine, vendu a la
    cloture de la derniere — contre la semaine prise de cloture a cloture.

    La difference entre les deux, c'est le trou du week-end : ce que le
    titre fait entre la cloture du vendredi et l'ouverture du lundi.
    """
    if d is None or not {"open", "close"} <= set(getattr(d, "columns", [])):
        return {"semaines": 0, "erreur": "ouvertures absentes"}
    x = d[["open", "close"]].dropna()
    x = x[(x["open"] > 0) & (x["close"] > 0)]
    if len(x) < 30:
        return {"semaines": 0, "erreur": "historique insuffisant"}
    iso = x.index.isocalendar()
    cle = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    g = x.groupby(cle.values)
    ouv = g["open"].first()
    clo = g["close"].last()
    semaine = (clo / ouv - 1.0) * 100.0
    precedente = clo.shift(1)
    base = ((clo / precedente - 1.0) * 100.0).dropna()
    semaine = semaine.iloc[1:]           # memes semaines que la base
    n, nb = len(semaine), len(base)
    if n < MINI_PERIODES or nb < MINI_PERIODES:
        return {"semaines": int(n), "erreur": "trop peu de semaines"}
    k, kb = int((semaine > 0).sum()), int((base > 0).sum())
    w = wilson(k, n)
    taux_base = kb / nb
    return {
        "semaines": int(n), "hausses": k, "part": k / n, "wilson": _wpc(k, n),
        "mediane": float(semaine.median()),
        "base_part": taux_base, "base_pct": round(taux_base * 100, 1),
        "base_mediane": float(base.median()),
        # L'intervalle contient-il le taux de base ? Alors rien ne
        # distingue « lundi -> vendredi » d'une semaine quelconque.
        "indiscernable": bool(w[0] <= taux_base <= w[1]),
    }


def tableau(d, bench=None) -> dict:
    """Les cinq durees usuelles et la semaine « lundi -> vendredi »."""
    return {"horizons": [mesure(d, h, bench) for _nom, h in HORIZONS],
            "lundi_vendredi": lundi_vendredi(d),
            "mini_periodes": MINI_PERIODES,
            "rappel": RAPPEL, "rappel_bien": RAPPEL_BIEN}


# ---------------------------------------------------------------------
# En phrases, pour le majordome et la ligne de commande
# ---------------------------------------------------------------------

def _pc(x, dec=1, signe=True) -> str:
    if x is None:
        return "—"
    s = f"{x:+.{dec}f}" if signe else f"{x:.{dec}f}"
    return s.replace(".", ",") + " %"


def lignes(m: dict) -> list[str]:
    """Une mesure, en phrases. Aucun chiffre qui ne soit dans `m`."""
    if m.get("erreur") or not m.get("periodes"):
        return [f"{m.get('libelle', '?')} : {m.get('erreur', 'rien à mesurer')}."]
    n = m["periodes"]
    out = [f"{m['libelle']} — {n} période(s) sans chevauchement depuis "
           f"le {m.get('depuis', '?')}."]
    if m.get("part") is not None:
        a, b = m["wilson"]
        out.append(f"En hausse à la fin : {m['hausses']} sur {n} "
                   f"(intervalle {a:.0f} à {b:.0f} %).")
    else:
        out.append(f"En hausse à la fin : {m['hausses']} sur {n} — trop "
                   f"peu de périodes pour en tirer une proportion.")
    out.append(f"Résultat médian {_pc(m['mediane'])} ; le pire "
               f"{_pc(m['pire'])}, le meilleur {_pc(m['meilleure'])}.")
    out.append(f"En chemin, recul médian sous le prix d'achat "
               f"{_pc(m['recul_median'])}, le pire {_pc(m['recul_pire'])}.")
    ind = m.get("indice")
    if ind:
        if ind.get("part_battu") is not None:
            a, b = ind["wilson_battu"]
            out.append(f"Mieux que l'indice sur les mêmes dates : "
                       f"{ind['battu']} sur {ind['periodes']} (intervalle "
                       f"{a:.0f} à {b:.0f} %) ; médiane de "
                       f"l'indice {_pc(ind['mediane'])}.")
        else:
            out.append(f"Mieux que l'indice : {ind['battu']} sur "
                       f"{ind['periodes']} ; médiane de l'indice "
                       f"{_pc(ind['mediane'])}.")
    o = m.get("objectif")
    if o:
        t = (f"Objectif {_pc(o['cible'], 0)} touché en cours de route : "
             f"{o['touche']} sur {n}")
        if o.get("wilson"):
            t += f" (intervalle {o['wilson'][0]:.0f} à " \
                 f"{o['wilson'][1]:.0f} %)"
        if o.get("seances_medianes") is not None:
            t += f", en {o['seances_medianes']:.0f} séances en médiane"
        out.append(t + ".")
    return out


def ligne_lundi(lv: dict) -> str:
    """« Achete lundi, vendu vendredi », contre une semaine quelconque."""
    if not lv or lv.get("erreur"):
        return ("Lundi → vendredi : " + (lv or {}).get("erreur", "rien à mesurer")
                + ".")
    a, b = lv["wilson"]
    return (f"Acheté à l'ouverture du lundi, vendu à la clôture du vendredi : "
            f"{lv['hausses']} semaines en hausse sur {lv['semaines']} "
            f"(intervalle {a:.0f} à {b:.0f} %), contre {lv['base_pct']:.0f} % "
            f"pour une semaine quelconque — "
            + ("indiscernable du hasard." if lv["indiscernable"]
               else "écart net, sur une seule mesure parmi plusieurs."))


def resume(m: dict) -> str:
    """Une duree, en une ligne : pour le tableau des cinq."""
    if m.get("erreur") or not m.get("periodes"):
        return f"{m.get('libelle', '?')} : {m.get('erreur', 'rien à mesurer')}."
    t = f"{m['libelle']} : {m['hausses']} en hausse sur {m['periodes']}"
    if m.get("wilson"):
        t += f" ({m['wilson'][0]:.0f} à {m['wilson'][1]:.0f} %)"
    t += f", médiane {_pc(m['mediane'])}, pire {_pc(m['pire'])}"
    ind = m.get("indice")
    if ind:
        t += f", mieux que l'indice {ind['battu']} sur {ind['periodes']}"
    return t + "."


def main(argv=None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return
    tk = args[0].upper()
    from . import cache as ch
    from .memoire import bench_de
    d = ch.charge(tk, annees=20)
    b = ch.charge(bench_de(tk), annees=20)
    if len(args) >= 3:
        h = seances(float(args[1].replace(",", ".")), args[2])
        for l in lignes(mesure(d, h, b)):
            print("  " + l)
        print()
    t = tableau(d, b)
    for m in t["horizons"]:
        for l in lignes(m):
            print("  " + l)
        print()
    print("  " + ligne_lundi(t["lundi_vendredi"]))
    print("\n  " + RAPPEL)


if __name__ == "__main__":
    main()
