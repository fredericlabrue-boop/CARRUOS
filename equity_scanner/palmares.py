"""Une liste de titres, passee aux 13 blocs, et classee.

CE QUE FREDERIC A DEMANDE, ET CE QUI POSE PROBLEME
--------------------------------------------------
« Classe-moi dans l'ordre les plus pertinentes, avec un ratio risque /
gain favorable. » Deux mots demandent une reponse honnete avant la
premiere ligne de code.

  1. « LES PLUS PERTINENTES » demande un ordre. Un ordre construit en
     additionnant des criteres ponderes est exactement le score
     composite que le projet refuse : les poids ne viennent de nulle
     part, et le classement qui en sort a l'air quantitatif sans
     l'etre.

     La specification, elle, ECRIT deja un ordre : `rules.rank()`, la
     force relative a 6 mois. C'est celui-la qu'on utilise — avec son
     propre avertissement, ecrit dans son docstring : c'est un
     DEPARTAGE, pas un signal valide, et il ajoute un degre de liberte.

     Les autres tris proposes (risque le plus faible, R moyen mesure le
     plus eleve, blocs manquants) trient sur UN fait a la fois. Aucune
     addition, aucun poids. Un tri sur un fait se verifie ; un score
     compose, non.

  2. « RATIO RISQUE / GAIN » suppose un objectif de gain. La
     specification n'en a pas : elle dit « aucun take-profit », et le
     motif est mesure — zero TP touche, 97 % de sorties par autre
     chose. Il n'y a donc pas de denominateur a inventer.

     Ce qui existe et qui se mesure :
       - le RISQUE, defini par la specification : (entree - stop) /
         entree, en pourcentage, et en euros pour le sleeve ;
       - ce que ce signal a REELLEMENT rendu sur CE titre : nombre de
         trades, gagnants, intervalle de Wilson, R moyen, profit
         factor.

     Le second n'est pas une promesse : c'est un releve, avec son
     intervalle, et il porte sur une hypothese qui a rendu NO-GO en
     Phase 0. Il est affiche parce qu'il est verifiable, pas parce
     qu'il est encourageant.

    py -m equity_scanner.palmares COIN HOOD TLX.DE MC.PA
"""

from __future__ import annotations

import argparse

import numpy as np

VERSION = "palmares-v1.0"

# Les groupes, dans l'ordre ou ils s'affichent. Ecrit ici, une fois.
GROUPES = [
    ("complet", "LES 13 BLOCS PASSENT"),
    ("proche", "IL MANQUE UN OU DEUX BLOCS"),
    ("loin", "SIGNAL ABSENT"),
    ("sortie", "CONDITIONS DE SORTIE ACTIVES"),
    ("hors", "HORS CRITÈRES — un veto de la spécification"),
    ("na", "DONNÉES INSUFFISANTES"),
    ("refus", "DONNÉES REFUSÉES"),
    ("erreur", "NON LISIBLES"),
]

# Les tris proposes. Chacun porte sur UN fait, jamais sur une somme.
# `cle` rend le couple (valeur de tri, ticker) pour que deux titres a
# egalite sortent toujours dans le meme ordre.
TRIS = {
    "spec": ("l'ordre de la spécification : force relative 6 mois",
             lambda t: (-_f(t.get("rs_6m"), -1e9), t["ticker"])),
    "blocs": ("le plus de blocs remplis d'abord",
              lambda t: (-t.get("ok", 0), t["ticker"])),
    "risque": ("le risque le plus faible d'abord",
               lambda t: (_f((t.get("niveaux") or {}).get("risque"), 1e9),
                          t["ticker"])),
    "mesure": ("le R moyen mesuré sur ce titre, le plus élevé d'abord",
               lambda t: (-_f((t.get("histo") or {}).get("evR"), -1e9),
                          t["ticker"])),
    "alpha": ("par ordre alphabétique — le plus honnête si le tri de la "
              "spécification vous gêne",
              lambda t: (t["ticker"],)),
}
TRI_DEFAUT = "spec"

AVERTISSEMENT_TRI = (
    "Le tri par défaut est celui de la spécification — force relative à "
    "6 mois — et son propre code le dit : c'est un DÉPARTAGE, pas un "
    "signal validé. Il ajoute un degré de liberté qui n'a pas passé la "
    "Phase 0. Si ce tri vous gêne, prenez l'ordre alphabétique : c'est "
    "plus honnête qu'un tri non testé.")

AVERTISSEMENT_RATIO = (
    "Il n'y a pas de « ratio risque / gain » ici, parce que la "
    "spécification n'a aucun objectif de gain : elle dit « aucun "
    "take-profit ». Ce qui est affiché, c'est le RISQUE défini par la "
    "spécification, et en face ce que ce signal a réellement rendu sur "
    "ce titre — avec son intervalle, et sur une hypothèse qui a rendu "
    "NO-GO en Phase 0.")


