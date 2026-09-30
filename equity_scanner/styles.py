"""OBJECTIF PAR STYLE — « TLX, je veux +50 € en un mois : quelle
strategie ? Day trading, scalping, a l'heure ? »

A QUOI CA REPOND

Frederic choisit un titre, une somme, un gain vise et une duree. La
question « quelle strategie » a deux moities.

* Celle qui se MESURE : pour chaque style — scalping, a l'heure, day
  trading, swing d'une semaine, swing d'un mois, position d'un an —, ce
  que sa duree a DONNE sur ce titre, aux seuils de SA somme : combien de
  periodes ont touche le gain, combien la meme perte, lequel d'abord, et
  l'indice aux memes seuils a cote. Plus ce que l'objectif DEMANDE : le
  mouvement, les frais d'un aller-retour, et l'objectif repete sur un an.
* Celle qui ne se mesure pas : « lequel choisir ». Aucune strategie n'a
  passe sa Phase 0, et designer apres coup la duree qui a le mieux marche
  est la peche que le protocole interdit — six styles, ce sont six
  chances d'en voir un briller par hasard. Les lignes sont donc dans
  l'ORDRE DES DUREES, jamais triees sur leur resultat, et la page le dit.

CE QUI SE MESURE, ET COMMENT

* Scalping et a l'heure : RIEN. Le programme n'a aucun historique
  intraday (chantier 7) ; une bougie journaliere ne contient aucun
  instant de la seance. Refuses avec leur raison, plutot que remplis avec
  des chiffres qui n'existent pas. Les frais d'un aller-retour, eux, se
  calculent, et c'est ce qui pese le plus sur un style qui en fait cent.
* Day trading : UNE SEANCE, achete a l'ouverture et revendu a la cloture.
  La bougie donne l'ouverture, le plus haut, le plus bas et la cloture :
  le gain touche (plus haut), la perte touchee (plus bas) et la fin se
  lisent. L'ORDRE, non : quand les deux ont ete touches dans la meme
  seance, on ne sait pas lequel d'abord, et ces seances sont comptees a
  part — jamais attribuees.
* Semaine, mois, an : les periodes sans chevauchement de RECHERCHE
  (`recherche.mesure`), sur les clotures.
* Les bougies : les figures de la derniere seance et ce qu'elles ont ete
  suivies de sur ce titre, contre son taux de base (`chandeliers`).

    py -m equity_scanner.styles TLX.DE 3000 50 "1 mois"
"""

from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

from . import detention as dt
from . import recherche as rc

VERSION = "styles-v1.0"

# Les styles, DANS L'ORDRE DES DUREES. Cet ordre est ecrit ici et ne
# depend d'aucun resultat : trier sur ce qui a le mieux marche ferait du
# tableau une recommandation.
#   seances : None = rien de mesurable ici ; 0 = une seance, de
#   l'ouverture a la cloture ; n = n seances de cloture a cloture.
STYLES = (
    {"cle": "scalping", "nom": "SCALPING", "seances": None,
     "duree": "quelques secondes à quelques minutes"},
    {"cle": "heure", "nom": "À L'HEURE", "seances": None,
     "duree": "une à quelques heures, dans la séance"},
    {"cle": "day", "nom": "DAY TRADING", "seances": 0,
     "duree": "une séance : acheté à l'ouverture, revendu à la clôture"},
    {"cle": "semaine", "nom": "SWING COURT", "seances": 5,
     "duree": "une semaine (5 séances)"},
    {"cle": "mois", "nom": "SWING", "seances": 21,
     "duree": "un mois (21 séances)"},
    {"cle": "an", "nom": "POSITION", "seances": 252,
     "duree": "un an (252 séances)"},
)

# L'historique : celui de RECHERCHE — dix ans pour les durees courtes,
# vingt au-dela de six mois (dix ans ne font que dix periodes d'un an).
SEANCES_AN = 252

