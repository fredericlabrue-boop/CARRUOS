"""Page unique : graphique interactif + verdict, sur trois unites de temps.

Une seule page HTML. Onglets 1 jour / 1 semaine / 1 mois : les bougies, les
indicateurs ET le verdict changent ensemble.

Seul le JOURNALIER est le systeme. L'hebdo et le mensuel sont du contexte :
si la tendance hebdo est cassee, un signal journalier est suspect.

Lightweight Charts 4.2.0, version epinglee (la v5 a change l'API).
"""

from __future__ import annotations

import html
import json
import webbrowser
from pathlib import Path

import numpy as np
import pandas as pd

from . import hud as hd
from . import reglages as rg
from .dashboard import LABELS
from . import interet as it
from .indicators import PERIODES, enrich
from .rules import evaluate, evaluate_exit, market_regime_ok, position_size

# La bibliotheque de graphiques. Elle etait chargee UNIQUEMENT depuis un
# CDN : sans internet, la page s'ouvrait avec quatre colonnes de texte et
# un grand vide a la place du graphique, sans un mot d'explication. Le
# mode cle USB rend ce cas tres concret.
#
# On essaie donc d'abord une copie locale, puis le CDN, et si les deux
# echouent la page le DIT au lieu de rester blanche.
LOCAL = "/statique/lightweight-charts.js"


def source_trace() -> str:
    """Ou aller chercher la bibliotheque de graphiques.

    C'est le SERVEUR qui tranche, au moment de fabriquer la page, parce
    que lui seul sait si la copie locale existe. Une seule balise, et
    elle est BLOQUANTE : le script de la page ne demarre qu'une fois la
    bibliotheque chargee.

    La version precedente essayait le fichier local puis basculait sur le
    CDN depuis `onerror`. Ca ne pouvait pas marcher : le script de repli
    etait ajoute de facon ASYNCHRONE, donc le code de la page s'executait
    avant qu'il soit charge et trouvait toujours la bibliotheque absente.
    Resultat : « GRAPHIQUE INDISPONIBLE » meme avec une connexion
    parfaite. Le message de secours reste utile — il ne se declenche
    plus que quand la source choisie est vraiment injoignable.
    """
    try:
        if (Path(__file__).resolve().parent / "statique"
                / "lightweight-charts.js").is_file():
            return LOCAL
    except OSError:
        pass
    return CDN
CDN = "https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"

# (cle, libelle, regle de reechantillonnage, nombre de barres affichees)
#
# Le libelle dit la TAILLE DE LA BOUGIE, pas la fenetre — sauf 5 ANS, qui
# dit la fenetre. C'est la lecture naturelle, et elle manquait : « 1 AN »
# se lit spontanement comme « un an d'historique » alors que ce sont des
# bougies annuelles. `FENETRE` donne la couverture reelle de chaque
# onglet, affichee a cote du libelle pour lever l'ambiguite.
UNITES = [("jour", "1 JOUR", None, 420),
          ("semaine", "1 SEMAINE", "W-FRI", 300),
          ("cinq_ans", "5 ANS", "W-FRI", 261),
          ("mois", "1 MOIS", "ME", 180),
          ("trimestre", "1 TRIMESTRE", "QE", 80),
          ("an", "1 AN", "YE", 30)]

def fenetre_reelle(bloc) -> str:
    """La periode REELLEMENT couverte par un onglet, calculee sur ses
    propres dates.

    Une constante aurait menti des que l'historique du titre est plus
    court que la fenetre visee : « 30 ans » sous un onglet qui n'en
    montre que dix-neuf, ou sous un ETF cree en 2019.
    """
    if not bloc or "ohlc" not in bloc or len(bloc["ohlc"]) < 2:
        return ""
    o = bloc["ohlc"]
    try:
        deb = pd.Timestamp(o[0]["time"])
        fin = pd.Timestamp(o[-1]["time"])
    except Exception:
        return ""
    jours = (fin - deb).days
    if jours < 62:
        return f"{max(1, jours // 7)} sem."
    if jours < 400:
        return f"{round(jours / 30.44)} mois"
    return f"{jours / 365.25:.0f} ans"

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

# ---------------------------------------------------------------------
# Conversion de calendrier, pas reglage de performance.
#
# Le probleme : `enrich` appliquait 200, 50, 20, 14, 12-26-9 a TOUTES les
# unites. Sur bougies mensuelles, une SMA 200 couvre seize ans — elle ne
# s'affichait jamais, et les autres courbes ne representaient pas ce que
# l'oeil croyait lire.
#
# La correction : une barre hebdomadaire vaut 5 barres journalieres, une
# mensuelle 21, une trimestrielle 63. On divise les longueurs par ce
# facteur pour couvrir le meme horizon REEL. C'est de l'arithmetique de
# calendrier : aucune valeur n'a ete choisie en regardant un resultat.
#
# Plancher a 5 barres : en dessous, une moyenne ne moyenne plus rien. Les
# indicateurs qui tombent sous le plancher sont marques indisponibles
# plutot que traces a tort.
# ---------------------------------------------------------------------

BARRES_PAR_UNITE = {"jour": 1, "semaine": 5, "cinq_ans": 5, "mois": 21,
                    "trimestre": 63, "an": 252}
PLANCHER = 5


def periodes_unite(cle: str) -> dict | None:
    """Longueurs converties pour une unite. None pour le journalier :
    ce sont alors les valeurs gelees de la strategie."""
    f = BARRES_PAR_UNITE.get(cle, 1)
    if f == 1:
        return None
    b = PERIODES

    def d(n, mini=PLANCHER):
        return max(mini, round(n / f))

    return {"sma_longue": d(b["sma_longue"]), "sma_moyenne": d(b["sma_moyenne"]),
            "ema_courte": d(b["ema_courte"]), "atr": d(b["atr"], 5),
            "rsi": d(b["rsi"], 7),
            "macd": (d(b["macd"][0], 4), d(b["macd"][1], 8), d(b["macd"][2], 3)),
            "bb": (d(b["bb"][0]), b["bb"][1]),
            "vol_ma": d(b["vol_ma"]), "pente": d(b["pente"], 3),
            "haut": d(b["haut"], 6), "dollar_vol": d(b["dollar_vol"])}


def mini_barres(cle: str, pe: dict | None) -> int:
    """Nombre de barres en dessous duquel une unite n'a rien a montrer.

    On demande de quoi calculer la plus longue moyenne convertie, plus
    deux barres pour que la pente ait un sens. Jamais moins de huit :
    en dessous, un graphique n'est plus un graphique.
    """
    if pe is None:
        return 40                       # journalier : inchange
    besoin = max(pe["sma_longue"], pe["sma_moyenne"], pe["bb"][0],
                 pe["macd"][1]) + 2
    return max(8, besoin)


def _f(v):
    try:
        v = float(v)
        return round(v, 4) if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _reech(df: pd.DataFrame, regle: str | None) -> pd.DataFrame:
    if regle is None:
        return df
    return df.resample(regle).agg(AGG).dropna()


def _dates(idx) -> list:
    """Les dates au format attendu par le graphique, en une passe.

    `strftime` appele barre par barre sur un Timestamp est lent ; sur
    l'index entier, pandas le fait en C. Sur mille barres relues deux
    fois par page, ce n'est plus un detail.
    """
    return idx.strftime("%Y-%m-%d").tolist()


def _serie(d, col, n):
    """Une serie d'indicateur, prete pour le graphique.

    `.items()` construisait un Timestamp et un scalaire pandas par barre.
    En numpy, les memes valeurs sortent d'un coup — arrondies a la meme
    decimale, donc le graphique est au pixel pres le meme.
    """
    v = d[col].tail(n)
    vals = v.to_numpy(dtype=float)
    fini = np.isfinite(vals)
    if not fini.any():
        return []
    dates = _dates(v.index)
    arr = np.round(vals, 4)
    return [{"time": dates[i], "value": float(arr[i])}
            for i in range(len(arr)) if fini[i]]


def _ohlc(d, n) -> list:
    """Les bougies. `high` et `low` sont bornes par l'ouverture et la
    cloture comme avant : une bougie dont le plus haut serait sous son
    ouverture ne se dessine pas."""
    q = d.tail(n)
    o = q["open"].to_numpy(dtype=float)
    h = q["high"].to_numpy(dtype=float)
    b = q["low"].to_numpy(dtype=float)
    c = q["close"].to_numpy(dtype=float)
    hi = np.round(np.maximum.reduce([o, h, b, c]), 4)
    lo = np.round(np.minimum.reduce([o, h, b, c]), 4)
    o4, c4 = np.round(o, 4), np.round(c, 4)
    bon = np.isfinite(o4) & np.isfinite(c4) & np.isfinite(hi) & np.isfinite(lo)
    dates = _dates(q.index)
    return [{"time": dates[i], "open": float(o4[i]), "high": float(hi[i]),
             "low": float(lo[i]), "close": float(c4[i])}
            for i in range(len(dates)) if bon[i]]


def _volume(d, n) -> list:
    q = d.tail(n)
    v = np.round(q["volume"].to_numpy(dtype=float), 4)
    hausse = q["close"].to_numpy(dtype=float) >= q["open"].to_numpy(dtype=float)
    fini = np.isfinite(v)
    dates = _dates(q.index)
    return [{"time": dates[i], "value": float(v[i]),
             "color": "#10b98130" if hausse[i] else "#ef444430"}
            for i in range(len(dates)) if fini[i]]


def _cone(d, regle, horizon: int = 20) -> dict:
    """Cone de dispersion. Ce n'est PAS une prediction.

    Aucun indicateur ne predit le prix. Ce que la mesure permet, en
    revanche, c'est de dire ou le prix peut RAISONNABLEMENT se trouver
    dans N seances, compte tenu de la volatilite observee.

    La derive est fixee a ZERO volontairement. Une derive estimee sur le
    passe recent serait une prediction deguisee, et c'est exactement ce
    qu'on refuse de faire. Le cone est symetrique : il dit l'amplitude,
    jamais le sens.

    Largeur en racine du temps : la dispersion d'une marche aleatoire
    croit en sqrt(t), pas en t. A 20 seances elle vaut 4,5 fois celle
    d'une seule seance, pas 20 fois.
    """
    import numpy as _np
    c = d["close"].dropna()
    if len(c) < 80:
        return {}
    lr = _np.log(c / c.shift(1)).dropna().tail(120)
    sig = float(lr.std())
    if not _np.isfinite(sig) or sig <= 0:
        return {}
    dernier = float(c.iloc[-1])
    fin = c.index[-1]
    pas = {"W-FRI": 7, "ME": 31, "QE": 92, "YE": 365}.get(regle)
    if pas:
        futur = [fin + pd.Timedelta(days=pas * k) for k in range(1, horizon + 1)]
    else:
        futur = list(pd.bdate_range(fin + pd.Timedelta(days=1),
                                    periods=horizon))
    bandes = {"h1": [], "b1": [], "h2": [], "b2": [], "mid": []}
    for k, ts in enumerate(futur, 1):
        e = sig * (k ** 0.5)
        j = ts.strftime("%Y-%m-%d")
        bandes["mid"].append({"time": j, "value": round(dernier, 4)})
        for cle, z in (("h1", 1), ("b1", -1), ("h2", 2), ("b2", -2)):
            bandes[cle].append({"time": j,
                                "value": round(dernier * float(_np.exp(z * e)), 4)})
    return {"bandes": bandes, "sigma_j": round(sig * 100, 2),
            "horizon": horizon,
            "ampl1": round((float(_np.exp(sig * horizon ** 0.5)) - 1) * 100, 1),
            "ampl2": round((float(_np.exp(2 * sig * horizon ** 0.5)) - 1) * 100, 1)}