def _f(v, defaut=None):
    try:
        x = float(v)
        return x if np.isfinite(x) else defaut
    except (TypeError, ValueError):
        return defaut


def decoupe(saisie: str) -> list[str]:
    """Une saisie libre -> une liste de jetons.

    On coupe sur les espaces, virgules, points-virgules et retours a la
    ligne. PAS sur les points : `MC.PA` et `TLX.DE` en contiennent un.
    Un jeton a points multiples est eclate PLUS TARD, quand on peut
    demander aux donnees si le ticker existe — voir `eclate()`.
    """
    brut = saisie.replace(";", " ").replace(",", " ")
    brut = brut.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return list(dict.fromkeys(m.strip().upper()
                              for m in brut.split() if m.strip()))


def _segmente(pieces: list[str], existe, vus=None) -> list[str] | None:
    """Segmente une liste de morceaux en tickers QUI EXISTENT TOUS.

    C'est le probleme du decoupage de mots, et il se resout en demandant
    au dictionnaire — ici, aux donnees. Un ticker fait un morceau
    (`COIN`) ou deux quand le second est un suffixe de place (`MC.PA`).

    On essaie le collage a DEUX morceaux d'abord, sinon « MC.PA » se
    perdrait en « MC » puis « PA ». Mais seulement si le resultat
    EXISTE : c'est la difference entre demander et deviner.

    Rend None si aucune segmentation complete n'est possible.
    """
    from .resolve import SUFFIXES

    if not pieces:
        return []
    if vus is None:
        vus = {}
    cle = len(pieces)
    if cle in vus:
        return vus[cle]

    essais = []
    if len(pieces) >= 2 and ("." + pieces[1]) in SUFFIXES:
        essais.append((pieces[0] + "." + pieces[1], 2))
    essais.append((pieces[0], 1))

    for tk, saut in essais:
        try:
            if not existe(tk):
                continue
        except Exception:
            continue
        reste = _segmente(pieces[saut:], existe, vus)
        if reste is not None:
            vus[cle] = [tk] + reste
            return vus[cle]
    vus[cle] = None
    return None


def _coupe_sur_points(jeton: str) -> list[str]:
    """Decoupe de dernier recours, quand aucune segmentation ne marche.

    Elle recolle les suffixes de place de gauche a droite. Elle ne peut
    pas etre sure : dans « COIN.HOOD.MC.PA », `.MC` est le suffixe de
    Madrid, donc « HOOD.MC » est plausible — alors que Frederic voulait
    « HOOD » puis « MC.PA ». C'est pour cela qu'on ne s'en sert QU'APRES
    avoir demande aux donnees.
    """
    from .resolve import SUFFIXES

    morceaux, courant = [], ""
    for bout in jeton.split("."):
        if courant and ("." + bout) in SUFFIXES:
            morceaux.append(courant + "." + bout)
            courant = ""
        else:
            if courant:
                morceaux.append(courant)
            courant = bout
    if courant:
        morceaux.append(courant)
    return [m for m in morceaux if m]


def eclate(jeton: str, existe) -> list[str]:
    """Un jeton -> un ou plusieurs tickers, tranche par LES DONNEES.

    `existe(tk)` doit rendre vrai si le ticker se charge.

    L'ordre des essais dit tout. On demande D'ABORD si le jeton entier
    est un ticker : `MC.PA` existe, on n'y touche pas. Sinon on cherche
    une segmentation dont TOUS les morceaux existent. Et seulement si
    rien ne marche, on coupe a l'aveugle — en sachant que c'est un
    pis-aller, pas une reponse.
    """
    if "." not in jeton:
        return [jeton]
    try:
        if existe(jeton):
            return [jeton]
    except Exception:
        pass
    pieces = [p for p in jeton.split(".") if p]
    seg = _segmente(pieces, existe)
    if seg:
        return seg
    return _coupe_sur_points(jeton)


def _histo(d, ticker, bench) -> dict | None:
    """Ce que ce signal a rendu sur CE titre. Avec Wilson, jamais un taux nu."""
    from . import backtest as bt
    from .interet import wilson

    try:
        tr = bt.trades_ticker(d, ticker, bench)
    except Exception:
        return None
    if not tr:
        return {"n": 0}
    rs = [x.R for x in tr]
    gains = [r for r in rs if r > 0]
    perte = -sum(r for r in rs if r < 0)
    bas, _p, haut = wilson(len(gains), len(rs))
    return {
        "n": len(rs), "gagnants": len(gains),
        "bas": round(bas), "haut": round(haut),
        "evR": round(float(np.mean(rs)), 2),
        "pf": round(sum(gains) / perte, 2) if perte > 0 else None,
        "duree": round(float(np.mean([x.barres for x in tr]))),
    }