REFUS_SCALPING = (
    "Rien ne se mesure ici. Le programme n'a aucun historique à la "
    "minute — yfinance n'en garde que quelques jours —, et une bougie "
    "journalière ne contient aucun instant de la séance. En face : un "
    "teneur de marché automatisé, qui voit le carnet d'ordres et dont le "
    "métier est de gagner l'écart. Tant que « qui est en face, et "
    "pourquoi perdrait-il ? » n'a pas de réponse écrite, le protocole dit "
    "de s'arrêter (chantier 7).")
REFUS_HEURE = rc.REFUS_HEURE

RAPPEL_DAY = (
    "Une bougie journalière donne l'ouverture, le plus haut, le plus bas "
    "et la clôture — pas l'ordre dans lequel ils sont venus. Les séances "
    "où le gain ET la perte ont été touchés sont comptées à part : on ne "
    "sait pas lequel est venu d'abord.")

RAPPEL = (
    "Ce tableau dit ce que chaque durée a DONNÉ sur ce titre, pas ce "
    "qu'elle va donner, et il ne choisit aucun style : les lignes sont "
    "dans l'ordre des durées, jamais triées sur leur résultat. Plusieurs "
    "durées comparées, ce sont autant de chances d'en voir une briller "
    "par le seul hasard ; retenir celle qui a le mieux marché serait la "
    "pêche que le protocole interdit. Aucune stratégie n'a passé sa "
    "Phase 0 : ce n'est pas un avis.")

RAPPEL_REPETE = (
    "« Répété » est de l'arithmétique : le gain visé multiplié par le "
    "nombre de périodes d'une année, sans réinvestir. Ce n'est pas ce "
    "qu'un style va rendre : c'est ce que l'objectif demande. L'indice "
    "est à côté, pour l'échelle.")

RAPPEL_FRAIS = (
    "Chaque aller-retour paie les frais du backtest ({c} % par côté, "
    "spread et glissement compris){f}. Un style qui en fait cent par mois "
    "les paie cent fois : c'est le premier chiffre à regarder avant le "
    "scalping.")


def _strategies() -> list[dict]:
    """Les trois strategies ecrites en 2026, et leur style. Les durees
    sont LUES dans les moteurs, jamais recopiees."""
    from . import pead as pe
    from . import short as sh
    return [
        {"num": "n°1", "nom": "Repli en tendance",
         "style": "achat tenu jusqu'à la première de ses quatre "
                  "conditions de sortie — du swing",
         "etat": "NO-GO en Phase 0"},
        {"num": "n°2", "nom": "Dérive après une bonne surprise de résultats",
         "style": f"achat tenu au plus {pe.MAX_BARRES} séances — du swing",
         "etat": "NO-GO au passage unique du 29 septembre 2026"},
        {"num": "n°3",
         "nom": "Dérive après une mauvaise surprise de résultats",
         "style": f"vente à découvert, au plus {sh.MAX_BARRES} séances "
                  "— du swing",
         "etat": "abandonnée le 30 septembre 2026, NO-GO en répétition"},
    ]


RAPPEL_STRATEGIES = (
    "Aucune stratégie de day trading, de scalping ou à l'heure n'a été "
    "écrite : il faudrait des données à la minute et une réponse écrite à "
    "« qui est en face ? ». Une nouvelle stratégie, quel que soit son "
    "style, s'écrit, se gèle et se juge sur une période qu'elle n'a pas "
    "vue — c'est le brouillon 2027.")


# ---------------------------------------------------------------------
# La duree demandee
# ---------------------------------------------------------------------

