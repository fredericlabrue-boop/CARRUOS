"""Gains espered a l'entree, et ce qu'un take-profit ferait vraiment.

DEUX QUESTIONS QUI N'ONT PAS LA MEME REPONSE

1. « Combien puis-je esperer gagner sur cette ligne ? »
   C'est de l'ARITHMETIQUE tant qu'on parle de la position : combien de
   titres, combien d'euros risques, ce que vaut chaque R en euros, quel
   mouvement il faut pour couvrir les frais et l'impot. Ce module le
   calcule.

   Cela devient une PREDICTION des qu'on multiplie par une esperance. Une
   esperance n'existe que si elle a ete mesuree sur un echantillon, et
   elle ne vaut que ce que vaut cet echantillon. On la rend donc toujours
   avec son nombre de trades et son intervalle de Wilson — jamais un
   chiffre seul.

   Et quand l'hypothese est NO-GO, l'esperance honnete est : AUCUNE. Pas
   un petit nombre optimiste, pas « ca depend ». Aucune.

2. « Comment parametrer mon take-profit ? »
   Ce module ne repond pas a cette question, et c'est deliberе. Il repond
   a une autre, qui est mesurable : « QU'AURAIT FAIT un take-profit a
   chaque niveau, sur MES trades ? »

   La difference n'est pas un detail de formulation. Choisir un niveau
   parce qu'il sort le mieux dans cette table, c'est exactement la peche
   que le protocole interdit : sept parametres a cinq valeurs font 78 125
   combinaisons et environ 3 900 faux positifs a z >= 2. Un take-profit
   choisi ainsi aurait l'air excellent sur le passe et ne vaudrait rien.

   Pour ajouter vraiment un take-profit : nouvelle specification, nouvelle
   empreinte, nouvelle periode de validation non touchee. La table
   ci-dessous sert a savoir si ca vaut la peine d'ecrire ce document —
   pas a remplir un champ.

CE QUE DIT DEJA LA SPECIFICATION

Les hypotheses 2 et 3 sont explicites : « AUCUN take-profit ». Motif
ecrit noir sur blanc, et ce n'est pas une opinion, c'est un constat :
zero take-profit touche sur la version precedente, 97 % de sorties par
autre chose. Un take-profit coupe la derive exactement la ou elle produit
son rendement.

    py -m equity_scanner.sortie --csv phase0-sp500.csv
"""

from __future__ import annotations

import argparse
import csv as _csv
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest as bt

# Niveaux passes en revue, en multiples de risque. Ce ne sont PAS des
# parametres de la strategie : rien ici n'est gele, rien ici ne s'applique.
# C'est l'axe d'un tableau de mesure.
NIVEAUX = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)


# ---------------------------------------------------------------------
# Le parcours d'un trade, en multiples de risque
# ---------------------------------------------------------------------
def parcours(t, d: pd.DataFrame) -> dict | None:
    """Ce que la ligne a fait ENTRE son entree et sa sortie.

    Tout est mesure sur les CLOTURES, pas sur les plus hauts de seance.
    C'est ce que fait le moteur pour le stop, et il faut s'y tenir : un
    take-profit mesure sur les plus hauts se declencherait sur des meches
    qu'un ordre reel n'aurait pas forcement attrapees. Mesurer sur la
    cloture sous-estime peut-etre un peu le take-profit ; mesurer sur le
    plus haut le surestimerait beaucoup, et dans le sens qui fait plaisir.
    """
    risque = getattr(t, "risque", 0.0)
    if risque <= 0 or t.ticker not in getattr(d, "_nom", {"": None}) and d is None:
        return None
    if "close" not in d.columns:
        return None
    sens = getattr(t, "sens", 1)
    c = d["close"]
    a = int(c.index.searchsorted(t.entree_d, side="left"))
    b = int(c.index.searchsorted(t.sortie_d, side="right"))
    if b <= a:
        return None
    seg = c.iloc[a:b].to_numpy(dtype=float)
    # R latent a chaque seance, frais d'aller-retour deja comptes : c'est
    # ce qu'on encaisserait en sortant a cette cloture-la.
    r = ((seg * (1 - bt.COUT_PAR_COTE - bt.SLIPPAGE) - t.entree) * sens
         ) / risque
    if not len(r) or not np.isfinite(r).any():
        return None
    k = int(np.nanargmax(r))
    return {
        "ticker": t.ticker,
        "R_final": float(t.R),
        "R_max": float(r[k]),          # MFE : le meilleur moment de la ligne
        "R_min": float(np.nanmin(r)),  # MAE : le pire
        "barre_max": k,
        "barres": int(t.barres),
        "rendu": float(r[k] - t.R),    # ce qui a ete rendu apres le sommet
    }


