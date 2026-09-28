"""« Je mets 800 €, je veux +50 € en une semaine : trouve-moi des actions. »

A QUOI CA REPOND

Frederic regle ses parametres — la somme, le gain vise en euros, la duree
— et le programme passe un univers entier (US, Europe) a la question qui
se MESURE : sur l'historique de chaque titre, combien de periodes de cette
duree ont donne ce gain, et combien ont coute la meme somme. Le reste —
« lesquelles vont le faire la semaine prochaine » — ne se mesure pas, et
la page le dit au lieu de le deviner.

COMMENT C'EST MESURE

* La somme devient un nombre ENTIER de titres, au cours du jour converti
  en euros : 800 € sur une action a 300 € n'en achetent que deux, soit
  600 € investis, et +50 € demandent alors +8,3 %, pas +6,25 %. Un titre
  plus cher que la somme n'est pas achetable, et c'est ecrit.
* Les frais sont ceux du backtest (spread, commission et glissement, par
  cote), plus des frais fixes par ordre si on les donne. Le gain vise est
  NET de frais, donc le mouvement demande est plus grand. L'impot n'est
  pas compte, et la page le dit.
* Des periodes qui ne se chevauchent pas, comptees a rebours depuis la
  derniere seance, sur les clotures — les memes que la carte SI JE
  GARDE… Pour chacune : le gain a-t-il ete touche en chemin, la meme
  perte a-t-elle ete touchee, lequel D'ABORD, et ou la periode a fini.
* Chaque proportion porte son intervalle de Wilson ; sous MINI_PERIODES,
  aucune n'est donnee.

CE QUE LE PROGRAMME REFUSE, ET POURQUOI

* « Les actions potentielles ». Aucune hypothese sur ces titres n'a ete
  specifiee ni testee. Les tris portent chacun sur UN fait mesure, et la
  colonne de la perte est toujours a cote de celle du gain.
* L'illusion principale, chiffree sur place : les titres qui ont le plus
  souvent donne +50 € en une semaine sont, presque toujours, ceux qui ont
  le plus souvent COUTE 50 €. Toucher un seuil, c'est d'abord de
  l'amplitude. La page calcule la correlation entre les deux colonnes sur
  la liste qu'elle affiche.
* « Gain d'abord » sur dix ans, c'est la tendance PASSEE du titre — et un
  indice d'aujourd'hui ne contient que les societes qui ont survecu. Ce
  n'est pas une prevision.
* Une heure. Une bougie journaliere ne contient aucune heure
  intermediaire, et le programme n'a pas d'historique intraday (chantier
  7) : la demande est refusee avec sa raison, plutot que remplie avec des
  chiffres qui n'existent pas.

    py -m equity_scanner.recherche nasdaq100 800 50 "1 semaine"
"""

from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

from . import detention as dt

# Les durees proposees, dans l'ordre des durees. Une autre se tape.
DUREES = (("1 jour", 1), ("1 semaine", 5), ("1 mois", 21), ("3 mois", 63),
          ("6 mois", 126), ("1 an", 252), ("2 ans", 504), ("5 ans", 1260))

# Seances par unite, celles de la carte SI JE GARDE…
UNITES = dict(dt.UNITES)

# Au-dessous, aucune proportion : c'est le seuil de la carte SI JE GARDE…
MINI_PERIODES = dt.MINI_PERIODES

# L'historique charge. Dix ans pour les durees courtes ; au-dela de six
# mois, dix ans ne font plus que quelques periodes, on en prend vingt.
ANNEES_COURT = 10
ANNEES_LONG = 20
SEUIL_LONG = 126

# Un univers a la fois, US et Europe ensemble si on veut.
UNIVERS = {
    "nasdaq100": "Nasdaq 100",
    "sp500": "S&P 500",
    "us": "US large (S&P 500 + Nasdaq 100)",
    "cac40": "CAC 40",
    "dax": "DAX",
    "stoxx600": "STOXX Europe 600",
    "us_europe": "US large + STOXX 600",
    "us_total": "Toute la cote US",
    "europe_total": "Toute l'Europe",
}