def duree(nombre, unite: str) -> dict:
    """La duree tapee, rangee : le style qu'elle designe, ou une ligne a
    part. {"style": cle} ou {"seances": n, "libelle": …} ou {"erreur"}."""
    u = (unite or "").strip().lower()
    if u.startswith(("minute", "seconde")) or u in ("min", "s"):
        return {"style": "scalping"}
    if u.startswith("heure") or u == "h":
        return {"style": "heure"}
    d = rc.seances(nombre, unite)
    if "refus" in d:
        return {"erreur": d["refus"]}
    h = d["seances"]
    if h == 1:
        return {"style": "day"}
    for s in STYLES:
        if s["seances"] == h:
            return {"style": s["cle"]}
    return {"seances": h, "libelle": d["libelle"]}


# ---------------------------------------------------------------------
# Ce qui a eu lieu
# ---------------------------------------------------------------------

def mesure_seance(d: pd.DataFrame, sg: float, sp: float) -> dict:
    """Chaque seance, achetee a l'ouverture et revendue a la cloture : le
    gain touche (plus haut), la perte touchee (plus bas), les deux — ordre
    inconnu —, et la fin. Une seance est une periode : elles ne se
    chevauchent pas."""
    need = {"open", "high", "low", "close"}
    if d is None or not need <= set(getattr(d, "columns", [])):
        return {"seances": 1, "intra": True, "periodes": 0,
                "erreur": "ouverture, plus haut et plus bas absents"}
    o = d["open"].to_numpy(float)
    hi = d["high"].to_numpy(float)
    lo = d["low"].to_numpy(float)
    c = d["close"].to_numpy(float)
    ok = (np.isfinite(o) & np.isfinite(hi) & np.isfinite(lo)
          & np.isfinite(c) & (o > 0))
    o, hi, lo, c = o[ok], hi[ok], lo[ok], c[ok]
    idx = d.index[ok]
    n = int(len(o))
    out = {"seances": 1, "intra": True, "periodes": n}
    if n == 0:
        out["erreur"] = "aucune séance exploitable"
        return out
    g = hi / o - 1.0 >= sg
    p = lo / o - 1.0 <= sp
    fin = c / o - 1.0
    kg, kp, kb = int(g.sum()), int(p.sum()), int((g & p).sum())
    assez = n >= rc.MINI_PERIODES
    out.update({
        "depuis": str(pd.Timestamp(idx[0]).date()),
        "gain_touche": kg, "perte_touchee": kp, "les_deux": kb,
        "gain_seul": kg - kb, "perte_seule": kp - kb,
        "ni_l_un_ni_l_autre": n - kg - kp + kb,
        "fini_au_gain": int((fin >= sg).sum()),
        "fini_a_la_perte": int((fin <= sp).sum()),
        "part_gain": kg / n if assez else None,
        "wilson_gain": rc._wpc(kg, n),
        "part_perte": kp / n if assez else None,
        "wilson_perte": rc._wpc(kp, n),
        # L'ordre n'est pas connu : aucune proportion « d'abord ».
        "part_dabord": None, "wilson_dabord": None,
    })
    return out


def repete(gain: float, investi: float, seances: int) -> dict:
    """L'objectif repete a chaque periode d'une annee, sans reinvestir.
    De l'arithmetique : ce que l'objectif DEMANDE, pas ce qu'il rendra."""
    par_an = SEANCES_AN / max(1, int(seances))
    eur = gain * par_an
    return {"periodes_an": round(par_an, 2), "eur_an": round(eur, 2),
            "pct_an": (round(eur / investi * 100, 1) if investi else None)}


def rendement_annuel(close: pd.Series) -> float | None:
    """Le rendement annuel compose de l'indice sur l'historique charge,
    en %. Un repere d'echelle, pas une promesse."""
    c = pd.Series(close, dtype=float).dropna()
    c = c[c > 0]
    if len(c) < SEANCES_AN:
        return None
    return round(((c.iloc[-1] / c.iloc[0]) ** (SEANCES_AN / (len(c) - 1))
                  - 1) * 100, 1)


