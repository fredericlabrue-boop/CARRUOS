"""Controle du moteur : equivalence, non-regression, et parametres geles.

    py -m equity_scanner.test_moteur

Trois familles de verifications.

  1. EQUIVALENCE. Le backtest evalue les treize blocs en numpy, d'un coup
     sur toute la serie, parce qu'un appel par barre mettrait des heures.
     Son docstring affirmait que l'egalite avec `evaluate()` etait
     « verifiee par test » — le test n'existait pas. Il existe maintenant,
     et il compare barre a barre sur plusieurs series.

  2. NON-REGRESSION. Un test par defaut corrige. Chacun echouerait sur la
     version d'avant : ils sont ecrits pour ca, pas pour decorer.

  3. PARAMETRES GELES. L'empreinte SHA256 des constantes de strategie est
     ecrite en dur ici. Si quelqu'un — humain ou machine — deplace un
     seuil pour faire passer un backtest, ce test tombe et dit lequel.
     C'est la regle absolue du projet, rendue executable.

Aucun reseau, aucune ecriture hors d'un dossier temporaire.
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pandas as pd

ECHECS: list[str] = []

# Empreinte des parametres au moment ou la strategie a ete figee.
# NE PAS mettre a jour pour faire passer le test : si elle a change, c'est
# qu'un parametre a bouge, et c'est CA qu'il faut regarder.
EMPREINTE_GELEE = ("827439d2d46ccbea1c021394f4a0fba3628045546b21bf767db2416c"
                   "78f5c127")


def ok(nom: str, cond) -> None:
    cond = bool(cond)
    print(f"  {'PASS ' if cond else 'ÉCHEC'}  {nom}")
    if not cond:
        ECHECS.append(nom)


# ---------------------------------------------------------------------
# Series synthetiques
# ---------------------------------------------------------------------
def serie(n=1200, seed=3, derive=0.0004, vol=0.014, depart=100.0,
          debut="2015-01-02") -> pd.DataFrame:
    r = np.random.default_rng(seed)
    c = [depart]
    for _ in range(n - 1):
        c.append(c[-1] * (1 + derive + r.normal(0, vol)))
    c = np.array(c)
    i = pd.bdate_range(debut, periods=n)
    o = np.concatenate([[c[0]], c[:-1]]) * (1 + r.normal(0, 0.002, n))
    return pd.DataFrame({
        "open": o,
        "high": np.maximum(o, c) * (1 + abs(r.normal(0, 0.004, n))),
        "low": np.minimum(o, c) * (1 - abs(r.normal(0, 0.004, n))),
        "close": c, "volume": r.uniform(5e6, 2.5e7, n)}, index=i)


# ---------------------------------------------------------------------
def test_parametres_geles() -> None:
    from . import audit as ad
    from .indicators import PERIODES
    from . import rules as R

    print("\n— Parametres geles (regle absolue du projet) —")
    ok("PERIODES inchangees : RSI 14, MACD 12-26-9, Bollinger 20/2, "
       "SMA 200/50, EMA 20",
       PERIODES["rsi"] == 14 and PERIODES["macd"] == (12, 26, 9)
       and PERIODES["bb"] == (20, 2.0) and PERIODES["sma_longue"] == 200
       and PERIODES["sma_moyenne"] == 50 and PERIODES["ema_courte"] == 20)
    ok("seuils de rules.py inchanges",
       (R.PULLBACK_WINDOW, R.RSI_ZONE, R.RSI_FLOOR, R.EMA_BAND_ATR,
        R.RVOL_MIN, R.STOP_ATR_MULT, R.MAX_POSITIONS)
       == (10, (40.0, 55.0), 40.0, 0.5, 1.2, 1.5, 5))
    actuelle = ad.empreinte()
    ok(f"empreinte SHA256 identique a celle de la specification "
       f"({actuelle[:12]}…)", actuelle == EMPREINTE_GELEE)
    if actuelle != EMPREINTE_GELEE:
        print(f"          -> attendue {EMPREINTE_GELEE[:32]}…")
        print(f"          -> obtenue  {actuelle[:32]}…")
        print("          -> un parametre a change. Le resultat de toute")
        print("             validation anterieure ne s'applique plus.")


def test_indicateurs() -> None:
    from .indicators import bars_since_high, enrich

    print("\n— Indicateurs —")
    d = serie(600, seed=5)
    ancienne = d["high"].rolling(60, min_periods=60).apply(
        lambda w: float(len(w) - 1 - int(np.argmax(w))), raw=True)
    nouvelle = bars_since_high(d["high"], 60)
    ok("bars_since_high vectorise : valeurs identiques a rolling().apply()",
       np.allclose(ancienne.dropna(), nouvelle.dropna()))
    ok("bars_since_high vectorise : memes NaN de chauffe",
       (ancienne.isna() == nouvelle.isna()).all())

    # rvol et rs doivent SUIVRE la conversion de calendrier.
    e = enrich(d, bench_close=d["close"] * 0.9,
               periodes={"vol_ma": 4, "sma_moyenne": 5, "sma_longue": 40})
    ok("rvol suit la conversion de calendrier (vol_ma=4)",
       int(e["rvol"].notna().sum()) == len(d) - 3)
    ok("rs_ma50 suit la conversion de calendrier (sma_moyenne=5)",
       int(e["rs_ma50"].notna().sum()) == len(d) - 4)
    ej = enrich(d, bench_close=d["close"] * 0.9)
    ok("en journalier, rien ne change : rvol sur 20 barres",
       int(ej["rvol"].notna().sum()) == len(d) - 19)

    from .indicators import colonnes_manquantes
    ok("colonnes_manquantes signale l'absence d'indice de reference",
       colonnes_manquantes(enrich(d)) == ["rs", "rs_ma50", "rs_6m"])


def test_regles() -> None:
    from .indicators import enrich
    from . import rules as R

    print("\n— Regles : bornes de fenetre —")
    b = serie(400, seed=11, derive=0.0006, vol=0.009, depart=400.0)
    d = enrich(serie(400, seed=7), bench_close=b["close"])

    # Defaut corrige : i positif < PULLBACK_WINDOW produisait une tranche
    # a borne negative, donc une fenetre VIDE et un stop a NaN.
    s = R.evaluate(d, "X", True, i=5, days_to_earnings=30)
    ok("barre precoce : la fenetre de repli n'est pas vide (stop calcule)",
       np.isfinite(s.stop) or "ATR" in " ".join(s.vetos))
    ok("barre precoce : la date rendue est bien celle de la barre",
       s.date == d.index[5])

    # i=0 n'a pas de veille : le declencheur n'est pas evaluable.
    leve = False
    try:
        R.evaluate(d, "X", True, i=0, days_to_earnings=30)
    except ValueError:
        leve = True
    ok("barre 0 refusee au lieu de comparer a la derniere barre du futur",
       leve)

    hors = False
    try:
        R.evaluate(d, "X", True, i=10_000, days_to_earnings=30)
    except IndexError:
        hors = True
    ok("indice hors serie refuse", hors)

    # Sans indice de reference, la force relative n'est pas mesurable.
    sans = enrich(serie(400, seed=7))
    s2 = R.evaluate(sans, "X", True, days_to_earnings=30)
    ok("sans indice : force relative declaree non calculee, veto pose",
       not s2.fired and any("FORCE RELATIVE" in v for v in s2.vetos))


def test_equivalence() -> None:
    from . import backtest as bt
    from .indicators import enrich
    from .rules import evaluate

    print("\n— Equivalence : signaux_vectorises == evaluate, barre a barre —")
    total_sig, total_diff = 0, 0
    for seed in (3, 17, 42):
        braw = serie(1200, seed=seed + 100, derive=0.0005, vol=0.009,
                     depart=400.0)
        d = enrich(serie(1200, seed=seed), bench_close=braw["close"])
        bo = enrich(braw).reindex(d.index).ffill()
        vec = bt.signaux_vectorises(d, bo)
        diff = []
        for i in range(230, len(d)):
            bench_ok = bool(bo["close"].iloc[i] > bo["sma200"].iloc[i])
            s = evaluate(d, "X", bench_ok, i=i, days_to_earnings=30)
            # Le vectorise n'evalue que les vetos calculables sur
            # historique : on ecarte les autres de la comparaison.
            vetos = [v for v in s.vetos
                     if "RÉSULTATS" not in v and "ouverte" not in v
                     and "positions" not in v]
            if (all(s.blocks.values()) and not vetos) != bool(vec[i]):
                diff.append(i)
        total_sig += int(vec[230:].sum())
        total_diff += len(diff)
    ok(f"3 series x ~970 barres, {total_sig} signaux : aucun desaccord",
       total_diff == 0)

    # Une colonne absente n'est pas une condition fausse.
    leve = False
    try:
        d2 = enrich(serie(600, seed=8))
        bt.signaux_vectorises(d2, enrich(serie(600, seed=9)).reindex(d2.index))
    except ValueError:
        leve = True
    ok("colonne d'indicateur absente : erreur explicite au lieu de zero "
       "signal en silence", leve)


def test_moteur_backtest() -> None:
    from . import backtest as bt
    from . import rules as R
    from .indicators import enrich

    print("\n— Moteur de backtest —")
    braw = serie(1200, seed=111, derive=0.0005, vol=0.009, depart=400.0)
    bench = enrich(braw)
    d = enrich(serie(1200, seed=3), bench_close=braw["close"])

    # La fenetre du stop doit SUIVRE PULLBACK_WINDOW : sinon le test de
    # robustesse de la Phase 0 ne teste rien.
    base = bt.trades_ticker(d, "X", bench)
    R.PULLBACK_WINDOW = 4
    try:
        etroit = bt.trades_ticker(d, "X", bench)
    finally:
        R.PULLBACK_WINDOW = 10
    stops_base = [round(t.stop0, 4) for t in base]
    stops_etroit = [round(t.stop0, 4) for t in etroit]
    ok("decaler PULLBACK_WINDOW change reellement les stops du moteur",
       stops_base != stops_etroit)

    # Deux sorties le meme jour ne doivent pas s'ecraser.
    T = bt.Trade
    paire = [T("A", pd.Timestamp("2022-01-03"), pd.Timestamp("2022-02-03"),
               100, 90, 95, 2, 20, "stop"),
             T("B", pd.Timestamp("2022-01-04"), pd.Timestamp("2022-02-03"),
               100, 130, 95, 2, 20, "duree")]
    p = bt.portefeuille(paire)
    ok("sorties simultanees : la courbe garde le depart et l'arrivee",
       len(p["courbe"]) >= 2)

    # Drawdown : les pertes latentes doivent se voir.
    idx = pd.bdate_range("2022-01-03", periods=40)
    px = pd.Series(np.concatenate([np.linspace(100, 70, 20),
                                   np.linspace(70, 130, 20)]), index=idx)
    ser = {"A": pd.DataFrame({"close": px}, index=idx)}
    t = T("A", idx[0], idx[-1], 100.0, 130.0, 95.0, 2.0, 39, "duree")
    sans = bt.portefeuille([t])
    avec = bt.portefeuille([t], series=ser)
    ok("drawdown quotidien : la perte latente de -6 R apparait",
       avec["dd"] > 0.05 and sans["dd"] == 0.0)
    ok("drawdown quotidien : le capital final reste le meme",
       abs(avec["final"] - sans["final"]) < 1e-6)
    ok("la source du drawdown est annoncee",
       avec["dd_source"] == "quotidienne"
       and sans["dd_source"] == "sorties seulement")

    # Taille de ligne calculee sur le capital d'ENTREE.
    suite = [T("A", pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-10"),
               100, 110, 95, 2, 5, "x"),
             T("B", pd.Timestamp("2022-01-11"), pd.Timestamp("2022-01-20"),
               100, 110, 95, 2, 7, "x")]
    r = bt.portefeuille(suite, risque=0.01, capital=10_000.0)
    attendu = 10_000.0
    for tr in suite:
        attendu += attendu * 0.01 * tr.R
    ok("capital compose sur la mise du jour d'entree",
       abs(r["final"] - attendu) < 1e-6)


def test_phase0() -> None:
    from . import backtest as bt
    from . import phase0
    from .indicators import enrich


    print("\n— Phase 0 —")
    braw = serie(2000, seed=211, derive=0.0005, vol=0.009, depart=400.0)
    bench = enrich(braw)
    d = enrich(serie(2000, seed=13), bench_close=braw["close"])
    trades = bt.trades_ticker(d, "X", bench, "2022-01-01", "2026-12-31")
    if len(trades) < 20:
        trades = bt.trades_ticker(d, "X", bench)

    # Les tirages au hasard doivent rester dans la fenetre des trades.
    _reel, _mu, z1 = phase0.z_contre_hasard(
        trades, {"X": d}, debut="2022-01-01", fin="2026-12-31")
    _r2, _m2, z2 = phase0.z_contre_hasard(trades, {"X": d})
    ok("z_contre_hasard accepte une fenetre explicite",
       np.isfinite(z1) and np.isfinite(z2))

    # Memes couts des deux cotes.
    import inspect
    src = inspect.getsource(phase0.z_contre_hasard)
    ok("le hasard paie les memes couts que le systeme (J+1 + slippage)",
       "COUT_PAR_COTE" in src and "SLIPPAGE" in src)

    # Une chaine a la place d'une liste doit etre refusee.
    leve = False
    try:
        phase0.lance("sp500")
    except TypeError:
        leve = True
    ok("lance() refuse une chaine ('sp500' valait 5 titres s, p, 5, 0, 0)",
       leve)


def test_pead() -> None:
    from . import pead
    from .indicators import enrich

    print("\n— Derive post-annonce —")
    braw = serie(1500, seed=311, derive=0.0005, vol=0.009, depart=400.0)
    bo = enrich(braw)
    # Titre au calendrier decale : c'est le cas qui faisait lire l'indice
    # a une AUTRE date.
    d = enrich(serie(1200, seed=23, debut="2016-03-01"),
               bench_close=braw["close"])
    aligne = pead.aligne(bo, d.index)
    ok("l'indice est realigne sur le calendrier du titre",
       len(aligne) == len(d) and (aligne.index == d.index).all())
    ok("l'alignement ne cree pas de valeurs manquantes en fin de serie",
       bool(np.isfinite(aligne["close"].iloc[-1])))
    memes = pead.aligne(bo, bo.index)
    ok("un calendrier deja identique n'est pas recopie inutilement",
       memes is bo)


def test_comparatif() -> None:
    from . import comparatif as cp

    print("\n— Comparatif net d'impot —")
    idx = pd.to_datetime(["2022-03-01", "2022-12-30", "2023-12-29"])
    courbe = pd.Series([12000.0, 13000.0, 15000.0], index=idx)
    s = cp.systeme_net(courbe, 10_000.0)
    ok("l'annee 1 part du capital de depart, pas du premier point de courbe",
       abs(s["detail"][0]["debut"] - 10_000.0) < 1e-6)
    ok("barre_a_franchir ne sature plus sur une periode courte",
       cp.barre_a_franchir(0.15, 0.4) < 0.30)
    ok("la barre monte avec l'horizon (impot differe du buy & hold)",
       cp.barre_a_franchir(0.15, 10) > cp.barre_a_franchir(0.15, 3))


def test_qualite() -> None:
    import datetime as dt

    from . import qualite as ql

    print("\n— Controle qualite des donnees —")
    saine = serie(600, seed=31, debut="2023-01-02")
    bench = serie(600, seed=32, debut="2023-01-02")
    jour = saine.index[-1].date() + dt.timedelta(days=1)

    def verdict(d, b=bench):
        return ql.controle(d, b, "T", aujourdhui=jour)

    ok("serie saine acceptee", verdict(saine).utilisable)

    trouee = saine.drop(saine.index[300:325])
    ok("25 seances manquantes : refusee", not verdict(trouee).utilisable)

    split = saine.copy()
    split.iloc[350:, :4] = split.iloc[350:, :4] / 4.0
    ok("division par 4 non ajustee : refusee", not verdict(split).utilisable)

    krach = saine.copy()
    kb = bench.copy()
    krach.iloc[400:, :4] *= 0.55
    kb.iloc[400:, :4] *= 0.55
    ok("krach general titre + indice : ce n'est PAS une division",
       verdict(krach, kb).utilisable)

    mort = saine.copy()
    mort.iloc[-6:, mort.columns.get_loc("volume")] = 0.0
    ok("six seances sans echange : refusee", not verdict(mort).utilisable)

    casse = saine.copy()
    casse.iloc[10, casse.columns.get_loc("high")] = 1.0
    ok("plus haut sous le plus bas : refusee", not verdict(casse).utilisable)

    ok("serie arretee il y a 30 seances : refusee",
       not verdict(saine.iloc[:-30]).utilisable)
    ok("historique de 120 barres : refuse (SMA200 impossible)",
       not verdict(saine.iloc[-120:]).utilisable)

    gardees, refusees = ql.filtre({"BON": saine, "SPLIT": split},
                                  bench, exige_recent=False)
    ok("filtre() separe et donne le motif de chaque refus",
       list(gardees) == ["BON"] and len(refusees) == 1
       and "division" in refusees[0][1])


def test_audit() -> None:
    from . import audit as ad
    from . import rules as R
    from .indicators import enrich

    print("\n— Journal d'audit —")
    b = serie(400, seed=41, derive=0.0006, vol=0.009, depart=400.0)
    d = enrich(serie(400, seed=42), bench_close=b["close"])
    s = R.evaluate(d, "AAPL", True, days_to_earnings=30)

    emp = ad.empreinte()
    rec = ad.ligne(s, d, source="test")
    ok("identifiant reproductible a partir du contenu",
       rec["id"] == ad.identifiant("AAPL", rec["date_barre"], emp))
    ok("les treize blocs sont journalises", len(rec["blocs"]) == 13)
    ok("les indicateurs de la barre sont releves",
       len(rec["indicateurs"]) >= 20)
    ok("aucun NaN dans le JSON (non serialisable en JSON strict)",
       all(v is None or isinstance(v, (int, float))
           for v in rec["indicateurs"].values()))

    avant = ad.empreinte()
    R.RSI_FLOOR = 35.0
    try:
        apres = ad.empreinte()
    finally:
        R.RSI_FLOOR = 40.0
    ok("deplacer un parametre gele change l'empreinte", avant != apres)
    ok("le remettre en place restaure l'empreinte", ad.empreinte() == avant)

    from pathlib import Path
    chemin = Path(tempfile.mkdtemp()) / "audit.jsonl"
    ad.enregistre(s, d, fichier=chemin)
    R.RSI_FLOOR = 35.0
    try:
        ad.enregistre(R.evaluate(d, "MSFT", True, days_to_earnings=30), d,
                      fichier=chemin)
    finally:
        R.RSI_FLOOR = 40.0
    v = ad.verifie(chemin)
    ok("un changement de parametre en cours de journal est detecte",
       v["parametres_changes"] and len(v["empreintes"]) == 2)
    ok("aucun identifiant incoherent", not v["identifiants_incoherents"])


def test_robuste() -> None:
    from . import robuste as rb
    from .backtest import Trade

    print("\n— Epreuves de robustesse —")

    def faux(rs, debut="2022-01-03"):
        idx = pd.bdate_range(debut, periods=len(rs) * 8 + 10)
        return [Trade("T", idx[k * 8], idx[k * 8 + 5], 100.0,
                      100.0 + R * 5 + 0.1, 95.0, 2.0, 5, "x")
                for k, R in enumerate(rs)]

    rng = np.random.default_rng(4)
    concentre = list(rng.normal(-0.10, 0.35, 160))
    concentre[40:56] = list(np.full(16, 2.6))
    reparti = list(rng.normal(0.10, 0.35, 160))

    vc = rb.verdict_walk_forward(rb.walk_forward(faux(concentre)))
    vr = rb.verdict_walk_forward(rb.walk_forward(faux(reparti)))
    ok("un gain concentre sur une seule fenetre est signale",
       not vc["stable"] and vc["concentration"] > 0.5)
    ok("un gain reparti n'est pas signale", vr["stable"])

    mc = rb.monte_carlo(faux(reparti), tirages=500)
    ok("Monte Carlo : le 95e centile du drawdown depasse celui observe",
       mc["dd_p95"] >= mc["dd_observe"])
    ok("Monte Carlo : un risque de ruine est chiffre",
       0.0 <= mc["risque_ruine"] <= 1.0)

    bs = rb.bootstrap(faux(reparti))
    ok("bootstrap : l'intervalle encadre la valeur observee",
       bs["pf_bas"] <= bs["pf_observe"] <= bs["pf_haut"])
    ok("bootstrap : le tirage se fait par blocs, pas trade par trade",
       bs["bloc"] > 1)

    bas, _c, haut = rb.wilson(6, 13)
    ok("Wilson sur 6 gagnants / 13 trades : intervalle ~23 % a 71 %",
       22 < bas < 25 and 69 < haut < 73)
    ok("Wilson sur 0 trade rend l'intervalle complet",
       rb.wilson(0, 0) == (0.0, 0.0, 100.0))


def test_cache() -> None:
    import time

    from . import cache as ch
    from . import data as dl

    print("\n— Cache et chargement parallele —")
    appels = {"n": 0}
    vrai = dl.load_yf

    def faux(tk, years=3, **kw):
        appels["n"] += 1
        time.sleep(0.03)
        if tk == "CASSE":
            raise ValueError("aucune donnee pour CASSE")
        return serie(300, seed=abs(hash(tk)) % 10_000, debut="2023-01-02")

    dl.load_yf = faux
    try:
        ch.oublie()
        tickers = [f"T{i:03d}" for i in range(24)] + ["CASSE"]
        t0 = time.perf_counter()
        s, e = ch.charge_lot(tickers, fils=8)
        parallele = time.perf_counter() - t0
        sequentiel = len(tickers) * 0.03
        ok(f"25 titres en {parallele:.2f} s contre {sequentiel:.2f} s "
           f"l'un apres l'autre", parallele < sequentiel * 0.5)
        ok("24 series chargees, 1 echec rapporte avec son ticker",
           len(s) == 24 and e and e[0][0] == "CASSE")

        ch.oublie()                       # on vide la memoire, pas le disque
        avant = appels["n"]
        t0 = time.perf_counter()
        s2, _ = ch.charge_lot(tickers, fils=8)
        chaud = time.perf_counter() - t0
        ok("cache disque : une seule tentative reseau (le ticker en echec)",
           appels["n"] - avant == 1)
        ok(f"cache disque : {chaud:.3f} s au lieu de {parallele:.2f} s",
           chaud < parallele)
        ok("series identiques apres relecture du cache",
           all(s[k].equals(s2[k]) for k in s))

        ok("data.loader() resout la fonction a l'appel (substitution "
           "possible en test)", dl.loader("yf") is faux)
    finally:
        dl.load_yf = vrai
        ch.oublie()


def test_resolve_et_app() -> None:
    import inspect
    import re

    from . import app
    from . import resolve as rs

    print("\n— Resolution et interface —")
    ok("la table ALIAS est consultee : SANOFI -> SAN.PA",
       rs.candidats("SANOFI") == ["SAN.PA"])
    ok("un code d'un autre fournisseur est traduit : SASY -> SAN.PA",
       rs.candidats("SASY") == ["SAN.PA"])
    ok("un ticker deja qualifie passe sans detour",
       rs.candidats("MC.PA") == ["MC.PA"])
    ok("un mnemonique US inconnu essaie toujours les places",
       rs.candidats("ZZZZ")[0] == "ZZZZ" and len(rs.candidats("ZZZZ")) > 1)

    src = inspect.getsource(app)
    ok("app importe le module news au niveau module",
       bool(re.search(r"^from \. import news as nw", src, re.M)))
    scan = src.split("def _scan")[1].split("\ndef ")[0]
    # On regarde le CODE, pas le commentaire qui raconte le defaut corrige.
    corps = scan.split('"""')[-1]
    code = "\n".join(l for l in corps.splitlines()
                     if not l.lstrip().startswith("#"))
    ok("_scan ne passe plus days_to_earnings=None en dur",
       "days_to_earnings=None" not in code
       and "days_to_earnings=jours" in code)
    ok("_scan consulte le calendrier des resultats",
       "earnings_map" in scan)
    ok("_scan passe par le cache parallele", "charge_lot" in scan)
    ok("_scan controle la qualite avant d'evaluer", "ql.controle" in scan)
    ok("_scan journalise dans l'audit", "ad.enregistre" in scan)
    val = src.split("def _val_lance")[1].split("\ndef ")[0]
    ok("le bouton VALIDATION passe une liste de tickers, pas une chaine",
       'phase0.lance("sp500"' not in val and "tables_univers()" in val)


