"""L'INTERET d'un titre — des faits comptes, jamais un avis.

Frederic demande « un interet / opinion a chaque fois que je consulte une
action ». La premiere moitie de la demande se sert. La seconde, non, et
il faut dire pourquoi plutot que de la servir en douce.

CE QUE CE MODULE NE FAIT PAS, et pourquoi
-----------------------------------------
Pas de score composite. L'ancien `forecast.py` additionnait sept poids
(trend 25, momentum 15, force relative 15...) qu'aucune mesure ne
justifiait, et en tirait « NVDA — HAUSSIER, confiance 68 % ». Onze
nombres inventes produisaient une opinion qui avait l'air d'un calcul.
Ce module ne multiplie rien par rien : il COMPTE.

Pas de verdict directionnel. « ACHETER » est une opinion. « 11 des 13
blocs de la specification sont reunis, il manque le volume (RVOL 0,81
pour un seuil de 1,20) et le declencheur MACD » est un fait, verifiable
ligne a ligne, et qui dit en plus quoi surveiller.

CE QU'IL FAIT
-------------
Quatre comptes, et rien d'autre :

  1. Les 13 blocs d'entree : combien passent, et pour chacun de ceux qui
     manquent, la valeur MESUREE en face de son seuil. C'est la partie
     utile : « il manque 2 blocs » ne dit pas quoi guetter, « RVOL 0,81
     pour 1,20 » si.
  2. L'eligibilite : les vetos de la specification (prix, volume dollar,
     gap recent). Un veto n'est pas un bloc manquant, c'est un titre qui
     sort du cadre.
  3. L'accord des unites de temps : le meme decompte sur les six unites.
     Un titre a 13/13 en journalier et 6/13 en mensuel n'est pas le meme
     dossier qu'un titre a 13/13 partout. On ne pondere pas, on aligne.
  4. L'historique du signal SUR CE TITRE : nombre de trades, gagnants,
     et l'intervalle de Wilson. Jamais un pourcentage seul.

L'ECHELLE
---------
Le niveau affiche n'est pas un jugement : c'est le nom du compte. Les
sept marches sont fixees ICI, avant tout usage, et ne dependent d'aucun
poids. Leur ordre d'evaluation est celui de `NIVEAUX`.

    py -m equity_scanner.interet NVDA
"""

from __future__ import annotations

import argparse
import datetime as dt

import numpy as np

from . import rules as R
from .dashboard import LABELS

VERSION = "interet-v1.0"

# L'echelle. Chaque marche porte le compte qui la declenche, dans
# l'ordre ou on les essaie. Aucune n'est une opinion : « IL MANQUE
# 2 BLOCS » est verifiable, « ACHETER » ne l'est pas.
NIVEAUX = [
    ("refus", "DONNÉES REFUSÉES",
     "le contrôle qualité interdit tout signal sur cette série"),
    ("na", "DONNÉES INSUFFISANTES",
     "au moins un indicateur n'est pas calculable sur cette unité"),
    ("hors", "HORS CRITÈRES",
     "la spécification exclut ce titre, quels que soient ses blocs"),
    ("sortie", "CONDITIONS DE SORTIE ACTIVES",
     "au moins deux des quatre sorties de la spécification sont vraies"),
    ("complet", "LES 13 BLOCS PASSENT",
     "la spécification est entièrement satisfaite aujourd'hui"),
    ("proche", "IL MANQUE PEU",
     "un ou deux blocs seulement"),
    ("loin", "SIGNAL ABSENT",
     "trois blocs manquants ou plus"),
]
TITRES = {c: t for c, t, _ in NIVEAUX}
MOTIFS = {c: m for c, _, m in NIVEAUX}

# Ce texte s'affiche a chaque consultation. Il n'est pas decoratif : il
# empeche de lire « 13 / 13 » comme « avantage demontre ».
PAS_UN_AVIS = (
    "Ce n'est pas un avis. C'est le compte des conditions écrites AVANT "
    "le test, et la liste de celles qui manquent. La décision reste la "
    "vôtre.")
RAPPEL_PHASE0 = (
    "Aucune hypothèse n'a passé sa Phase 0. Treize blocs sur treize "
    "veut dire que la spécification est satisfaite — pas qu'un avantage "
    "existe.")


