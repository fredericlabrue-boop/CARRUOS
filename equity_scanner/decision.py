"""AVANT L'ORDRE — une decision preparee par des faits et des regles
ecrites d'avance.

A QUOI CA REPOND

« Aide-moi a decider. » Aucune hypothese n'a passe sa Phase 0 : le
programme ne sait pas QUOI acheter, et ne le dit pas. Il peut en revanche,
pour un achat que VOUS envisagez, faire trois choses qui se verifient :

1. Les FAITS, mesures a l'instant :
   - combien de titres pour ne risquer que RISQUE_DEFAUT % du capital si
     le stop est touche, sans depasser PLAFOND du capital sur la ligne —
     les deux regles de risque que vos trois specifications ecrivent ;
   - ce que votre stop represente pour CE titre : en ATR, en mouvements
     quotidiens ordinaires, et combien de fois, sur son historique, une
     periode de votre duree a touche ce niveau en chemin ;
   - le calendrier (resultats pendant la detention ?), le mouvement
     recent, le marche (l'indice et sa moyenne 200 seances), votre
     portefeuille (poids apres l'achat, correlation avec vos lignes).
2. Les QUESTIONS qu'on oublie une fois l'ordre passe, posees AVANT :
   pourquoi, qu'est-ce qui me ferait dire que j'avais tort, quelle perte
   j'accepte. La liste est ecrite ici, une fois (`QUESTIONS`).
3. La TRACE : la decision est ecrite au carnet, datee, avec les faits
   recalcules COTE SERVEUR a cet instant — pas ce que la page affichait.
   C'est ce qui permettra plus tard de mesurer vos decisions, les bonnes
   et les mauvaises, en entier.

Aucun verdict. Le compte des points remplis n'est pas un signal : huit
points sur huit veulent dire que la decision est PREPAREE, pas qu'elle
est bonne.

    py -m equity_scanner.decision TLX.DE 20000 2 mois
"""

from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

from . import rules as R

# Les deux regles de risque, reprises des specifications — jamais
# recopiees : si une specification bougeait, la page suivrait.
RISQUE_DEFAUT = R.RISK_PER_TRADE * 100      # % du capital perdu au stop
PLAFOND = R.MAX_WEIGHT                      # part du capital sur une ligne

# Une correlation se mesure sur au moins ce nombre de seances communes.
SEANCES_CORR = 120
ANNEES = 10

# La liste de controle, ecrite AVANT tout usage. Trois genres :
#   texte : vous l'ecrivez ;  case : vous le cochez ;  fait : le programme
#   le constate. Aucune ne porte de seuil invente ici : 1 % et 25 % sont
#   ceux de vos specifications, le reste est votre reponse.
QUESTIONS = (
    ("raison", "texte", "Pourquoi cet achat ? Écrit avant l'ordre."),
    ("tort", "texte", "Qu'est-ce qui me ferait dire que j'avais tort, en "
                      "dehors du stop ?"),
    ("stop", "fait", "Le stop est fixé avant l'achat, sous le prix d'entrée."),
    ("perte", "case", "J'accepte la perte si le stop est touché."),
    ("duree", "fait", "La durée envisagée est fixée."),
    ("plafond", "fait", "La ligne reste sous le plafond du capital après "
                        "l'achat."),
    ("resultats", "case", "Je sais si des résultats tombent pendant la "
                          "détention."),
    ("mouvement", "case", "Je n'achète pas à cause du seul mouvement "
                          "récent du titre."),
)

RAPPEL = (
    "Aucune hypothèse n'a passé sa Phase 0 : le programme ne sait pas quoi "
    "acheter, et ne le dit pas. Ces faits préparent VOTRE décision ; ils ne "
    "la prennent pas. Tous les points remplis ne font pas un signal.")
RAPPEL_STOP = (
    "Un stop sur clôture ne protège pas d'un écart d'ouverture : une "
    "mauvaise nouvelle publiée la nuit peut faire ouvrir le titre bien "
    "au-dessous. La perte affichée est celle AU niveau du stop.")
RAPPEL_HISTO = (
    "Ce que les périodes passées ont donné, pas ce que la prochaine "
    "donnera. Et un titre encore coté aujourd'hui est, par construction, "
    "un titre qui a survécu à son passé.")