# Un tri = un fait. Aucun tri sur une combinaison.
TRIS = {
    "gain": "gain touché (part des périodes)",
    "perte": "perte touchée (part des périodes, la plus rare d'abord)",
    "dabord": "gain touché AVANT la perte (part des cas tranchés)",
    "nom": "ticker",
}
TRI_DEFAUT = "gain"

REFUS_HEURE = (
    "Une heure ne se mesure pas ici : une bougie journalière ne contient "
    "aucune heure intermédiaire, et le programme n'a pas d'historique "
    "intraday (yfinance n'en garde que quelques jours). Il faudrait un "
    "abonnement de données minute, et une spécification écrite avant — "
    "c'est le chantier 7. La plus courte durée mesurable est la séance.")

RAPPEL = (
    "Ce que chaque titre a DONNÉ sur son historique, pas ce qu'il va "
    "donner. Aucune hypothèse sur ces titres n'a été spécifiée ni testée : "
    "le haut de la liste n'est pas une sélection, c'est un tri. Ce n'est "
    "pas un avis.")
RAPPEL_AMPLITUDE = (
    "Toucher +{g} en chemin, c'est d'abord de l'amplitude : un titre qui "
    "bouge beaucoup touche plus souvent le gain ET la perte. Regardez les "
    "deux colonnes ensemble.")
RAPPEL_SURVIVANT = (
    "« Gain d'abord » mesure la tendance PASSÉE du titre sur la période "
    "chargée. La liste est la composition d'aujourd'hui : les sociétés qui "
    "ont chuté puis quitté l'indice n'y sont plus, et le tableau en est "
    "flatté.")
RAPPEL_FRAIS = (
    "Gain et perte NETS des frais du backtest ({c} % par côté, spread et "
    "glissement compris){f}. L'impôt n'est pas compté ; le change non "
    "plus, pour un titre hors zone euro.")


# ---------------------------------------------------------------------
# La duree demandee
# ---------------------------------------------------------------------

def seances(nombre, unite: str) -> dict:
    """{"seances": n} ou {"refus": raison}. L'heure est refusee."""
    u = (unite or "").strip().lower()
    u = {"jour": "jours", "journee": "jours", "journée": "jours",
         "seance": "jours", "séance": "jours", "seances": "jours",
         "séances": "jours", "semaine": "semaines", "an": "ans",
         "annee": "ans", "année": "ans", "annees": "ans",
         "années": "ans"}.get(u, u)
    if u.startswith("heure") or u in ("h", "minute", "minutes"):
        return {"refus": REFUS_HEURE}
    try:
        x = float(str(nombre).replace(",", "."))
    except (TypeError, ValueError):
        return {"refus": "Durée illisible : un nombre, puis jours, "
                         "semaines, mois ou ans."}
    if u not in UNITES or x <= 0:
        return {"refus": "Durée illisible : un nombre, puis jours, "
                         "semaines, mois ou ans."}
    n = dt.seances(x, u)
    if n > 252 * 20:
        return {"refus": "Plus de vingt ans : aucun historique chargé ne "
                         "contient deux périodes de cette durée."}
    return {"seances": n, "libelle": dt.libelle(n)}


def annees_pour(h: int) -> int:
    return ANNEES_COURT if h <= SEUIL_LONG else ANNEES_LONG


# ---------------------------------------------------------------------
# La somme, le gain, les frais : le mouvement que cela DEMANDE
# ---------------------------------------------------------------------

def cout_par_cote() -> float:
    """Les frais du backtest, par cote : spread et commission, plus le
    glissement. Les memes que ceux qui ont servi a la Phase 0."""
    from . import backtest as bt
    return bt.COUT_PAR_COTE + bt.SLIPPAGE


