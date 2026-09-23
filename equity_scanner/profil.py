"""Le profil d'un instrument : ce qui le distingue, mesure.

« On ne traite pas une action Tesla comme un ETF monde ou un ETF
Nasdaq. » C'est vrai, et c'est verifiable — donc ca se mesure plutot que
ca ne se decrete.

Ce module ne dit jamais « celui-ci est fait pour le court terme ». Il
dit trois choses, toutes verifiables :

1. **Ce que l'instrument EST** — action, ETF, indice — quand le
   fournisseur de donnees le declare, et avec la mention qu'il s'agit
   d'une declaration et non d'une mesure.
2. **Comment il BOUGE** — volatilite annualisee, ecart quotidien
   ordinaire, ATR en pourcentage, pire recul historique et temps qu'il
   a mis a le rattraper, nombre de seances a plus de 5 %.
3. **Combien de temps la SPECIFICATION le garde** — la duree reelle des
   trades que ses regles de sortie produisent sur CE titre. C'est le
   seul chiffre qui reponde vraiment a « court ou long terme ? », parce
   qu'il vient des regles appliquees a l'historique, pas d'une
   impression.

Le point 3 merite d'etre dit clairement : l'horizon n'est pas une
decision qu'on prend, c'est une **consequence** des conditions de
sortie. La specification ferme a la premiere des quatre conditions
atteinte. Sur un ETF monde, ces conditions se declenchent rarement, donc
les positions durent. Sur un titre a forte amplitude, elles se
declenchent vite. La difference qu'il cherche existe, elle se mesure, et
elle sort du meme moteur que le reste.

Ce que ce module refuse
-----------------------
Un score composite qui melangerait volatilite, type et duree en un
chiffre unique : c'est ce que le projet refuse depuis le debut, et une
somme ponderee de criteres non testes ajoute des degres de liberte sans
rien demontrer.

Un classement « celui-ci d'abord ». Chaque mesure se lit seule.

Une esperance de gain. Aucune hypothese n'a passe sa Phase 0 ; la duree
de detention mesuree dit combien de temps les regles gardent une ligne,
elle ne dit rien sur ce que cette ligne rapporte.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# --- Bandes de volatilite, ECRITES AVANT toute mesure ----------------
#
# Le nom de chaque bande decrit ce qui a ete mesure, jamais ce qu'il
# faudrait en faire : « TRES AGITE » se verifie, « SPECULATIF » est un
# jugement. La borne haute de la derniere bande est volontairement
# ouverte.
#
# Les bornes sont en volatilite annualisee des rendements quotidiens.
# Reperes usuels : un ETF obligataire tourne autour de 5 %, un ETF monde
# autour de 15 %, un indice technologique autour de 22 %, une grande
# valeur de croissance autour de 40 %, une petite capitalisation ou une
# valeur en crise bien au-dela.
BANDES = (
    (0.00, 0.08, "tres_calme", "TRES CALME"),
    (0.08, 0.16, "calme", "CALME"),
    (0.16, 0.25, "moyen", "AMPLITUDE MOYENNE"),
    (0.25, 0.40, "agite", "AGITE"),
    (0.40, 0.65, "tres_agite", "TRES AGITE"),
    (0.65, float("inf"), "extreme", "AMPLITUDE EXTREME"),
)

# 252 seances par an : la convention de place, pas un reglage.
SEANCES_AN = 252

# En dessous, une volatilite annualisee ne veut rien dire : un ecart-type
# sur trente points est lui-meme tres imprecis.
MINI_BARRES = 120


def bande(vol: float | None) -> tuple[str, str]:
    """La bande d'une volatilite annualisee, et son libelle."""
    if vol is None or not math.isfinite(vol):
        return ("inconnue", "AMPLITUDE NON MESURABLE")
    for lo, hi, cle, lab in BANDES:
        if lo <= vol < hi:
            return (cle, lab)
    return ("extreme", "AMPLITUDE EXTREME")


def _vol(rend: pd.Series) -> float | None:
    """Volatilite annualisee. None si l'echantillon est trop court."""
    r = rend.dropna()
    if len(r) < MINI_BARRES:
        return None
    v = float(r.std(ddof=1)) * math.sqrt(SEANCES_AN)
    return v if math.isfinite(v) else None