def test_univers_figes() -> None:
    from . import data as dl

    print("\n— Univers historiques (biais du survivant) —")
    dl.figer_univers("cac40", ["MC.PA", "OR.PA", "TTE.PA"], date="2020-06-30")
    dl.figer_univers("cac40", ["MC.PA", "OR.PA"], date="2024-01-02")
    tk, jour = dl.univers_a_la_date("cac40", "2021-01-01")
    ok("la composition rendue est la plus proche AVANT la date",
       jour == "2020-06-30" and len(tk) == 3)
    tk2, jour2 = dl.univers_a_la_date("cac40", "2025-01-01")
    ok("une composition plus recente est utilisee quand elle existe",
       jour2 == "2024-01-02" and len(tk2) == 2)
    ok("aucune composition avant la date : rien n'est invente",
       dl.univers_a_la_date("cac40", "2015-01-01") == ([], ""))
    ok("l'avertissement de biais du survivant est explicite",
       "BIAIS DU SURVIVANT" in dl.avertissement("cac40", "2010-01-01"))
    ok("pas d'avertissement quand une composition d'epoque couvre la periode",
       dl.avertissement("cac40", "2021-01-01") == "")


def main() -> int:
    os.chdir(tempfile.mkdtemp())      # aucune ecriture dans le dossier reel
    test_parametres_geles()
    test_indicateurs()
    test_regles()
    test_equivalence()
    test_moteur_backtest()
    test_phase0()
    test_pead()
    test_comparatif()
    test_qualite()
    test_audit()
    test_robuste()
    test_cache()
    test_resolve_et_app()
    test_univers_figes()

    print()
    if ECHECS:
        print(f"  {len(ECHECS)} ECHEC(S) :")
        for e in ECHECS:
            print(f"    - {e}")
        return 1
    print("  Moteur sain : tous les controles passent.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