def _marqueurs(d, bo, n):
    """Les fleches de signal sur le graphique.

    Cette fonction appelait `evaluate()` une fois par barre — 724 appels
    scalaires par page, chacun construisant des Series pandas pour lire
    treize booleens. A elle seule elle pesait 3 des 5 secondes de
    generation de la page.

    `signaux_vectorises` calcule les memes treize blocs d'un coup sur
    toute la serie, en numpy. Son equivalence avec `evaluate()` barre par
    barre est verifiee par `test_moteur` — ce n'est pas une
    approximation, c'est le meme resultat.

    On retombe sur la boucle si la version vectorisee echoue : une
    fleche manquante vaut mieux qu'une page blanche.
    """
    debut = max(210, len(d) - n)
    try:
        from . import backtest as bt
        feu = bt.signaux_vectorises(d, bo)
        idx = d.index
        return [{"time": idx[i].strftime("%Y-%m-%d"),
                 "position": "belowBar", "color": "#10b981",
                 "shape": "arrowUp", "text": "A"}
                for i in range(debut, len(d)) if feu[i]]
    except Exception:
        pass
    out = []
    for i in range(debut, len(d)):
        try:
            ok = bool(bo["close"].iloc[i] > bo["sma200"].iloc[i])
            if evaluate(d, "X", ok, i=i, days_to_earnings=999).fired:
                out.append({"time": d.index[i].strftime("%Y-%m-%d"),
                            "position": "belowBar", "color": "#10b981",
                            "shape": "arrowUp", "text": "A"})
        except Exception:
            continue
    return out


def _code(k):
    return k.split("_")[0]


def _bloc_etats(d, s):
    """ok / ko / na. 'na' = indicateur pas encore calculable faute d'historique
    (une SMA200 mensuelle demande 200 mois). On ne compte JAMAIS un manque de
    donnees comme un echec : ce serait un faux verdict."""
    row = d.iloc[-1]
    besoins = {"1b": "sma200", "1c": "sma50_slope20", "1d": "rs_ma50",
               "1e": "macd", "2a": "ema20", "2b": "rsi14", "2c": "rsi14",
               "2d": "bars_since_high60", "3a": "macd_hist", "3b": "ema20",
               "4a": "rvol"}
    out = []
    for k, v in s.blocks.items():
        c = _code(k)
        col = besoins.get(c)
        # Piege : `_f(x) or np.nan` transforme un 0.0 legitime en NaN
        # (0.0 est falsy). bars_since_high60 vaut 0 quand le plus haut est
        # aujourd'hui -> tout etait marque "donnees manquantes".
        val = _f(row.get(col)) if col is not None else None
        na = col is not None and val is None
        out.append({"nom": LABELS.get(c, k), "etat": "na" if na else ("ok" if v else "ko")})
    return out


def _perf_signal(d, ticker, bench):
    """Performance historique du signal SUR CE TITRE precisement.

    Ce n'est pas le backtest de la Phase 0 (qui juge le systeme sur tout un
    univers) : c'est la fiche de ce titre. Un signal qui a echoue 9 fois sur
    10 ici merite de la mefiance meme si le systeme est valide globalement.
    """
    from . import backtest as bt
    try:
        tr = bt.trades_ticker(d, ticker, bench)
    except Exception:
        return None
    if not tr:
        return {"n": 0}
    rs = [x.R for x in tr]
    g = [r for r in rs if r > 0]
    perte = -sum(r for r in rs if r < 0)
    return {
        "n": len(tr),
        # Le compte exact de gagnants, pas le taux arrondi reconverti en
        # compte : l'intervalle de Wilson se calcule sur des entiers.
        "gagnants": len(g),
        "taux": round(len(g) / len(rs) * 100),
        "evR": round(float(np.mean(rs)), 2),
        "pf": round(sum(g) / perte, 2) if perte > 0 else 99.0,
        "duree": round(float(np.mean([x.barres for x in tr]))),
        "derniers": [{"d": x.entree_d.strftime("%m/%y"), "R": round(x.R, 1),
                      "m": x.motif} for x in tr[-4:]],
    }


def _jauges(d, bench):
    """Tout ce qui se lit d'un coup d'oeil : ou est le prix par rapport a
    chaque repere, exprime en ATR (comparable d'un titre a l'autp) et en %."""
    r = d.iloc[-1]
    c, atr = float(r["close"]), float(r["atr14"])
    def dist(col):
        v = _f(r.get(col))
        if v is None or not atr:
            return None
        return {"pct": round((c / v - 1) * 100, 1), "atr": round((c - v) / atr, 1)}

    h52 = float(d["high"].tail(252).max())
    b52 = float(d["low"].tail(252).min())
    bw = d["bb_width"].tail(252).dropna()
    rang = (float((bw < bw.iloc[-1]).mean() * 100) if len(bw) > 20 else None)

    def perf(n):
        if len(d) <= n:
            return None
        a = c / float(d["close"].iloc[-n - 1]) - 1
        b = bench["close"].reindex(d.index).ffill()
        m = float(b.iloc[-1]) / float(b.iloc[-n - 1]) - 1
        return {"titre": round(a * 100, 1), "ecart": round((a - m) * 100, 1)}

    return {
        "rsi": _f(r["rsi14"]), "rvol": _f(r["rvol"]), "atr": round(atr, 2),
        "atr_pct": round(atr / c * 100, 1),
        "ema20": dist("ema20"), "sma50": dist("sma50"), "sma200": dist("sma200"),
        "h52": round(h52, 2), "b52": round(b52, 2),
        "d_h52": round((c / h52 - 1) * 100, 1),
        "d_b52": round((c / b52 - 1) * 100, 1),
        "squeeze": None if rang is None else round(rang),
        "p1m": perf(21), "p3m": perf(63), "p6m": perf(126), "p12m": perf(252),
    }


# Le niveau d'interet -> la classe CSS de la pastille, et le mot court
# qu'elle affiche. Le mot long reste dans la carte INTERET : « LES 13
# BLOCS PASSENT » ne tient pas dans un cercle de 132 pixels.
VERDICT_CSS = {"refus": "na", "na": "na", "hors": "hors", "sortie": "vente",
               "complet": "achat", "proche": "proche", "loin": "aucun"}
VERDICT_MOT = {"refus": "DONNÉES REFUSÉES", "na": "DONNÉES INSUFFISANTES",
               "hors": "HORS CRITÈRES", "sortie": "SORTIE",
               "complet": "ACHAT", "proche": "PROCHE", "loin": "AUCUN"}


def _sous_verdict(u: dict) -> str:
    """La ligne sous le mot : toujours un compte, jamais un adjectif."""
    n = u["niveau"]
    if n == "refus":
        m = u.get("refus_motifs") or []
        return m[0] if m else "le contrôle qualité refuse cette série"
    if n == "na":
        return (f"{u['na']} indicateur(s) non calculable(s) sur cette "
                f"unité de temps")
    if n == "hors":
        return u["vetos"][0] if u["vetos"] else "veto de la spécification"
    if n == "sortie":
        return f"{u['sorties_actives']} conditions de sortie actives"
    if n == "complet":
        return "les 13 blocs passent"
    return f"{u['ko']} bloc(s) manquant(s)"


def _analyse(brut, bench_brut, regle, nb, ticker, sleeve, ccy, pre=None,
             cle=None, qual=None):
    """Une unite de temps.

    `pre` permet de fournir le couple (titre, indice) deja enrichi. La
    page construisait l'unite JOUR deux fois : une fois pour les jauges
    et les modules, une fois ici, avec exactement les memes arguments.
    Sur douze appels a `enrich` par page, deux etaient des doublons
    exacts.
    """
    # La cle est passee par l'appelant. La deduire de `regle` marchait
    # tant qu'une regle de reechantillonnage n'appartenait qu'a une seule
    # unite ; des que deux unites partagent la meme taille de bougie —
    # 5 ANS et 1 SEMAINE sont toutes deux hebdomadaires — la recherche
    # rendait toujours la premiere, et la seconde heritait des mauvaises
    # longueurs.
    _cle = cle or next((k for k, _, r, _ in UNITES if r == regle), "jour")
    _pe = periodes_unite(_cle)
    if pre is not None:
        d, b = pre
    else:
        d = enrich(_reech(brut, regle),
                   bench_close=_reech(bench_brut, regle)["close"],
                   periodes=_pe)
        b = enrich(_reech(bench_brut, regle), periodes=_pe)
    # Combien de barres faut-il ? Un plancher unique de 40 rendait
    # l'onglet 1 AN TOUJOURS vide : vingt ans d'historique ne font que
    # vingt barres annuelles. L'onglet affichait « pas assez
    # d'historique » quel que soit le titre — d'où le « données
    # indisponibles » permanent sur les ETF qu'on regarde justement sur
    # longue période.
    #
    # Le besoin réel, c'est la plus longue moyenne CONVERTIE pour cette
    # unité, plus une marge. Les indicateurs qui manquent encore sont
    # marqués « na » par _bloc_etats, et le verdict bascule sur DONNEES
    # INSUFFISANTES au lieu d'inventer un faux AUCUN.
    besoin = mini_barres(_cle, _pe)
    if len(d) < besoin:
        # « Pas assez d'historique » ne disait ni combien il en manquait,
        # ni pourquoi. On rend le detail : on voit tout de suite si le
        # titre est trop jeune ou si l'unite est trop large pour lui.
        return {"insuffisant": {
            "barres": len(d), "besoin": besoin,
            "depuis": str(d.index[0].date()) if len(d) else "?"}}
    bo = b.reindex(d.index).ffill()
    ok = bool(market_regime_ok(b))
    s = evaluate(d, ticker, ok, days_to_earnings=999)
    etats = _bloc_etats(d, s)
    sorties = evaluate_exit(d, ok)
    n_ko = sum(1 for e in etats if e["etat"] == "ko")
    n_na = sum(1 for e in etats if e["etat"] == "na")
    n_out = sum(1 for v in sorties.values() if v)

    # L'INTERET de l'unite : le meme decompte, mais avec les deux
    # nombres que chaque bloc manquant a compares. « il manque 2 blocs »
    # ne dit pas quoi guetter ; « RVOL 0,81 pour un seuil de 1,20 » si.
    try:
        interet = it.lire_unite(
            d, b, s, sorties, etats, cle=_cle, periodes=_pe,
            refuse=bool(qual and not qual[0]), motifs=(qual or (True, ()))[1])
    except Exception:
        interet = None

    # Le verdict DECOULE de l'interet, il ne se calcule plus a cote :
    # deux echelles paralleles finissent par se contredire. Et celle-ci
    # regarde les VETOS, ce que l'ancienne ne faisait pas — un titre
    # dont les 13 blocs passent mais dont le volume dollar est sous le
    # plancher de la specification s'affichait ACHAT, niveaux compris,
    # alors que la specification interdit l'entree.
    if interet is None:
        v = ("aucun", "AUCUN", f"{n_ko} blocs manquants")
    else:
        v = (VERDICT_CSS[interet["niveau"]], VERDICT_MOT[interet["niveau"]],
             _sous_verdict(interet))

    niveaux = None
    if v[0] == "achat":
        ps = position_size(s, sleeve)
        niveaux = {"entree": round(s.entry, 2), "stop": round(s.stop, 2),
                   "atr": round(s.atr, 2), "risque": round(s.risk_pct * 100, 1),
                   "titres": ps["shares"], "montant": round(ps["notional"]),
                   "rEUR": round(ps["risk_eur"]), "ccy": ccy}

    last = d.iloc[-1]
    out = {
        "verdict": {"type": v[0], "titre": v[1], "sous": v[2]},
        "interet": interet,
        "blocs": etats,
        "sorties": [{"nom": k, "actif": bool(x)} for k, x in sorties.items()],
        "niveaux": niveaux,
        "stats": {"cours": _f(last["close"]), "rsi": _f(last["rsi14"]),
                  "atr": _f(last["atr14"]), "bougies": min(nb, len(d))},
        # `iterrows()` construit une Series pandas complete par barre, et
        # `r.open` passe par __getattr__. Sur mille barres parcourues deux
        # fois, cela pesait le tiers de la page. Les memes nombres, lus en
        # numpy, sont identiques a l'arrondi pres — qui est le meme.
        "ohlc": _ohlc(d, nb),
        "volume": _volume(d, nb),
        "markers": _marqueurs(d, bo, nb),
        "cone": _cone(d, regle),
    }
    for k, col in [("ema20", "ema20"), ("sma50", "sma50"), ("sma200", "sma200"),
                   ("bbu", "bb_up"), ("bbl", "bb_low"), ("rsi", "rsi14"),
                   ("macd", "macd"), ("macds", "macd_sig"), ("macdh", "macd_hist")]:
        out[k] = _serie(d, col, nb)
    return out