def _recul_max(close: pd.Series) -> dict:
    """Le pire recul depuis un sommet, et le temps de retour.

    « Combien ce titre a-t-il deja perdu » est la question que personne
    ne pose avant d'acheter et que tout le monde se pose apres. Le temps
    de retour compte autant que la profondeur : un recul de 30 % rattrape
    en quatre mois et un recul de 30 % rattrape en six ans ne demandent
    pas la meme patience.
    """
    c = close.dropna()
    if len(c) < 30:
        return {"pct": None, "date": None, "jours_retour": None,
                "rattrape": None}
    sommet = c.cummax()
    recul = c / sommet - 1.0
    i = int(recul.values.argmin())
    creux_d = c.index[i]
    pire = float(recul.iloc[i])
    niveau = float(sommet.iloc[i])
    # Premiere cloture qui repasse au-dessus du sommet d'avant le creux.
    apres = c.iloc[i:]
    revenus = apres[apres >= niveau]
    if len(revenus):
        jours = int((revenus.index[0] - sommet[sommet == niveau].index[0]).days)
        rattrape = True
    else:
        jours = int((c.index[-1] - sommet[sommet == niveau].index[0]).days)
        rattrape = False
    return {"pct": pire, "date": str(creux_d.date()),
            "jours_retour": jours, "rattrape": rattrape}


def _lien(rend: pd.Series, rend_b: pd.Series) -> dict:
    """Beta et correlation au repere, sur la partie commune.

    Le beta seul trompe : un beta de 1,2 avec une correlation de 0,2 veut
    dire que le titre bouge fort ET ailleurs. Les deux se lisent
    ensemble, donc ils sortent ensemble.
    """
    a, b = rend.align(rend_b, join="inner")
    a, b = a.dropna(), b.dropna()
    a, b = a.align(b, join="inner")
    if len(a) < MINI_BARRES:
        return {"beta": None, "correlation": None, "n": int(len(a))}
    vb = float(b.var(ddof=1))
    if vb <= 0:
        return {"beta": None, "correlation": None, "n": int(len(a))}
    beta = float(a.cov(b) / vb)
    cor = float(a.corr(b))
    return {"beta": beta if math.isfinite(beta) else None,
            "correlation": cor if math.isfinite(cor) else None,
            "n": int(len(a))}


