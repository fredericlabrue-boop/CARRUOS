"""Calibration du critere 4 sur des cours PUREMENT ALEATOIRES.

POURQUOI CE MODULE EXISTE

Le protocole de validation appelle le critere 4 — le score z contre des
entrees au hasard — « le seul qui compte vraiment », et il s'appuie sur
une mesure precise :

    « Mesure faite le 12 septembre sur des cours purement aleatoires :
      profit factor 1,48 · esperance positive · score z +0,93 <- le seul
      qui rejette. »

Cette phrase est le fondement chiffre de tout le dispositif. Elle a ete
obtenue une fois, a la main, avec une certaine construction du temoin.
Elle n'etait reproductible nulle part.

Ce module la rend reproductible. Il fabrique des univers de cours
strictement aleatoires — derive nulle, aucune structure, RIEN a trouver —
rejoue la Phase 0 dessus, et rend la distribution des z obtenus. Sur du
bruit, un temoin honnete doit rendre un z centre sur zero et ne franchir
le seuil de 2 qu'exceptionnellement.

CE QU'IL FAUT SAVOIR AVANT DE LIRE UN RESULTAT D'ICI

Deux temoins coexistent dans `phase0` : celui a duree appariee, avec
lequel le point de calibration a ete etabli, et celui a memes regles de
sortie, que decrit mot pour mot l'etape 6 du protocole.

Ils ne rendent pas le meme z sur les memes trades — les ecarts observes
vont de quelques dixiemes a pres de deux points. Lequel est le mieux
centre sur du bruit n'est PAS tranche : sur une dizaine d'univers, la
reponse change d'une serie a l'autre, parce que l'ecart-type du z a
cette taille d'echantillon est de l'ordre de 1 a 2. Un chiffre tire de
douze univers ne vaut rien ; c'est precisement ce que ce module permet
de constater au lieu de le deviner.

Il faut donc des univers assez gros pour approcher les 200 trades
qu'exige le critere 1, et beaucoup de repetitions. En attendant,
`phase0.z_retenu()` retient le PLUS DEFAVORABLE des deux : c'est la
seule option qui ne peut pas etre jouee dans le sens du resultat.

CE QUE CE MODULE NE FAIT PAS

Il ne choisit pas le temoin. Il mesure, il affiche, et il laisse la
decision a une specification ecrite avant le prochain test. Choisir un
temoin apres avoir vu lequel donne un meilleur z serait exactement la
peche que le protocole interdit.

    py -m equity_scanner.calibration
    py -m equity_scanner.calibration --univers 20 --titres 70
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

SEANCES = 2600
DEBUT = "2014-01-02"


def _graine(texte: str) -> int:
    """Graine stable d'un ticker. `hash()` varie d'un lancement a l'autre
    en Python 3 : s'en servir rendrait la calibration irreproductible."""
    return sum((i + 1) * ord(c) for i, c in enumerate(texte)) % (2 ** 31)


def univers_bruit(n_titres: int, rep: int, seances: int = SEANCES):
    """Fabrique un generateur de cours purement aleatoires.

    Derive NULLE : pas de tendance haussiere a capter, pas de retour a la
    moyenne a exploiter. Un systeme qui « gagne » la-dessus ne gagne rien.
    """
    idx = pd.bdate_range(DEBUT, periods=seances)

    def cours(ticker: str, years: int = 20, **_):
        r = np.random.default_rng(_graine(f"{rep}|{ticker}"))
        c = np.empty(seances)
        c[0] = 100.0
        pas = r.normal(0.0, 0.013, seances - 1)
        for k in range(1, seances):
            c[k] = c[k - 1] * (1.0 + pas[k - 1])
        o = np.concatenate([[c[0]], c[:-1]])
        return pd.DataFrame({
            "open": o,
            "high": np.maximum(o, c) * 1.006,
            "low": np.minimum(o, c) * 0.994,
            "close": c,
            "volume": r.uniform(4e6, 9e6, seances)}, index=idx)

    tickers = [f"Z{rep:02d}N{i:02d}" for i in range(n_titres)]
    return cours, tickers, f"Z{rep:02d}BENCH"


