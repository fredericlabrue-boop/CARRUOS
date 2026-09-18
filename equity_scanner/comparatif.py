"""Comparatif : le systeme contre l'achat-conservation, net d'impot.

C'est le seul chiffre qui decide. Un systeme peut passer les cinq
criteres de la Phase 0 et rester un mauvais choix, parce qu'il n'a
jamais ete compare a ce que Frederic fait deja : acheter SMH et ne rien
toucher.

Deux frictions separent les deux approches :

  1. Le PFU. Une rotation realise ses plus-values chaque annee, donc
     paie 30 % chaque annee. Le buy & hold ne paie qu'a la sortie, et
     l'impot differe continue de travailler entre-temps.
  2. Les frais de courtage, environ 1 % par an sur une rotation active.

Consequence chiffree, calculee ici et non estimee. A 15 % brut par an :

    horizon    PFU seul    PFU + 1 % de frais
    5 ans       16,15 %          17,14 %
    10 ans      17,30 %          18,28 %

Les deux premiers chiffres etaient ceux annonces au depart : ils ne
comptaient que l'impot. La colonne de droite est la vraie barre, frais
compris. Elle monte avec l'horizon, parce que l'impot que le buy & hold
ne paie pas encore continue de travailler.

    py -m equity_scanner.comparatif --ref SMH
"""

from __future__ import annotations

import argparse

import pandas as pd

PFU = 0.30
FRAIS_ROTATION = 0.01      # aller-retour moyen, en part du capital par an


def _annualise(debut: float, fin: float, annees: float) -> float:
    if debut <= 0 or fin <= 0 or annees <= 0:
        return 0.0
    return (fin / debut) ** (1 / annees) - 1


def buy_and_hold(close: pd.Series, capital: float = 10_000.0) -> dict:
    """Achat au premier jour, vente au dernier. L'impot ne frappe qu'une
    fois, a la sortie, sur la plus-value totale."""
    c = close.dropna()
    if len(c) < 2:
        return {}
    annees = (c.index[-1] - c.index[0]).days / 365.25
    brut = capital * float(c.iloc[-1] / c.iloc[0])
    pv = max(0.0, brut - capital)
    net = brut - pv * PFU
    courbe = capital * (c / c.iloc[0])
    pic = courbe.cummax()
    return {"brut": brut, "net": net, "annees": annees,
            "tri_brut": _annualise(capital, brut, annees),
            "tri_net": _annualise(capital, net, annees),
            "dd": abs(float(((courbe - pic) / pic).min())),
            "courbe": courbe}


def systeme_net(courbe: pd.Series, capital: float = 10_000.0) -> dict:
    """Applique au systeme ce que le backtest ignore : le PFU realise
    chaque annee civile, et les frais de rotation.

    L'impot est preleve sur la performance de l'annee, uniquement si
    elle est positive. Une annee perdante ne rend rien : c'est le
    traitement le plus defavorable, donc le plus honnete a utiliser ici
    (le report de moins-values existe, mais il ne se transporte pas
    d'un support a l'autre et on ne va pas s'en servir pour embellir un
    resultat).
    """
    c = courbe.dropna()
    if len(c) < 2:
        return {}
    annees = (c.index[-1] - c.index[0]).days / 365.25

    # La courbe du backtest commence au premier point APRES le depart : son
    # premier element porte deja le resultat du premier trade. Prendre
    # bloc.iloc[0] comme base de l'annee 1 effaçait donc ce trade du calcul
    # d'impot, alors que `tri_brut` ci-dessous, lui, le comptait. Deux
    # chiffres du meme tableau se contredisaient. On prefixe le capital de
    # depart pour que les deux lisent la meme histoire.
    if float(c.iloc[0]) != float(capital):
        veille = c.index[0] - pd.Timedelta(days=1)
        c = pd.concat([pd.Series([float(capital)],
                                 index=pd.DatetimeIndex([veille])), c])

    cap = capital
    detail = []
    for an, bloc in c.groupby(c.index.year):
        debut = cap
        brut_fin = debut * float(bloc.iloc[-1] / bloc.iloc[0])
        frais = debut * FRAIS_ROTATION
        gain = brut_fin - debut - frais
        impot = max(0.0, gain) * PFU
        cap = brut_fin - frais - impot
        detail.append({"annee": int(an), "debut": debut, "brut": brut_fin,
                       "frais": frais, "impot": impot, "fin": cap})
    pic = c.cummax()
    return {"net": cap, "annees": annees,
            "tri_brut": _annualise(capital, float(c.iloc[-1]), annees),
            "tri_net": _annualise(capital, cap, annees),
            "dd": abs(float(((c - pic) / pic).min())),
            "detail": detail}