def _declare(ticker: str) -> dict:
    """Ce que le fournisseur DECLARE : type, nom, categorie.

    C'est une declaration, pas une mesure, et le rapport le dit. Un ETF
    mal etiquete reste mal etiquete ; les mesures, elles, ne dependent
    d'aucun libelle. Si l'appel echoue — hors ligne, quota, ticker
    inconnu — le profil se passe tres bien de lui.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).get_info() or {}
    except Exception:
        return {"disponible": False}
    t = (info.get("quoteType") or "").upper()
    return {
        "disponible": True,
        "type": t or None,
        "nom": info.get("longName") or info.get("shortName"),
        "categorie": info.get("category") or info.get("sector"),
        "devise": info.get("currency"),
        "lignes": info.get("holdings") and len(info["holdings"]) or None,
    }


def _pc(x, dec=1):
    """Une part, rangee en POURCENT et deja arrondie.

    Le dossier doit contenir le nombre tel qu'il sera lu. Multiplier par
    cent dans le gabarit d'affichage suffirait a faire sortir un chiffre
    qui n'est nulle part dans le dossier — et `test_moteur` le voit : il
    releve tous les nombres affiches et refuse ceux qui n'y figurent
    pas. La regle est la meme que pour `dossier.py` : les gabarits
    formatent, ils ne calculent pas.
    """
    if x is None:
        return None
    x = float(x) * 100.0
    return round(x, dec) if math.isfinite(x) else None


def _ar(x, dec=2):
    if x is None:
        return None
    x = float(x)
    return round(x, dec) if math.isfinite(x) else None


def mesures(d: pd.DataFrame, bench: pd.DataFrame | None = None,
            ticker: str = "", declare: bool = True) -> dict:
    """Tout ce qui se mesure sur la serie, sans rien decider.

    `d` porte deja ses indicateurs (`indicators.enrich`). `bench` sert au
    beta et a la correlation ; sans lui, ces deux lignes manquent et le
    reste tient.
    """
    close = d["close"]
    rend = close.pct_change()
    out: dict = {"ticker": (ticker or "").upper(),
                 "barres": int(len(d)),
                 "depuis": str(d.index[0].date()) if len(d) else None,
                 "jusqu_a": str(d.index[-1].date()) if len(d) else None}

    v1 = _vol(rend.tail(SEANCES_AN))
    v3 = _vol(rend.tail(SEANCES_AN * 3))
    vt = _vol(rend)
    out["volatilite"] = {"un_an": v1, "trois_ans": v3, "tout": vt,
                         "un_an_pc": _pc(v1), "trois_ans_pc": _pc(v3)}
    cle, lab = bande(v1 if v1 is not None else vt)
    out["bande"] = cle
    out["bande_libelle"] = lab

    # L'ecart quotidien « ordinaire » : un ecart-type. Deux seances sur
    # trois tiennent dedans. C'est de l'arithmetique sur la volatilite,
    # pas une prevision — et c'est la traduction la plus directe de
    # « combien ca bouge » en euros.
    ref = v1 if v1 is not None else vt
    ecart = None if ref is None else ref / math.sqrt(SEANCES_AN)
    out["ecart_jour_ordinaire"] = ecart
    out["ecart_jour_ordinaire_pc"] = _pc(ecart, 2)

    if "atr14" in d.columns and len(d):
        a = float(d["atr14"].iloc[-1])
        c = float(close.iloc[-1])
        out["atr_pct"] = a / c if c and math.isfinite(a) else None
    else:
        out["atr_pct"] = None
    out["atr_pc"] = _pc(out["atr_pct"], 2)

    rm = _recul_max(close)
    rm["pc"] = _pc(rm.get("pct"))
    out["recul_max"] = rm

    r = rend.dropna()
    part = float((r.abs() > 0.05).mean()) if len(r) else None
    out["seances_fortes"] = {
        "n": int((r.abs() > 0.05).sum()),
        "sur": int(len(r)),
        "part": part,
        "part_pc": _pc(part),
    }

    if bench is not None and len(bench):
        lien = _lien(rend, bench["close"].pct_change())
    else:
        lien = {"beta": None, "correlation": None, "n": 0}
    lien["beta_ar"] = _ar(lien.get("beta"))
    lien["correlation_ar"] = _ar(lien.get("correlation"))
    out["repere"] = lien

    out["declare"] = _declare(ticker) if (declare and ticker) else {
        "disponible": False}
    return out


def duree_detention(d: pd.DataFrame, bench: pd.DataFrame,
                    ticker: str = "") -> dict:
    """Combien de temps la SPECIFICATION garde une ligne sur ce titre.

    On rejoue ses regles sur tout l'historique disponible et on releve la
    duree des trades qu'elles produisent. C'est le seul chiffre qui
    reponde a « court ou long terme » sans rien inventer : l'horizon est
    une consequence des quatre conditions de sortie, pas un choix.

    Ce n'est PAS un resultat de performance. L'hypothese a rendu NO-GO en
    Phase 0 ; ce qu'on mesure ici est la duree, pas le gain, et les deux
    ne se deduisent pas l'un de l'autre.
    """
    from . import backtest as bt
    try:
        trades = bt.trades_ticker(d, ticker or "?", bench)
    except Exception as exc:
        return {"n": 0, "erreur": f"{type(exc).__name__}: {exc}"}
    if not trades:
        return {"n": 0, "mediane": None, "q1": None, "q3": None,
                "motifs": {}}
    barres = sorted(t.barres for t in trades)
    motifs: dict = {}
    for t in trades:
        motifs[t.motif] = motifs.get(t.motif, 0) + 1
    return {
        "n": len(barres),
        "mediane": int(np.median(barres)),
        "q1": int(np.percentile(barres, 25)),
        "q3": int(np.percentile(barres, 75)),
        "mini": barres[0],
        "maxi": barres[-1],
        "motifs": dict(sorted(motifs.items(), key=lambda kv: -kv[1])),
        "depuis": str(trades[0].entree_d.date()),
        "jusqu_a": str(trades[-1].sortie_d.date()),
    }


# ---------------------------------------------------------------------
# Mise en phrases
# ---------------------------------------------------------------------
#
# Meme contrat que `dossier.py` : aucun chiffre n'est calcule ici. Les
# gabarits ne font que poser en francais ce que `mesures()` et
# `duree_detention()` ont deja produit. Si un nombre n'est pas dans le
# dictionnaire recu, aucune phrase ne peut le sortir.

def _pct(x, n=1):
    """Un pourcentage DEJA calcule. Aucune arithmetique ici."""
    return "—" if x is None else f"{x:.{n}f} %".replace(".", ",")


def _nb(x):
    """Un nombre DEJA arrondi."""
    return "—" if x is None else f"{x:.2f}".replace(".", ",")


def lignes(m: dict, dd: dict | None = None) -> list[tuple[str, str]]:
    """Le profil en couples (libelle, valeur), prets a afficher."""
    out = [("AMPLITUDE", m.get("bande_libelle", "—"))]
    v = m.get("volatilite") or {}
    out.append(("Volatilite annualisee, 1 an", _pct(v.get("un_an_pc"))))
    out.append(("Volatilite annualisee, 3 ans", _pct(v.get("trois_ans_pc"))))
    out.append(("Ecart quotidien ordinaire",
                _pct(m.get("ecart_jour_ordinaire_pc"), 2)))
    out.append(("ATR 14 rapporte au cours", _pct(m.get("atr_pc"), 2)))

    r = m.get("recul_max") or {}
    if r.get("pc") is not None:
        txt = f"{_pct(r['pc'])} (creux du {r['date']})"
        if r.get("jours_retour") is not None:
            txt += (f", rattrape en {r['jours_retour']} jours"
                    if r.get("rattrape")
                    else f", pas encore rattrape apres {r['jours_retour']} jours")
        out.append(("Pire recul depuis un sommet", txt))

    s = m.get("seances_fortes") or {}
    if s.get("sur"):
        out.append(("Seances a plus de 5 %",
                    f"{s['n']} sur {s['sur']} ({_pct(s.get('part_pc'), 1)})"))

    rep = m.get("repere") or {}
    if rep.get("beta_ar") is not None:
        out.append(("Beta au repere", _nb(rep["beta_ar"])))
        out.append(("Correlation au repere", _nb(rep.get("correlation_ar"))))

    dec = m.get("declare") or {}
    if dec.get("disponible") and dec.get("type"):
        lib = {"EQUITY": "action", "ETF": "ETF", "INDEX": "indice",
               "MUTUALFUND": "fonds",
               "CRYPTOCURRENCY": "crypto-actif"}.get(dec["type"], dec["type"])
        out.append(("Type declare par la source", lib))
        if dec.get("categorie"):
            out.append(("Categorie declaree", str(dec["categorie"])))

    if dd and dd.get("n"):
        out.append(("Duree mesuree des positions",
                    f"mediane {dd['mediane']} seances "
                    f"(moitie centrale : {dd['q1']} a {dd['q3']}), "
                    f"sur {dd['n']} trades"))
        if dd.get("motifs"):
            premier = next(iter(dd["motifs"].items()))
            out.append(("Cause de sortie la plus frequente",
                        f"{premier[0]} ({premier[1]} fois sur {dd['n']})"))
    elif dd is not None:
        out.append(("Duree mesuree des positions",
                    "aucun trade sur l'historique disponible"))
    return out


RAPPEL = ("Ces chiffres decrivent comment l'instrument a bouge et combien "
          "de temps les regles de la specification gardent une ligne "
          "dessus. Ils ne disent rien de ce qu'il rapportera : aucune "
          "hypothese n'a passe sa Phase 0.")

RAPPEL_DECLARE = ("Le type et la categorie sont DECLARES par la source de "
                  "donnees, ils ne sont pas mesures. Les autres lignes, si.")