CSS = hd.CSS + rg.CSS_OPTIONS + rg.CSS_THEMES + rg.TIROIR_CSS + """
*{box-sizing:border-box;margin:0}
html,body{height:100%;margin:0;overflow:hidden}
body{background:var(--fond);color:var(--txt);
 font:var(--police,14px) ui-sans-serif,Segoe UI,system-ui}
/* Disposition en couronne : les panneaux entourent la projection du cerf,
   qui occupe le centre. Tout tient dans la hauteur de la fenetre. */
.wrap{height:100vh;display:grid;gap:8px;padding:9px;
 grid-template-columns:238px minmax(0,1fr) 258px 306px;
 grid-template-rows:auto auto minmax(0,1fr) auto}
.wrap>.hd{grid-column:1/-1}
.wrap>.ol{grid-column:1/-1;display:flex;align-items:center;gap:9px;
 flex-wrap:wrap;padding:7px 11px;background:rgba(4,10,14,.5);
 border:1px solid #0d2a33;margin-top:-8px;
 clip-path:polygon(11px 0,100% 0,100% calc(100% - 11px),
 calc(100% - 11px) 100%,0 100%,0 11px)}
.ot{font:500 7.5px ui-monospace,monospace;letter-spacing:.24em;color:var(--txt-faible)}
.osep{width:1px;height:16px;background:#123c47;margin:0 3px}
.ol label{display:flex;align-items:center;gap:5px;font-size:10.5px;
 color:var(--txt-doux);cursor:pointer;user-select:none;letter-spacing:.06em}
.ol input{display:none}
.ol .sw{width:20px;height:3px;border-radius:2px;opacity:.28;
 transition:opacity .15s,background-color .15s}
.ol input:checked+.sw{opacity:1;box-shadow:0 0 7px currentColor}
.ol label:hover{color:#e8f6fa}
.zb{background:#08222a;border:1px solid var(--bord-fort);color:#22d3ee;
 padding:3px 10px;font:500 10.5px ui-monospace,monospace;letter-spacing:.1em;
 cursor:pointer;
 clip-path:polygon(5px 0,100% 0,100% calc(100% - 5px),
 calc(100% - 5px) 100%,0 100%,0 5px)}
.zb:hover{background:#0e3b48}
.oz{font-size:9px;color:#2f5462;letter-spacing:.1em;margin-left:auto}
.pil-l{grid-column:1;grid-row:3;min-height:0;overflow-y:auto;
 display:flex;flex-direction:column;gap:5px}
/* Chaque chiffre porte son seuil : on ne lit plus "38" sans savoir ce que
   38 vaut. */
/* --- LE BANDEAU DES MODULES ------------------------------------
   Il n'avait AUCUN style. `.mods`, `.mod`, `.hdr2`, `.bar`, `.neu`
   et `.arc` n'etaient definis nulle part : les seules regles
   existantes, `.pil-l .mod` et `.pil-l .kv`, surchargeaient du vide.
   Le bandeau du bas s'affichait donc en texte brut empile — les
   libelles colles aux chiffres, « 57RSI 14 zone 40-55 » — pendant
   que tout le reste de la page etait soigne. */
.mods{display:grid;gap:11px;align-items:start;
 grid-template-columns:repeat(auto-fit,minmax(min(100%,208px),1fr))}
.mod{background:#0d1219;border:1px solid #1a2330;border-radius:11px;
 padding:11px 13px;min-width:0}
.mod h4{font:500 8.5px ui-monospace,Consolas,monospace;letter-spacing:.2em;
 color:#475a72;margin:0 0 8px}
/* Le chiffre et son libelle sur la meme ligne, le libelle en retrait :
   sans cela ils se collaient en un seul mot. */
.mod .hdr2{display:flex;align-items:baseline;gap:8px;margin-bottom:5px}
.mod .hdr2 b{font:500 17px ui-monospace,Consolas,monospace;color:#e2eaf3;
 font-variant-numeric:tabular-nums}
.mod .hdr2 span{font-size:10px;color:#475a72;letter-spacing:.06em}
.mod .kv{display:flex;align-items:baseline;justify-content:space-between;
 gap:8px;font-size:11.5px;line-height:1.85;color:#64748b}
/* `color` sur `b` en general, mais JAMAIS sur un `b` qui porte deja
   son signe : `.mod .kv b` et `.mod .pos` ont la meme specificite, et
   c'est la derniere declaree qui gagne. Celles-ci viennent apres. */
.mod .kv b{font-weight:500;color:#cbd5e1;font-variant-numeric:tabular-nums}
/* La petite jauge : bande sombre = zone recherchee, trait clair = valeur.
   Les noms viennent du HTML produit par `_modules`, releves dessus. */
.mod .gg{position:relative;height:4px;border-radius:2px;background:#182230;
 margin:1px 0 9px}
.mod .gg .zone{position:absolute;top:0;bottom:0;background:#134a56;
 border-radius:2px}
.mod .gg .val{position:absolute;top:-3px;width:2px;height:10px;margin-left:-1px;
 background:#e2eaf3;border-radius:1px}
.mod .pos{color:var(--pos)}
.mod .neg{color:var(--neg)}
.mod .neu{color:#7f93ab}
.mod .dot{display:inline-block;width:6px;height:6px;border-radius:50%;
 background:currentColor;margin-right:6px;flex:none}
.mod .off{opacity:.45}
.mod .tl{font-size:10.5px;color:#64748b;line-height:1.6}
.mod .ex{font-size:10px;color:#475a72;line-height:1.65;margin-top:7px}
.mod .clk{cursor:pointer}
.mod .clk:hover{color:var(--acc)}
.mod svg{display:block;margin:0 auto;max-width:100%;height:auto}
/* Les actualites : des liens, pas un pave. Sans regle ils heritaient du
   bleu souligne du navigateur et debordaient leur carte. */
.mod .nw2{display:flex;flex-direction:column;gap:9px}
.mod .nw2 a{color:#cbd5e1;text-decoration:none;font-size:11.5px;
 line-height:1.45;display:block;overflow-wrap:anywhere}
.mod .nw2 a:hover{color:var(--acc)}
.mod .nw2 .m{font-size:9.5px;color:#475a72;letter-spacing:.04em}
/* Une DATE n'est pas un nombre : dans le creneau des grands chiffres,
   « date inconnue » s'affichait en 17 px et ecrasait sa carte. */
.mod[data-mod=resultats] .hdr2 b{font-size:13px;letter-spacing:.02em}
.pil-l .mod{padding:8px 10px;background:none;border:0}
.pil-l .mods{grid-template-columns:1fr;gap:6px}
.pil-l .mod h4{font-size:7.5px;letter-spacing:.2em;margin-bottom:5px}
.pil-l .kv{padding:2px 0;font-size:10.5px;line-height:1.25}
.pil-l .kv b{font-size:11px}
.pil-l .ex{font-size:9.5px;line-height:1.45}
.pil-c{grid-column:2;grid-row:3;min-height:0;display:grid;gap:7px;
 grid-template-rows:minmax(190px,3.2fr) minmax(74px,1fr) minmax(74px,1fr)}
.pil-h{grid-column:3;grid-row:3;min-height:0;display:flex;
 flex-direction:column;align-items:center;justify-content:center;
 gap:9px;padding:14px 12px;position:relative;overflow:hidden;
 background:rgba(4,10,14,.45);border:1px solid #0d2a33;
 clip-path:polygon(15px 0,100% 0,100% calc(100% - 15px),
 calc(100% - 15px) 100%,0 100%,0 15px)}
.pil-h::before{content:"";position:absolute;inset:0;pointer-events:none;
 background:radial-gradient(ellipse at 50% 62%,rgba(34,211,238,.09) 0%,
 transparent 62%)}
.pil-h .noyau{width:min(100%,196px);height:auto;aspect-ratio:1}
.pil-h .nom{font:300 17px ui-monospace,Consolas,monospace;
 letter-spacing:.34em;text-indent:.34em;color:#e8f6fa;
 text-shadow:0 0 22px rgba(34,211,238,.4);position:relative}
.pil-h .sst{font:400 7.5px ui-monospace,monospace;letter-spacing:.3em;
 color:var(--txt-faible);margin-top:-4px;position:relative}
.pil-h .tk{font:500 15px ui-monospace,monospace;letter-spacing:.22em;
 color:#c9b28a;position:relative;margin-top:4px}
/* Feu de decision : l'anneau se remplit au prorata des blocs valides et
   la couleur donne la reponse avant meme de lire. Un systeme non valide
   ne merite pas un bouton "acheter" : il merite un compteur honnete. */
.feu{position:relative;width:132px;height:132px;color:#475a72}
.feu svg{width:100%;height:100%;display:block}
.feu .fb{transition:stroke-dasharray .9s cubic-bezier(.2,1,.3,1)}
.feu .fc{transform-origin:66px 66px;animation:tour 34s linear infinite}
.feu .fv{position:absolute;inset:0;display:flex;align-items:center;
 justify-content:center;font:500 16px ui-monospace,monospace;
 letter-spacing:.14em;color:currentColor;margin-top:-9px}
.feu .fn{position:absolute;left:0;right:0;bottom:36px;text-align:center;
 font:400 9px ui-monospace,monospace;letter-spacing:.2em;color:#475a72}
.feu.pulse{animation:battement 1.9s ease-in-out infinite}
@keyframes battement{0%,100%{filter:drop-shadow(0 0 0 transparent)}
 50%{filter:drop-shadow(0 0 13px currentColor)}}
.pil-h .kv{width:100%;display:flex;justify-content:space-between;
 font-size:10px;color:#475a72;padding:3px 0;border-top:1px solid #0b2028;
 position:relative}
.pil-h .kv b{color:var(--txt-fort);font-weight:500}
.pil-r{grid-column:4;grid-row:3;min-height:0;overflow-y:auto;
 display:flex;flex-direction:column;gap:6px;padding-top:1px}
/* Le verdict reste visible meme quand la liste des blocs defile. */
.pil-r>.vd{position:sticky;top:0;z-index:3;flex:none;margin-bottom:0}
.pil-r .box{padding:9px 11px}
.pil-r .box h3{margin-bottom:6px}
.pil-r .bl{padding:2.5px 0;font-size:11.5px;line-height:1.3}
.pil-r .vd{padding:11px 14px;border-radius:0;
 clip-path:polygon(11px 0,100% 0,100% calc(100% - 11px),
 calc(100% - 11px) 100%,0 100%,0 11px)}
.pil-r .vd .t{font-size:23px}
.pil-r .ex div{padding:1.5px 0;font-size:11px}
.pil-r .lv{gap:5px 9px}
.pil-r .lv .k{font-size:7.5px}
.pil-r .lv .v{font-size:12.5px}
.wrap>.bas{grid-column:1/-1;max-height:13vh;overflow-y:auto;
 overscroll-behavior:contain}
.wrap>.bas::-webkit-scrollbar{height:5px;width:5px}
.wrap>.bas::-webkit-scrollbar-thumb{background:#13323c}
.pil-l::-webkit-scrollbar,.pil-r::-webkit-scrollbar{width:5px}
.pil-l::-webkit-scrollbar-thumb,.pil-r::-webkit-scrollbar-thumb{
 background:#1c2635;border-radius:3px}
@media(max-width:1500px){
 .wrap{grid-template-columns:218px minmax(0,1fr) 232px 284px}}
@media(max-width:1250px){html,body{overflow:auto}
 .wrap{height:auto;grid-template-columns:1fr;grid-template-rows:none}
 .pil-l,.pil-c,.pil-h,.pil-r{grid-column:1;grid-row:auto}
 .pil-h{min-height:300px}
 .pil-c{grid-template-rows:480px 140px 140px}}
.hd{display:flex;align-items:center;gap:18px;flex-wrap:wrap;margin-bottom:18px}
.hd h1{font-size:30px;font-weight:600;color:#f8fafc;letter-spacing:.02em}
.hd .px{font-size:19px;color:#cbd5e1;font-variant-numeric:tabular-nums}
.hd .mt{font-size:12.5px;color:#576a83}
.tabs{display:flex;gap:4px;background:#0d1219;border:1px solid #1a2330;
 border-radius:11px;padding:4px;margin-left:auto;margin-right:46px}
.tabs button{background:none;border:0;color:#64748b;font:500 12.5px inherit;
 letter-spacing:.12em;padding:7px 16px 5px;border-radius:8px;cursor:pointer;
 display:flex;flex-direction:column;align-items:center;gap:1px;
 transition:background-color .13s,color .13s}
.tabs button i{font:400 8.5px ui-monospace,monospace;letter-spacing:.1em;
 font-style:normal;opacity:.6}
.tabs button:hover{color:#cbd5e1}
.tabs button.on{background:#1b2635;color:#f1f5f9}
.grid{display:grid;grid-template-columns:1fr 344px;gap:14px;align-items:start}
@media(max-width:1080px){.grid{grid-template-columns:1fr}}
.box{background:#0d1219;border:1px solid #1a2330;border-radius:13px;padding:11px}
.box+.box{margin-top:11px}
.lb{font-size:10px;letter-spacing:.2em;color:#475a72;padding:3px 7px 9px;display:flex;justify-content:space-between}
.vd{border-radius:13px;padding:22px;margin-bottom:11px;border:1px solid;
 position:relative;overflow:hidden}
.vd .t{font-size:31px;font-weight:600;line-height:1;letter-spacing:.02em}
.vd .s{font-size:12.5px;margin-top:8px;opacity:.8}
.v-achat{background:#052a22;border-color:#127a5f;color:var(--pos);
 animation:entree .7s cubic-bezier(.2,.9,.3,1)}
@keyframes entree{from{transform:scale(.975);opacity:0}to{transform:none;opacity:1}}
/* Un seul balayage de lumiere, deux fois. Marque la raretE du signal sans
   simuler un gain : aucun euro n'est gagne quand un bloc passe. */
.v-achat::after{content:"";position:absolute;top:0;left:-42%;width:42%;height:100%;
 background:linear-gradient(100deg,transparent,rgba(201,178,138,.22),transparent);
 transform:skewX(-18deg);animation:balai 1.6s ease .4s 2;pointer-events:none}
@keyframes balai{from{transform:translateX(0) skewX(-18deg)}
to{transform:translateX(450%) skewX(-18deg)}}
.v-achat .t{animation:chiffre .8s cubic-bezier(.2,1.1,.3,1) .1s backwards}
@keyframes chiffre{from{opacity:0;transform:translateY(10px) scale(.93)}
 to{opacity:1;transform:none}}
.v-achat .s{animation:fdv .7s ease .45s backwards}
@keyframes fdv{from{opacity:0}to{opacity:.8}}
.card.ok{animation:arrive .6s cubic-bezier(.2,.9,.3,1) backwards}
.card.ok:nth-of-type(2){animation-delay:.1s}
.card.ok:nth-of-type(3){animation-delay:.2s}
@keyframes arrive{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.card.ok .bar i{animation:remplit 1s cubic-bezier(.3,0,.2,1) .3s backwards}
@keyframes remplit{from{transform:scaleX(0)}}
.v-vente{background:#2c1014;border-color:#8b2733;color:var(--neg)}
.v-proche{background:#2a1f07;border-color:#8a6413;color:#fbbf24}
.v-aucun{background:#12181f;border-color:#243040;color:#7c8ba1}
.v-na{background:#151322;border-color:#38306b;color:#a78bfa}
.side .box{padding:15px 17px}
.side h3{font-size:10px;letter-spacing:.2em;color:#475a72;font-weight:500;margin-bottom:11px}
.bl{display:flex;align-items:center;gap:9px;font-size:13px;line-height:2.05}
.bl i{width:15px;height:15px;border-radius:4px;flex:none;font-style:normal;font-size:10px;text-align:center;line-height:15px}
.i-ok{background:#052a22;color:var(--pos)}.i-ko{background:#2c1014;color:var(--neg)}.i-na{background:#1b1830;color:#a78bfa}
.ko{color:#fca5a5}.na{color:#c4b5fd}.okt{color:#64748b}
.lv{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.lv div{background:#121a24;border-radius:8px;padding:9px 12px}
.lv .k{font-size:9.5px;letter-spacing:.14em;color:#475a72;margin-bottom:3px}
.lv .v{font-size:17px;color:#f1f5f9;font-variant-numeric:tabular-nums}
.tg{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}
.tg label{display:flex;align-items:center;gap:6px;background:#0d1219;border:1px solid #1a2330;border-radius:18px;padding:5px 13px;font-size:12px;cursor:pointer;user-select:none}
.tg label:hover{border-color:#2a3a4f}
.tg input{accent-color:var(--acc);margin:0;cursor:pointer}
.sw{width:9px;height:9px;border-radius:2px}
.note{font-size:12px;color:#475a72;line-height:1.85;margin-top:16px;border-top:1px solid #1a2330;padding-top:13px}
.ex{font-size:12.5px;line-height:1.95;color:#64748b}
.ex b{color:var(--neg);font-weight:500}
/* HORS CRITERES : un veto de la specification. Ni vert ni rouge —
   le titre ne concourt pas, ce n'est pas un jugement sur son cours. */
.v-hors{background:#1d1626;border-color:#4a3a63;color:#c4a5e4}
/* --- la carte INTERET --------------------------------------------- */
.int{border-radius:13px;padding:18px 20px;margin-bottom:11px;
 border:1px solid #243040;background:#0e141c}
.int>h3{font-size:10px;letter-spacing:.2em;color:#475a72;font-weight:500;
 margin-bottom:12px}
.int .gd{display:flex;align-items:baseline;justify-content:space-between;gap:14px}
.int .gd b{font-size:24px;font-weight:600;line-height:1.08;letter-spacing:.01em}
.int .gd u{text-decoration:none;font-size:21px;flex:none;opacity:.85;
 font-variant-numeric:tabular-nums}
.int .mo{font-size:12.5px;color:#64748b;margin-top:8px;line-height:1.6}
.int .sec{margin-top:15px;border-top:1px solid #1a2330;padding-top:12px}
.int .sec>span{font-size:9.5px;letter-spacing:.2em;color:#475a72;display:block;
 margin-bottom:9px}
.int .mq{font-size:13px;line-height:1.45;margin-bottom:10px}
.int .mq b{color:#fca5a5;font-weight:500;display:block}
.int .mq i{font-style:normal;color:#64748b;font-size:12px;
 font-variant-numeric:tabular-nums}
/* Colonnes FIXES : un libelle plus long ne doit pas decaler la grille.
   C'est le defaut qui faisait sauter les rails. */
.int .ut{display:grid;grid-template-columns:104px 46px 1fr;gap:7px 10px;
 align-items:center;font-size:12px}
.int .ut span{color:#64748b;letter-spacing:.05em}
.int .ut em{font-style:normal;text-align:right;color:#cbd5e1;
 font-variant-numeric:tabular-nums}
.int .jg{height:6px;border-radius:3px;background:#182230;overflow:hidden}
.int .jg i{display:block;height:100%;border-radius:3px;background:currentColor;
 transform-origin:left center;animation:remplit 1s cubic-bezier(.3,0,.2,1) .2s backwards}
.int .av{font-size:11.5px;color:#475a72;line-height:1.75;margin-top:15px;
 border-top:1px solid #1a2330;padding-top:12px}
.int .av b{color:#94a3b8;font-weight:500}
.n-complet{color:var(--pos)}.n-proche{color:#fbbf24}.n-loin{color:#7c8ba1}
.n-sortie{color:var(--neg)}.n-hors{color:#c4a5e4}.n-na{color:#a78bfa}
.n-refus{color:var(--neg)}.n-vide{color:#475a72}
"""

