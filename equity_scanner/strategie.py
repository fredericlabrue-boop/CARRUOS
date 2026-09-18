"""Strategie patrimoniale : projection de reinvestissement, revue de ligne.

DEUX QUESTIONS, DEUX NATURES TRES DIFFERENTES.

  1. « Si je reinvestis mes gains, combien puis-je esperer ? »
     C'est de l'ARITHMETIQUE. Trois traitements fiscaux du meme
     rendement ne donnent pas le meme capital final, et l'ecart se
     calcule exactement. Le rendement, lui, est une HYPOTHESE que vous
     fournissez : le module ne le predit pas, il en tire les
     consequences. Changer l'hypothese change tout le tableau, et c'est
     precisement ce qu'il faut voir.

  2. « Mon TLX est monte puis redescendu : je garde ou je vends ? »
     Ce n'est PAS de l'arithmetique, et ce module ne repondra pas.
     Il donne les FAITS — le plus haut atteint, le recul depuis ce
     sommet, la distance au stop, les ecarts aux moyennes — et l'etat
     des QUATRE CONDITIONS DE SORTIE ECRITES dans la specification.
     C'est votre plan qui decide, pas un score invente ici.

     La regle du projet est explicite : aucun verdict directionnel
     derive de poids non testes. Un module qui afficherait « VENDRE,
     confiance 72 % » serait exactement le defaut qu'on refuse depuis
     le debut. La difference entre « deux conditions de sortie sur
     quatre sont actives » et « vends » n'est pas une nuance de style :
     la premiere est verifiable, la seconde est une opinion deguisee.

  Quant au geopolitique : rien ici ne le quantifie, et rien ne le fera.
  Les actualites sont du CONTEXTE pour votre verification avant de
  passer l'ordre. Une information publique est deja dans les cours.

    py -m equity_scanner.strategie --capital 10000 --taux 8 --ans 15
    py -m equity_scanner.strategie --ligne TLX
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Fiscalite par defaut : le prelevement forfaitaire unique du compte-titres.
PFU = 0.30
# Un PEA de plus de cinq ans ne paie que les prelevements sociaux.
PEA_5ANS = 0.172
FRAIS_ROTATION = 0.01      # aller-retour moyen, en part du capital par an

HORIZONS = (1, 3, 5, 10, 15, 20)


# =====================================================================
# 1. PROJECTION — arithmetique pure
# =====================================================================
def projette(capital: float, taux_annuel: float, annees: int = 15,
             versement_mensuel: float = 0.0, impot: float = PFU,
             frais_rotation: float = FRAIS_ROTATION) -> dict:
    """Le meme rendement, trois traitements fiscaux.

    `taux_annuel` est une hypothese en clair (0.08 = 8 %/an). Ce n'est
    pas une prevision et le module ne pretend pas en produire une.

      A. CAPITALISANT   — un ETF qui reinvestit ses dividendes en
         interne. Rien n'est realise en route, donc rien n'est impose
         avant la revente. L'impot differe continue de travailler.
      B. ROTATION       — ce que fait un systeme qui achete et revend.
         Chaque annee realise ses plus-values, donc les impose, et paie
         ses frais de courtage.
      C. GAINS RETIRES  — les gains sortent du compte chaque annee.
         Le capital ne grossit plus : c'est la difference entre un
         revenu et un patrimoine.

    Les interets se composent MENSUELLEMENT pour que les versements
    reguliers comptent a leur date reelle ; l'impot et les frais de la
    rotation s'appliquent en fin d'annee civile, comme dans la vraie vie.
    """
    capital = max(0.0, float(capital))
    versement = max(0.0, float(versement_mensuel))
    annees = max(1, int(annees))
    if capital <= 0 and versement <= 0:
        return {"ok": False, "raison": "ni capital de depart ni versement"}

    taux_m = (1.0 + taux_annuel) ** (1.0 / 12.0) - 1.0

    cap_a = cap_b = cap_c = capital
    verse = capital                 # total sorti de la poche
    retire_cumule = 0.0
    lignes = []

    for an in range(1, annees + 1):
        debut_b, debut_c = cap_b, cap_c
        for _ in range(12):
            cap_a = cap_a * (1 + taux_m) + versement
            cap_b = cap_b * (1 + taux_m) + versement
            cap_c = cap_c * (1 + taux_m) + versement
            verse += versement

        # B : fin d'annee civile, on solde l'impot et les frais.
        frais = debut_b * frais_rotation
        gain_annee = cap_b - debut_b - (versement * 12) - frais
        du = max(0.0, gain_annee) * impot
        cap_b = cap_b - frais - du

        # C : les gains de l'annee sortent du compte, nets d'impot. Seuls
        # les versements font encore grossir le capital. Meme cadence que
        # B : sans cela, l'ecart entre les deux melangerait la fiscalite
        # avec un artefact de calcul.
        gain_c = cap_c - debut_c - (versement * 12)
        retire_cumule += max(0.0, gain_c) * (1 - impot)
        cap_c = debut_c + versement * 12

        # A : rien n'est du tant qu'on ne vend pas.
        plus_value_a = max(0.0, cap_a - verse)
        net_a = cap_a - plus_value_a * impot

        lignes.append({
            "an": an,
            "verse": round(verse, 2),
            "capitalisant_brut": round(cap_a, 2),
            "capitalisant_net": round(net_a, 2),
            "rotation_net": round(cap_b, 2),
            "retire_capital": round(cap_c, 2),
            "retire_cumule": round(retire_cumule, 2),
            "retire_total": round(cap_c + retire_cumule, 2),
            "impot_annee_rotation": round(du, 2),
            "frais_annee_rotation": round(frais, 2),
        })

    fin = lignes[-1]
    ecart = fin["capitalisant_net"] - fin["rotation_net"]
    return {
        "ok": True,
        "hypothese": {
            "capital": round(capital, 2), "taux": taux_annuel,
            "annees": annees, "versement_mensuel": round(versement, 2),
            "impot": impot, "frais_rotation": frais_rotation,
        },
        "lignes": lignes,
        "verse_total": fin["verse"],
        "capitalisant_net": fin["capitalisant_net"],
        "rotation_net": fin["rotation_net"],
        "retire_total": fin["retire_total"],
        "ecart_capitalisant_rotation": round(ecart, 2),
        "part_perdue_en_friction": (
            round(ecart / fin["capitalisant_net"] * 100, 2)
            if fin["capitalisant_net"] > 0 else 0.0),
        "barre_brute": barre_a_franchir(taux_annuel, annees, impot,
                                        frais_rotation),
    }


def barre_a_franchir(taux_ref: float, annees: float, impot: float = PFU,
                     frais: float = FRAIS_ROTATION) -> float:
    """Rendement BRUT que la rotation doit produire pour seulement EGALER
    le capitalisant, une fois l'impot annuel et les frais comptes.

    On resout numeriquement : quel taux brut, ampute chaque annee de
    l'impot sur le gain et des frais, rend la meme somme nette qu'un
    placement impose une seule fois a la sortie ?
    """
    n = max(1, int(round(annees)))
    cible = (1 + taux_ref) ** n
    cible_net = 1 + (cible - 1) * (1 - impot)
    lo, hi = taux_ref, taux_ref + 0.60
    for _ in range(80):
        mid = (lo + hi) / 2
        cap = 1.0
        for _a in range(n):
            brut = cap * (1 + mid)
            f = cap * frais
            gain = brut - cap - f
            cap = brut - f - max(0.0, gain) * impot
        if cap < cible_net:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 6)


def table_friction(taux_ref: float = 0.10, impot: float = PFU,
                   frais: float = FRAIS_ROTATION) -> list:
    """Le surcout de la rotation selon l'horizon. Aucune donnee de
    marche : c'est de l'arithmetique fiscale pure."""
    out = []
    for ans in HORIZONS:
        b = barre_a_franchir(taux_ref, ans, impot, frais)
        out.append({"annees": ans, "brut_necessaire": b,
                    "surcout": round(b - taux_ref, 6)})
    return out


# =====================================================================
# 2. REVUE D'UNE LIGNE DETENUE — des faits, pas un verdict
# =====================================================================
def revue_ligne(ligne: dict, d: pd.DataFrame, marche_ok: bool,
                impot: float = PFU, earn: dict | None = None) -> dict:
    """Tout ce qui est MESURABLE sur une position ouverte.

    `ligne` vient du registre des positions : ticker, quantite, entree,
    stop, date. `d` est la serie enrichie du titre.

    Le cas qui motive ce module : un titre monte, puis redescend. Trois
    chiffres disent cette histoire mieux qu'une opinion —

      - le plus haut atteint DEPUIS L'ENTREE (et quand) ;
      - le recul depuis ce sommet, en pourcentage ;
      - le gain latent maximum qu'on a laisse filer.

    Ce sont des faits. Ce qu'il faut en faire est ecrit dans votre plan,
    pas ici.
    """
    from .rules import evaluate_exit

    out = {"ticker": ligne.get("ticker", ""), "ok": False}
    if d is None or d.empty or "close" not in d.columns:
        out["erreur"] = "serie indisponible"
        return out

    entree = float(ligne.get("entree") or 0.0)
    qte = float(ligne.get("quantite") or 0.0)
    if entree <= 0:
        out["erreur"] = "prix d'entree manquant"
        return out

    cours = float(d["close"].iloc[-1])
    depuis = ligne.get("date") or ""
    idx = d.index
    debut = pd.Timestamp(depuis) if depuis else idx[0]
    seg = d[idx >= debut]
    if len(seg) < 2:
        seg = d.tail(2)

    haut = float(seg["high"].max()) if "high" in seg else float(seg["close"].max())
    bas = float(seg["low"].min()) if "low" in seg else float(seg["close"].min())
    date_haut = seg["high"].idxmax() if "high" in seg else seg["close"].idxmax()

    # MFE / MAE : le meilleur et le pire du trajet, en clair.
    mfe = (haut / entree - 1) * 100
    mae = (bas / entree - 1) * 100
    pnl = (cours / entree - 1) * 100
    recul = (cours / haut - 1) * 100 if haut > 0 else 0.0
    rendu = mfe - pnl                      # part du gain maximum rendue

    r = d.iloc[-1]
    atr = float(r.get("atr14", np.nan))

    def ecart(col):
        v = r.get(col, np.nan)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(v) or v <= 0:
            return None
        return {"pct": round((cours / v - 1) * 100, 2),
                "atr": round((cours - v) / atr, 2)
                if np.isfinite(atr) and atr > 0 else None}

    stop = ligne.get("stop")
    marge_stop = (round((cours / float(stop) - 1) * 100, 2)
                  if stop else None)

    sorties = evaluate_exit(d, marche_ok)
    actives = [k for k, v in sorties.items() if v]

    # Cout fiscal d'une vente MAINTENANT : un fait, pas un conseil.
    plus_value = (cours - entree) * qte
    impot_du = max(0.0, plus_value) * impot
    out.update({
        "ok": True,
        "cours": round(cours, 4),
        "entree": round(entree, 4),
        "quantite": qte,
        "valeur": round(cours * qte, 2),
        "pnl_pct": round(pnl, 2),
        "pnl_eur": round(plus_value, 2),
        "depuis": str(pd.Timestamp(debut).date()),
        "seances_detenues": int(len(seg)),
        # Le coeur de la question « monte puis redescendu »
        "plus_haut": round(haut, 4),
        "date_plus_haut": str(pd.Timestamp(date_haut).date()),
        "plus_bas": round(bas, 4),
        "mfe_pct": round(mfe, 2),
        "mae_pct": round(mae, 2),
        "recul_depuis_haut_pct": round(recul, 2),
        "gain_rendu_pct": round(rendu, 2),
        # Reperes techniques, en ATR pour etre comparables d'un titre a l'autre
        "atr": round(atr, 4) if np.isfinite(atr) else None,
        "atr_pct": (round(atr / cours * 100, 2)
                    if np.isfinite(atr) and cours else None),
        "ema20": ecart("ema20"), "sma50": ecart("sma50"),
        "sma200": ecart("sma200"),
        "rsi": (round(float(r["rsi14"]), 1)
                if "rsi14" in d and np.isfinite(r["rsi14"]) else None),
        "rvol": (round(float(r["rvol"]), 2)
                 if "rvol" in d and np.isfinite(r["rvol"]) else None),
        "stop": float(stop) if stop else None,
        "marge_stop_pct": marge_stop,
        # Le plan ecrit, et lui seul
        "sorties": sorties,
        "sorties_actives": actives,
        "n_sorties": len(actives),
        "marche_ok": bool(marche_ok),
        # Fiscalite d'une vente immediate
        "impot_si_vente": round(impot_du, 2),
        "net_si_vente": round(cours * qte - impot_du, 2),
        "taux_impot": impot,
        "resultats": earn or {},
    })
    return out


def point_mort_fiscal(revue: dict, impot: float = PFU) -> dict | None:
    """De combien le titre doit-il encore monter pour qu'attendre batte
    vendre aujourd'hui puis replacer ailleurs ?

    Vendre realise la plus-value et declenche l'impot : la somme
    replacee est amputee d'autant. Garder laisse la totalite travailler,
    impot differe. L'ecart est un HANDICAP CHIFFRE pour le nouveau
    placement — ce n'est pas une raison de garder un titre que votre
    plan dit de vendre, c'est le prix du billet, et il se calcule.
    """
    if not revue.get("ok"):
        return None
    val = revue["valeur"]
    net = revue["net_si_vente"]
    if val <= 0 or net <= 0:
        return None
    handicap = val / net - 1
    return {
        "valeur_si_garde": round(val, 2),
        "net_si_vendu": round(net, 2),
        "impot": revue["impot_si_vente"],
        "handicap_pct": round(handicap * 100, 2),
    }


def texte_projection(p: dict) -> str:
    """Le tableau, en clair."""
    if not p.get("ok"):
        return f"\n  Projection impossible : {p.get('raison')}\n"
    h = p["hypothese"]
    L = ["", "  " + "=" * 68,
         f"  PROJECTION — hypothese de {h['taux']:.1%} brut par an sur "
         f"{h['annees']} ans",
         "  " + "=" * 68,
         f"    capital de depart   {h['capital']:>12,.0f} EUR",
         f"    versement mensuel   {h['versement_mensuel']:>12,.0f} EUR",
         f"    imposition          {h['impot']:>12.1%}",
         f"    frais de rotation   {h['frais_rotation']:>12.1%} par an",
         "",
         "    CE TAUX EST VOTRE HYPOTHESE, PAS UNE PREVISION.",
         "    Le module en tire les consequences, il ne les devine pas.",
         "",
         f"    {'an':<5}{'verse':>12}{'capitalisant':>15}"
         f"{'rotation':>13}{'gains retires':>15}"]
    for x in p["lignes"]:
        if x["an"] in HORIZONS or x["an"] == h["annees"]:
            L.append(f"    {x['an']:<5}{x['verse']:>12,.0f}"
                     f"{x['capitalisant_net']:>15,.0f}"
                     f"{x['rotation_net']:>13,.0f}"
                     f"{x['retire_total']:>15,.0f}")
    L += ["",
          f"    Au bout de {h['annees']} ans, vous avez verse "
          f"{p['verse_total']:,.0f} EUR.",
          f"      capitalisant, net d'impot   {p['capitalisant_net']:>12,.0f} EUR",
          f"      rotation active, net        {p['rotation_net']:>12,.0f} EUR",
          f"      gains retires au fil de l'eau {p['retire_total']:>10,.0f} EUR",
          "",
          f"    La friction fiscale de la rotation coute "
          f"{p['ecart_capitalisant_rotation']:+,.0f} EUR, soit "
          f"{p['part_perdue_en_friction']:.1f} %.",
          f"    Pour seulement EGALER le capitalisant, la rotation doit "
          f"produire {p['barre_brute']:.2%} brut par an",
          f"    au lieu de {h['taux']:.2%}. C'est la barre reelle.",
          ""]
    return "\n".join(L)


def texte_revue(r: dict) -> str:
    if not r.get("ok"):
        return f"\n  {r.get('ticker')} : {r.get('erreur')}\n"
    pm = point_mort_fiscal(r, r.get("taux_impot", PFU))
    L = ["", f"  {r['ticker']}  —  {r['quantite']:.0f} titres a "
             f"{r['entree']:.2f}, detenus depuis le {r['depuis']} "
             f"({r['seances_detenues']} seances)",
         "",
         "  LE TRAJET",
         f"    cours actuel              {r['cours']:>10.2f}",
         f"    plus haut depuis l'entree {r['plus_haut']:>10.2f}   "
         f"le {r['date_plus_haut']}",
         f"    plus bas depuis l'entree  {r['plus_bas']:>10.2f}",
         f"    gain latent MAXIMUM       {r['mfe_pct']:>+9.2f} %",
         f"    gain latent AUJOURD'HUI   {r['pnl_pct']:>+9.2f} %",
         f"    recul depuis le sommet    {r['recul_depuis_haut_pct']:>+9.2f} %",
         f"    part du gain rendue       {r['gain_rendu_pct']:>9.2f} points",
         "",
         "  OU SE TROUVE LE PRIX"]
    for nom, cle in (("EMA 20", "ema20"), ("SMA 50", "sma50"),
                     ("SMA 200", "sma200")):
        e = r.get(cle)
        if e:
            atr = "" if e["atr"] is None else f"   ({e['atr']:+.1f} ATR)"
            L.append(f"    ecart a la {nom:<8}{e['pct']:>+9.2f} %{atr}")
    if r.get("rsi") is not None:
        L.append(f"    RSI 14                    {r['rsi']:>9.1f}")
    if r.get("marge_stop_pct") is not None:
        L.append(f"    marge avant le stop       {r['marge_stop_pct']:>+9.2f} %")
    L += ["", "  CE QUE DIT VOTRE PLAN  "
               f"({r['n_sorties']} condition(s) de sortie active(s) sur "
               f"{len(r['sorties'])})"]
    for k, v in r["sorties"].items():
        L.append(f"    {'ACTIVE  ' if v else 'dormante'}  {k}")
    if r.get("resultats", {}).get("jours") is not None:
        L.append(f"\n  RESULTATS dans {r['resultats']['jours']} seances "
                 f"({r['resultats'].get('date', '')})")
    if pm:
        L += ["", "  SI VOUS VENDEZ AUJOURD'HUI",
              f"    valeur de la ligne        {pm['valeur_si_garde']:>10,.2f} EUR",
              f"    impot du                  {-pm['impot']:>10,.2f} EUR",
              f"    net replacable            {pm['net_si_vendu']:>10,.2f} EUR",
              f"    Le nouveau placement part avec {pm['handicap_pct']:.2f} % "
              f"de retard.",
              "    Ce n'est pas une raison de garder : c'est le prix du "
              "billet, chiffre."]
    L += ["",
          "  Aucun verdict n'est calcule ici. Les conditions de sortie "
          "ci-dessus",
          "  sont celles de votre specification ; les chiffres sont "
          "mesures. Ce que",
          "  vous en faites vous appartient.",
          ""]
    return "\n".join(L)


# =====================================================================
def main() -> None:
    import argparse
    a = argparse.ArgumentParser(description="Strategie patrimoniale")
    a.add_argument("--capital", type=float, default=10_000.0)
    a.add_argument("--taux", type=float, default=8.0,
                   help="hypothese de rendement brut annuel, en %%")
    a.add_argument("--ans", type=int, default=15)
    a.add_argument("--mensuel", type=float, default=0.0)
    a.add_argument("--pea", action="store_true",
                   help="imposition d'un PEA de plus de 5 ans (17,2 %%)")
    a.add_argument("--ligne", default="", help="revue d'un titre detenu")
    o = a.parse_args()
    impot = PEA_5ANS if o.pea else PFU

    if o.ligne:
        from . import cache as ch
        from . import positions as ps
        from .indicators import enrich
        from .rules import market_regime_ok

        lignes = [x for x in ps.charge()
                  if x["ticker"].upper() == o.ligne.upper()]
        if not lignes:
            print(f"\n  {o.ligne.upper()} n'est pas dans votre registre.")
            print("  Ajoutez-le depuis la page d'accueil.\n")
            return
        bench_brut = ch.charge("SPY", annees=3)
        marche = market_regime_ok(enrich(bench_brut))
        d = enrich(ch.charge(lignes[0]["ticker"], annees=3),
                   bench_close=bench_brut["close"])
        print(texte_revue(revue_ligne(lignes[0], d, marche, impot)))
        return

    print(texte_projection(projette(o.capital, o.taux / 100.0, o.ans,
                                    o.mensuel, impot)))
    print("  COUT DE LA ROTATION SELON L'HORIZON")
    print(f"    {'horizon':<10}{'brut necessaire':>18}{'surcout':>12}")
    for x in table_friction(o.taux / 100.0, impot):
        print(f"    {str(x['annees']) + ' ans':<10}"
              f"{x['brut_necessaire']:>17.2%}"
              f"{x['surcout'] * 100:>11.2f} pt")
    print("    Plus l'horizon est long, plus l'impot que le capitalisant")
    print("    ne paie pas encore travaille, et plus la barre monte.\n")


if __name__ == "__main__":
    main()
