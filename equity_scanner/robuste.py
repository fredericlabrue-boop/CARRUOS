"""Walk-forward, Monte Carlo et bootstrap. Chantier n°4 du registre.

CE QUE CES TROIS TESTS REPONDENT, ET CE QU'ILS NE REPONDENT PAS

La Phase 0 rend un chiffre par critere : 240 trades, PF 1,22, z 2,4. Ces
chiffres sont des POINTS. Ils ne disent rien de leur propre fragilite.
Trois questions restent ouvertes, et ce sont celles qui coutent de
l'argent quand on ne se les pose pas.

  1. L'avantage tient-il sur TOUTE la periode, ou vient-il d'un trimestre ?
     -> walk_forward(). On decoupe le hors echantillon en fenetres
     consecutives et on regarde chacune. Un systeme dont tout le resultat
     tient dans deux mois de 2023 n'a pas un avantage : il a eu de la
     chance une fois.

     Precision honnete : il n'y a ici AUCUNE reoptimisation, puisque les
     parametres sont geles. Ce n'est donc pas le walk-forward classique
     (calibrer, avancer, recalibrer). C'est un test de STABILITE, et
     c'est le seul qui ait un sens quand rien n'est calibre.

  2. Le resultat dependait-il de l'ORDRE dans lequel les trades sont
     tombes ? -> monte_carlo(). Les memes trades, melanges 5 000 fois.
     L'esperance ne bouge pas — c'est la meme somme — mais le drawdown,
     lui, bouge enormement. Le drawdown observe est UN tirage parmi
     d'autres ; ce qui compte, c'est celui qu'on aurait pu vivre.

  3. Les mesures sont-elles precises, ou juste calculees ? -> bootstrap().
     Sur 40 trades, un profit factor de 1,25 est compatible avec 0,8
     comme avec 1,9. Afficher 1,25 tout seul laisse croire a une
     precision qui n'existe pas.

Aucun de ces tests ne peut sauver un systeme. Ils ne peuvent que le tuer
plus tot, ce qui est exactement leur utilite.

    py -m equity_scanner.robuste --csv phase0-sp500.csv
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TIRAGES_MC = 5000
TIRAGES_BOOT = 2000
RISQUE = 0.01
RUINE = 0.30              # perte du capital consideree comme rupture


# ---------------------------------------------------------------------
# Outils communs
# ---------------------------------------------------------------------
def wilson(succes: int, n: int, z: float = 1.96) -> tuple:
    """Intervalle de confiance de Wilson sur une proportion.

    Rend (bas, centre, haut) en pourcentage. Avec 13 trades, un taux
    observe de 46 % ne veut pas dire 46 % de chances : il veut dire
    quelque part entre 23 % et 71 %. C'est cette largeur qu'il faut
    montrer, jamais le point central tout seul.
    """
    if not n:
        return (0.0, 0.0, 100.0)
    p = succes / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    e = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - e) * 100, max(0.0, min(1.0, c)) * 100,
            min(1.0, c + e) * 100)


def profit_factor(rs) -> float:
    g = sum(r for r in rs if r > 0)
    p = -sum(r for r in rs if r < 0)
    if p == 0:
        return float("inf") if g > 0 else 0.0
    return g / p


def _courbe(rs, risque: float = RISQUE, capital: float = 1.0) -> np.ndarray:
    """Capital compose, un point par trade, dans l'ordre donne."""
    return capital * np.cumprod(1.0 + np.asarray(rs, dtype=float) * risque)


def _drawdown(courbe: np.ndarray, capital: float = 1.0) -> float:
    plein = np.concatenate(([capital], courbe))
    pic = np.maximum.accumulate(plein)
    return float(np.max((pic - plein) / pic))