def _fr(x, dec: int = 2) -> str:
    """4195.26 -> « 4 195,26 » : un nombre ecrit comme on le lit."""
    try:
        return f"{float(x):,.{dec}f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return "?"


def _coupe(d: pd.DataFrame, annees: int) -> pd.DataFrame:
    if d is None or not len(d):
        return d
    debut = d.index[-1] - pd.DateOffset(years=annees)
    return d[d.index >= debut]


def _ecart_jour(close: pd.Series) -> float | None:
    """Le mouvement d'une seance ordinaire sur un an : la mediane des
    variations absolues, en %."""
    r = pd.Series(close, dtype=float).pct_change().abs().dropna().tail(
        SEANCES_AN)
    return round(float(r.median()) * 100, 2) if len(r) >= 20 else None


def _bougies(d: pd.DataFrame) -> dict:
    """Les figures de la derniere seance et ce qu'elles ont ete suivies de
    sur ce titre, contre son taux de base — jamais ce qu'elles annoncent."""
    from . import chandeliers as cd
    from .indicators import enrich
    r = cd.lecture(enrich(d.copy()))
    presentes = [{"nom": f["nom"], "forme": f["forme"], "n": f["n"],
                  "suivi": f["suivi"]}
                 for f in r["figures"] if f["aujourdhui"]]
    return {"derniere": r["derniere"], "figures": presentes,
            "comptage": r.get("comptage"), "rappel": r["rappel"],
            "mini_cas": cd.MINI_CAS}


# ---------------------------------------------------------------------
# Tout ensemble
# ---------------------------------------------------------------------

def _charge_defaut(tk: str, annees: int):
    from . import cache as ch
    return ch.charge(tk, annees=annees)