def seuils(capital: float, gain: float, prix_eur: float | None,
           frais_fixes: float = 0.0) -> dict:
    """Combien de titres, combien investi, et le mouvement BRUT qu'il faut
    pour gagner — ou perdre — `gain` euros NETS de frais.

    net = investi × r − 2 × (frais fixes) − 2 × c × investi
    gain net ≥ G   ⇔  r ≥ (G + 2F) / investi + 2c
    perte nette ≥ G ⇔ r ≤ −(G − 2F) / investi + 2c
    """
    c = cout_par_cote()
    if not prix_eur or prix_eur <= 0 or not math.isfinite(prix_eur):
        return {"achetable": None}
    titres = int(capital // prix_eur)
    if titres < 1:
        return {"achetable": False, "titres": 0,
                "prix_eur": round(prix_eur, 2)}
    investi = titres * prix_eur
    sg = (gain + 2 * frais_fixes) / investi + 2 * c
    sp = -(gain - 2 * frais_fixes) / investi + 2 * c
    out = {"achetable": True, "titres": titres, "investi": round(investi, 2),
           "prix_eur": round(prix_eur, 2),
           "seuil_gain": sg, "seuil_perte": sp}
    if sp >= 0:
        # Les frais seuls coutent deja la somme : le titre peut monter et
        # la perte etre atteinte quand meme. On le dit plutot que de
        # mesurer une chose absurde.
        out["frais_trop_lourds"] = True
    return out


# ---------------------------------------------------------------------
# Ce qui a eu lieu, periode par periode
# ---------------------------------------------------------------------

def _wpc(k: int, n: int) -> list | None:
    return dt._wpc(k, n) if n >= MINI_PERIODES else None


def mesure(close: pd.Series, h: int, sg: float, sp: float) -> dict:
    """Toutes les periodes de h seances, sans chevauchement : le gain
    touche, la perte touchee, lequel d'abord, et la fin.

    Vectorise : une matrice (periodes × h) des chemins, rapportes au
    cours d'achat. Une boucle par periode coutait des secondes par
    univers sur les periodes d'une seance."""
    c = pd.Series(close, dtype=float).dropna()
    c = c[c > 0]
    bornes = dt._bornes(len(c), int(h))
    n = len(bornes)
    out = {"seances": int(h), "periodes": n}
    if n == 0:
        out["erreur"] = f"moins de {h} séances d'historique"
        return out
    px = c.to_numpy()
    a = np.array([x for x, _ in bornes])
    idx = a[:, None] + 1 + np.arange(int(h))[None, :]
    chemin = px[idx] / px[a][:, None] - 1.0
    g, p = chemin >= sg, chemin <= sp
    tg, tp = g.any(axis=1), p.any(axis=1)
    # Le premier indice ou chaque seuil est touche ; h si jamais.
    ig = np.where(tg, g.argmax(axis=1), h)
    ip = np.where(tp, p.argmax(axis=1), h)
    gd = tg & (ig < ip)
    pd_ = tp & (ip < ig)
    fin = chemin[:, -1]
    kg, kp, kgd, kpd = int(tg.sum()), int(tp.sum()), int(gd.sum()), int(pd_.sum())
    tranche = kgd + kpd
    out.update({
        "depuis": str(c.index[bornes[0][0]].date()),
        "gain_touche": kg, "perte_touchee": kp,
        "gain_dabord": kgd, "perte_dabord": kpd,
        "ni_l_un_ni_l_autre": n - tranche,
        "fini_au_gain": int((fin >= sg).sum()),
        "fini_a_la_perte": int((fin <= sp).sum()),
        "part_gain": kg / n if n >= MINI_PERIODES else None,
        "wilson_gain": _wpc(kg, n),
        "part_perte": kp / n if n >= MINI_PERIODES else None,
        "wilson_perte": _wpc(kp, n),
        "part_dabord": (kgd / tranche if tranche >= MINI_PERIODES
                        else None),
        "wilson_dabord": _wpc(kgd, tranche),
        "seances_au_gain": (float(np.median(ig[tg] + 1)) if kg else None),
    })
    return out


# ---------------------------------------------------------------------
# Un univers
# ---------------------------------------------------------------------

def _liste(univers: str) -> list[str]:
    from . import data as dl
    if univers == "us_europe":
        return list(dict.fromkeys(dl.UNIVERS["us"][1]()
                                  + dl.UNIVERS["stoxx600"][1]()))
    return list(dl.UNIVERS[univers][1]())


def _devise(tk: str) -> str:
    try:
        from .find import devise
        return devise(tk)
    except Exception:
        return "USD"


def taux_change(devises, charge) -> dict:
    """Combien d'unites de chaque devise pour UN euro, au dernier cours.
    Une devise sans taux reste absente : ses titres sont marques
    « achetable : inconnu » plutot que convertis au hasard."""
    out = {"EUR": 1.0}
    for dv in sorted(set(devises) - {"EUR"}):
        paire = "GBP" if dv == "GBp" else dv
        try:
            x = charge(f"EUR{paire}=X")
            v = float(pd.Series(x["close"]).dropna().iloc[-1])
            if v > 0:
                # Londres cote en PENCE : cent pence par livre.
                out[dv] = v * (100.0 if dv == "GBp" else 1.0)
        except Exception:
            continue
    return out


def correlation(xs, ys) -> float | None:
    """Pearson, sur les titres qui ont les deux proportions. Sous dix
    titres, rien : une correlation sur cinq points ne dit rien."""
    paires = [(x, y) for x, y in zip(xs, ys)
              if x is not None and y is not None]
    if len(paires) < 10:
        return None
    a = np.array(paires, dtype=float)
    if a[:, 0].std() == 0 or a[:, 1].std() == 0:
        return None
    return round(float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]), 2)