# ---------------------------------------------------------------------
# 1. Stabilite dans le temps
# ---------------------------------------------------------------------
def walk_forward(trades, mois: int = 6) -> list[dict]:
    """Decoupe les trades en fenetres consecutives et mesure chacune.

    La fenetre est datee sur l'ENTREE du trade : c'est la date a laquelle
    la decision a ete prise, donc celle qui appartient a la periode.
    """
    if not trades:
        return []
    lignes = sorted(((pd.Timestamp(t.entree_d), t) for t in trades),
                    key=lambda x: x[0])
    debut, fin = lignes[0][0], lignes[-1][0]
    bornes, cur = [], debut
    while cur <= fin:
        suivant = cur + pd.DateOffset(months=mois)
        bornes.append((cur, suivant))
        cur = suivant

    out = []
    for a, b in bornes:
        lot = [t for d, t in lignes if a <= d < b]
        if not lot:
            out.append({"debut": str(a.date()), "fin": str((b - pd.Timedelta(days=1)).date()),
                        "n": 0, "pf": 0.0, "ev": 0.0, "gagnants": 0,
                        "dd": 0.0, "positive": False})
            continue
        rs = [t.R for t in lot]
        courbe = _courbe(rs)
        out.append({
            "debut": str(a.date()),
            "fin": str((b - pd.Timedelta(days=1)).date()),
            "n": len(rs), "pf": profit_factor(rs),
            "ev": float(np.mean(rs)),
            "gagnants": int(sum(1 for r in rs if r > 0)),
            "dd": _drawdown(courbe),
            "positive": float(np.sum(rs)) > 0,
        })
    return out


def verdict_walk_forward(fenetres: list[dict]) -> dict:
    """Combien de fenetres sont positives, et le resultat tient-il a une
    seule d'entre elles ?"""
    pleines = [f for f in fenetres if f["n"] > 0]
    if not pleines:
        return {"fenetres": 0, "positives": 0, "concentration": 0.0,
                "sans_la_meilleure": 0.0, "stable": False}
    sommes = np.array([f["ev"] * f["n"] for f in pleines])
    total = float(sommes.sum())
    meilleure = float(sommes.max())
    # Part du resultat total apportee par la meilleure fenetre. Au-dela de
    # 100 %, tout le reste perd de l'argent : le systeme n'a gagne qu'une
    # fois, par accident de calendrier.
    concentration = (meilleure / total) if total > 0 else float("inf")
    return {
        "fenetres": len(pleines),
        "positives": int(sum(1 for f in pleines if f["positive"])),
        "concentration": concentration,
        "sans_la_meilleure": total - meilleure,
        "stable": (total > 0 and (total - meilleure) > 0
                   and sum(1 for f in pleines if f["positive"]) >= 0.6 * len(pleines)),
    }


# ---------------------------------------------------------------------
# 2. Monte Carlo sur l'ordre des trades
# ---------------------------------------------------------------------
def monte_carlo(trades, tirages: int = TIRAGES_MC, risque: float = RISQUE,
                graine: int = 7, ruine: float = RUINE) -> dict:
    """Les memes trades, dans un ordre different, 5 000 fois.

    Ce qui change n'est pas le resultat final — la somme est la meme, au
    detail de composition pres — mais le CHEMIN. Le drawdown observe une
    fois n'est qu'un tirage : celui qu'on aurait pu vivre est ailleurs
    dans cette distribution.
    """
    rs = np.array([t.R for t in trades], dtype=float)
    if len(rs) < 10:
        return {"n": len(rs), "assez": False}
    rng = np.random.default_rng(graine)
    dds = np.empty(tirages)
    fins = np.empty(tirages)
    ruines = 0
    for k in range(tirages):
        ordre = rng.permutation(rs)
        courbe = np.cumprod(1.0 + ordre * risque)
        plein = np.concatenate(([1.0], courbe))
        pic = np.maximum.accumulate(plein)
        dd = float(np.max((pic - plein) / pic))
        dds[k] = dd
        fins[k] = courbe[-1]
        if dd >= ruine:
            ruines += 1
    reel = _drawdown(_courbe(rs, risque))
    return {
        "n": len(rs), "assez": True, "tirages": tirages,
        "dd_observe": reel,
        "dd_median": float(np.median(dds)),
        "dd_p90": float(np.percentile(dds, 90)),
        "dd_p95": float(np.percentile(dds, 95)),
        "dd_pire": float(dds.max()),
        "fin_median": float(np.median(fins)),
        "fin_p05": float(np.percentile(fins, 5)),
        "fin_p95": float(np.percentile(fins, 95)),
        "part_perdante": float((fins < 1.0).mean()),
        "risque_ruine": ruines / tirages,
        "seuil_ruine": ruine,
    }