# ------------------------------------------------------------ utilitaires
def _num(x):
    try:
        v = float(str(x).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _r(x, n=2):
    return None if x is None or not math.isfinite(float(x)) else round(
        float(x), n)


def _banc(ticker: str) -> tuple[str, str]:
    """L'indice de reference de la place — celui du regime des
    specifications : SPY aux Etats-Unis, le STOXX 600 en Europe."""
    from .recherche import _devise
    return (("SPY", "S&P 500") if _devise(ticker) == "USD"
            else ("^STOXX", "STOXX 600"))


def _charge_defaut(tk: str):
    from . import cache as ch
    return ch.charge(tk, annees=ANNEES)


def stop_specification(d: pd.DataFrame, entree: float) -> float | None:
    """Le stop que la specification n°1 ECRIT pour un achat : le plus bas
    des deux, sous le plus bas du repli recent ou a 1,5 ATR sous
    l'entree. Une reference ecrite d'avance, pas une recommandation."""
    if "atr14" not in d or not len(d):
        return None
    atr = float(d["atr14"].iloc[-1])
    if not math.isfinite(atr) or atr <= 0:
        return None
    bas = float(d["low"].iloc[-R.PULLBACK_WINDOW:].min())
    return float(min(bas - R.STOP_SWING_BUFFER * atr,
                     entree - R.STOP_ATR_MULT * atr))


def taille(capital_eur: float, entree_eur: float, stop_eur: float,
           risque_pct: float = RISQUE_DEFAUT, plafond: float = PLAFOND,
           deja_eur: float = 0.0) -> dict:
    """Combien de titres. Le risque fixe le nombre ; le plafond le borne,
    en comptant ce que vous detenez deja sur la ligne."""
    unite = entree_eur - stop_eur
    out = {"titres": 0, "par_risque": 0, "par_plafond": 0,
           "plafonne": False, "motif": ""}
    if capital_eur <= 0 or entree_eur <= 0:
        out["motif"] = "capital ou prix illisible"
        return out
    if unite <= 0:
        out["motif"] = "le stop doit être SOUS le prix d'entrée"
        return out
    par_risque = int((capital_eur * risque_pct / 100.0) // unite)
    reste = max(0.0, plafond * capital_eur - deja_eur)
    par_plafond = int(reste // entree_eur)
    n = min(par_risque, par_plafond)
    out.update({"titres": n, "par_risque": par_risque,
                "par_plafond": par_plafond,
                "plafonne": par_plafond < par_risque})
    if n == 0:
        out["motif"] = ("la ligne atteint déjà le plafond" if reste <= 0
                        else "un seul titre dépasserait le plafond"
                        if par_plafond == 0
                        else "un seul titre ferait perdre plus que le "
                             "risque choisi si le stop est touché")
    return out


# ------------------------------------------------------------ l'examen
def examine(ticker: str, capital: float, entree=None, stop=None,
            risque: float = RISQUE_DEFAUT, nombre=2, unite: str = "mois",
            gain_vise=None, reponses: dict | None = None,
            detenus: list | None = None, charge=None,
            jours_resultats: int | None = None) -> dict:
    """Tous les faits d'un achat envisage, et l'etat de la liste.

    `charge(tk)` rend les cours bruts (cache.charge par defaut) ;
    `detenus` : [{ticker, quantite}] ; `jours_resultats` : seances
    jusqu'a la prochaine publication, None si inconnue. Rien n'est decide.
    """
    from . import profil as pf
    from . import qualite as ql
    from . import recherche as rc
    from .indicators import enrich

    charge = charge or _charge_defaut
    tk = (ticker or "").strip().upper()
    reponses = reponses or {}
    out = {"ok": False, "ticker": tk, "rappel": RAPPEL,
           "rappel_stop": RAPPEL_STOP, "rappel_histo": RAPPEL_HISTO}
    capital = _num(capital)
    if not tk:
        out["erreur"] = "Tapez un ticker, avec sa place : TLX.DE, AAPL, MC.PA."
        return out
    if not capital or capital <= 0:
        out["erreur"] = "Tapez le capital total du compte, en euros."
        return out
    dur = rc.seances(nombre, unite)
    if "refus" in dur:
        out["erreur"] = dur["refus"]
        return out
    h = dur["seances"]
    try:
        brut = charge(tk)
    except Exception as exc:
        out["erreur"] = f"Cours de {tk} introuvables ({type(exc).__name__})."
        return out
    if brut is None or len(brut) < 60:
        out["erreur"] = f"Historique de {tk} trop court ou absent."
        return out
    btk, bnom = _banc(tk)
    try:
        bench = charge(btk)
    except Exception:
        bench = None
    d = enrich(brut, bench_close=None if bench is None else bench["close"])
    close = d["close"].astype(float)
    dev = rc._devise(tk)
    fx = rc.taux_change([dev], charge).get(dev)
    cours = float(close.iloc[-1])
    ent = _num(entree) or cours
    st_spec = stop_specification(d, ent)
    st = _num(stop)
    stop_source = "le vôtre"
    if st is None:
        st, stop_source = st_spec, "celui qu'écrit la spécification n°1"

    out.update({"ok": True, "devise": dev, "cours": _r(cours, 4),
                "date": str(d.index[-1].date()), "entree": _r(ent, 4),
                "stop": _r(st, 4) if st is not None else None,
                "stop_source": stop_source,
                "stop_specification": _r(st_spec, 4),
                "capital": _r(capital, 2), "risque_pct": _r(risque, 2),
                "plafond_pct": _r(PLAFOND * 100, 0),
                "duree": dur["libelle"], "seances": h,
                "taux": None if fx is None else _r(fx, 6)})

    # --- la qualite des donnees, d'abord ---------------------------------
    try:
        q = ql.controle(brut, bench, ticker=tk)
        out["qualite"] = {"utilisable": bool(q.utilisable),
                          "resume": q.resume()}
    except Exception as exc:
        out["qualite"] = {"utilisable": None,
                          "resume": f"contrôle impossible ({type(exc).__name__})"}

    # --- la taille --------------------------------------------------------
    held = {(x.get("ticker") or "").upper(): _num(x.get("quantite")) or 0.0
            for x in (detenus or [])}
    deja_qte = held.get(tk, 0.0)
    if fx is None or st is None:
        out["taille"] = {"titres": 0, "motif": (
            "pas de taux de change pour " + dev if fx is None
            else "stop incalculable (ATR indisponible) : tapez le vôtre")}
    else:
        e_eur, s_eur = ent / fx, st / fx
        deja_eur = deja_qte * cours / fx
        t = taille(capital, e_eur, s_eur, risque, PLAFOND, deja_eur)
        frais = 2 * rc.cout_par_cote()
        inv = t["titres"] * e_eur
        t.update({
            "prix_eur": _r(e_eur, 4),
            "investi_eur": _r(inv, 2),
            "perte_stop_eur": _r(t["titres"] * (e_eur - s_eur) + inv * frais, 2),
            "perte_stop_pct_capital": _r((t["titres"] * (e_eur - s_eur)
                                          + inv * frais) / capital * 100, 2),
            "frais_eur": _r(inv * frais, 2),
            "poids_apres_pct": _r((deja_eur + inv) / capital * 100, 1),
            "deja_titres": deja_qte, "deja_eur": _r(deja_eur, 2)})
        out["taille"] = t

    # --- ce que le stop represente pour CE titre ------------------------
    try:
        m = pf.mesures(d, bench, ticker=tk, declare=False)
    except Exception:
        m = {}
    if st is not None and ent > st:
        dist = (ent - st) / ent
        atr = float(d["atr14"].iloc[-1]) if "atr14" in d else float("nan")
        ej = m.get("ecart_jour_ordinaire")
        s = {"distance_pct": _r(dist * 100, 2),
             "en_atr": _r((ent - st) / atr, 2) if atr and math.isfinite(atr)
             else None,
             "ecart_jour_pct": _r(ej * 100, 2) if ej else None,
             "en_ecarts_jour": _r(dist / ej, 1) if ej else None}
        g = _num(gain_vise)
        sg = (g / 100.0) if g and g > 0 else dist
        s["gain_seuil_pct"] = _r(sg * 100, 2)
        s["gain_seuil_source"] = ("votre gain visé" if g and g > 0
                                  else "la même distance au-dessus")
        s["histo"] = rc.mesure(close, h, sg, -dist)
        out["stop_faits"] = s
    else:
        out["stop_faits"] = None

    # --- le mouvement recent ---------------------------------------------
    def var(n):
        return (_r((close.iloc[-1] / close.iloc[-1 - n] - 1) * 100, 1)
                if len(close) > n else None)
    haut = float(close.tail(252).max())
    bas = float(close.tail(252).min())
    out["mouvement"] = {"5_seances": var(5), "1_mois": var(21),
                        "3_mois": var(63),
                        "sous_plus_haut_1an": _r((cours / haut - 1) * 100, 1),
                        "sur_plus_bas_1an": _r((cours / bas - 1) * 100, 1)}

    # --- le calendrier ---------------------------------------------------
    cal = {"jours": jours_resultats}
    if jours_resultats is None:
        cal["pendant"] = None
    else:
        cal["pendant"] = bool(jours_resultats <= h)
    out["calendrier"] = cal

    # --- le marche -------------------------------------------------------
    out["marche"] = rc.marche(bench, bnom) if bench is not None else None

    # --- le portefeuille -------------------------------------------------
    lignes, rend = [], close.pct_change()
    for htk, qte in sorted(held.items()):
        if not htk or not qte:
            continue
        x = {"ticker": htk, "quantite": qte}
        try:
            hd = charge(htk)
            hc = hd["close"].astype(float)
            hdev = rc._devise(htk)
            hfx = rc.taux_change([hdev], charge).get(hdev)
            if hfx:
                x["valeur_eur"] = _r(qte * float(hc.iloc[-1]) / hfx, 2)
                x["poids_pct"] = _r(qte * float(hc.iloc[-1]) / hfx
                                    / capital * 100, 1)
            if htk != tk:
                a = pd.concat([rend, hc.pct_change()], axis=1,
                              join="inner").dropna().tail(252)
                if len(a) >= SEANCES_CORR:
                    x["correlation"] = _r(float(np.corrcoef(
                        a.iloc[:, 0], a.iloc[:, 1])[0, 1]), 2)
                    x["seances_corr"] = int(len(a))
        except Exception:
            x["erreur"] = "cours indisponibles"
        lignes.append(x)
    out["portefeuille"] = {
        "lignes": lignes,
        "valeur_eur": _r(sum(x.get("valeur_eur") or 0 for x in lignes), 2),
        "deja": deja_qte > 0}

    out["liste"] = liste(out, reponses)
    return out


def liste(ex: dict, reponses: dict) -> dict:
    """L'etat de la liste de controle. Un compte, pas un verdict."""
    t = ex.get("taille") or {}
    cal = ex.get("calendrier") or {}
    faits = {
        "stop": ex.get("stop") is not None and ex.get("entree") is not None
        and ex["stop"] < ex["entree"],
        "duree": bool(ex.get("seances")),
        "plafond": (t.get("titres", 0) > 0
                    and (t.get("poids_apres_pct") or 0)
                    <= (ex.get("plafond_pct") or 0) + 1e-9),
    }
    items = []
    for cle, genre, lib in QUESTIONS:
        if genre == "texte":
            rempli = bool(str(reponses.get(cle) or "").strip())
        elif genre == "case":
            rempli = bool(reponses.get(cle))
        else:
            rempli = bool(faits.get(cle))
        det = ""
        if cle == "perte" and t.get("perte_stop_eur") is not None:
            det = (f"{t['perte_stop_eur']:.2f} €, soit "
                   f"{t['perte_stop_pct_capital']:.2f} % du capital, frais "
                   f"compris").replace(".", ",")
        elif cle == "resultats":
            det = ("date des prochains résultats inconnue : à vérifier à "
                   "la main" if cal.get("jours") is None else
                   f"prochains résultats dans {cal['jours']} séances — "
                   + ("PENDANT la durée envisagée" if cal.get("pendant")
                      else "après la durée envisagée"))
        elif cle == "stop" and ex.get("stop") is not None:
            det = (f"{ex['stop']:.2f} {ex.get('devise', '')} — "
                   f"{ex.get('stop_source', '')}").replace(".", ",", 1)
        elif cle == "duree" and ex.get("duree"):
            det = str(ex["duree"])
        elif cle == "plafond" and t.get("poids_apres_pct") is not None:
            det = (f"{t['poids_apres_pct']:.1f} % après l'achat, plafond "
                   f"{ex.get('plafond_pct'):.0f} %").replace(".", ",")
        items.append({"cle": cle, "genre": genre, "libelle": lib,
                      "rempli": rempli, "detail": det})
    n = sum(1 for i in items if i["rempli"])
    return {"items": items, "remplis": n, "total": len(items),
            "manquent": [i["libelle"] for i in items if not i["rempli"]]}


# ------------------------------------------------------------ la trace
def enregistre(ex: dict, reponses: dict) -> dict:
    """Ecrit la decision au carnet : les faits recalcules par le serveur,
    et vos reponses, dates. Rien n'est interprete."""
    from . import carnet as cn
    if not ex.get("ok"):
        return {"ok": False, "erreur": ex.get("erreur", "examen impossible")}
    t = ex.get("taille") or {}
    titre = (f"AVANT L'ORDRE {ex['ticker']} — {t.get('titres', 0)} titres, "
             f"stop {_fr(ex.get('stop'))} {ex.get('devise', '')}").strip()
    texte = ("POURQUOI : " + str(reponses.get("raison") or "—").strip()
             + "\n\nJ'AURAI TORT SI : " + str(reponses.get("tort") or "—")
             .strip())
    faits = {k: ex.get(k) for k in ("ticker", "date", "cours", "entree",
                                    "stop", "stop_source", "devise",
                                    "capital", "risque_pct", "duree",
                                    "taille", "stop_faits", "mouvement",
                                    "calendrier", "marche", "portefeuille",
                                    "qualite", "liste")}
    faits["reponses"] = {k: reponses.get(k) for k, _g, _l in QUESTIONS}
    e = cn.ajoute(titre=titre, texte=texte, ticker=ex["ticker"],
                  genre="decision", donnees=cn._simplifie(faits))
    return {"ok": True, "entree": {"id": e["id"], "date": e["date"],
                                   "titre": e["titre"]}}


def inscrit_ligne(ex: dict, quantite=None, prix=None) -> dict:
    """L'ordre passe : la ligne entre au registre des positions AVEC son
    stop, pour que l'accueil et l'onglet IBKR le surveillent. Une ligne
    deja inscrite n'est pas ecrasee."""
    from . import positions as ps
    if not ex.get("ok") or ex.get("stop") is None:
        return {"ok": False, "erreur": "examen incomplet : pas de stop"}
    tk = ex["ticker"]
    if tk in ps.tickers():
        return {"ok": False, "erreur": (
            f"{tk} est déjà au registre des positions : mettez la ligne à "
            f"jour dans MES POSITIONS, sans l'écraser.")}
    q = _num(quantite) or (ex.get("taille") or {}).get("titres") or 0
    p = _num(prix) or ex.get("entree")
    if q <= 0 or not p:
        return {"ok": False, "erreur": "quantité ou prix illisible"}
    ps.ajoute(tk, q, p, ex["stop"])
    return {"ok": True, "ligne": {"ticker": tk, "quantite": q, "entree": p,
                                  "stop": ex["stop"]}}


# ------------------------------------------------------------ en clair
def _fr(x, dec=2):
    return "—" if x is None else f"{x:,.{dec}f}".replace(",", " ").replace(
        ".", ",")


def lignes(ex: dict) -> list[str]:
    """Les faits en phrases, pour la ligne de commande et le majordome.
    Chaque chiffre vient de `ex`."""
    if not ex.get("ok"):
        return [ex.get("erreur", "examen impossible")]
    t, s = ex.get("taille") or {}, ex.get("stop_faits") or {}
    L = [f"{ex['ticker']} — cours {_fr(ex['cours'], 2)} {ex['devise']} au "
         f"{ex['date']} ; entrée {_fr(ex['entree'], 2)}, stop "
         f"{_fr(ex['stop'], 2)} ({ex['stop_source']})."]
    if t.get("titres"):
        L.append(f"Taille : {t['titres']} titres pour {_fr(t['investi_eur'])} €"
                 f" ; perte au stop {_fr(t['perte_stop_eur'])} €, soit "
                 f"{_fr(t['perte_stop_pct_capital'])} % du capital ; poids "
                 f"après l'achat {_fr(t['poids_apres_pct'], 1)} %"
                 + (" — borné par le plafond." if t.get("plafonne") else "."))
    else:
        L.append(f"Taille : aucun titre — {t.get('motif', '')}.")
    if s:
        L.append(f"Le stop est à {_fr(s['distance_pct'])} % de l'entrée, "
                 f"soit {_fr(s['en_atr'])} ATR et {_fr(s['en_ecarts_jour'], 1)}"
                 f" fois le mouvement quotidien ordinaire.")
        hs = s.get("histo") or {}
        if hs.get("periodes"):
            L.append(f"Sur {hs['periodes']} périodes de {ex['duree']} : "
                     f"−{_fr(s['distance_pct'])} % touché en chemin "
                     f"{hs['perte_touchee']} fois, +{_fr(s['gain_seuil_pct'])} %"
                     f" touché {hs['gain_touche']} fois.")
    c = ex.get("calendrier") or {}
    L.append("Résultats : " + ("date inconnue, à vérifier." if c.get("jours")
                              is None else f"dans {c['jours']} séances."))
    li = ex.get("liste") or {}
    L.append(f"Liste : {li.get('remplis', 0)} points sur {li.get('total', 0)}"
             f" remplis.")
    return L + ["", RAPPEL]


def main(argv=None) -> None:
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 2:
        print(__doc__)
        return
    nb, un = (a[2], a[3]) if len(a) > 3 else (2, "mois")
    from . import data as dl
    ex = examine(a[0], a[1], nombre=nb, unite=un,
                 jours_resultats=dl.days_to_earnings_yf(a[0].upper()))
    print()
    for x in lignes(ex):
        print("  " + x)
    print()


if __name__ == "__main__":
    main()