def evalue_un(ticker: str, sleeve: float, bench_brut, bench_enr,
              jours_resultats=None) -> dict:
    """Un titre : les 13 blocs, les vetos, le risque, et l'historique."""
    from . import cache as ch
    from . import chart as gr
    from . import interet as it
    from . import qualite as ql
    from . import rules as R
    from .indicators import enrich

    out = {"ticker": ticker}
    try:
        brut = ch.charge(ticker, annees=10)
        d = enrich(brut, bench_close=bench_brut["close"])
    except Exception as exc:
        out.update(groupe="erreur", motif=f"{type(exc).__name__}: {exc}")
        return out

    rap = ql.controle(brut, bench=bench_brut, ticker=ticker)
    marche = bool(R.market_regime_ok(bench_enr))
    try:
        sig = R.evaluate(d, ticker, marche, days_to_earnings=jours_resultats)
    except Exception as exc:
        out.update(groupe="erreur", motif=f"{type(exc).__name__}: {exc}")
        return out

    sorties = R.evaluate_exit(d, marche)
    etats = gr._bloc_etats(d, sig)
    u = it.lire_unite(d, bench_enr, sig, sorties, etats,
                      refuse=not rap.utilisable, motifs=rap.bloquants)

    niveaux = None
    if np.isfinite(sig.stop) and sig.entry > sig.stop > 0:
        taille = R.position_size(sig, float(sleeve))
        niveaux = {
            "entree": round(float(sig.entry), 2),
            "stop": round(float(sig.stop), 2),
            "risque": round(float(sig.risk_pct) * 100, 2),
            "atr": round(float(sig.atr), 2),
            "titres": taille["shares"],
            "montant": round(taille["notional"]),
            "risque_eur": round(taille.get("risk_eur", 0.0)),
            "plafonne": bool(taille.get("capped")),
        }

    out.update({
        "groupe": u["niveau"],
        "titre_groupe": u["titre"],
        "ok": u["ok"], "total": u["total"], "compte": u["compte"],
        "manquants": u["manquants"],
        "vetos": u["vetos"], "vigilance": u["vigilance"],
        "refus_motifs": u["refus_motifs"],
        "sorties_actives": u["sorties_actives"],
        "declenche": bool(sig.fired),
        "rs_6m": _f(sig.rs_6m),
        "niveaux": niveaux,
        "histo": _histo(d, ticker, bench_enr),
        "cours": round(float(d["close"].iloc[-1]), 2),
        "date": str(d.index[-1].date()),
        "alertes": rap.alertes,
    })
    return out


def evalue(tickers, sleeve: float = 8000.0, marche: str = "us",
           tri: str = TRI_DEFAUT, av_key: str | None = None,
           journal=lambda _m: None) -> dict:
    """La liste complete, groupee et triee."""
    from . import cache as ch
    from . import data as dl
    from . import resolve as rs
    from .indicators import enrich

    bench_tk = "SPY" if marche == "us" else "^STOXX"
    try:
        bench_brut = ch.charge(bench_tk, annees=10)
        bench_enr = enrich(bench_brut)
    except Exception as exc:
        return {"ok": False, "erreur": f"indice {bench_tk} indisponible ({exc})"}

    # Les dates de resultats : un veto de la specification en depend, et
    # « inconnu » n'est pas « sans risque ».
    cal = {}
    if av_key:
        try:
            from . import news as nw
            cal = nw.earnings_map(av_key)
        except Exception:
            cal = {}

    def _existe(t):
        try:
            ch.charge(t, annees=1)
            return True
        except Exception:
            return False

    # Les jetons a points multiples sont eclates ICI, ou l'on peut
    # demander aux donnees si le ticker existe.
    demandes: list[str] = []
    for j in tickers:
        demandes += eclate(j, _existe)
    demandes = list(dict.fromkeys(demandes))

    lignes, inconnus = [], []
    for saisie in demandes:
        tk, _sugg = rs.resoudre(saisie, lambda t: ch.charge(t, annees=3),
                                journal=journal)
        if tk is None:
            inconnus.append(saisie)
            lignes.append({"ticker": saisie, "groupe": "erreur",
                           "motif": "ticker introuvable"})
            continue
        jours = None
        if tk in cal:
            try:
                from . import news as nw
                jours = nw.seances_avant(cal[tk])
            except Exception:
                jours = None
        if jours is None and marche == "us":
            try:
                jours = dl.days_to_earnings_yf(tk)
            except Exception:
                jours = None
        lignes.append(evalue_un(tk, sleeve, bench_brut, bench_enr, jours))

    if tri not in TRIS:
        tri = TRI_DEFAUT
    cle = TRIS[tri][1]
    groupes = []
    for g, libelle in GROUPES:
        dedans = [x for x in lignes if x.get("groupe") == g]
        if not dedans:
            continue
        try:
            dedans.sort(key=cle)
        except Exception:
            dedans.sort(key=lambda x: x["ticker"])
        groupes.append({"cle": g, "titre": libelle, "lignes": dedans})

    return {
        "ok": True, "version": VERSION, "tri": tri,
        "tri_libelle": TRIS[tri][0], "tris": {k: v[0] for k, v in TRIS.items()},
        "sleeve": sleeve, "marche": marche,
        "n": len(lignes), "inconnus": inconnus,
        "groupes": groupes,
        "avertissement_tri": AVERTISSEMENT_TRI,
        "avertissement_ratio": AVERTISSEMENT_RATIO,
    }