def cle_tri(tri: str):
    def v(x, k):
        return (x.get("mesure") or {}).get(k)
    if tri == "nom":
        return lambda x: (0, x["ticker"])
    k = {"gain": "part_gain", "perte": "part_perte",
         "dabord": "part_dabord"}.get(tri, "part_gain")
    signe = 1 if tri == "perte" else -1
    # Les titres sans proportion vont a la fin, toujours : les oublier
    # flatterait le haut de la liste, les mettre devant le brouillerait.
    return lambda x: ((1, 0.0, x["ticker"]) if v(x, k) is None
                      else (0, signe * v(x, k), x["ticker"]))


def cherche(univers: str, capital: float, gain: float, nombre, unite: str,
            frais_fixes: float = 0.0, tri: str = TRI_DEFAUT,
            charge_lot=None, charge=None, journal=None) -> dict:
    """Le passage complet d'un univers. Rend des FAITS par titre, le
    compte de ce qui n'a pas pu etre mesure, et les rappels."""
    if univers not in UNIVERS:
        return {"ok": False, "erreur": "univers inconnu"}
    try:
        capital, gain = float(capital), float(gain)
        frais_fixes = float(frais_fixes or 0)
    except (TypeError, ValueError):
        return {"ok": False, "erreur": "somme, gain ou frais illisibles"}
    if capital <= 0 or gain <= 0 or frais_fixes < 0:
        return {"ok": False, "erreur": "la somme et le gain doivent être "
                                       "positifs"}
    d = seances(nombre, unite)
    if "refus" in d:
        return {"ok": False, "erreur": d["refus"], "refus": True}
    h = d["seances"]
    annees = annees_pour(h)
    if charge_lot is None or charge is None:
        from . import cache as ch
        charge_lot = charge_lot or (lambda l: ch.charge_lot(
            l, annees=annees, journal=journal, pas=50))
        charge = charge or (lambda tk: ch.charge(tk, annees=1))

    from . import qualite as ql
    liste = _liste(univers)
    series, echecs = charge_lot(liste)
    fx = taux_change([_devise(t) for t in series], charge)

    lignes, refus = [], [{"ticker": t, "motif": m} for t, m in echecs]
    for tk in sorted(series):
        brut = series[tk]
        try:
            rap = ql.controle(brut, ticker=tk)
            if not rap.utilisable:
                refus.append({"ticker": tk, "motif": rap.resume()})
                continue
            close = pd.Series(brut["close"], dtype=float).dropna()
            dv = _devise(tk)
            prix = float(close.iloc[-1])
            prix_eur = prix / fx[dv] if dv in fx else None
            s = seuils(capital, gain, prix_eur, frais_fixes)
            ligne = {"ticker": tk, "devise": dv, "prix": round(prix, 4),
                     "date": str(close.index[-1].date()), **s}
            if s.get("achetable") and not s.get("frais_trop_lourds"):
                ligne["mesure"] = mesure(close, h, s["seuil_gain"],
                                         s["seuil_perte"])
            lignes.append(ligne)
        except Exception as exc:
            refus.append({"ticker": tk, "motif": f"{type(exc).__name__}"})

    mes = [x for x in lignes if x.get("mesure")]
    lignes.sort(key=cle_tri(tri if tri in TRIS else TRI_DEFAUT))

    # Le marche lui-meme, aux memes seuils pour la somme entiere : la
    # ligne de reference du tableau.
    reperes = []
    c = cout_par_cote()
    for bk in (("SPY", "S&P 500"), ("^STOXX", "STOXX 600")):
        try:
            b = charge_lot([bk[0]])[0].get(bk[0])
            if b is None:
                continue
            sg = (gain + 2 * frais_fixes) / capital + 2 * c
            sp = -(gain - 2 * frais_fixes) / capital + 2 * c
            if sp < 0:
                reperes.append({"ticker": bk[0], "nom": bk[1],
                                "mesure": mesure(b["close"], h, sg, sp)})
        except Exception:
            continue

    fr = (f", plus {frais_fixes:g} € par ordre" if frais_fixes else "")
    return {
        "ok": True, "univers": univers, "nom_univers": UNIVERS[univers],
        "capital": capital, "gain": gain, "frais_fixes": frais_fixes,
        "seances": h, "libelle": d["libelle"], "annees": annees,
        "mini": MINI_PERIODES,
        "tri": tri if tri in TRIS else TRI_DEFAUT,
        "lignes": lignes, "refus": refus, "reperes": reperes,
        "taux": {k: round(v, 4) for k, v in fx.items()},
        "compte": {
            "univers": len(liste), "charges": len(series),
            "mesures": len(mes),
            "non_achetables": sum(1 for x in lignes
                                  if x.get("achetable") is False),
            "sans_change": sum(1 for x in lignes
                               if x.get("achetable") is None),
            "frais_trop_lourds": sum(1 for x in lignes
                                     if x.get("frais_trop_lourds")),
            "trop_peu": sum(1 for x in mes
                            if x["mesure"].get("part_gain") is None),
            "refuses": len(refus),
        },
        "correlation": correlation(
            [x["mesure"].get("part_gain") for x in mes],
            [x["mesure"].get("part_perte") for x in mes]),
        "rappels": [RAPPEL,
                    RAPPEL_AMPLITUDE.format(g=f"{gain:g} €"),
                    RAPPEL_SURVIVANT,
                    RAPPEL_FRAIS.format(c=f"{c * 100:.2f}".replace(".", ","),
                                        f=fr)],
    }


def main(argv=None) -> None:
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 4:
        print(__doc__)
        return
    uni, cap, g = a[0], float(a[1]), float(a[2])
    nb, _, un = a[3].partition(" ")
    r = cherche(uni, cap, g, nb, un or "semaines",
                journal=lambda m: print(m))
    if not r.get("ok"):
        print("  " + r.get("erreur", "échec"))
        return
    print(f"\n  {r['nom_univers']} — {cap:g} € pour +{g:g} € en "
          f"{r['libelle']}, sur {r['annees']} ans\n")
    for x in r["lignes"][:40]:
        m = x.get("mesure") or {}
        if not m.get("periodes"):
            continue
        print(f"  {x['ticker']:<10} gain {m['gain_touche']:>4}/{m['periodes']:<4}"
              f" perte {m['perte_touchee']:>4}/{m['periodes']:<4}"
              f" d'abord {m['gain_dabord']}/{m['gain_dabord'] + m['perte_dabord']}")
    print(f"\n  corrélation gain touché / perte touchée : {r['correlation']}")
    for t in r["rappels"]:
        print("\n  " + t)


if __name__ == "__main__":
    main()