def examine(ticker: str, capital, gain, nombre=1, unite: str = "mois",
            frais_fixes=0.0, charge=None) -> dict:
    """Tous les styles, sur un titre, aux seuils d'une somme et d'un gain.
    `charge(tk, annees)` rend les cours bruts. Rien n'est choisi."""
    from . import qualite as ql
    charge = charge or _charge_defaut
    tk = (ticker or "").strip().upper()
    out = {"ok": False, "ticker": tk, "version": VERSION, "rappel": RAPPEL,
           "rappel_day": RAPPEL_DAY, "rappel_repete": RAPPEL_REPETE,
           "strategies": _strategies(),
           "rappel_strategies": RAPPEL_STRATEGIES}
    try:
        capital = float(str(capital).replace(",", "."))
        gain = float(str(gain).replace(",", "."))
        frais_fixes = float(str(frais_fixes or 0).replace(",", "."))
    except (TypeError, ValueError):
        out["erreur"] = "Somme, gain ou frais illisibles."
        return out
    if not tk:
        out["erreur"] = "Tapez un ticker, avec sa place : TLX.DE, AAPL, MC.PA."
        return out
    if capital <= 0 or gain <= 0 or frais_fixes < 0:
        out["erreur"] = "La somme et le gain visé doivent être positifs."
        return out
    du = duree(nombre, unite)
    if "erreur" in du:
        out["erreur"] = du["erreur"]
        return out

    try:
        brut = charge(tk, rc.ANNEES_LONG)
    except Exception as exc:
        out["erreur"] = f"Cours de {tk} introuvables ({type(exc).__name__})."
        return out
    if brut is None or len(brut) < 60:
        out["erreur"] = f"Historique de {tk} trop court ou absent."
        return out
    rap = ql.controle(brut, ticker=tk)
    if not rap.utilisable:
        out["erreur"] = f"Données de {tk} refusées : {rap.resume()}"
        return out

    dv = rc._devise(tk)
    fx = rc.taux_change([dv], lambda t: charge(t, 1))
    close = pd.Series(brut["close"], dtype=float).dropna()
    prix = float(close.iloc[-1])
    prix_eur = prix / fx[dv] if dv in fx else None
    s = rc.seuils(capital, gain, prix_eur, frais_fixes)
    if s.get("achetable") is None:
        out["erreur"] = (f"Pas de taux de change pour {dv} : la somme ne se "
                         "convertit pas en titres.")
        return out
    if not s.get("achetable"):
        out["erreur"] = (f"Une action de {tk} vaut {_fr(s.get('prix_eur'))} € : "
                         f"{_fr(capital, 0)} € n'en achètent aucune.")
        return out
    c = rc.cout_par_cote()
    investi = s["investi"]
    aller_retour = 2 * c * investi + 2 * frais_fixes
    ej = _ecart_jour(close)

    bk = ("SPY", "S&P 500") if dv == "USD" else ("^STOXX", "STOXX 600")
    try:
        banc = charge(bk[0], rc.ANNEES_LONG)
    except Exception:
        banc = None
    # L'indice aux memes seuils, pour la somme entiere.
    sg_b = (gain + 2 * frais_fixes) / capital + 2 * c
    sp_b = -(gain - 2 * frais_fixes) / capital + 2 * c

    out.update({
        "ok": True, "devise": dv, "prix": round(prix, 4),
        "date": str(close.index[-1].date()),
        "capital": capital, "gain": gain, "frais_fixes": frais_fixes,
        "titres": s["titres"], "investi": investi,
        "prix_eur": s["prix_eur"],
        "seuil_gain_pct": round(s["seuil_gain"] * 100, 2),
        "seuil_perte_pct": round(s["seuil_perte"] * 100, 2),
        "frais_trop_lourds": bool(s.get("frais_trop_lourds")),
        "cout_cote_pct": round(c * 100, 3),
        "aller_retour_eur": round(aller_retour, 2),
        "aller_retour_part_gain": round(aller_retour / gain * 100, 1),
        "ecart_jour_pct": ej,
        "en_seances": (round(s["seuil_gain"] * 100 / ej, 1)
                       if ej else None),
        "indice": {"ticker": bk[0], "nom": bk[1]},
        "mini": rc.MINI_PERIODES,
        "rappel_frais": RAPPEL_FRAIS.format(
            c=f"{c * 100:.2f}".replace(".", ","),
            f=(f", plus {frais_fixes:g} € par ordre" if frais_fixes else "")),
        "votre": du,
    })
    if banc is not None and len(banc):
        out["indice"]["rendement_an"] = rendement_annuel(
            _coupe(banc, rc.ANNEES_COURT)["close"])
        out["indice"]["annees"] = rc.ANNEES_COURT

    lignes = []
    styles = [dict(x) for x in STYLES]
    if "seances" in du:
        styles.append({"cle": "votre", "nom": "VOTRE DURÉE",
                       "seances": du["seances"], "duree": du["libelle"]})
        # L'ordre des durees, toujours : la ligne tapee prend sa place.
        styles.sort(key=lambda x: (-1 if x["seances"] is None
                                   else x["seances"]))
        cle_votre = "votre"
    else:
        cle_votre = du["style"]
    for st in styles:
        L = {"cle": st["cle"], "nom": st["nom"], "duree": st["duree"],
             "votre": st["cle"] == cle_votre,
             "aller_retour_eur": round(aller_retour, 2)}
        h = st["seances"]
        if h is None:
            L["refus"] = (REFUS_SCALPING if st["cle"] == "scalping"
                          else REFUS_HEURE)
        elif s.get("frais_trop_lourds"):
            L["refus"] = ("Les frais d'un aller-retour coûtent déjà le gain "
                          "visé : rien à mesurer.")
        else:
            ans = rc.annees_pour(max(1, h))
            dd = _coupe(brut, ans)
            bb = _coupe(banc, ans) if banc is not None else None
            if h == 0:
                L["mesure"] = mesure_seance(dd, s["seuil_gain"],
                                            s["seuil_perte"])
                if bb is not None and sp_b < 0:
                    L["indice"] = mesure_seance(bb, sg_b, sp_b)
                L["repete"] = repete(gain, investi, 1)
            else:
                L["mesure"] = rc.mesure(dd["close"], h, s["seuil_gain"],
                                        s["seuil_perte"])
                if bb is not None and sp_b < 0:
                    L["indice"] = rc.mesure(bb["close"], h, sg_b, sp_b)
                L["repete"] = repete(gain, investi, h)
            L["annees"] = ans
        lignes.append(L)
    out["lignes"] = lignes
    out["mesurees"] = sum(1 for L in lignes if L.get("mesure", {})
                          .get("part_gain") is not None)
    try:
        out["bougies"] = _bougies(_coupe(brut, rc.ANNEES_COURT))
    except Exception as exc:
        out["bougies"] = {"erreur": f"{type(exc).__name__}"}
    return json_sur(out)