def profil(trades, series: dict) -> dict:
    """Distribution des parcours. Des faits, aucune recommandation."""
    p = [x for x in (parcours(t, series.get(t.ticker))
                     for t in trades if t.ticker in series) if x]
    if not p:
        return {"n": 0, "parcours": []}
    rmax = np.array([x["R_max"] for x in p])
    rfin = np.array([x["R_final"] for x in p])
    rendu = np.array([x["rendu"] for x in p])
    atteint = {niv: int((rmax >= niv).sum()) for niv in NIVEAUX}
    # Parmi les lignes qui ont touche +1R a un moment, combien finissent
    # dans le rouge ? C'est le chiffre qui donne envie d'un take-profit.
    touche1 = rmax >= 1.0
    return {
        "n": len(p),
        "parcours": p,
        "R_max_median": float(np.median(rmax)),
        "R_final_moyen": float(rfin.mean()),
        "rendu_median": float(np.median(rendu)),
        "atteint": atteint,
        "touche_1R": int(touche1.sum()),
        "touche_1R_puis_perte": int((touche1 & (rfin < 0)).sum()),
        "barre_max_mediane": float(np.median([x["barre_max"] for x in p])),
    }


# ---------------------------------------------------------------------
# Ce qu'un take-profit aurait fait
# ---------------------------------------------------------------------
def tronque(t, d: pd.DataFrame, niveau: float):
    """Le meme trade, sorti au premier passage a `niveau` R sur cloture.

    Un take-profit ne peut que faire sortir PLUS TOT. Il ne change ni le
    signal d'entree, ni quoi que ce soit avant la barre ou il se
    declenche. Rejouer le trade tronque est donc exact, pas une
    approximation — a une reserve pres, ecrite dans `table()`.
    """
    risque = getattr(t, "risque", 0.0)
    if risque <= 0 or d is None or "close" not in d.columns:
        return t
    sens = getattr(t, "sens", 1)
    c = d["close"]
    a = int(c.index.searchsorted(t.entree_d, side="left"))
    b = int(c.index.searchsorted(t.sortie_d, side="right"))
    if b <= a:
        return t
    seg = c.iloc[a:b]
    px = seg.to_numpy(dtype=float)
    r = ((px * (1 - bt.COUT_PAR_COTE - bt.SLIPPAGE) - t.entree) * sens) / risque
    hit = np.flatnonzero(r >= niveau)
    if not len(hit):
        return t
    k = int(hit[0])
    if k == 0:                       # deja au niveau des l'entree : on garde
        return t
    neuf = type(t)(**{**t.__dict__,
                      "sortie_d": seg.index[k],
                      "sortie": bt._prix_sortie(float(px[k])),
                      "barres": k,
                      "motif": f"take-profit {niveau:g}R"})
    return neuf


def _mesures(trades, series: dict, max_poids: float) -> dict:
    rs = [t.R for t in trades]
    gains = sum(x for x in rs if x > 0)
    pertes = -sum(x for x in rs if x < 0)
    pf = (gains / pertes) if pertes > 0 else (float("inf") if gains else 0.0)
    pt = bt.portefeuille(trades, series=series, max_poids=max_poids)
    return {"n": len(trades), "pf": pf,
            "ev": float(np.mean(rs)) if rs else 0.0,
            "reussite": (sum(1 for x in rs if x > 0) / len(rs)) if rs else 0.0,
            "duree": float(np.mean([t.barres for t in trades])) if trades else 0.0,
            "dd": pt["dd"] * 100.0}