# Le vocabulaire depend de l'unite de temps. « la veille » et
# « 10 seances » sont justes sur l'onglet 1 JOUR et faux partout
# ailleurs : sur l'onglet 1 MOIS, la barre precedente est le mois
# precedent. Un texte exact sur une unite et faux sur cinq autres est
# pire qu'un texte generique.
# Trois formes, pas deux : « un plus haut de le trimestre precedent »
# est du francais casse. Le genitif se contracte, l'adverbe non.
MOTS = {
    "jour":      ("séances", "la veille", "de la veille"),
    "semaine":   ("semaines", "la semaine précédente", "de la semaine précédente"),
    "cinq_ans":  ("semaines", "la semaine précédente", "de la semaine précédente"),
    "mois":      ("mois", "le mois précédent", "du mois précédent"),
    "trimestre": ("trimestres", "le trimestre précédent", "du trimestre précédent"),
    "an":        ("années", "l'année précédente", "de l'année précédente"),
}


def _f(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def n(x, dec: int = 2) -> str:
    """Un nombre en francais, avec la virgule. `?` si on ne l'a pas."""
    if x is None:
        return "?"
    return f"{float(x):.{dec}f}".replace(".", ",")


def mesures(d, bench, pos: int = -1, cle: str = "jour",
            periodes: dict | None = None) -> dict:
    """Pour chacun des 13 blocs : la valeur mesuree face a son seuil.

    C'est la seule partie qui demande de connaitre les regles dans le
    detail. Elle ne les REJOUE pas — `rules.evaluate` reste seul juge du
    passage — elle EXPOSE les deux nombres que la regle a compares, pour
    qu'on voie de combien on est loin.
    """
    pas, veille, deveille = MOTS.get(cle, MOTS["jour"])
    # La fenetre de repli et le plus haut sont CONVERTIS par unite
    # (chart.periodes_unite). Ecrire « 60j » en dur mentait des qu'on
    # quittait le journalier.
    haut = (periodes or {}).get("haut", 60)
    m = len(d)
    p = pos if pos >= 0 else m + pos
    row, prev = d.iloc[p], d.iloc[max(0, p - 1)]
    win = d.iloc[max(0, p - R.PULLBACK_WINDOW + 1): p + 1]
    br = bench.iloc[-1] if bench is not None and len(bench) else None
    atr = _f(row.get("atr14")) or 0.0
    c = _f(row.get("close"))

    def paire(v, s, texte):
        return {"valeur": v, "seuil": s, "texte": texte}

    rsi_min = _f(win["rsi14"].min()) if "rsi14" in win else None
    rsi_max = _f(win["rsi14"].max()) if "rsi14" in win else None
    ecart = None if c is None or _f(row.get("ema20")) is None else abs(
        c - _f(row.get("ema20")))
    bande = R.EMA_BAND_ATR * atr if atr else None

    out = {
        "1a": paire(
            _f(br["close"]) if br is not None else None,
            _f(br["sma200"]) if br is not None else None,
            "l'indice est à {v} pour une MM200 à {s}"),
        "1b": paire(c, _f(row.get("sma200")),
                    "le titre est à {v} pour une MM200 à {s}"),
        "1c": paire(_f(row.get("sma50_slope20")), 0.0,
                    "pente de la MM50 sur 20 barres : {v} (il faut > {s})"),
        "1d": paire(_f(row.get("rs")), _f(row.get("rs_ma50")),
                    "force relative {v} pour sa moyenne 50 barres à {s}"),
        "1e": paire(_f(row.get("macd")), 0.0,
                    "ligne MACD à {v} (il faut > {s})"),
        # Le bloc 2a passe par l'un OU l'autre chemin : dans la bande
        # autour de l'EMA20, ou un passage sous la moyenne de Bollinger
        # pendant le repli. Ne montrer que le premier ferait croire a un
        # echec la ou le second a suffi.
        "2a": paire(ecart, bande,
                    "écart à l'EMA20 : {v} pour une bande de {s} "
                    "(0,5 ATR) — ou, à défaut, un passage sous la "
                    "moyenne de Bollinger"),
        "2b": paire(rsi_min, None,
                    "RSI de {v} à " + n(rsi_max) + " sur "
                    f"{R.PULLBACK_WINDOW} {pas} — il en faut un entre "
                    f"{R.RSI_ZONE[0]:.0f} et {R.RSI_ZONE[1]:.0f}"),
        "2c": paire(rsi_min, R.RSI_FLOOR,
                    "RSI descendu à {v} (il ne doit pas passer sous {s})"),
        "2d": paire(_f(row.get("bars_since_high60")),
                    float(R.PULLBACK_WINDOW),
                    "{v} " + pas + f" depuis le plus haut {haut} "
                    "barres (maximum {s})"),
        "3a": paire(_f(row.get("macd_hist")), _f(prev.get("macd_hist")),
                    "histogramme MACD {v} contre {s} " + veille),
        "3b": paire(c, _f(row.get("ema20")),
                    "clôture {v} pour une EMA20 à {s}"),
        "3c": paire(c, _f(prev.get("high")),
                    "clôture {v} pour un plus haut " + deveille
                    + " à {s}"),
        "4a": paire(_f(row.get("rvol")), R.RVOL_MIN,
                    "volume relatif {v} (il faut au moins {s})"),
    }
    for k, v in out.items():
        dec = 0 if k == "2d" else 2
        v["texte"] = v["texte"].format(v=n(v["valeur"], dec),
                                       s=n(v["seuil"], dec))
    return out


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


def niveau(n_ko: int, n_na: int, n_out: int, vetos, refuse: bool) -> str:
    """L'echelle, appliquee dans l'ordre de NIVEAUX. Rien d'autre.

    Ecrite une fois, ici, et ne peut pas etre reglee titre par titre :
    c'est ce qui la distingue d'un avis.
    """
    if refuse:
        return "refus"
    if n_na > 0:
        return "na"
    if vetos:
        return "hors"
    if n_out >= 2:
        return "sortie"
    if n_ko == 0:
        return "complet"
    if n_ko <= 2:
        return "proche"
    return "loin"


def lire_unite(d, bench, sig, sorties, etats, refuse: bool = False,
               cle: str = "jour", periodes: dict | None = None,
               motifs=()) -> dict:
    """L'interet sur UNE unite de temps, a partir de ce qui est deja calcule.

    `etats` vient de `chart._bloc_etats` : ok / ko / na. On ne recalcule
    pas les blocs — on les compte et on va chercher les deux nombres que
    chaque bloc manquant a compares.
    """
    n_ok = sum(1 for e in etats if e["etat"] == "ok")
    n_ko = sum(1 for e in etats if e["etat"] == "ko")
    n_na = sum(1 for e in etats if e["etat"] == "na")
    n_out = sum(1 for v in sorties.values() if v)
    vetos = list(sig.vetos) if sig is not None else []
    # « RESULTATS INCONNUS » n'est pas un defaut du titre : c'est un
    # defaut de notre calendrier. Il figure en vigilance, pas en veto,
    # sinon tout titre sans couverture Alpha Vantage serait HORS
    # CRITERES en permanence.
    vigilance = [v for v in vetos if v.startswith("RÉSULTATS INCONNUS")]
    vetos = [v for v in vetos if not v.startswith("RÉSULTATS INCONNUS")]

    try:
        det = mesures(d, bench, cle=cle, periodes=periodes)
    except Exception:
        det = {}

    manquants = []
    for e in etats:
        if e["etat"] != "ko":
            continue
        code = next((c for c, lab in LABELS.items() if lab == e["nom"]), None)
        info = det.get(code, {})
        manquants.append({"code": code or "?", "nom": e["nom"],
                          "texte": info.get("texte", "")})

    cle = niveau(n_ko, n_na, n_out, vetos, refuse)
    # « Le controle qualite refuse cette serie » sans dire laquelle des
    # anomalies a bloque n'apprend rien et ne se verifie pas. Le motif
    # exact remonte jusqu'a la carte.
    motifs = list(motifs)
    return {
        "niveau": cle, "titre": TITRES[cle], "motif": MOTIFS[cle],
        "refus_motifs": motifs,
        "ok": n_ok, "ko": n_ko, "na": n_na, "total": len(etats),
        "compte": f"{n_ok} / {len(etats)}",
        "manquants": manquants,
        "vetos": vetos, "vigilance": vigilance,
        "sorties_actives": n_out,
    }


def accord(unites: dict) -> dict:
    """Le meme decompte sur toutes les unites de temps, aligne.

    Aucune moyenne, aucune ponderation : une ligne par unite. Un titre
    a 13/13 en journalier et 6/13 en mensuel se voit d'un coup d'oeil,
    et personne n'a decide a la place du lecteur laquelle compte.
    """
    lignes, pleines, mesurables = [], 0, 0
    for cle, lab, bloc in unites:
        if not bloc or not bloc.get("interet"):
            lignes.append({"cle": cle, "label": lab, "compte": "—",
                           "niveau": "vide", "ok": 0, "total": 0,
                           "titre": "PAS ASSEZ D'HISTORIQUE"})
            continue
        it = bloc["interet"]
        lignes.append({"cle": cle, "label": lab, "compte": it["compte"],
                       "niveau": it["niveau"], "titre": it["titre"],
                       "ok": it["ok"], "total": it["total"]})
        if it["niveau"] != "na":
            mesurables += 1
            if it["ko"] == 0:
                pleines += 1
    return {"lignes": lignes, "pleines": pleines, "mesurables": mesurables,
            "phrase": (f"{pleines} unité(s) de temps sur {mesurables} "
                       f"mesurable(s) ont leurs 13 blocs")
            if mesurables else "aucune unité de temps mesurable"}


def historique(perf: dict | None) -> dict | None:
    """Le signal sur CE titre. Avec Wilson, jamais un taux nu."""
    if not perf or not perf.get("n"):
        return None
    g = perf.get("gagnants")
    if g is None:
        g = round(perf.get("taux", 0) * perf["n"] / 100)
    b, _p, h = wilson(int(g), int(perf["n"]))
    return {"n": perf["n"], "gagnants": int(g),
            "bas": round(b), "haut": round(h),
            "evR": perf.get("evR"),
            "phrase": (f"{g} trades gagnants sur {perf['n']} — "
                       f"intervalle de confiance {b:.0f} à {h:.0f} %"),
            "reserve": ("Moins de 30 trades : l'intervalle est trop large "
                        "pour trancher." if perf["n"] < 30 else "")}


def carte(unite: dict, acc: dict | None = None, hist: dict | None = None,
          ticker: str = "") -> dict:
    """Le bloc pret a afficher, a chaque consultation d'un titre."""
    return {
        "version": VERSION, "ticker": ticker,
        "horodatage": dt.datetime.now().isoformat(timespec="seconds"),
        "unite": unite, "accord": acc, "historique": hist,
        "pas_un_avis": PAS_UN_AVIS, "rappel": RAPPEL_PHASE0,
    }


# --------------------------------------------------------------------
# Ligne de commande
# --------------------------------------------------------------------

def _ligne(car: dict) -> str:
    u = car["unite"]
    L = [f"\n  {car['ticker']}  —  INTÉRÊT",
         f"  {u['titre']}   ({u['compte']} blocs)",
         f"  {u['motif']}", ""]
    if u["manquants"]:
        L.append("  IL MANQUE :")
        for m in u["manquants"]:
            L.append(f"    · {m['nom']}")
            if m["texte"]:
                L.append(f"        {m['texte']}")
        L.append("")
    if u.get("refus_motifs"):
        L.append("  POURQUOI LA SÉRIE EST REFUSÉE :")
        L += [f"    · {v}" for v in u["refus_motifs"]] + [""]
    if u["vetos"]:
        L.append("  VETOS DE LA SPÉCIFICATION :")
        L += [f"    · {v}" for v in u["vetos"]] + [""]
    if u["vigilance"]:
        L.append("  À VÉRIFIER À LA MAIN :")
        L += [f"    · {v}" for v in u["vigilance"]] + [""]
    if car.get("accord"):
        L.append("  LES UNITÉS DE TEMPS :")
        for g in car["accord"]["lignes"]:
            L.append(f"    {g['label']:<14} {g['compte']:>8}   {g['titre']}")
        L += [f"    -> {car['accord']['phrase']}", ""]
    if car.get("historique"):
        h = car["historique"]
        L.append("  CE SIGNAL SUR CE TITRE :")
        L.append(f"    {h['phrase']}")
        if h["reserve"]:
            L.append(f"    {h['reserve']}")
        L.append("")
    L += ["  " + car["rappel"], "  " + car["pas_un_avis"], ""]
    return "\n".join(L)


def rapport(ticker: str, marche: str = "us") -> dict:
    from . import cache as ch
    from . import chart as gr
    from . import qualite as ql
    from .indicators import enrich

    bench_tk = "SPY" if marche == "us" else "^STOXX"
    brut = ch.charge(ticker, annees=20)
    bench_brut = ch.charge(bench_tk, annees=20)
    d = enrich(brut, bench_close=bench_brut["close"])
    b = enrich(bench_brut)

    rap = ql.controle(d, bench=b, ticker=ticker)
    refuse = not getattr(rap, "utilisable", True)

    ok = bool(R.market_regime_ok(b))
    sig = R.evaluate(d, ticker, ok, days_to_earnings=999)
    sorties = R.evaluate_exit(d, ok)
    etats = gr._bloc_etats(d, sig)
    u = lire_unite(d, b, sig, sorties, etats, refuse=refuse,
                   motifs=rap.bloquants)

    unites = []
    for cle, lab, regle, nb in gr.UNITES:
        try:
            deja = (d, b) if regle is None else None
            bloc = gr._analyse(brut, bench_brut, regle, nb, ticker, 8000.0,
                               "", pre=deja, cle=cle)
        except Exception:
            bloc = None
        unites.append((cle, lab, bloc))
    return carte(u, accord(unites), historique(gr._perf_signal(d, ticker, b)),
                 ticker)


def main() -> None:
    p = argparse.ArgumentParser(description="L'intérêt d'un titre, en faits")
    p.add_argument("ticker")
    p.add_argument("--marche", default="us", choices=("us", "europe"))
    a = p.parse_args()
    print(_ligne(rapport(a.ticker.upper(), a.marche)))


if __name__ == "__main__":
    main()