CSS += """
/* Quadrillage derriere les graphiques, comme le plan de parcelle.
   En image de fond et non en pseudo-element : pas de position:relative
   impose au conteneur, donc aucun effet sur le dimensionnement. */
.pil-c > div{background-image:
 repeating-linear-gradient(90deg,rgba(34,211,238,.05) 0 1px,
 transparent 1px 52px),
 repeating-linear-gradient(0deg,rgba(34,211,238,.04) 0 1px,
 transparent 1px 34px)}
"""

JS = """
// Sans la bibliotheque, cette ligne levait une ReferenceError et TOUT le
// script mourait : les quatre colonnes, les unites de temps, les modules.
// On verifie d'abord, on explique, et on laisse le reste de la page
// fonctionner.
if(typeof LightweightCharts === 'undefined'){
 // Il n'existe pas d'element « graph » : les conteneurs sont p1/p2/p3.
 // Viser un id inexistant renvoyait sur document.body, et
 // insertBefore(m, body) posait le message HORS du body — invisible.
 var z = document.getElementById('p1');
 var m = document.createElement('div');
 m.style.cssText = 'padding:18px 20px;margin:10px 0;'
  + 'border:1px solid var(--bord-fort);background:var(--pan-fond);'
  + 'font:13px ui-monospace,monospace;line-height:1.8;color:var(--txt-doux)';
 m.innerHTML = '<b style="color:var(--neg)">GRAPHIQUE INDISPONIBLE</b><br>'
  + "La bibliotheque de trace n'a pas pu etre chargee : ni copie locale, "
  + 'ni acces au reseau.<br><br>'
  + 'Pour ne plus jamais en dependre, telecharge une fois ce fichier :<br>'
  + '<span style="color:var(--acc)">unpkg.com/lightweight-charts@4.2.0/'
  + 'dist/lightweight-charts.standalone.production.js</span><br>'
  + 'et pose-le dans <span style="color:var(--acc)">'
  + 'equity_scanner/statique/lightweight-charts.js</span>.<br><br>'
  + 'Tout le reste de cette page fonctionne : les quatre colonnes, les '
  + 'blocs, les niveaux et les unites de temps sont calcules ici, pas '
  + 'par la bibliotheque.';
 if(z && z.parentNode){ z.parentNode.insertBefore(m, z); }
 else { document.body.insertBefore(m, document.body.firstChild); }
}
const D=DATA; const LC=(typeof LightweightCharts!=='undefined')
 ? LightweightCharts : null;
let U='jour';
const base={layout:{background:{color:'transparent'},textColor:'#64748b',fontSize:11},
 grid:{vertLines:{color:'#141c27'},horzLines:{color:'#141c27'}},
 rightPriceScale:{borderColor:'#1a2330'},timeScale:{borderColor:'#1a2330',rightOffset:5},
 crosshair:{mode:0,vertLine:{color:'#33465e',labelBackgroundColor:'#22d3ee'},
            horzLine:{color:'#33465e',labelBackgroundColor:'#22d3ee'}},
 handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true},
 handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true,
              axisDoubleClickReset:true}};
// Les hauteurs viennent du conteneur, pas de valeurs figees : la page
// doit tenir dans la fenetre quelle que soit sa taille.
// Un faux graphique quand la bibliotheque manque : il avale les appels
// au lieu de lever. Les quatre colonnes ne doivent rien a la
// bibliotheque, elles n'ont pas a mourir avec elle.
const RIEN=function(){};
const MUET_TEMPS={fitContent:RIEN,setVisibleLogicalRange:RIEN,
 getVisibleLogicalRange:function(){return null;},
 subscribeVisibleLogicalRangeChange:RIEN,
 unsubscribeVisibleLogicalRangeChange:RIEN,applyOptions:RIEN};
const MUET={setData:RIEN,setMarkers:RIEN,applyOptions:RIEN,
 createPriceLine:function(){return {applyOptions:RIEN,remove:RIEN};},
 removePriceLine:RIEN,remove:RIEN,
 priceScale:function(){return {applyOptions:RIEN};},
 addLineSeries:function(){return MUET;},
 addCandlestickSeries:function(){return MUET;},
 addHistogramSeries:function(){return MUET;},
 addAreaSeries:function(){return MUET;},
 timeScale:function(){return MUET_TEMPS;},
 subscribeCrosshairMove:RIEN,unsubscribeCrosshairMove:RIEN,
 resize:RIEN};
function mk(id){const el=document.getElementById(id);
 if(!LC||!el) return MUET;
 const h=Math.max(90,el.parentElement.clientHeight-30);
 return LC.createChart(el,Object.assign({},base,{height:h,width:el.clientWidth}));}
const cP=mk('p1'),cR=mk('p2'),cM=mk('p3');
// Cone de dispersion : quatre lignes pointillees vers l'avenir. Elles ne
// disent rien du SENS, seulement de l'amplitude plausible.
const co2h=cP.addLineSeries({color:'rgba(148,163,184,.35)',lineWidth:1,
 lineStyle:2,priceLineVisible:false,lastValueVisible:false});
const co2b=cP.addLineSeries({color:'rgba(148,163,184,.35)',lineWidth:1,
 lineStyle:2,priceLineVisible:false,lastValueVisible:false});
const co1h=cP.addLineSeries({color:'rgba(34,211,238,.55)',lineWidth:1,
 lineStyle:2,priceLineVisible:false,lastValueVisible:false});
const co1b=cP.addLineSeries({color:'rgba(34,211,238,.55)',lineWidth:1,
 lineStyle:2,priceLineVisible:false,lastValueVisible:false});
const comid=cP.addLineSeries({color:'rgba(201,178,138,.4)',lineWidth:1,
 lineStyle:1,priceLineVisible:false,lastValueVisible:false});
const bou=cP.addCandlestickSeries({upColor:'#10b981',downColor:'#ef4444',
 borderVisible:false,wickUpColor:'#10b981',wickDownColor:'#ef4444'});
const vol=cP.addHistogramSeries({priceScaleId:'v',priceFormat:{type:'volume'},
 priceLineVisible:false,lastValueVisible:false});
cP.priceScale('v').applyOptions({scaleMargins:{top:.87,bottom:0}});
function L(c,col,w,st){return c.addLineSeries({color:col,lineWidth:w||1,lineStyle:st||0,
 priceLineVisible:false,lastValueVisible:false});}
const ema=L(cP,'#22d3ee',2),s50=L(cP,'#f59e0b',1),s200=L(cP,'#a78bfa',1),
 bbu=L(cP,'#3b4d66',1,2),bbl=L(cP,'#3b4d66',1,2),
 rsi=L(cR,'#e879f9',2),macd=L(cM,'#22d3ee',2),macs=L(cM,'#f59e0b',1);
const mach=cM.addHistogramSeries({priceLineVisible:false,lastValueVisible:false});
[40,55,80].forEach(v=>rsi.createPriceLine({price:v,color:'#33465e',lineWidth:1,
 lineStyle:2,axisLabelVisible:true}));
const G={ema20:[ema],sma50:[s50],sma200:[s200],bb:[bbu,bbl],rsi:[rsi],macd:[macd,macs,mach]};

function ic(e){return e==='ok'?'<i class="i-ok">✓</i>':e==='ko'?'<i class="i-ko">✕</i>':'<i class="i-na">?</i>';}
function cls(e){return e==='ok'?'okt':e==='ko'?'ko':'na';}

// La carte INTERET. Elle ne conseille rien : elle compte les conditions
// ecrites AVANT le test, nomme celles qui manquent avec le nombre mesure
// en face de son seuil, aligne les six unites de temps sans les ponderer,
// et rappelle qu'aucune hypothese n'a passe sa Phase 0.
function carteInteret(d){
 const u = d && d.interet;
 const I = (typeof INTERET !== 'undefined') ? INTERET : null;
 if(!u && !I) return '';
 const cl = u ? u.niveau : 'vide';
 let h = '<div class="int n-'+cl+'"><h3>INTÉRÊT</h3>';
 if(u){
  h += '<div class="gd"><b>'+u.titre+'</b><u>'+u.compte+'</u></div>';
  h += '<div class="mo">'+u.motif+'</div>';
  if(u.manquants && u.manquants.length){
   h += '<div class="sec"><span>IL MANQUE</span>';
   u.manquants.forEach(m=>{h += '<div class="mq"><b>'+m.nom+'</b>'
     + (m.texte ? '<i>'+m.texte+'</i>' : '') + '</div>';});
   h += '</div>';
  }
  if(u.refus_motifs && u.refus_motifs.length){
   h += '<div class="sec"><span>POURQUOI LA SÉRIE EST REFUSÉE</span>';
   u.refus_motifs.forEach(v=>{h += '<div class="mq"><b>'+v+'</b></div>';});
   h += '</div>';
  }
  if(u.vetos && u.vetos.length){
   h += '<div class="sec"><span>VETOS DE LA SPÉCIFICATION</span>';
   u.vetos.forEach(v=>{h += '<div class="mq"><b>'+v+'</b></div>';});
   h += '</div>';
  }
  if(u.vigilance && u.vigilance.length){
   h += '<div class="sec"><span>À VÉRIFIER À LA MAIN</span>';
   u.vigilance.forEach(v=>{h += '<div class="mq"><i>'+v+'</i></div>';});
   h += '</div>';
  }
 }
 if(I && I.accord && I.accord.lignes && I.accord.lignes.length){
  h += '<div class="sec"><span>LES UNITÉS DE TEMPS</span><div class="ut">';
  I.accord.lignes.forEach(g=>{
   const part = (g.total ? Math.round(g.ok/g.total*100) : 0);
   h += '<span>'+g.label+'</span><em>'+g.compte+'</em>'
      + '<div class="jg n-'+g.niveau+'"><i style="transform:scaleX('
      + (part/100).toFixed(3) + ')"></i></div>';
  });
  h += '</div><div class="mo">' + I.accord.phrase + '</div></div>';
 }
 if(I && I.historique){
  const x = I.historique;
  h += '<div class="sec"><span>CE SIGNAL SUR CE TITRE</span>'
     + '<div class="mo">' + x.phrase
     + (x.reserve ? '<br>' + x.reserve : '') + '</div></div>';
 }
 if(I){
  h += '<div class="av"><b>' + I.rappel + '</b><br>' + I.pas_un_avis + '</div>';
 }
 return h + '</div>';
}

function draw(){
 const d=D[U];
 if(!d || d.insuffisant){
  var i = d && d.insuffisant;
  var m = "Pas assez d'historique pour cette unite de temps.";
  if(i){
   m = '<b>' + i.barres + ' barre(s) disponible(s)</b>, ' + i.besoin
     + " necessaires pour cette unite.<br>L'historique de ce titre "
     + 'commence le ' + i.depuis + ".<br><br>Une unite large demande "
     + "beaucoup d'annees : vingt ans ne font que vingt barres "
     + 'annuelles. Essayez une unite plus fine.';
  }
  document.getElementById('side').innerHTML='<div class="box">'+m+'</div>'
    + carteInteret(null);
  return;
 }
 bou.setData(d.ohlc); bou.setMarkers(d.markers); vol.setData(d.volume);
 // le cone repart du dernier cours, vers l'avenir
 const K=(d.cone&&d.cone.bandes)?d.cone.bandes:{h1:[],b1:[],h2:[],b2:[],mid:[]};
 co1h.setData(K.h1); co1b.setData(K.b1);
 co2h.setData(K.h2); co2b.setData(K.b2); comid.setData(K.mid);
 const ci=document.getElementById('coneinfo');
 if(ci){
  ci.textContent = d.cone && d.cone.sigma_j
   ? 'DISPERSION '+d.cone.horizon+' BARRES : \u00b1'+d.cone.ampl1
     +' % (68 %) \u00b7 \u00b1'+d.cone.ampl2+' % (95 %) \u00b7 volatilite '
     +d.cone.sigma_j+' %/barre'
   : '';
 }
 ema.setData(d.ema20); s50.setData(d.sma50); s200.setData(d.sma200);
 bbu.setData(d.bbu); bbl.setData(d.bbl); rsi.setData(d.rsi);
 macd.setData(d.macd); macs.setData(d.macds);
 mach.setData(d.macdh.map(p=>({time:p.time,value:p.value,
   color:p.value>=0?'#10b98180':'#ef444480'})));
 [cP,cR,cM].forEach(c=>c.timeScale().fitContent());

 const v=d.verdict;
 let h='<div class="vd v-'+v.type+'"><div class="t">'+v.titre+
       '</div><div class="s">'+v.sous+'</div></div>';
 h+=carteInteret(d);
 if(d.niveaux){const n=d.niveaux;
  h+='<div class="box"><h3>NIVEAUX</h3><div class="lv">'+
   '<div><div class="k">ENTRÉE</div><div class="v">'+n.entree+'</div></div>'+
   '<div><div class="k">STOP</div><div class="v">'+n.stop+'</div></div>'+
   '<div><div class="k">RISQUE</div><div class="v">'+n.risque+'%</div></div>'+
   '<div><div class="k">ATR</div><div class="v">'+n.atr+'</div></div>'+
   '<div><div class="k">TITRES</div><div class="v">'+n.titres+'</div></div>'+
   '<div><div class="k">MONTANT '+n.ccy+'</div><div class="v">'+n.montant+'</div></div>'+
   '</div></div>';}
 h+='<div class="box"><h3>LES 13 BLOCS D\\'ENTRÉE</h3>';
 d.blocs.forEach(b=>{h+='<div class="bl">'+ic(b.etat)+'<span class="'+cls(b.etat)+
   '">'+b.nom+'</span></div>';});
 h+='</div><div class="box"><h3>CONDITIONS DE SORTIE</h3><div class="ex">';
 d.sorties.forEach(s=>{h+=s.actif?'<div><b>● '+s.nom+'</b></div>'
                                 :'<div>○ '+s.nom+'</div>';});
 h+='</div></div>';
 document.getElementById('side').innerHTML=h;

 // --- colonne centrale : le resume en trois chiffres ---
 const coul={achat:'#34d399',vente:'#f87171',proche:'#f59e0b',
             hors:'#c4a5e4',na:'#a78bfa',
             aucun:'#475a72',vide:'#475a72'}[v.type]||'#475a72';
 const vh=document.getElementById('vd-h');
 if(vh){
  vh.textContent=v.titre;
  const ok=d.blocs.filter(b=>b.etat==='ok').length;
  const feu=document.getElementById('feu');
  feu.style.color=coul;
  const C=2*Math.PI*56, part=C*ok/d.blocs.length;
  feu.querySelector('.fb').setAttribute('stroke-dasharray',
    part.toFixed(1)+' '+(C-part).toFixed(1));
  feu.classList.toggle('pulse', v.type==='achat'||v.type==='sortie');
  if(U==='jour' && vh.dataset.dit!==v.titre){
   vh.dataset.dit=v.titre;
   const dit={achat:'Signal complet. Les treize blocs sont valides.',
    vente:'Conditions de sortie actives.',
    hors:'Hors critères. Un veto de la spécification.',
    na:'Données insuffisantes sur cette unité de temps.',
    proche:ok+' blocs sur '+d.blocs.length+'. Signal incomplet.',
    aucun:'Aucun signal.'}[v.type];
   if(dit) parle(TICKER+'. '+dit);
  }
  document.getElementById('vd-n').textContent=ok+' / '+d.blocs.length+' BLOCS';
  document.getElementById('vd-blocs').textContent=ok+' / '+d.blocs.length;
  document.getElementById('vd-stop').textContent=
    d.niveaux? d.niveaux.stop : '\\u2014';
  const ch=document.getElementById('vd-ch');
  ch.textContent = CHANCE || '\\u2014';
  ch.style.color = CHANCE ? '#f59e0b' : '#475a72';
 }
 document.getElementById('px').textContent=d.stats.cours;
 document.getElementById('mt').textContent='RSI '+Math.round(d.stats.rsi)+
   ' · ATR '+d.stats.atr;
 var ns=document.getElementById('nsig');
 if(ns)ns.textContent=d.markers.length+' signaux / '+d.stats.bougies+' bougies';
}

document.querySelectorAll('.tabs button').forEach(b=>b.addEventListener('click',()=>{
 document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('on'));
 b.classList.add('on'); U=b.dataset.u;
 try{majLong();}catch(e){} draw();}));

let lock=false;
[cP,cR,cM].forEach(src=>src.timeScale().subscribeVisibleLogicalRangeChange(r=>{
 if(lock||!r)return; lock=true;
 [cP,cR,cM].forEach(c=>{if(c!==src)c.timeScale().setVisibleLogicalRange(r);});
 lock=false;}));
function redim(){[[cP,'p1'],[cR,'p2'],[cM,'p3']].forEach(([c,id])=>{
 const el=document.getElementById(id);
 c.applyOptions({width:el.clientWidth,
  height:Math.max(90,el.parentElement.clientHeight-30)});});}
// --- interrupteurs d'indicateurs : ils pilotent la visibilite des series
const SERIES={cone:[co1h,co1b,co2h,co2b,comid],
              ema20:[ema],sma50:[s50],sma200:[s200],bb:[bbu,bbl],
              rsi:[rsi],macd:[macd,macs,mach]};
document.querySelectorAll('.ol input[data-k]').forEach(function(inp){
 inp.addEventListener('change',function(){
  (SERIES[inp.dataset.k]||[]).forEach(function(s){
   s.applyOptions({visible:inp.checked});});
 });
});
// Le tiroir de reglages agit sur les memes series.
window.CARRUOS_IND=function(cle,actif){
 const inp=document.querySelector('.ol input[data-k="'+cle+'"]');
 if(inp){inp.checked=actif;}
 (SERIES[cle]||[]).forEach(function(s){s.applyOptions({visible:actif});});
};

// --- zoom : on agit sur l'echelle de temps des trois graphiques a la fois
function zoom(f){
 [cP,cR,cM].forEach(function(c){
  const ts=c.timeScale(), r=ts.getVisibleLogicalRange();
  if(!r) return;
  const mid=(r.from+r.to)/2, demi=(r.to-r.from)/2*f;
  ts.setVisibleLogicalRange({from:mid-demi,to:mid+demi});
 });
}
document.getElementById('z+').onclick=function(){zoom(0.7);};
document.getElementById('z-').onclick=function(){zoom(1.45);};
// on rappelle sur quelles longueurs les courbes sont tracees
const LONG={jour:'200 / 50 / 20 \u00b7 RSI 14 \u00b7 MACD 12-26-9',
 semaine:'40 / 10 / 5 \u00b7 RSI 7 \u00b7 MACD 4-8-3',
 mois:'10 / 5 / 5 \u00b7 RSI 7 \u00b7 MACD 4-8-3',
 trimestre:'5 / 5 / 5 \u00b7 RSI 7 \u00b7 MACD 4-8-3',
 an:'5 / 5 / 5 \u00b7 RSI 7 \u00b7 MACD 4-8-3'};
function majLong(){
 const o=document.getElementById('oz');
 if(!o)return;
 o.textContent=(LONG[U]||'')+(U==='jour'?' (valeurs de la strategie)'
   :' \u2014 converties pour le meme horizon');
}
majLong();
// --- Annonce vocale du verdict. Voix de synthese du systeme : ce n'est
//     pas celle du film, et personne ne peut la reproduire legalement.
//     Elle dit ce que l'ecran affiche, rien de plus.
let VOIX = localStorage.getItem('carruos_voix')==='1';
function majVoix(){
 const b=document.getElementById('vx');
 if(!b)return;
 b.textContent = VOIX?'COUPER':'ACTIVER';
 b.classList.toggle('on', VOIX);
}
function parle(txt){
 if(!VOIX || !window.speechSynthesis) return;
 try{
  speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(txt);
  u.lang='fr-FR'; u.rate=0.98; u.pitch=0.82; u.volume=0.9;
  const v=speechSynthesis.getVoices()
    .filter(x=>x.lang && x.lang.indexOf('fr')===0);
  const grave=v.find(x=>/Paul|Thierry|Claude|Henri/i.test(x.name));
  if(grave||v[0]) u.voice=grave||v[0];
  speechSynthesis.speak(u);
 }catch(e){}
}
const b_vx=document.getElementById('vx');
if(b_vx){
 majVoix();
 b_vx.onclick=function(){
  VOIX=!VOIX;
  try{localStorage.setItem('carruos_voix', VOIX?'1':'0');}catch(e){}
  majVoix();
  if(VOIX) parle('Systeme vocal actif.');
  else if(window.speechSynthesis) speechSynthesis.cancel();
 };
}
if(window.speechSynthesis) speechSynthesis.onvoiceschanged=function(){};

document.getElementById('z0').onclick=function(){
 [cP,cR,cM].forEach(function(c){c.timeScale().fitContent();});
};
// les trois graphiques restent alignes quand on zoome a la molette
let sync=false;
[[cP,[cR,cM]],[cR,[cP,cM]],[cM,[cP,cR]]].forEach(function(pair){
 pair[0].timeScale().subscribeVisibleLogicalRangeChange(function(r){
  if(sync||!r) return; sync=true;
  pair[1].forEach(function(c){c.timeScale().setVisibleLogicalRange(r);});
  sync=false;
 });
});

window.addEventListener('resize',redim); setTimeout(redim,60);
// Pilotage des indicateurs depuis le tiroir de reglages.
window.CARRUOS_IND=function(cle,actif){
 if(cle==='volume'){vol.applyOptions({visible:actif});return;}
 if(cle==='signaux'){bou.setMarkers(actif?(D[U]||{}).markers||[]:[]);return;}
 (G[cle]||[]).forEach(s=>s.applyOptions({visible:actif}));};
draw();

// Horloge de seance. Intl.DateTimeFormat connait les regles d'heure d'ete
// de chaque place : aucune table a maintenir cote Python.
(function(){
 var el=document.querySelector('[data-marche]'); if(!el)return;
 var eu=el.dataset.marche==='europe';
 var TZ=eu?'Europe/Paris':'America/New_York';
 var O=eu?[9,0]:[9,30], C=eu?[17,30]:[16,0];
 function local(tz){return new Date(new Date().toLocaleString('en-US',{timeZone:tz}));}
 function hhmm(h,m){return ('0'+h).slice(-2)+'h'+('0'+m).slice(-2);}
 function paris(h,m){
  var d=local(TZ); d.setHours(h,m,0,0);
  var s=d.toLocaleString('en-US',{timeZone:TZ});
  var p=new Date(new Date(s).toLocaleString('en-US',{timeZone:'Europe/Paris'}));
  // decalage entre la place et Paris, calcule sur l'instant courant
  var a=local(TZ), b=local('Europe/Paris');
  var dec=Math.round((b-a)/3600000);
  var hh=(h+dec+24)%24; return hhmm(hh,m);
 }
 function tick(){
  var n=local(TZ), jour=n.getDay(), mn=n.getHours()*60+n.getMinutes();
  var o=O[0]*60+O[1], c=C[0]*60+C[1];
  var ouvert=(jour>=1&&jour<=5&&mn>=o&&mn<c);
  document.getElementById('d1').className='dot '+(ouvert?'on':'off');
  document.getElementById('etat').textContent=
    ouvert?'Seance ouverte':(jour===0||jour===6?'Week-end':'Seance fermee');
  document.getElementById('ouv').textContent=paris(O[0],O[1])+' Paris';
  document.getElementById('clo').textContent=paris(C[0],C[1])+' Paris';
  if(ouvert){var r=c-mn;
   document.getElementById('reste').textContent=
     Math.floor(r/60)+'h'+('0'+(r%60)).slice(-2);
  } else {document.getElementById('reste').textContent='-';}
  var fen=(ouvert&&(c-mn)<=20);
  document.getElementById('d2').className='dot '+(fen?'win':'off');
  document.getElementById('win').textContent=
    fen?"Fenetre d'execution OUVERTE":"Fenetre a "+paris(C[0],C[1]-20)+' Paris';
 }
 tick(); setInterval(tick,20000);
})();

"""

