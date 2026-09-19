"""Ce que le titre fait a chaque horizon, et quel objectif est atteignable.

A QUOI CA REPOND

  « A une semaine, ce titre bouge de combien ? »
  « Si je veux prendre mon profit, un take-profit de combien serait
    envisageable ? »

Ces deux questions ont une reponse mesurable, et ce module la donne. Une
troisieme n'en a pas : « est-ce que ca va monter ? ». Rien ici n'y
repond, et l'absence est voulue.

COMMENT C'EST MESURE, ET POURQUOI PAS AUTREMENT

On ne modelise pas. On regarde ce que le titre A FAIT, sur toutes les
fenetres de son historique.

Pour l'amplitude : toutes les fenetres de H seances, la variation de
chacune, et on rend les quantiles. Pas de loi normale, pas de racine du
temps — les vraies series ont des queues epaisses, et un modele
lognormal sous-estime justement les mouvements qui comptent.

Pour un objectif : sur chaque fenetre, le titre est-il monte de X % a un
moment avant la fin ? En combien de seances ? Et parmi les fenetres qui
y sont arrivees, combien ont ensuite tout rendu ?

TROIS RESERVES, ET ELLES COMPTENT

1. C'est INCONDITIONNEL. On part de n'importe quelle seance, pas d'un
   signal d'entree. C'est une propriete du TITRE, pas d'une strategie.
   Si une strategie faisait mieux que ca, il faudrait le demontrer en
   Phase 0 — ce qu'aucune n'a fait a ce jour.

2. Les fenetres se CHEVAUCHENT. Mille fenetres de 252 seances tirees
   d'un historique de 5 000 seances ne sont pas mille observations
   independantes : il y en a environ vingt. Le nombre de fenetres
   independantes est affiche a cote, et c'est lui qu'il faut regarder.

3. Une frequence passee n'est pas une probabilite future. « Ce titre a
   touche +10 % dans 40 % des mois ecoules » ne veut pas dire « il y a
   40 % de chances le mois prochain ». La volatilite change, l'entreprise
   change, et un titre qui a double ne refera pas le meme chemin.

    py -m equity_scanner.horizon MC.PA
    py -m equity_scanner.horizon NVDA --cibles 5 10 15 20
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

# Horizons en seances de bourse. Un mois calendaire fait environ 21
# seances, une annee environ 252 : ce sont ces chiffres-la qui comptent,
# pas les jours du calendrier.
HORIZONS = (("1 jour", 1), ("1 semaine", 5), ("2 semaines", 10),
            ("1 mois", 21), ("3 mois", 63), ("6 mois", 126), ("1 an", 252))

# Objectifs passes en revue, en pourcentage. Aucun n'est un parametre de
# strategie : rien ici n'est gele et rien ici ne declenche quoi que ce soit.
CIBLES = (2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 50.0)

MINI_FENETRES = 30          # en-dessous, on ne rend rien plutot qu'un chiffre


def _cloture(d: pd.DataFrame) -> pd.Series | None:
    if d is None or "close" not in getattr(d, "columns", []):
        return None
    c = d["close"].dropna().astype(float)
    return c if len(c) >= 120 else None


# ---------------------------------------------------------------------
# Amplitude par horizon
# ---------------------------------------------------------------------
def amplitude(d: pd.DataFrame, horizons=HORIZONS) -> list[dict]:
    """Variation observee sur toutes les fenetres de chaque horizon.

    On rend la MEDIANE de la variation absolue — le mouvement typique —
    et les quantiles 16/84 et 2,5/97,5 de la variation signee, qui
    encadrent respectivement deux tiers et 95 % des fenetres passees.

    La mediane du signe n'est PAS affichee comme une prevision. Elle
    figure parce qu'un titre qui a monte sur toute la periode donnerait
    un encadrement decale vers le haut, et il faut pouvoir le voir plutot
    que de le subir.
    """
    c = _cloture(d)
    if c is None:
        return []
    px = c.to_numpy()
    n = len(px)
    out = []
    for nom, h in horizons:
        if n <= h + MINI_FENETRES:
            continue
        var = (px[h:] / px[:-h] - 1.0) * 100.0
        var = var[np.isfinite(var)]
        if len(var) < MINI_FENETRES:
            continue
        out.append({
            "nom": nom, "seances": h,
            "fenetres": int(len(var)),
            # Des fenetres qui se recouvrent ne sont pas des observations
            # independantes. Celui-ci est le nombre honnete.
            "independantes": max(1, int(len(var) // h)),
            "typique": float(np.median(np.abs(var))),
            "bas68": float(np.percentile(var, 16)),
            "haut68": float(np.percentile(var, 84)),
            "bas95": float(np.percentile(var, 2.5)),
            "haut95": float(np.percentile(var, 97.5)),
            "pire": float(var.min()),
            "meilleure": float(var.max()),
            "mediane_signee": float(np.median(var)),
        })
    return out


# ---------------------------------------------------------------------
# Quel objectif est atteignable
# ---------------------------------------------------------------------
def _fenetres(px: np.ndarray, h: int) -> np.ndarray:
    """Toutes les fenetres de h seances SUIVANT chaque point de depart."""
    from numpy.lib.stride_tricks import sliding_window_view
    return sliding_window_view(px[1:], h)          # depart exclu du parcours


def atteinte(d: pd.DataFrame, cibles=CIBLES, seances: int = 21) -> list[dict]:
    """Pour chaque objectif : a-t-il ete touche, en combien de temps, et
    la hausse a-t-elle tenu ?

    « Touche » se lit sur les CLOTURES, comme tout le reste du programme.
    Un objectif mesure sur les plus hauts de seance se declencherait sur
    des meches qu'un ordre reel n'attrape pas toujours — ce serait plus
    flatteur et moins vrai.
    """
    c = _cloture(d)
    if c is None:
        return []
    px = c.to_numpy()
    if len(px) < seances + MINI_FENETRES + 2:
        return []
    depart = px[:-seances - 1]
    suite = _fenetres(px, seances)[:len(depart)]
    if not len(depart):
        return []

    fin = suite[:, -1]
    out = []
    for cible in cibles:
        seuil = depart * (1.0 + cible / 100.0)
        touche = suite >= seuil[:, None]
        atteint = touche.any(axis=1)
        k = int(atteint.sum())
        if not k:
            out.append({"cible": cible, "fenetres": int(len(depart)),
                        "independantes": max(1, len(depart) // seances),
                        "part": 0.0, "seances_medianes": None,
                        "part_rendue": None, "fin_moyenne": None})
            continue
        # Premiere seance ou l'objectif est franchi, pour les seules
        # fenetres qui le franchissent.
        premiere = np.argmax(touche, axis=1)[atteint] + 1
        # Parmi celles qui ont touche : combien finissent SOUS l'objectif ?
        rendue = fin[atteint] < seuil[atteint]
        out.append({
            "cible": cible,
            "fenetres": int(len(depart)),
            "independantes": max(1, int(len(depart) // seances)),
            "part": k / len(depart),
            "seances_medianes": float(np.median(premiere)),
            "part_rendue": float(rendue.mean()),
            "fin_moyenne": float(np.mean(fin[atteint] / depart[atteint] - 1)
                                 * 100),
        })
    return out


def cibles_du_titre(d: pd.DataFrame, n: int = 6) -> tuple:
    """Objectifs exprimes dans l'unite du titre, pas en pourcentages ronds.

    Un objectif de +10 % ne veut pas dire la meme chose sur un titre qui
    bouge de 0,8 % par seance et sur un autre qui bouge de 3 %. On part
    donc de l'ATR : 1, 2, 3, 5, 8 et 12 fois le mouvement quotidien
    typique. Sur un titre calme cela donne des objectifs serres, sur un
    titre nerveux des objectifs larges — ce qui est le but.
    """
    c = _cloture(d)
    if c is None:
        return CIBLES
    atr = None
    if "atr14" in d.columns:
        v = d["atr14"].dropna()
        if len(v):
            atr = float(v.iloc[-1])
    if not atr or not np.isfinite(atr) or atr <= 0:
        # Sans ATR calcule, l'ecart-type quotidien fait un substitut
        # honnete : meme grandeur, meme role.
        r = np.log(c / c.shift(1)).dropna().tail(120)
        if not len(r):
            return CIBLES
        atr = float(c.iloc[-1]) * float(r.std())
    pct = atr / float(c.iloc[-1]) * 100.0
    if not np.isfinite(pct) or pct <= 0:
        return CIBLES
    return tuple(round(pct * m, 1) for m in (1, 2, 3, 5, 8, 12))[:n]


# ---------------------------------------------------------------------
# L'arithmetique d'une entree — ce qui n'est pas une prevision
# ---------------------------------------------------------------------
def entree(prix: float, stop: float, sleeve: float,
           risque_pct: float = 0.01, max_poids: float = 0.25,
           impot: float = 0.30, frais_par_cote: float = 0.0015) -> dict:
    """Combien de titres, combien d'euros en jeu, et a partir de quand on
    gagne quelque chose. Que de l'arithmetique : rien ici ne suppose que
    le titre monte."""
    if prix <= 0 or stop <= 0 or stop >= prix:
        return {"ok": False,
                "motif": "le stop doit etre strictement sous le prix"}
    unitaire = prix - stop
    titres = int((risque_pct * sleeve) // unitaire)
    plafond = int((max_poids * sleeve) // prix)
    rogne = titres > plafond
    titres = max(0, min(titres, plafond))
    mort = 2 * frais_par_cote
    return {
        "ok": titres > 0,
        "motif": "" if titres > 0
                 else "sleeve trop petit pour un titre a ce niveau de risque",
        "prix": prix, "stop": stop,
        "risque_unitaire": unitaire,
        "risque_pct_titre": unitaire / prix,
        "titres": titres,
        "notionnel": titres * prix,
        "risque_eur": titres * unitaire,
        "poids": (titres * prix / sleeve) if sleeve else 0.0,
        "plafonne": rogne,
        "euro_par_R": titres * unitaire,
        "euro_par_R_net": titres * unitaire * (1 - impot),
        "point_mort_pct": mort,
        "point_mort_prix": prix * (1 + mort),
        "impot": impot,
    }


def gain_espere(entr: dict, ev_R: float | None, n_trades: int,
                validee: bool) -> dict:
    """Traduit une esperance MESUREE en euros — ou refuse de le faire.

    `validee` dit si l'hypothese a passe sa Phase 0. Sans avantage
    demontre, le gain espere n'est pas un petit nombre prudent : il est
    nul. Afficher autre chose donnerait a une esperance inexistante
    l'apparence d'une prevision.
    """
    if not validee or ev_R is None or n_trades <= 0:
        return {"chiffrable": False, "n_trades": int(n_trades or 0),
                "pourquoi": (
                    "Aucune hypothese n'a passe sa Phase 0. Il n'y a donc "
                    "pas d'esperance mesuree a convertir en euros. Un gain "
                    "espere se calcule a partir d'un avantage demontre ; "
                    "sans avantage demontre il vaut zero, pas un petit "
                    "nombre optimiste.")}
    brut = ev_R * entr.get("euro_par_R", 0.0)
    return {"chiffrable": True, "ev_R": ev_R, "n_trades": int(n_trades),
            "euros_par_trade": brut,
            "euros_par_trade_net": brut * (1 - entr.get("impot", 0.30)),
            "avertissement": (
                f"Moyenne sur {n_trades} trades passes, pas une prevision "
                "sur celui-ci. Une ligne prise isolement ne rend pas la "
                "moyenne : elle touche son stop ou elle ne le touche pas.")}


# ---------------------------------------------------------------------
# Rendu texte
# ---------------------------------------------------------------------
def texte_amplitude(lignes: list[dict], ticker: str = "") -> str:
    if not lignes:
        return "\n  Historique trop court pour mesurer une amplitude.\n"
    L = [f"\n  AMPLITUDE PAR HORIZON{' — ' + ticker if ticker else ''}",
         "  Mesuree sur les fenetres passees. Aucune direction.",
         "",
         f"    {'horizon':<13}{'typique':>9}{'2 sur 3 entre':>22}"
         f"{'19 sur 20 entre':>24}{'indep.':>8}"]
    for x in lignes:
        L.append(f"    {x['nom']:<13}{x['typique']:>8.1f}%"
                 f"{x['bas68']:>13.1f}%{x['haut68']:>+8.1f}%"
                 f"{x['bas95']:>14.1f}%{x['haut95']:>+8.1f}%"
                 f"{x['independantes']:>8}")
    L.append("")
    L.append("    « typique » = variation absolue mediane : la moitie des")
    L.append("    fenetres ont bouge de moins que ca, l'autre de plus.")
    L.append("    « indep. » = fenetres qui ne se chevauchent pas. C'est la")
    L.append("    vraie taille de l'echantillon, pas le nombre de fenetres.")
    return "\n".join(L) + "\n"


def texte_atteinte(lignes: list[dict], seances: int, nom: str = "") -> str:
    if not lignes:
        return "\n  Historique trop court pour mesurer un objectif.\n"
    L = [f"\n  QUEL TAKE-PROFIT SERAIT ENVISAGEABLE — horizon {nom or seances}",
         "",
         f"    {'objectif':>9}{'touche':>9}{'en (median)':>14}"
         f"{'puis rendu':>13}{'indep.':>8}"]
    for x in lignes:
        cible = "+" + format(x["cible"], ".1f") + "%"
        if x["seances_medianes"] is None:
            L.append(f"    {cible:>9}{'jamais':>9}{'—':>14}{'—':>13}"
                     f"{x['independantes']:>8}")
            continue
        # Arrondir a 0 % une part non nulle ferait lire « jamais atteint »
        # sur une ligne qui l'a ete. On ecrit « <1 % ».
        part = ("<1%" if 0 < x["part"] < 0.005
                else format(x["part"], ".0%"))
        rendu = ("<1%" if 0 < x["part_rendue"] < 0.005
                 else format(x["part_rendue"], ".0%"))
        L.append(f"    {cible:>9}{part:>9}"
                 f"{format(x['seances_medianes'], '.0f') + ' j':>14}"
                 f"{rendu:>13}{x['independantes']:>8}")
    L.append("")
    L.append("    « touche » = part des fenetres passees ou le titre est")
    L.append("    monte au moins une fois a ce niveau, en cloture.")
    L.append("    « puis rendu » = parmi celles-la, part qui a fini SOUS")
    L.append("    l'objectif. C'est exactement ce qu'un take-profit evite —")
    L.append("    et c'est aussi la hausse qu'il coupe quand elle continue.")
    L.append("")
    L.append("    CE QUE CE TABLEAU N'EST PAS. Il part de n'importe quelle")
    L.append("    seance, pas d'un signal. C'est une propriete du titre, pas")
    L.append("    d'une strategie, et une frequence passee n'est pas une")
    L.append("    probabilite future.")
    return "\n".join(L) + "\n"


def texte_entree(e: dict, g: dict | None = None) -> str:
    if not e.get("ok"):
        return f"\n  Entree non calculable : {e.get('motif', '')}\n"
    L = ["\n  L'ENTREE EN EUROS  (arithmetique, aucune prevision)",
         f"    prix d'entree            {e['prix']:.2f}",
         f"    stop                     {e['stop']:.2f}"
         f"   ({e['risque_pct_titre']:.1%} sous l'entree)",
         f"    titres                   {e['titres']}"
         + ("   (plafonne par le poids maximum)" if e["plafonne"] else ""),
         f"    montant engage           {e['notionnel']:,.0f}"
         f"   ({e['poids']:.1%} du sleeve)",
         f"    perte si le stop saute   {e['risque_eur']:,.0f}",
         f"    un R vaut                {e['euro_par_R']:,.0f} brut"
         f"  /  {e['euro_par_R_net']:,.0f} apres impot",
         f"    point mort (frais)       {e['point_mort_prix']:.2f}"
         f"   (+{e['point_mort_pct']:.2%})"]
    if g is not None:
        L.append("")
        if not g.get("chiffrable"):
            L.append("    GAIN ESPERE : non chiffrable.")
            L += [f"    {x}" for x in _plie(g["pourquoi"], 64)]
        else:
            L.append(f"    esperance mesuree        {g['ev_R']:+.3f} R "
                     f"sur {g['n_trades']} trades")
            L.append(f"    soit                     "
                     f"{g['euros_par_trade']:+,.0f} brut  /  "
                     f"{g['euros_par_trade_net']:+,.0f} net")
            L += [f"    {x}" for x in _plie(g["avertissement"], 64)]
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
def rapport(ticker: str, cibles=None, journal=print) -> dict:
    from . import cache as ch
    from .indicators import enrich

    journal(f"\n  Chargement de {ticker}...")
    brut = ch.charge(ticker, annees=10)
    if brut is None or not len(brut):
        journal(f"  {ticker} : aucune donnee.\n")
        return {}
    d = enrich(brut)
    amp = amplitude(d)
    journal(texte_amplitude(amp, ticker))

    cib = tuple(cibles) if cibles else cibles_du_titre(d)
    for nom, h in (("1 semaine", 5), ("1 mois", 21), ("3 mois", 63)):
        att = atteinte(d, cib, h)
        if att:
            journal(texte_atteinte(att, h, nom))
    return {"amplitude": amp, "cibles": cib}


def main() -> None:
    a = argparse.ArgumentParser(
        description="Amplitude par horizon et objectifs atteignables")
    a.add_argument("ticker")
    a.add_argument("--cibles", type=float, nargs="*", default=None,
                   help="objectifs en %% (sinon deduits de l'ATR du titre)")
    o = a.parse_args()
    rapport(o.ticker, o.cibles)


if __name__ == "__main__":
    main()