def json_sur(x):
    """Des types que json sait ecrire : numpy et NaN n'y entrent pas."""
    if isinstance(x, dict):
        return {k: json_sur(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [json_sur(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return v if math.isfinite(v) else None
    if isinstance(x, np.bool_):
        return bool(x)
    return x


# ---------------------------------------------------------------------
# En ligne de commande
# ---------------------------------------------------------------------

def _pc(w) -> str:
    return f" ({w[0]:.0f}–{w[1]:.0f} %)" if w else ""


def texte(r: dict) -> str:
    if not r.get("ok"):
        return f"\n  {r.get('ticker')} : {r.get('erreur')}\n"
    L = [f"\n  OBJECTIF PAR STYLE — {r['ticker']}, +{r['gain']:g} € avec "
         f"{r['capital']:g} €", "",
         f"  {r['titres']} titres, {r['investi']:.2f} € investis. +"
         f"{r['gain']:g} € nets demandent {r['seuil_gain_pct']:+.2f} %, la "
         f"même perte {r['seuil_perte_pct']:+.2f} %.",
         f"  Un aller-retour coûte {r['aller_retour_eur']:.2f} € de frais, "
         f"{r['aller_retour_part_gain']:.0f} % du gain visé.", ""]
    for x in r["lignes"]:
        tete = f"  {x['nom']:<13} {x['duree']}" + ("   ← VOTRE DURÉE"
                                                   if x["votre"] else "")
        L.append(tete)
        if x.get("refus"):
            L.append("      " + x["refus"])
            continue
        m = x.get("mesure") or {}
        if not m.get("periodes"):
            L.append("      " + str(m.get("erreur", "rien à mesurer")))
            continue
        L.append(f"      {m['periodes']} périodes depuis {m.get('depuis')} : "
                 f"gain touché {m['gain_touche']}{_pc(m.get('wilson_gain'))}, "
                 f"même perte {m['perte_touchee']}"
                 f"{_pc(m.get('wilson_perte'))}")
        if m.get("intra"):
            L.append(f"      les deux dans la séance : {m['les_deux']} "
                     "(ordre inconnu)")
        elif m.get("wilson_dabord"):
            L.append(f"      gain d'abord : {m['gain_dabord']} sur "
                     f"{m['gain_dabord'] + m['perte_dabord']}"
                     f"{_pc(m['wilson_dabord'])}")
        rp = x.get("repete") or {}
        L.append(f"      répété : {rp.get('eur_an', 0):,.0f} € par an, "
                 f"{rp.get('pct_an')} % de la somme".replace(",", " "))
    L += ["", "  " + r["rappel"], ""]
    return "\n".join(L)


def main(argv=None) -> None:
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 3:
        print(__doc__)
        return
    nb, un = "1", "mois"
    if len(a) >= 4:
        p = a[3].split()
        nb, un = (p[0], p[1]) if len(p) == 2 else ("1", p[0])
    print(texte(examine(a[0], a[1], a[2], nb, un)))


if __name__ == "__main__":
    main()