def barre_a_franchir(tri_ref_brut: float, annees: float) -> float:
    """Rendement brut que la rotation doit produire pour EGALER le buy &
    hold, une fois le PFU annuel et les frais pris en compte.

    On resout numeriquement : on cherche le taux brut qui, ampute chaque
    annee de 30 % du gain et de 1 % de frais, rend la meme somme nette
    qu'un buy & hold impose une seule fois a la fin.
    """
    cible = (1 + tri_ref_brut) ** annees
    cible_net = 1 + (cible - 1) * (1 - PFU)
    lo, hi = tri_ref_brut, tri_ref_brut + 0.60
    # Au moins une annee de rotation, sinon la boucle ne tourne pas et la
    # bisection converge vers sa borne haute sans rien avoir calcule.
    n_annees = max(1, int(round(annees)))
    for _ in range(80):
        mid = (lo + hi) / 2
        cap = 1.0
        for _a in range(n_annees):
            brut = cap * (1 + mid)
            frais = cap * FRAIS_ROTATION
            gain = brut - cap - frais
            cap = brut - frais - max(0.0, gain) * PFU
        if cap < cible_net:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def compare(courbe_systeme: pd.Series, close_ref: pd.Series,
            nom_ref: str = "SMH", capital: float = 10_000.0) -> dict:
    s = systeme_net(courbe_systeme, capital)
    r = buy_and_hold(close_ref, capital)
    if not s or not r:
        return {"ok": False, "raison": "series insuffisantes"}
    annees = min(s["annees"], r["annees"])
    barre = barre_a_franchir(r["tri_brut"], annees)
    ecart = s["tri_net"] - r["tri_net"]
    return {"ok": True, "nom_ref": nom_ref, "annees": annees,
            "systeme": s, "reference": r, "barre_brute": barre,
            "ecart_net": ecart,
            "surcout_friction": barre - r["tri_brut"],
            "verdict": "GO" if ecart > 0 and s["dd"] <= r["dd"] * 1.25
                       else ("MARGINAL" if ecart > 0 else "NON")}


def rapport(res: dict, journal=print) -> None:
    if not res.get("ok"):
        journal(f"  Comparatif impossible : {res.get('raison')}")
        return
    s, r = res["systeme"], res["reference"]
    journal("\n" + "=" * 62)
    journal(f"  SYSTEME CONTRE {res['nom_ref']} ACHETE ET CONSERVE")
    journal(f"  Periode : {res['annees']:.1f} ans  ·  PFU {PFU:.0%}  ·  "
            f"frais {FRAIS_ROTATION:.0%}/an")
    journal("=" * 62)
    journal(f"    {'':<26}{'SYSTEME':>13}{res['nom_ref']:>13}")
    journal(f"    {'Rendement brut /an':<26}{s['tri_brut']:>12.2%}"
            f"{r['tri_brut']:>13.2%}")
    journal(f"    {'Rendement NET /an':<26}{s['tri_net']:>12.2%}"
            f"{r['tri_net']:>13.2%}")
    journal(f"    {'Capital final net':<26}{s['net']:>12,.0f}"
            f"{r['net']:>13,.0f}")
    journal(f"    {'Drawdown maximal':<26}{s['dd']:>12.1%}{r['dd']:>13.1%}")
    journal("")
    journal(f"    Barre a franchir en BRUT pour seulement egaler "
            f"{res['nom_ref']} : {res['barre_brute']:.2%}/an")
    journal(f"    Surcout de la friction : "
            f"{res['surcout_friction'] * 100:+.2f} points par an")
    journal(f"    Ecart NET obtenu : {res['ecart_net'] * 100:+.2f} points/an")
    journal("")
    if res["verdict"] == "GO":
        journal("  GO - le systeme bat la reference NET d'impot et de frais,")
        journal("  sans degrader le drawdown de plus de 25 %.")
    elif res["verdict"] == "MARGINAL":
        journal("  MARGINAL - le systeme gagne en net, mais au prix d'un")
        journal("  drawdown nettement plus lourd. A toi de juger si la")
        journal("  difference paie le risque supplementaire vecu.")
    else:
        journal("  NON - le systeme ne bat pas l'achat-conservation une fois")
        journal("  l'impot et les frais comptes. Toute la complexite ajoutee")
        journal("  ne produit rien. Garder la reference est le choix rationnel.")
    journal("=" * 62 + "\n")


def table_friction(journal=print) -> None:
    """Ce que la rotation doit produire, selon l'horizon. Aucune donnee
    de marche : c'est de l'arithmetique fiscale pure."""
    journal("\n  COUT DE LA ROTATION  (reference a 15 % brut/an)")
    journal(f"    {'horizon':<10}{'brut necessaire':>18}{'surcout':>12}")
    for ans in (3, 5, 10, 15, 20):
        b = barre_a_franchir(0.15, ans)
        journal(f"    {str(ans) + ' ans':<10}{b:>17.2%}"
                f"{(b - 0.15) * 100:>11.2f} pt")
    journal("    Plus l'horizon est long, plus l'impot differe du buy & hold")
    journal("    travaille, et plus la barre monte.\n")


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--ref", default="SMH", help="ticker de reference")
    a.add_argument("--table", action="store_true",
                   help="seulement le cout de la rotation")
    o = a.parse_args()
    if o.table:
        table_friction()
        return
    table_friction()
    print("  Pour le comparatif complet, lance d'abord un backtest :")
    print("    py -m equity_scanner.phase0 --univers sp500")
    print("  puis reprends sa courbe de capital ici.")


if __name__ == "__main__":
    main()