TOGGLES = [("ema20", "EMA 20", "#22d3ee"), ("sma50", "SMA 50", "#f59e0b"),
           ("sma200", "SMA 200", "#a78bfa"), ("bb", "Bollinger", "#3b4d66"),
           ("rsi", "RSI", "#e879f9"), ("macd", "MACD", "#22d3ee")]


def build_html(brut, ticker, bench_brut, sleeve=8000.0, ccy="",
               barre="", marche="us", earn=None, actus=None) -> str:
    """Construit la page complete et la renvoie en texte.

    `barre` permet d'injecter une barre de controle (utilisee par l'appli
    Bruce, qui sert cette page dans sa propre fenetre au lieu de l'ecrire
    sur le disque).
    """
    e = html.escape
    dj = enrich(brut, bench_close=bench_brut["close"])
    bj = enrich(bench_brut)
    entete_hud, mods, souci = "", "", None
    jauges = perf = None
    chance = ""
    try:
        jauges = _jauges(dj, bj)
        perf = _perf_signal(dj, ticker, bj)
        mods = _modules(jauges, perf, ticker, marche, earn, actus)
        if perf and perf.get("n"):
            w = _wilson(round(perf["taux"] * perf["n"] / 100), perf["n"])
            chance = f"{w[0]:.0f}\u2013{w[2]:.0f} %"
    except Exception as exc:
        # Echouer en silence ici rend le probleme invisible : on l'affiche.
        import traceback
        souci = f"modules : {type(exc).__name__}: {exc}"
        traceback.print_exc()

    # Le controle qualite ne tournait pas sur la page graphique : un
    # titre dont `scan` refuse le signal s'y affichait quand meme comme
    # les autres. Une seule passe, sur la serie journaliere, partagee
    # par les six unites.
    qual = None
    try:
        from . import qualite as ql
        rq = ql.controle(brut, bench=bench_brut, ticker=ticker)
        qual = (rq.utilisable, tuple(rq.bloquants))
    except Exception:
        qual = None

    data = {}
    for cle, _lab, regle, nb in UNITES:
        try:
            # L'unite JOUR est deja enrichie au-dessus, avec les memes
            # arguments : on la repasse au lieu de la recalculer.
            deja = (dj, bj) if regle is None else None
            data[cle] = _analyse(brut, bench_brut, regle, nb, ticker,
                                 sleeve, ccy, pre=deja, cle=cle, qual=qual)
        except Exception:
            data[cle] = None

    # --- L'INTERET, la partie qui ne depend pas de l'onglet -----------
    # L'accord des unites de temps et l'historique du signal sur CE
    # titre. Aucune ponderation entre les six unites : on les aligne, le
    # lecteur voit lui-meme si elles disent la meme chose.
    try:
        inter = it.carte(
            unite=None,
            acc=it.accord([(k, lab, data.get(k)) for k, lab, _r, _n in UNITES]),
            hist=it.historique(perf),
            ticker=ticker)
    except Exception:
        import traceback
        traceback.print_exc()
        inter = {"accord": None, "historique": None,
                 "pas_un_avis": it.PAS_UN_AVIS, "rappel": it.RAPPEL_PHASE0}

    # Pas d'antislash dans une expression de f-string : interdit avant
    # Python 3.12. On construit la classe a part.
    morceaux = []
    for k, lab, _r, _n in UNITES:
        actif = ' class="on"' if k == "jour" else ""
        # La fenetre couverte, en petit sous le libelle : « 1 AN » se lit
        # spontanement comme « un an d'historique » alors que ce sont des
        # bougies annuelles sur trente ans.
        fen = fenetre_reelle(data.get(k))
        morceaux.append(f'<button data-u="{k}"{actif} '
                        f'title="couvre {fen}">'
                        f'{e(lab)}<i>{e(fen)}</i></button>')
    if jauges:
        vj = (data.get("jour") or {}).get("verdict", {})
        n_ko = len([b for b in (data.get("jour") or {}).get("blocs", [])
                    if b["etat"] == "ko"])
        etat = f'{vj.get("titre", "-")} - {13 - n_ko}/13 BLOCS'
        try:
            entete_hud = hd.entete(ticker, jauges, etat, perf, hd.TRACE, ccy)
        except Exception as exc:
            import traceback
            souci = f"HUD : {type(exc).__name__}: {exc}"
            traceback.print_exc()

    tabs = "".join(morceaux)
    tog = "".join(f'<label><input type="checkbox" data-k="{k}" checked>'
                  f'<span class="sw" style="background:{c}"></span>{e(l)}</label>'
                  for k, l, c in TOGGLES)

    reg = rg.charge()
    doc = (
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="icon" type="image/svg+xml" href="/carruos.svg"><link rel="alternate icon" href="/favicon.ico">'
        f"<title>{e(ticker)} &mdash; Carruos</title>"
        f"<style>{rg.variables(reg)}{CSS}</style></head>"
        f'<body class="{rg.classes(reg)}"{rg.corps_attrs(reg)}>'
        + rg.tiroir_html(reg)
        + '<div class="wrap">'
        # --- barre superieure ---
        f'<div class="hd">{barre}<h1>{e(ticker)}</h1>'
        f'<span class="px" id="px"></span><span class="mt" id="mt"></span>'
        f'<div class="tabs">{tabs}</div></div>'
        # --- barre d'outils : les interrupteurs existaient mais
        #     n'etaient jamais poses dans la page ---
        f'<div class="ol"><span class="ot">INDICATEURS</span>{tog}'
        '<span class="osep"></span>'
        '<label><input type="checkbox" data-k="cone" checked>'
        '<span class="sw" style="color:var(--txt);background:var(--txt)"></span>'
        'Dispersion</label>'
        '<span class="osep"></span><span class="ot">ZOOM</span>'
        '<button class="zb" id="z-">&minus;</button>'
        '<button class="zb" id="z+">+</button>'
        '<button class="zb" id="z0">AJUSTER</button>'
        '<span class="osep"></span><span class="ot">VOIX</span>'
        '<button class="zb" id="vx">ACTIVER</button>'
        '<span class="oz" id="coneinfo"></span>'
        '<span class="oz" id="oz">molette &middot; glisser</span></div>'
        # --- colonne gauche : cadrans, hologramme, rails ---
        f'<div class="pil-l">{entete_hud}</div>'
        # --- colonne centrale : les trois panneaux ---
        '<div class="pil-c">'
        '<div class="box"><div class="lb"><span>PRIX ET VOLUME</span>'
        '<span id="nsig"></span></div><div id="p1"></div></div>'
        '<div class="box"><div class="lb"><span>RSI 14</span>'
        '<span>zone 40-55</span></div><div id="p2"></div></div>'
        '<div class="box"><div class="lb"><span>MACD 12-26-9</span></div>'
        '<div id="p3"></div></div></div>'
        # --- colonne hologramme : le cerf, le nom, le verdict ---
        '<div class="pil-h">'
        + hd.noyau(hd.TRACE)
        + '<div class="nom">CARRUOS</div>'
        '<div class="sst">REPLI EN TENDANCE</div>'
        f'<div class="tk">{e(ticker)}</div>'
        '<div class="feu" id="feu"><svg viewBox="0 0 132 132">'
        '<circle class="fa" cx="66" cy="66" r="56" fill="none" '
        'stroke="#16323c" stroke-width="5"/>'
        '<circle class="fb" cx="66" cy="66" r="56" fill="none" '
        'stroke="currentColor" stroke-width="5" stroke-linecap="round" '
        'stroke-dasharray="0 352" transform="rotate(-90 66 66)"/>'
        '<circle class="fc" cx="66" cy="66" r="42" fill="none" '
        'stroke="currentColor" stroke-width="1" opacity=".35" '
        'stroke-dasharray="3 7"/></svg>'
        '<div class="fv" id="vd-h">ANALYSE</div>'
        '<div class="fn" id="vd-n">&mdash;</div></div>'
        '<div class="kv"><span>BLOCS</span><b id="vd-blocs">&mdash;</b></div>'
        '<div class="kv"><span>CHANCES</span><b id="vd-ch">&mdash;</b></div>'
        '<div class="kv"><span>STOP</span><b id="vd-stop">&mdash;</b></div>'
        '</div>'
        # --- colonne droite : verdict detaille, niveaux, blocs, sorties ---
        '<div class="pil-r" id="side"></div>'
        # --- bandeau bas : les modules ---
        f'<div class="bas">{mods}</div>'
        + (f'<div class="bas" style="background:#2c1014;border:1px solid #8b2733;'
           f'color:#fca5a5;border-radius:10px;padding:9px 15px;font-size:12.5px">'
           f'HUD indisponible &mdash; {e(souci)}</div>' if souci else "")
        + '</div>'
        f'<script src="{source_trace()}"></script>'
        "<script>const DATA=__D__;const CHANCE=" + json.dumps(chance)
        + ";const TICKER=" + json.dumps(ticker)
        + ";const INTERET=" + json.dumps(inter, ensure_ascii=False)
        + ";" + JS + rg.tiroir_js() + "</script></body></html>"
    ).replace("__D__", json.dumps(data, separators=(",", ":")))

    return doc