# --------------------------------------------------------------------
# Sortie texte
# --------------------------------------------------------------------

def _plie(texte: str, largeur: int = 76) -> list[str]:
    mots, ligne, out = texte.split(), "", []
    for m in mots:
        if len(ligne) + len(m) + 1 > largeur:
            out.append(ligne)
            ligne = m
        else:
            ligne = (ligne + " " + m).strip()
    if ligne:
        out.append(ligne)
    return out


def texte(r: dict) -> str:
    if not r.get("ok"):
        return f"\n  {r.get('erreur')}\n"
    L = [f"\n  {r['n']} titre(s) passés aux 13 blocs  ·  sleeve "
         f"{r['sleeve']:.0f}  ·  tri : {r['tri_libelle']}", ""]
    for g in r["groupes"]:
        L.append(f"  {g['titre']}")
        for t in g["lignes"]:
            if t["groupe"] == "erreur":
                L.append(f"    {t['ticker']:<10} {t.get('motif', '')}")
                continue
            n = t.get("niveaux") or {}
            h = t.get("histo") or {}
            risque = (f"risque {n['risque']:.2f} %" if n.get("risque")
                      else "risque non calculable")
            rs = t.get("rs_6m")
            L.append(f"    {t['ticker']:<10} {t['compte']:>7}   "
                     f"{t['cours']:>9}   {risque:<22}"
                     + (f"  RS6m {rs:+.2f}" if rs is not None else ""))
            if n.get("titres"):
                L.append(f"               entrée {n['entree']}  stop "
                         f"{n['stop']}  {n['titres']} titres pour "
                         f"{n['montant']}  risque {n['risque_eur']}"
                         + ("  (taille réduite par le plafond)"
                            if n["plafonne"] else ""))
            if h.get("n"):
                pf = "—" if h.get("pf") is None else f"{h['pf']}"
                L.append(f"               ce signal sur ce titre : "
                         f"{h['gagnants']}/{h['n']} gagnants "
                         f"(IC {h['bas']}–{h['haut']} %), R moyen "
                         f"{h['evR']:+.2f}, profit factor {pf}")
            elif h is not None:
                L.append("               ce signal n'a jamais été pris "
                         "sur ce titre : aucune référence propre")
            for v in t.get("vetos", []):
                L.append(f"               VETO : {v}")
            for v in t.get("refus_motifs", []):
                L.append(f"               REFUS : {v}")
            if t.get("manquants") and t["groupe"] in ("proche", "loin"):
                for m in t["manquants"][:3]:
                    L.append(f"               il manque : {m['nom']} — "
                             f"{m['texte']}")
        L.append("")
    if r.get("inconnus"):
        L.append(f"  Introuvables : {', '.join(r['inconnus'])}")
        L.append("")
    for ligne in _plie(r["avertissement_ratio"]):
        L.append("  " + ligne)
    L.append("")
    for ligne in _plie(r["avertissement_tri"]):
        L.append("  " + ligne)
    return "\n".join(L + [""])


def main() -> None:
    p = argparse.ArgumentParser(
        description="Passe une liste de titres aux 13 blocs et les classe")
    p.add_argument("tickers", nargs="+",
                   help="COIN HOOD TLX.DE, ou COIN.HOOD.TLX.DE")
    p.add_argument("--sleeve", type=float, default=8000.0)
    p.add_argument("--marche", default="us", choices=("us", "europe"))
    p.add_argument("--tri", default=TRI_DEFAUT, choices=sorted(TRIS))
    a = p.parse_args()
    liste = decoupe(" ".join(a.tickers))
    print(texte(evalue(liste, a.sleeve, a.marche, a.tri, journal=print)))


if __name__ == "__main__":
    main()
