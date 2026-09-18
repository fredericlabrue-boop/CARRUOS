"""Phase 0 : le systeme a-t-il un edge mesurable ?

    py -m equity_scanner.phase0 --univers us --sleeve 8000
    py -m equity_scanner.phase0 --univers sp500 --csv resultats.csv

Cinq criteres. Les CINQ doivent passer, sinon NO-GO et rien ne bouge.

  1. >= 200 trades hors echantillon
  2. profit factor >= 1,15
  3. esperance positive apres couts
  4. z >= 2 contre des entrees aleatoires de meme duree
  5. drawdown maximum < 20 %

Le critere 4 est le plus important et le moins intuitif. Gagner de l'argent
ne prouve rien : sur un marche haussier, acheter n'importe quand en gagne
aussi. La question est de savoir si le SIGNAL fait mieux que le hasard a
duree de detention egale. C'est ce que mesure le z.

Aucun grid search. Les parametres sont figes avant le test. Sinon 78 125
combinaisons produisent ~3 900 faux positifs a z >= 2, et le critere ne veut
plus rien dire.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from . import backtest as bt
from . import data as dl
from . import rules as R
from .indicators import enrich

IN_DEBUT, IN_FIN = "2010-01-01", "2021-12-31"
OOS_DEBUT, OOS_FIN = "2022-01-01", "2026-12-31"
TIRAGES = 1000


# --- Statistiques -----------------------------------------------------
def profit_factor(rs: list[float]) -> float:
    g = sum(r for r in rs if r > 0)
    p = -sum(r for r in rs if r < 0)
    return float("inf") if p == 0 else g / p


def z_contre_hasard(trades, series: dict, graine=7,
                    debut=None, fin=None) -> tuple:
    """Pour chaque trade reel (titre T, duree D), tire une entree au hasard
    sur T et detient exactement D barres. On refait l'ensemble 1000 fois pour
    obtenir la distribution nulle, puis on compare.

    Ce test neutralise le beta : si le systeme ne fait que capter la hausse
    du marche, le hasard capte la meme chose et z tombe a zero.

    DEUX CORRECTIONS.

    1. La FENETRE. Les tirages se faisaient sur tout l'historique
       disponible — soit 2006-2026 — alors que les trades compares sont
       ceux du hors echantillon 2022-2026. On comparait donc le systeme
       sur quatre ans a un hasard tire sur vingt ans, dont 2008 et 2020.
       Le z mesurait en partie la difference entre deux PERIODES, pas
       entre le signal et le hasard. Les tirages sont desormais bornes a
       la meme fenetre que les trades.

    2. LES COUTS. Le hasard payait `COUT_AR` (10 pb) quand les trades
       reels payaient l'ouverture J+1 plus le spread et le slippage des
       deux cotes (30 pb). Le systeme partait battu de 20 pb par trade.
       Les deux camps paient maintenant exactement la meme chose.
    """
    if not trades:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(graine)
    reel = float(np.mean([t.rendement for t in trades]))
    cout = 2 * (bt.COUT_PAR_COTE + bt.SLIPPAGE) if bt.EXECUTION_J1 else bt.COUT_AR

    # Fenetre de tirage : celle des trades compares, a defaut celle
    # demandee. Sans borne, on tirerait sur des regimes de marche que le
    # systeme n'a jamais eu l'occasion de traverser.
    d0 = pd.Timestamp(debut) if debut else min(t.entree_d for t in trades)
    d1 = pd.Timestamp(fin) if fin else max(t.sortie_d for t in trades)

    plan = []
    for t in trades:
        d = series.get(t.ticker)
        if d is None or len(d) < t.barres + 240:
            continue
        pos = np.flatnonzero((d.index >= d0) & (d.index <= d1))
        lo = max(220, int(pos[0])) if len(pos) else 220
        hi = (int(pos[-1]) if len(pos) else len(d) - 1) - t.barres
        if hi <= lo:
            continue
        plan.append((d["close"].to_numpy(), t.barres, lo, hi))
    if len(plan) < 20:
        return reel, 0.0, 0.0

    # Entierement vectorise : une passe numpy par titre, au lieu de
    # 1000 x len(plan) iterations Python. Les tirages sont les memes
    # (meme graine, meme ordre), donc le z rendu est identique.
    debuts = np.empty((TIRAGES, len(plan)), dtype=np.int64)
    for m, (_px, _dur, lo, hi) in enumerate(plan):
        debuts[:, m] = rng.integers(lo, hi, TIRAGES)
    rendements = np.empty((TIRAGES, len(plan)))
    for m, (px, dur, _lo, _hi) in enumerate(plan):
        d0 = debuts[:, m]
        rendements[:, m] = px[d0 + dur] / px[d0] - 1.0 - cout
    moyennes = rendements.mean(axis=1)
    mu, sd = float(moyennes.mean()), float(moyennes.std(ddof=1))
    z = 0.0 if sd == 0 else (reel - mu) / sd
    return reel, mu, z


def mesures(trades, series, debut=None, fin=None) -> dict:
    rs = [t.R for t in trades]
    rends = [t.rendement for t in trades]
    pf = profit_factor(rs)
    gagnants = [r for r in rs if r > 0]
    # `series` donne au portefeuille de quoi valoriser les lignes ouvertes
    # chaque seance : le drawdown cesse d'ignorer les pertes latentes.
    # MAX_WEIGHT etait respecte par le scan du jour et ignore par le
    # backtest : deux dimensionnements differents pour le meme systeme.
    pt = bt.portefeuille(trades, series=series, max_poids=R.MAX_WEIGHT)
    reel, nul, z = z_contre_hasard(trades, series, debut=debut, fin=fin)
    motifs = pd.Series([t.motif for t in trades]).value_counts().to_dict() if trades else {}
    return {
        "n": len(trades), "pf": pf,
        "ev_R": float(np.mean(rs)) if rs else 0.0,
        "ev_pct": float(np.mean(rends)) * 100 if rends else 0.0,
        "taux": len(gagnants) / len(rs) * 100 if rs else 0.0,
        "duree": float(np.mean([t.barres for t in trades])) if trades else 0.0,
        "dd": pt["dd"] * 100, "dd_source": pt["dd_source"],
        "dd_realise": pt["dd_realise"] * 100, "final": pt["final"],
        "pris": pt["pris"], "ecartes": pt["ecartes"],
        "rognees": pt.get("lignes_rognees", 0),
        "poids_max": pt.get("poids_max", 0.0) * 100,
        "z": z, "reel": reel * 100, "hasard": nul * 100, "motifs": motifs,
    }


def verdict(m: dict) -> tuple:
    c = [("trades OOS >= 200", m["n"] >= 200, f"{m['n']}"),
         ("profit factor >= 1,15", m["pf"] >= 1.15, f"{m['pf']:.2f}"),
         ("esperance > 0 apres couts", m["ev_R"] > 0, f"{m['ev_R']:+.3f} R"),
         ("z >= 2 contre le hasard", m["z"] >= 2.0, f"{m['z']:+.2f}"),
         ("drawdown < 20 %", m["dd"] < 20.0, f"{m['dd']:.1f} %")]
    return all(x[1] for x in c), c


# --- Robustesse -------------------------------------------------------
def robustesse(tickers, bench, series) -> list:
    """Chaque parametre decale de +-20 %. Un systeme qui ne survit qu'aux
    valeurs exactes est du surapprentissage, pas un edge.

    Ce n'est PAS un grid search : on ne garde aucune de ces valeurs. On
    verifie seulement que l'avantage ne tient pas a une virgule.

    Le moteur lit desormais ces seuils sur le module `rules` a chaque
    appel. Avant, `simule()` gardait sa fenetre de repli et son multiple
    d'ATR figes : decaler PULLBACK_WINDOW ne changeait rien au placement
    du stop, et la ligne « fenetre de repli +-20 % » du rapport ne testait
    donc pas ce qu'elle annoncait.
    """
    tests = [("RSI plancher", "RSI_FLOOR", R.RSI_FLOOR),
             ("RVOL minimum", "RVOL_MIN", R.RVOL_MIN),
             ("fenetre de repli", "PULLBACK_WINDOW", R.PULLBACK_WINDOW),
             ("multiple ATR du stop", "STOP_ATR_MULT", R.STOP_ATR_MULT)]
    out = []
    for nom, attr, base in tests:
        for signe in (-0.2, 0.2):
            val = base * (1 + signe)
            if attr == "PULLBACK_WINDOW":
                val = max(3, int(round(val)))
            setattr(R, attr, val)
            try:
                tr = []
                for tk in tickers:
                    d = series.get(tk)
                    if d is not None:
                        tr += bt.trades_ticker(d, tk, bench, OOS_DEBUT, OOS_FIN)
                pf = profit_factor([t.R for t in tr]) if tr else 0.0
                out.append((f"{nom} {signe:+.0%}", val, len(tr), pf, pf > 1.0))
            finally:
                setattr(R, attr, base)
    return out


# --- Execution --------------------------------------------------------
def charge_univers(tickers, bench_tk="SPY", ans=20, journal=print,
                   qualite_min: float | None = None):
    """Telecharge et enrichit tout l'univers.

    Les telechargements partent en parallele et passent par le cache
    disque : une deuxieme passe dans la journee ne touche plus le reseau.
    C'etait la totalite des « 25 a 40 minutes » annoncees, le calcul ne
    pesant que quelques secondes.

    Chaque serie passe ensuite le controle qualite. Une serie trouee ou
    perimee est ECARTEE, avec son motif : completer en silence reviendrait
    a fabriquer des barres qui n'ont jamais existe.
    """
    from . import cache as ch
    from . import qualite as ql

    bench_brut = ch.charge(bench_tk, annees=ans)
    bench = enrich(bench_brut)
    journal(f"    indice de reference {bench_tk} : {len(bench_brut)} barres")

    brutes, echecs = ch.charge_lot(tickers, annees=ans, journal=journal)
    series, rates = {}, [f"{tk} ({m})" for tk, m in echecs]
    refuses = 0
    for tk, brut in brutes.items():
        rap = ql.controle(brut, bench_brut, ticker=tk, exige_recent=False)
        if not rap.utilisable:
            rates.append(f"{tk} ({rap.resume()})")
            refuses += 1
            continue
        d = enrich(brut, bench_close=bench_brut["close"])
        if len(d) >= 400:
            series[tk] = d
        else:
            rates.append(f"{tk} (historique {len(d)} barres)")
    if refuses:
        journal(f"    {refuses} titre(s) ecarte(s) par le controle qualite")
    return bench, series, rates


def _plie(texte: str, largeur: int = 66) -> list[str]:
    """Coupe un paragraphe en lignes, sans couper les mots."""
    mots, lignes, cur = texte.split(), [], ""
    for m in mots:
        if len(cur) + len(m) + 1 > largeur:
            lignes.append(cur)
            cur = m
        else:
            cur = f"{cur} {m}".strip()
    if cur:
        lignes.append(cur)
    return lignes


def tableau(titre, m, journal=print):
    journal(f"\n  {titre}")
    journal(f"    trades              {m['n']}")
    journal(f"    profit factor       {m['pf']:.2f}")
    journal(f"    esperance           {m['ev_R']:+.3f} R   ({m['ev_pct']:+.2f} %)")
    journal(f"    taux de reussite    {m['taux']:.1f} %")
    journal(f"    duree moyenne       {m['duree']:.0f} seances")
    journal(f"    rendement moyen     {m['reel']:+.2f} %  "
            f"contre {m['hasard']:+.2f} % au hasard")
    journal(f"    z                   {m['z']:+.2f}")
    journal(f"    drawdown max        {m['dd']:.1f} %  "
            f"(valorisation {m.get('dd_source', '?')}, "
            f"realise seul {m.get('dd_realise', 0):.1f} %)")
    journal(f"    portefeuille        {m['pris']} pris, {m['ecartes']} ecartes "
            f"(5 positions max)")
    journal(f"    plafond de poids    {R.MAX_WEIGHT:.0%} par ligne  "
            f"({m.get('rognees', 0)} ligne(s) reduite(s) a l'entree, "
            f"poids max atteint {m.get('poids_max', 0):.1f} %)")
    if m["motifs"]:
        journal(f"    sorties             " +
                ", ".join(f"{k} {v}" for k, v in m["motifs"].items()))


def lance(tickers, csv=None, journal=print, univers: str = ""):
    """Rejeu complet sur un univers.

    `univers` est la CLE de l'univers (« sp500 », « us »...). Elle sert a
    retrouver une composition d'epoque figee, et a avertir quand il n'y
    en a pas.
    """
    from . import audit as ad

    if isinstance(tickers, str):
        # Garde-fou : une chaine a len() et s'itere caractere par
        # caractere. Passer "sp500" ici rejouait les regles sur cinq
        # titres nommes s, p, 5, 0 et 0, sans qu'aucune erreur ne sorte.
        raise TypeError("lance() attend une LISTE de tickers, pas la chaine "
                        f"{tickers!r}. Utilise data.UNIVERS[{tickers!r}][1]().")
    tickers = list(tickers)

    journal(f"\n  PHASE 0 — {len(tickers)} titres")
    journal(f"  in-sample {IN_DEBUT[:4]}-{IN_FIN[:4]}   "
            f"hors echantillon {OOS_DEBUT[:4]}-{OOS_FIN[:4]}")
    journal(f"  parametres FIGES, aucun grid search")
    journal(f"  empreinte des parametres : {ad.empreinte()[:16]}…\n")

    # Chantier n°1 : composition d'epoque si elle existe, avertissement
    # explicite sinon. On ne masque pas un biais qu'on ne sait pas corriger.
    if univers:
        histo, jour = dl.univers_a_la_date(univers, IN_DEBUT)
        if histo:
            journal(f"  Composition figee du {jour} : {len(histo)} titres "
                    f"(au lieu de la liste actuelle).")
            tickers = histo
        mot = dl.avertissement(univers, IN_DEBUT)
        if mot:
            for bout in _plie(mot, 66):
                journal(f"  {bout}")
            journal("")
    journal("  Chargement...")
    bench, series, rates = charge_univers(tickers, journal=journal)
    journal(f"  {len(series)} titres exploitables"
            + (f", {len(rates)} ecartes" if rates else ""))
    for motif in rates[:8]:
        journal(f"    ecarte : {motif}")
    if len(rates) > 8:
        journal(f"    ... et {len(rates) - 8} autres")
    if not series:
        journal("  Aucune serie exploitable : rien a tester. "
                "Verifie la connexion et la liste de tickers.")
        return False, {}

    journal("\n  Rejeu des regles...")
    tr_in, tr_oos = [], []
    for tk, d in series.items():
        tr_in += bt.trades_ticker(d, tk, bench, IN_DEBUT, IN_FIN)
        tr_oos += bt.trades_ticker(d, tk, bench, OOS_DEBUT, OOS_FIN)

    m_in = mesures(tr_in, series, IN_DEBUT, IN_FIN)
    m_oos = mesures(tr_oos, series, OOS_DEBUT, OOS_FIN)
    tableau("IN-SAMPLE (calibration, ne decide de rien)", m_in, journal)
    tableau("HORS ECHANTILLON (c'est lui qui decide)", m_oos, journal)

    ok, crit = verdict(m_oos)
    journal("\n  CRITERES GO/NO-GO")
    for nom, passe, val in crit:
        journal(f"    {'PASSE ' if passe else 'ECHOUE'}  {nom:<28} {val}")

    if ok:
        journal("\n  Robustesse (+-20 % sur chaque parametre)...")
        for nom, val, n, pf, bon in robustesse(list(series), bench, series):
            journal(f"    {'OK  ' if bon else 'NON '}  {nom:<26} "
                    f"valeur {val:<6} {n:4d} trades  PF {pf:.2f}")

    # L'audit avait raison : un avantage qui disparait des que les couts
    # montent n'est pas un avantage. On le mesure au lieu de l'esperer.
    journal("\n  SENSIBILITE AUX COUTS  (hors echantillon)")
    journal(f"    {'hypothese':<30}{'trades':>8}{'PF':>7}{'EV/trade':>10}")
    _j1, _c, _s = bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE
    for lib, j1, co, sl in [("cloture du jour, sans frais", False, 0.0, 0.0),
                            ("ouverture J+1, sans frais", True, 0.0, 0.0),
                            ("J+1 + 0,15 % par cote", True, 0.0010, 0.0005),
                            ("J+1 + 0,30 % par cote", True, 0.0020, 0.0010)]:
        bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE = j1, co, sl
        tr = []
        for tk, d in series.items():
            tr += bt.trades_ticker(d, tk, bench, OOS_DEBUT, OOS_FIN)
        rs = [x.R for x in tr]
        pfv = profit_factor(rs)
        ev = (sum(rs) / len(rs)) if rs else 0.0
        journal(f"    {lib:<30}{len(tr):>8}{pfv:>7.2f}{ev:>+10.3f}")
    bt.EXECUTION_J1, bt.COUT_PAR_COTE, bt.SLIPPAGE = _j1, _c, _s
    journal("    Si l'avantage ne survit pas a la derniere ligne, il n'existe pas.")

    # Les cinq criteres rendent des POINTS. Les epreuves ci-dessous disent
    # ce que ces points valent : reparti ou concentre, robuste a l'ordre
    # des trades, et mesure avec quelle precision.
    if tr_oos:
        try:
            from . import robuste as rbs
            rbs.rapport(tr_oos, journal=journal)
        except Exception as exc:
            journal(f"  Epreuves de robustesse indisponibles "
                    f"({type(exc).__name__}: {exc}).")

    journal("\n  " + "=" * 62)
    if ok:
        journal("  GO — les cinq criteres passent sur donnees hors echantillon.")
        journal("  Etape suivante : le comparatif contre SMH, net d'impot.")
        try:
            from . import comparatif as cp
            courbe = bt.portefeuille(tr_oos, series=series,
                                     max_poids=R.MAX_WEIGHT)["courbe"]
            ref = dl.load_yf("SMH", years=20)["close"]
            ref = ref[(ref.index >= courbe.index[0])
                      & (ref.index <= courbe.index[-1])]
            cp.rapport(cp.compare(courbe, ref, "SMH"), journal)
        except Exception as exc:
            journal(f"  Comparatif indisponible ({type(exc).__name__}: {exc}).")
            journal("  Lance-le a part : py -m equity_scanner.comparatif")
    else:
        journal("  NO-GO — le systeme n'a pas demontre d'edge.")
        journal("  SMH ne bouge pas, le sleeve reste vide, la philosophie ne")
        journal("  change pas. C'est un resultat, pas un echec : tu viens")
        journal("  d'economiser le cout d'une strategie non validee.")
    journal("  " + "=" * 62 + "\n")

    if csv and tr_oos:
        pd.DataFrame([{
            "ticker": t.ticker, "entree": t.entree_d.date(),
            "sortie": t.sortie_d.date(), "prix_entree": round(t.entree, 2),
            "prix_sortie": round(t.sortie, 2), "stop": round(t.stop0, 2),
            "R": round(t.R, 3), "rendement_pct": round(t.rendement * 100, 2),
            "barres": t.barres, "motif": t.motif} for t in tr_oos]).to_csv(
            csv, index=False)
        journal(f"  Trades hors echantillon : {csv}\n")
    return ok, m_oos


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--univers", choices=["us", "sp500", "europe", "cac40"],
                   default="us")
    p.add_argument("--tickers", default="")
    p.add_argument("--csv", default=None)
    a = p.parse_args()
    tables = {"us": dl.us_tickers_fige, "sp500": dl.sp500_tickers,
              "europe": dl.europe_tickers, "cac40": dl.cac40_tickers_fige}
    tk = ([x.strip().upper() for x in a.tickers.split(",") if x.strip()]
          or tables[a.univers]())
    lance(tk, a.csv, univers=("" if a.tickers else a.univers))


if __name__ == "__main__":
    main()