def _bar(val, lo, hi, zlo=None, zhi=None):
    """Petite jauge : bande verte = zone recherchee, trait blanc = valeur."""
    if val is None:
        return ""
    pos = max(0, min(100, (val - lo) / (hi - lo) * 100))
    z = ""
    if zlo is not None:
        a = max(0, min(100, (zlo - lo) / (hi - lo) * 100))
        b = max(0, min(100, (zhi - lo) / (hi - lo) * 100))
        z = f'<i class="zone" style="left:{a:.0f}%;width:{b-a:.0f}%"></i>'
    return f'<div class="gg">{z}<i class="val" style="left:{pos:.0f}%"></i></div>'


def _sgn(v, suff="%"):
    if v is None:
        return '<b class="neu">-</b>'
    c = "pos" if v > 0 else "neg" if v < 0 else "neu"
    return f'<b class="{c}">{v:+.1f}{suff}</b>'


def _wilson(succes, n, z=1.96):
    """Intervalle de confiance de Wilson sur un taux de reussite.

    Avec 13 trades, un taux observe de 46 % ne veut pas dire 46 % de
    chances. Il veut dire : quelque part entre 23 % et 71 %. C'est cette
    largeur qu'il faut montrer, pas le point central tout seul.
    """
    if not n:
        return None
    p = succes / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    e = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - e) * 100, max(0.0, min(1.0, c)) * 100, min(1.0, c + e) * 100