def table(trades, series: dict, niveaux=NIVEAUX,
          max_poids: float = 0.25) -> list[dict]:
    """Une ligne par niveau, plus la ligne « aucun take-profit ».

    RESERVE, et elle va dans le sens defavorable au take-profit — donc il
    faut la lire avant de conclure. Une sortie plus tot libere le titre
    plus tot : un nouveau signal aurait pu partir sur la meme valeur dans
    l'intervalle. Cette table ne les cree pas. Elle sous-estime donc
    legerement le NOMBRE de trades qu'un take-profit produirait. Elle
    n'affecte ni l'esperance par trade, ni le profit factor, qui sont
    exacts sur l'echantillon rejoue.
    """
    base = _mesures(list(trades), series, max_poids)
    lignes = [dict(base, niveau=None, coupes=0, part_coupee=0.0)]
    for niv in niveaux:
        coupes, nouveaux = 0, []
        for t in trades:
            u = tronque(t, series.get(t.ticker), niv)
            if u is not t:
                coupes += 1
            nouveaux.append(u)
        m = _mesures(nouveaux, series, max_poids)
        m.update({"niveau": niv, "coupes": coupes,
                  "part_coupee": coupes / len(trades) if trades else 0.0})
        lignes.append(m)
    return lignes


# ---------------------------------------------------------------------
# L'arithmetique d'une entree — ce qui n'est PAS une prediction
# ---------------------------------------------------------------------
def entree(prix: float, stop: float, sleeve: float,
           risque_pct: float = 0.01, max_poids: float = 0.25,
           impot: float = 0.30, frais_par_cote: float = 0.0015) -> dict:
    """Tout ce qu'on peut dire d'une entree AVANT de savoir ce qu'elle fera.

    Que de l'arithmetique : rien ici ne suppose que le titre monte.
    """
    unitaire = prix - stop
    if prix <= 0 or unitaire <= 0:
        return {"ok": False,
                "motif": "le stop doit etre sous le prix d'entree"}
    titres = int((risque_pct * sleeve) // unitaire)
    plafond = int((max_poids * sleeve) // prix)
    rogne = titres > plafond
    titres = max(0, min(titres, plafond))
    notionnel = titres * prix
    risque_eur = titres * unitaire
    # Mouvement necessaire pour ne RIEN gagner : les frais des deux cotes.
    mort = 2 * frais_par_cote
    return {
        "ok": titres > 0,
        "motif": "" if titres > 0 else
                 "sleeve trop petit pour un seul titre a ce niveau de risque",
        "prix": prix, "stop": stop,
        "risque_unitaire": unitaire,
        "risque_pct_titre": unitaire / prix,
        "titres": titres,
        "notionnel": notionnel,
        "risque_eur": risque_eur,
        "poids": notionnel / sleeve if sleeve else 0.0,
        "plafonne": rogne,
        "euro_par_R": risque_eur,
        "point_mort_pct": mort,
        "point_mort_prix": prix * (1 + mort),
        # Ce que vaut un R apres impot, si la ligne est gagnante et vendue.
        "euro_par_R_net": risque_eur * (1 - impot),
        "impot": impot,
    }


def esperance(entr: dict, ev_R: float | None, n_trades: int,
              valide: bool) -> dict:
    """Traduit une esperance MESUREE en euros — ou refuse de le faire.

    `valide` dit si l'hypothese a passe sa Phase 0. Si elle ne l'a pas
    passee, il n'y a pas d'esperance a traduire : la multiplier par un
    nombre d'euros donnerait un chiffre qui a l'air d'une prevision alors
    qu'il n'en est pas une.
    """
    if not valide or ev_R is None or n_trades <= 0:
        return {
            "chiffrable": False,
            "pourquoi": ("L'hypothese n'a pas passe sa Phase 0. Il n'y a "
                         "donc aucune esperance mesuree a convertir en "
                         "euros. Un gain espere se calcule a partir d'un "
                         "avantage demontre ; sans avantage demontre, le "
                         "gain espere est zero, pas un petit nombre."),
            "n_trades": n_trades,
        }
    par_trade = ev_R * entr.get("euro_par_R", 0.0)
    return {
        "chiffrable": True,
        "ev_R": ev_R,
        "n_trades": n_trades,
        "euros_par_trade": par_trade,
        "euros_par_trade_net": par_trade * (1 - entr.get("impot", 0.30)),
        "avertissement": (
            f"Moyenne sur {n_trades} trades passes, pas une prevision sur "
            "celui-ci. Une ligne prise isolement ne rend pas la moyenne : "
            "elle touche son stop ou elle ne le touche pas."),
    }


# ---------------------------------------------------------------------
# Rendu texte
# ---------------------------------------------------------------------
def texte_profil(p: dict) -> str:
    if not p.get("n"):
        return "\n  Aucun trade exploitable pour mesurer un parcours.\n"
    L = [f"\n  PARCOURS DES {p['n']} TRADES  (mesure sur les clotures)",
         f"    R maximum median          {p['R_max_median']:+.2f} R",
         f"    R final moyen             {p['R_final_moyen']:+.2f} R",
         f"    rendu apres le sommet     {p['rendu_median']:+.2f} R (median)",
         f"    sommet atteint vers la    {p['barre_max_mediane']:.0f}e seance",
         "",
         "    lignes ayant touche ce niveau a un moment :"]
    for niv, k in p["atteint"].items():
        part = k / p["n"] * 100
        L.append(f"      +{niv:g} R  {k:5d}  ({part:4.1f} %)")
    if p["touche_1R"]:
        part = p["touche_1R_puis_perte"] / p["touche_1R"] * 100
        L.append("")
        L.append(f"    {p['touche_1R_puis_perte']} lignes sur "
                 f"{p['touche_1R']} ({part:.0f} %) ont touche +1 R puis fini "
                 "dans le rouge.")
        L.append("    C'est ce chiffre qui donne envie d'un take-profit.")
        L.append("    La table ci-dessous dit ce qu'il en couterait.")
    return "\n".join(L) + "\n"


def texte_table(lignes: list[dict]) -> str:
    L = ["\n  CE QU'UN TAKE-PROFIT AURAIT FAIT, SUR CES MEMES TRADES",
         "",
         f"    {'take-profit':<16}{'trades':>7}{'coupees':>9}"
         f"{'PF':>7}{'EV/trade':>10}{'reussite':>10}{'duree':>7}{'DD':>8}"]
    for x in lignes:
        nom = "aucun (la regle)" if x["niveau"] is None \
              else f"+{x['niveau']:g} R"
        pf = "inf" if x["pf"] == float("inf") else f"{x['pf']:.2f}"
        L.append(f"    {nom:<16}{x['n']:>7}{x['coupes']:>9}{pf:>7}"
                 f"{x['ev']:>+10.3f}{x['reussite']:>9.0%}"
                 f"{x['duree']:>6.0f}j{x['dd']:>7.1f}%")
    base = lignes[0]
    meilleure = max(lignes[1:], key=lambda x: x["ev"], default=None)
    L.append("")
    if meilleure and meilleure["ev"] > base["ev"]:
        L.append(f"    Le niveau +{meilleure['niveau']:g} R sort au-dessus de "
                 "la regle actuelle sur CET echantillon.")
        L.append("    NE LE PARAMETRE PAS POUR AUTANT. Huit niveaux essayes,")
        L.append("    c'est huit chances qu'un d'entre eux sorte devant par")
        L.append("    hasard. Le tester correctement demande une nouvelle")
        L.append("    specification, une nouvelle empreinte, et une periode")
        L.append("    de validation qui n'a jamais ete regardee.")
    else:
        L.append("    Aucun niveau ne fait mieux que la regle actuelle.")
        L.append("    C'est le resultat attendu : un take-profit coupe la")
        L.append("    derive la ou elle produit son rendement.")
    L.append("")
    L.append("    RESERVE : une sortie plus tot libere le titre plus tot. Un")
    L.append("    nouveau signal aurait pu partir dans l'intervalle ; cette")
    L.append("    table ne le cree pas. Elle sous-estime donc le nombre de")
    L.append("    trades, pas l'esperance par trade ni le profit factor.")
    return "\n".join(L) + "\n"


def texte_entree(e: dict, esp: dict | None = None) -> str:
    if not e.get("ok"):
        return f"\n  Entree non calculable : {e.get('motif', '')}\n"
    L = ["\n  L'ENTREE, EN EUROS  (arithmetique, aucune prevision)",
         f"    prix d'entree             {e['prix']:.2f}",
         f"    stop                      {e['stop']:.2f}  "
         f"({e['risque_pct_titre']:.1%} sous l'entree)",
         f"    titres                    {e['titres']}"
         + ("   (plafonne par le poids maximum)" if e["plafonne"] else ""),
         f"    montant engage            {e['notionnel']:,.0f} EUR  "
         f"({e['poids']:.1%} du sleeve)",
         f"    perte si le stop saute    {e['risque_eur']:,.0f} EUR",
         f"    un R vaut                 {e['euro_par_R']:,.0f} EUR brut  "
         f"/ {e['euro_par_R_net']:,.0f} EUR apres impot",
         f"    point mort (frais seuls)  {e['point_mort_prix']:.2f}  "
         f"(+{e['point_mort_pct']:.2%})"]
    if esp is not None:
        L.append("")
        if not esp.get("chiffrable"):
            L.append("    GAIN ESPERE : non chiffrable.")
            for ligne in _plie(esp["pourquoi"], 66):
                L.append(f"    {ligne}")
        else:
            L.append(f"    esperance mesuree         {esp['ev_R']:+.3f} R "
                     f"sur {esp['n_trades']} trades")
            L.append(f"    soit par trade            "
                     f"{esp['euros_par_trade']:+,.0f} EUR brut / "
                     f"{esp['euros_par_trade_net']:+,.0f} EUR net")
            for ligne in _plie(esp["avertissement"], 66):
                L.append(f"    {ligne}")
    return "\n".join(L) + "\n"


def _plie(texte: str, largeur: int) -> list[str]:
    mots, ligne, out = texte.split(), "", []
    for m in mots:
        if len(ligne) + len(m) + 1 > largeur:
            out.append(ligne)
            ligne = m
        else:
            ligne = f"{ligne} {m}".strip()
    if ligne:
        out.append(ligne)
    return out


# ---------------------------------------------------------------------
# CLI : relit un rapport deja calcule
# ---------------------------------------------------------------------
def depuis_csv(chemin: str, journal=print) -> dict:
    """Rejoue un rapport de Phase 0. Les cours viennent du cache."""
    from . import cache as ch

    f = Path(chemin)
    if not f.exists():
        journal(f"\n  Fichier introuvable : {chemin}\n")
        return {}
    lignes = list(_csv.DictReader(f.open(encoding="utf-8")))
    if not lignes:
        journal("\n  Rapport vide.\n")
        return {}

    trades, tickers = [], sorted({l["ticker"] for l in lignes})
    journal(f"\n  {len(lignes)} trades sur {len(tickers)} titres.")
    journal("  Relecture des cours (cache)...")
    brutes, echecs = ch.charge_lot(tickers, annees=20, journal=journal)
    from .indicators import enrich
    series = {tk: enrich(d) for tk, d in brutes.items()}
    if echecs:
        journal(f"  {len(echecs)} titre(s) indisponible(s), ignore(s).")

    for l in lignes:
        if l["ticker"] not in series:
            continue
        try:
            trades.append(bt.Trade(
                l["ticker"], pd.Timestamp(l["entree"]),
                pd.Timestamp(l["sortie"]), float(l["prix_entree"]),
                float(l["prix_sortie"]), float(l["stop"]), 0.0,
                int(float(l["barres"])), l.get("motif", "")))
        except Exception:
            continue
    if not trades:
        journal("\n  Aucun trade reconstituable.\n")
        return {}

    p = profil(trades, series)
    journal(texte_profil(p))
    t = table(trades, series)
    journal(texte_table(t))
    return {"profil": p, "table": t}


def main() -> None:
    a = argparse.ArgumentParser(
        description="Parcours des trades et cout d'un take-profit")
    a.add_argument("--csv", required=True, help="un rapport de Phase 0")
    o = a.parse_args()
    depuis_csv(o.csv)


if __name__ == "__main__":
    main()