def mesure(n_univers: int = 12, n_titres: int = 70, mini: int = 20,
           journal=print) -> dict:
    """Rejoue la Phase 0 sur `n_univers` univers de bruit independants."""
    from . import backtest as bt
    from . import data as dl
    from . import phase0 as ph

    vrai_loader = dl.load_yf
    regles, durees, effectifs = [], [], []
    muet = lambda *a, **k: None
    try:
        for rep in range(n_univers):
            cours, tickers, bench_tk = univers_bruit(n_titres, rep)
            dl.load_yf = cours
            bench, series, _ = ph.charge_univers(
                tickers, bench_tk=bench_tk, journal=muet)
            trades = []
            for tk, d in series.items():
                trades += bt.trades_ticker(d, tk, bench,
                                           ph.OOS_DEBUT, ph.OOS_FIN)
            if len(trades) < mini:
                journal(f"    univers {rep:2d} : {len(trades):4d} trades "
                        f"— trop peu, ignore")
                continue
            _r, _m, zr = ph.z_contre_hasard(trades, series, bench=bench,
                                            debut=ph.OOS_DEBUT,
                                            fin=ph.OOS_FIN)
            zd = ph.z_duree_appariee(trades, series, debut=ph.OOS_DEBUT,
                                     fin=ph.OOS_FIN)
            regles.append(zr)
            durees.append(zd)
            effectifs.append(len(trades))
            journal(f"    univers {rep:2d} : {len(trades):4d} trades   "
                    f"z regles {zr:+.2f}   z duree {zd:+.2f}")
    finally:
        dl.load_yf = vrai_loader

    def stat(v):
        a = np.array(v, dtype=float)
        if len(a) < 2:
            return {"n": len(a), "moyenne": float(a.mean()) if len(a) else 0.0,
                    "ecart_type": 0.0, "min": 0.0, "max": 0.0, "faux": 0}
        return {"n": len(a), "moyenne": float(a.mean()),
                "ecart_type": float(a.std(ddof=1)),
                "min": float(a.min()), "max": float(a.max()),
                "faux": int((a >= 2.0).sum())}

    return {"regles": stat(regles), "duree": stat(durees),
            "trades": effectifs}


def rapport(n_univers: int = 12, n_titres: int = 70, journal=print) -> dict:
    journal("\n  CALIBRATION DU CRITERE 4 SUR DU BRUIT PUR")
    journal(f"  {n_univers} univers de {n_titres} titres, derive NULLE.")
    journal("  Il n'y a rien a trouver : un temoin honnete rend un z")
    journal("  centre sur zero et ne franchit 2 qu'exceptionnellement.\n")

    r = mesure(n_univers, n_titres, journal=journal)
    if not r["trades"]:
        journal("\n  Aucun univers n'a produit assez de trades. "
                "Augmente --titres.")
        return r

    journal(f"\n  {'temoin':<34}{'moyenne':>9}{'ec-type':>9}"
            f"{'min':>8}{'max':>8}{'z>=2':>8}")
    for nom, cle in (("duree appariee (l'ancien)", "duree"),
                     ("memes regles de sortie (protocole)", "regles")):
        v = r[cle]
        journal(f"  {nom:<34}{v['moyenne']:>+9.2f}{v['ecart_type']:>9.2f}"
                f"{v['min']:>+8.2f}{v['max']:>+8.2f}"
                f"{v['faux']:>5} /{v['n']:<3}")

    journal(f"\n  trades par univers : "
            f"{min(r['trades'])} a {max(r['trades'])} "
            f"(mediane {int(np.median(r['trades']))})")
    journal("\n  COMMENT LIRE CE TABLEAU")
    journal("  Une moyenne loin de zero veut dire que le temoin est biaise :")
    journal("  il donne un avantage au systeme sans que le systeme n'ait")
    journal("  rien demontre. La colonne z>=2 compte les FAUX POSITIFS —")
    journal("  des systemes qui passeraient le critere 4 sur du bruit.")
    journal("")
    journal("  Le critere 4 retient le plus defavorable des deux temoins")
    journal("  (phase0.z_retenu). Changer cela demande une nouvelle")
    journal("  specification, ecrite AVANT le prochain test.")
    journal("")
    journal("  RESERVE : le protocole exige au moins 200 trades. Tant que")
    journal("  les univers ci-dessus n'y arrivent pas, le z reste tres")
    journal("  bruyant et ces moyennes sont indicatives, pas definitives.")
    journal("")
    return r


def main() -> None:
    a = argparse.ArgumentParser(
        description="Calibration du critere 4 sur des cours aleatoires")
    a.add_argument("--univers", type=int, default=12)
    a.add_argument("--titres", type=int, default=70)
    o = a.parse_args()
    rapport(o.univers, o.titres)


if __name__ == "__main__":
    main()