def _arc_chance(perf):
    """Demi-cercle facon reacteur : le taux observe et son incertitude.

    On affiche la BANDE, pas une aiguille. Une aiguille laisserait croire
    a une precision qui n'existe pas sur 13 trades.
    """
    import math
    if not perf or not perf.get("n"):
        return ('<div class="mod" data-mod="signal"><h4>CHANCES DE GAGNER</h4>'
                '<div class="ex">Aucun trade de ce signal sur ce titre. '
                'Impossible d\'estimer quoi que ce soit.</div></div>')
    n = perf["n"]
    w = _wilson(perf.get("gagnants", round(perf["taux"] * n / 100)), n)
    lo, mid, hi = w
    R, cx, cy = 92, 110, 104
    def pt(pct):
        a = math.pi * (1 - pct / 100)
        return cx + R * math.cos(a), cy - R * math.sin(a)
    def arc(p1, p2, coul, larg, op=1.0):
        x1, y1 = pt(p1); x2, y2 = pt(p2)
        return (f'<path d="M{x1:.1f} {y1:.1f}A{R} {R} 0 0 1 {x2:.1f} {y2:.1f}" '
                f'fill="none" stroke="{coul}" stroke-width="{larg}" '
                f'stroke-linecap="round" opacity="{op}"/>')
    fiable = n >= 30
    coul = "#34d399" if lo > 50 else ("#f59e0b" if hi > 50 else "#f87171")
    svg = (f'<svg viewBox="0 0 220 128" style="width:100%;height:auto;display:block">'
           + arc(0, 100, "#16323c", 13)
           + arc(lo, hi, coul, 13, .88)
           + f'<line x1="{cx}" y1="{cy - R - 9:.0f}" x2="{cx}" '
             f'y2="{cy - R + 9:.0f}" stroke="#64748b" stroke-width="1.4"/>'
           + f'<text x="{cx}" y="{cy - 26}" text-anchor="middle" '
             f'fill="{coul}" font-size="27" font-family="ui-monospace,monospace">'
             f'{lo:.0f}\u2013{hi:.0f}%</text>'
           + f'<text x="{cx}" y="{cy - 9}" text-anchor="middle" fill="#475a72" '
             f'font-size="9" letter-spacing="1.6" '
             f'font-family="ui-monospace,monospace">FOURCHETTE A 95 %</text>'
           + f'<text x="14" y="{cy + 14}" fill="#334756" font-size="9" '
             f'font-family="ui-monospace,monospace">0 %</text>'
           + f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" fill="#64748b" '
             f'font-size="9" font-family="ui-monospace,monospace">50 %</text>'
           + f'<text x="206" y="{cy + 14}" text-anchor="end" fill="#334756" '
             f'font-size="9" font-family="ui-monospace,monospace">100 %</text>'
           + '</svg>')
    verdict = ("La fourchette est entierement au-dessus de 50 %."
               if lo > 50 else
               ("La fourchette contient 50 % : sur cet echantillon, ce signal "
                "n'est pas distinguable d'un tirage a pile ou face."
                if hi > 50 else
                "La fourchette est entierement sous 50 %."))
    return ('<div class="mod" data-mod="signal" style="min-width:0">'
            '<h4>CHANCES DE GAGNER &mdash; ESTIMATION</h4>' + svg
            + f'<div class="kv"><span>taux observe</span><b>{perf["taux"]}%</b></div>'
            + f'<div class="kv"><span>sur</span><b>{n} trade(s)</b></div>'
            + f'<div class="ex" style="margin-top:8px;max-width:100%">{verdict}'
            + ('' if fiable else ' Avec moins de 30 trades, la fourchette est '
               'trop large pour decider.')
            + ' Et la Phase 0 a rendu NO-GO : aucun avantage n\'a ete '
              'demontre sur l\'ensemble du systeme.</div></div>')