# ---------------------------------------------------------------------
# 3. Bootstrap par blocs
# ---------------------------------------------------------------------
def bootstrap(trades, tirages: int = TIRAGES_BOOT, bloc: int = 5,
              graine: int = 7) -> dict:
    """Intervalle de confiance du profit factor et de l'esperance.

    Le tirage se fait par BLOCS de trades consecutifs, pas trade par
    trade. Les resultats successifs d'un systeme de tendance ne sont pas
    independants : les bonnes periodes viennent groupees. Tirer un a un
    casserait cette structure et donnerait un intervalle trop etroit,
    donc trop rassurant.
    """
    rs = np.array([t.R for t in trades], dtype=float)
    n = len(rs)
    if n < 20:
        return {"n": n, "assez": False}
    rng = np.random.default_rng(graine)
    bloc = max(1, min(bloc, n // 4))
    n_blocs = int(np.ceil(n / bloc))
    pfs, evs = np.empty(tirages), np.empty(tirages)
    for k in range(tirages):
        debuts = rng.integers(0, n - bloc + 1, n_blocs)
        ech = np.concatenate([rs[i:i + bloc] for i in debuts])[:n]
        pfs[k] = profit_factor(ech)
        evs[k] = ech.mean()
    finis = pfs[np.isfinite(pfs)]
    gagnants = int((rs > 0).sum())
    bas, centre, haut = wilson(gagnants, n)
    return {
        "n": n, "assez": True, "bloc": bloc, "tirages": tirages,
        "pf_observe": profit_factor(rs),
        "pf_bas": float(np.percentile(finis, 2.5)) if len(finis) else 0.0,
        "pf_haut": float(np.percentile(finis, 97.5)) if len(finis) else 0.0,
        "ev_observe": float(rs.mean()),
        "ev_bas": float(np.percentile(evs, 2.5)),
        "ev_haut": float(np.percentile(evs, 97.5)),
        "part_pf_sous_1": float((pfs <= 1.0).mean()),
        "gagnants": gagnants,
        "taux_bas": bas, "taux_centre": centre, "taux_haut": haut,
    }


# ---------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------
def rapport(trades, journal=print, mois: int = 6) -> dict:
    """Les trois tests, affiches. Rend le detail pour usage programmatique."""
    if not trades:
        journal("\n  Aucun trade : rien a eprouver.")
        return {}

    fen = walk_forward(trades, mois)
    v = verdict_walk_forward(fen)
    mc = monte_carlo(trades)
    bs = bootstrap(trades)

    journal("\n  " + "=" * 62)
    journal(f"  EPREUVES DE ROBUSTESSE — {len(trades)} trades")
    journal("  " + "=" * 62)

    journal(f"\n  1. STABILITE DANS LE TEMPS  (fenetres de {mois} mois)")
    journal(f"     {'periode':<26}{'trades':>8}{'PF':>7}{'EV/trade':>11}{'DD':>8}")
    for f in fen:
        if f["n"] == 0:
            journal(f"     {f['debut']} → {f['fin']}{'0':>8}"
                    f"{'-':>7}{'-':>11}{'-':>8}")
            continue
        pf = "inf" if f["pf"] == float("inf") else f"{f['pf']:.2f}"
        journal(f"     {f['debut']} → {f['fin']}{f['n']:>8}{pf:>7}"
                f"{f['ev']:>+11.3f}{f['dd']:>7.1%}")
    if v["fenetres"]:
        journal(f"     {v['positives']}/{v['fenetres']} fenetres positives.")
        if np.isfinite(v["concentration"]):
            journal(f"     La meilleure fenetre apporte "
                    f"{v['concentration']:.0%} du resultat total.")
        journal(f"     Sans elle, il reste {v['sans_la_meilleure']:+.1f} R.")
        journal("     " + ("Resultat reparti sur la periode."
                           if v["stable"] else
                           "ATTENTION : le resultat tient a trop peu de "
                           "fenetres. Un avantage qui n'apparait qu'une fois "
                           "n'est pas distinguable d'un coup de chance."))

    journal(f"\n  2. ORDRE DES TRADES  ({mc.get('tirages', 0)} melanges)")
    if not mc.get("assez"):
        journal(f"     {mc['n']} trades : trop peu pour melanger quoi que ce soit.")
    else:
        journal(f"     drawdown observe une fois   {mc['dd_observe']:>8.1%}")
        journal(f"     drawdown median             {mc['dd_median']:>8.1%}")
        journal(f"     drawdown au 90e centile     {mc['dd_p90']:>8.1%}")
        journal(f"     drawdown au 95e centile     {mc['dd_p95']:>8.1%}")
        journal(f"     pire tirage                 {mc['dd_pire']:>8.1%}")
        journal(f"     tirages perdants            {mc['part_perdante']:>8.1%}")
        libelle = f"risque de perdre {mc['seuil_ruine']:.0%} du capital"
        journal(f"     {libelle:<28}{mc['risque_ruine']:>8.1%}")
        if mc["dd_p95"] > 0.20:
            journal("     Le critere « drawdown < 20 % » de la Phase 0 porte "
                    "sur UN tirage.")
            journal(f"     Dans 5 % des ordres possibles, il depasse "
                    f"{mc['dd_p95']:.0%}.")

    journal(f"\n  3. PRECISION DES MESURES  (bootstrap par blocs de "
            f"{bs.get('bloc', '-')})")
    if not bs.get("assez"):
        journal(f"     {bs['n']} trades : en dessous de 20, un intervalle de "
                f"confiance n'apprend rien.")
    else:
        pf = "inf" if bs["pf_observe"] == float("inf") else f"{bs['pf_observe']:.2f}"
        journal(f"     profit factor    {pf:>6}   "
                f"intervalle 95 % : {bs['pf_bas']:.2f} a {bs['pf_haut']:.2f}")
        journal(f"     esperance      {bs['ev_observe']:>+7.3f} R  "
                f"intervalle 95 % : {bs['ev_bas']:+.3f} a {bs['ev_haut']:+.3f}")
        journal(f"     taux de reussite  {bs['gagnants']}/{bs['n']}   "
                f"intervalle 95 % : {bs['taux_bas']:.0f} % a "
                f"{bs['taux_haut']:.0f} %")
        journal(f"     part des tirages ou le profit factor tombe sous 1 : "
                f"{bs['part_pf_sous_1']:.1%}")
        if bs["ev_bas"] <= 0:
            journal("     L'intervalle de l'esperance contient zero : sur cet "
                    "echantillon,")
            journal("     l'avantage n'est pas distinguable de l'absence "
                    "d'avantage.")
    journal("\n  " + "=" * 62 + "\n")
    return {"walk_forward": fen, "verdict": v, "monte_carlo": mc,
            "bootstrap": bs}


# ---------------------------------------------------------------------
def depuis_csv(chemin: str) -> list:
    """Relit les trades d'un CSV produit par phase0 ou pead.

    Permet d'eprouver un resultat deja calcule sans relancer trente
    minutes de backtest.
    """
    from .backtest import Trade

    df = pd.read_csv(chemin)
    out = []
    for _, r in df.iterrows():
        entree = float(r.get("prix_entree", 100.0))
        stop = float(r.get("stop", entree * 0.95))
        R = float(r.get("R", 0.0))
        risque = max(1e-9, entree - stop)
        out.append(Trade(
            ticker=str(r.get("ticker", "?")),
            entree_d=pd.Timestamp(r.get("entree")),
            sortie_d=pd.Timestamp(r.get("sortie")),
            entree=entree,
            # On reconstruit le prix de sortie a partir de R, pour que la
            # propriete R du Trade rende exactement la valeur du CSV.
            sortie=entree + R * risque + entree * 0.0010,
            stop0=stop, atr=float(r.get("atr", risque)),
            barres=int(r.get("barres", 1)), motif=str(r.get("motif", ""))))
    return out


def main() -> None:
    import argparse
    a = argparse.ArgumentParser(description="Epreuves de robustesse")
    a.add_argument("--csv", required=True,
                   help="trades produits par phase0 --csv ou pead --csv")
    a.add_argument("--mois", type=int, default=6,
                   help="largeur des fenetres de stabilite")
    o = a.parse_args()
    trades = depuis_csv(o.csv)
    print(f"\n  {len(trades)} trades relus depuis {o.csv}")
    rapport(trades, mois=o.mois)


if __name__ == "__main__":
    main()