def _modules(g, perf, ticker, marche, earn, actus):
    e = html.escape
    m = []

    # Momentum
    rsi, rvol = g["rsi"], g["rvol"]
    m.append('<div class="mod" data-mod="momentum"><h4>MOMENTUM</h4>'
             f'<div class="hdr2"><b>{rsi:.0f}</b><span>RSI 14 &middot; zone 40-55</span></div>'
             + _bar(rsi, 0, 100, 40, 55) +
             f'<div class="hdr2"><b>{rvol:.2f}</b><span>RVOL &middot; seuil 1,20</span></div>'
             + _bar(min(rvol, 3), 0, 3, 1.2, 3) +
             f'<div class="kv"><span>ATR 14</span><b>{g["atr"]} ({g["atr_pct"]}%)</b></div>'
             '</div>')

    # Position vs reperes
    k = []
    for lab, cle in (("EMA 20", "ema20"), ("SMA 50", "sma50"), ("SMA 200", "sma200")):
        v = g.get(cle)
        if v:
            k.append(f'<div class="kv"><span>{lab}</span>{_sgn(v["pct"])}'
                     f'<b class="neu">{v["atr"]:+.1f} ATR</b></div>')
    k.append(f'<div class="kv"><span>Plus haut 52s</span>{_sgn(g["d_h52"])}</div>')
    k.append(f'<div class="kv"><span>Plus bas 52s</span>{_sgn(g["d_b52"])}</div>')
    m.append('<div class="mod" data-mod="ecarts"><h4>ECART AUX REPERES</h4>' + "".join(k) + '</div>')

    # Force relative
    k = []
    for lab, cle in (("1 mois", "p1m"), ("3 mois", "p3m"),
                     ("6 mois", "p6m"), ("12 mois", "p12m")):
        v = g.get(cle)
        if v:
            k.append(f'<div class="kv"><span>{lab}</span>{_sgn(v["titre"])}'
                     f'{_sgn(v["ecart"])}</div>')
    m.append('<div class="mod" data-mod="perfrel"><h4>PERFORMANCE / ECART A L\'INDICE</h4>'
             + "".join(k) + '</div>')

    # Historique du signal sur CE titre
    if perf and perf.get("n"):
        d = "".join(f'<div class="kv"><span>{x["d"]} &middot; {x["m"]}</span>'
                    f'{_sgn(x["R"], " R")}</div>' for x in perf["derniers"])
        m.append(_arc_chance(perf))
        m.append('<div class="mod" data-mod="signal"><h4>CE SIGNAL SUR CE TITRE</h4>'
                 f'<div class="kv"><span>trades</span><b>{perf["n"]}</b></div>'
                 f'<div class="kv"><span>reussite</span><b>{perf["taux"]}%</b></div>'
                 f'<div class="kv"><span>profit factor</span><b>{perf["pf"]}</b></div>'
                 f'<div class="kv"><span>gain moyen</span>{_sgn(perf["evR"], " R")}</div>'
                 f'<div class="kv"><span>duree</span><b>{perf["duree"]} j</b></div>'
                 f'<div style="margin-top:9px;border-top:1px solid #141c27;padding-top:7px">'
                 f'{d}</div></div>')
    elif perf is not None:
        m.append('<div class="mod" data-mod="signal"><h4>CE SIGNAL SUR CE TITRE</h4>'
                 '<div class="tl">Aucun signal sur l\'historique disponible. '
                 'Pas de reference propre a ce titre.</div></div>')

    # Horloge de marche
    m.append(f'<div class="mod" data-mod="horloge" data-marche="{marche}"><h4>SEANCE ET EXECUTION</h4>'
             '<div class="clk"><span class="dot off" id="d1"></span>'
             '<span id="etat">-</span></div>'
             '<div class="kv" style="margin-top:9px"><span>ouverture</span>'
             '<b id="ouv">-</b></div>'
             '<div class="kv"><span>cloture</span><b id="clo">-</b></div>'
             '<div class="kv"><span>reste</span><b id="reste">-</b></div>'
             '<div class="clk" style="margin-top:9px"><span class="dot off" id="d2">'
             '</span><span id="win">-</span></div>'
             '<div class="tl" style="margin-top:7px">Les regles s\'evaluent sur '
             'cloture. La fenetre utile est <b>20 minutes avant la cloche</b>.'
             '</div></div>')

    # Resultats trimestriels
    if earn:
        cls = "neg" if earn["jours"] is not None and earn["jours"] < 10 else "pos"
        j = "inconnue" if earn["jours"] is None else f'{earn["jours"]} seances'
        m.append('<div class="mod" data-mod="resultats"><h4>RESULTATS TRIMESTRIELS</h4>'
                 f'<div class="hdr2"><b class="{cls}">{e(str(earn.get("date","?")))}</b></div>'
                 f'<div class="kv"><span>dans</span><b class="{cls}">{j}</b></div>'
                 + ('<div class="tl" style="margin-top:7px">Sous 10 seances : '
                    '<b>veto actif</b>, aucune entree.</div>'
                    if earn["jours"] is not None and earn["jours"] < 10 else
                    '<div class="tl" style="margin-top:7px">Hors periode de veto.'
                    '</div>') + '</div>')

    # Actualites
    if actus:
        liens = ""
        for a in actus[:5]:
            sc = a.get("score")
            c = "neu" if sc is None else ("neg" if sc < -.15 else
                                          "pos" if sc > .15 else "neu")
            lab = "" if sc is None else f' &middot; <span class="{c}">{sc:+.2f}</span>'
            liens += (f'<a href="{e(a.get("url") or "#")}" target="_blank">'
                      f'{e(a.get("titre",""))}<br><span class="m">'
                      f'{e(a.get("quand",""))} {e(a.get("source",""))}{lab}</span></a>')
        m.append('<div class="mod" data-mod="actus" style="grid-column:span 2"><h4>ACTUALITES</h4>'
                 f'<div class="nw2">{liens}</div></div>')

    return '<div class="mods">' + "".join(m) + '</div>'


def render(brut, ticker, bench_brut, sleeve=8000.0, ccy="", path=None,
           open_browser=True) -> Path:
    doc = build_html(brut, ticker, bench_brut, sleeve, ccy)
    out = Path(path or f"graphique-{ticker.replace('.', '_')}.html").resolve()
    out.write_text(doc, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.as_uri())
    return out
