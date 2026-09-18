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

# Les deux autres hypotheses du registre ont leurs propres constantes, donc
# leur propre empreinte. Trois empreintes separees, pas une seule : quand
# l'une bouge, on sait laquelle.
EMPREINTE_PEAD = ("d32cd9bf113ec0d70654224b21a03312e456d66a6e0f09e48f5ef801"
                  "78f8bd55")
EMPREINTE_SHORT = ("47d593c5c32df36d3e6336952a0968771d74cffb441668ffcff2fa7"
                   "d3b8ba63a")

# Empreinte des DOCUMENTS de specification, qui n'est pas la meme chose que
# celle des constantes : l'une protege le texte, l'autre le code.
DOCS_GELES = {
    "derive-post-annonce-v1.md":
        "f37d22bd76d253a4c686edb8fe1debb394490240593cc400a423a6f8fb428dee",
    "strategie-short-v1.md":
        "bc6a8d1798c38be9ca134c38b309e1d65a1b1108b8d92b6b99fe1a7c77aa175b",
    "protocole-validation-v1.md":
        "a65538649263f69e9d3f8e465e5ae0a1a3cb85918ec6f86349438b12138063ae",
}


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

    # --- les deux autres hypotheses ---
    for nom, obtenue, attendue in (
            ("derive post-annonce (hypothese n°2)",
             ad.empreinte_pead(), EMPREINTE_PEAD),
            ("vente a decouvert (hypothese n°3)",
             ad.empreinte_short(), EMPREINTE_SHORT)):
        ok(f"empreinte des constantes de {nom} ({obtenue[:12]}…)",
           obtenue == attendue)
        if obtenue != attendue:
            print(f"          -> attendue {attendue[:32]}…")
            print(f"          -> obtenue  {obtenue[:32]}…")

    ok("les trois hypotheses ont des empreintes DISTINCTES",
       len({ad.empreinte(), ad.empreinte_pead(),
            ad.empreinte_short()}) == 3)
    ok("empreintes() rend les trois, aucune a None",
       set(ad.empreintes()) == {ad.VERSION_STRATEGIE, ad.VERSION_PEAD,
                                ad.VERSION_SHORT}
       and all(v for v in ad.empreintes().values()))

    # --- les documents de specification ---
    import hashlib
    from pathlib import Path
    racine = Path(__file__).resolve().parent.parent
    for nom, attendu in DOCS_GELES.items():
        f = racine / nom
        if not f.exists():
            ok(f"{nom} present a cote du programme", False)
            continue
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        ok(f"{nom} n'a pas ete retouche ({h[:12]}…)", h == attendu)

    from . import pead as P
    ok("pead.py cite bien l'empreinte de sa specification",
       DOCS_GELES["derive-post-annonce-v1.md"] in (P.__doc__ or ""))


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


def test_optimisations() -> None:
    """Les versions rapides doivent rendre EXACTEMENT le meme resultat.

    Une optimisation qui change un chiffre n'est pas une optimisation,
    c'est un bug plus rapide.
    """
    from . import backtest as bt
    from . import qualite as ql
    from .indicators import enrich

    print("\n— Optimisations : resultat inchange —")
    braw = serie(1500, seed=311, derive=0.0005, vol=0.009, depart=400.0)
    bench = enrich(braw)
    d = enrich(serie(1500, seed=23), bench_close=braw["close"])
    bo = bench.reindex(d.index).ffill()
    positions = np.flatnonzero(bt.signaux_vectorises(d, bo))[:200]

    col = bt.colonnes_numpy(d, bo)
    memes = True
    for i in positions:
        a = bt.simule(d, int(i), "X", bo)            # colonnes extraites seule
        b = bt.simule(d, int(i), "X", bo, col)       # colonnes pre-extraites
        if (a is None) != (b is None):
            memes = False
            break
        if a is not None and (a.entree_d != b.entree_d
                              or a.sortie_d != b.sortie_d
                              or abs(a.entree - b.entree) > 1e-12
                              or abs(a.sortie - b.sortie) > 1e-12
                              or abs(a.stop0 - b.stop0) > 1e-12
                              or a.motif != b.motif):
            memes = False
            break
    ok(f"simule : {len(positions)} signaux, trades identiques avec et sans "
       f"colonnes pre-extraites", memes)

    # Le controle qualite construisait un pd.bdate_range par COUPLE de
    # barres : 150 000 appels sur une Phase 0, soit la moitie du temps
    # total. Il coutait plus cher que le backtest qu'il protege.
    def trou_lent(index):
        pire = 0
        for a, b in zip(index[:-1], index[1:]):
            pire = max(pire, len(pd.bdate_range(a, b)) - 2)
        return max(0, pire)

    def serie_lente(masque):
        m = np.asarray(masque, dtype=bool)
        pire = cur = 0
        for x in m:
            cur = cur + 1 if x else 0
            pire = max(pire, cur)
        return pire

    rng = np.random.default_rng(3)
    accord_trou = accord_serie = True
    for k in range(6):
        idx = pd.bdate_range("2015-01-02", periods=700)
        troue = idx[rng.random(700) > 0.02 * k]
        if trou_lent(troue) != ql._plus_long_trou(troue):
            accord_trou = False
        m = rng.random(400) < (0.08 * k + 0.05)
        if serie_lente(m) != ql._plus_longue_serie(m):
            accord_serie = False
    ok("_plus_long_trou vectorise : identique a la version lente",
       accord_trou)
    ok("_plus_longue_serie vectorisee : identique a la version lente",
       accord_serie)
    ok("_plus_long_trou tient les cas limites",
       ql._plus_long_trou(pd.DatetimeIndex([])) == 0
       and ql._plus_longue_serie([]) == 0
       and ql._plus_longue_serie([True] * 5) == 5)
    ok("_seances_ouvrees accorde avec pandas",
       ql._seances_ouvrees("2024-01-01", "2024-01-05")
       == len(pd.bdate_range("2024-01-01", "2024-01-05")))


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
        trades, {"X": d}, debut="2022-01-01", fin="2026-12-31", bench=bench)
    _r2, _m2, z2 = phase0.z_contre_hasard(trades, {"X": d}, bench=bench)
    ok("z_contre_hasard accepte une fenetre explicite",
       np.isfinite(z1) and np.isfinite(z2))

    # Le temoin rejoue le MOTEUR, donc il paie exactement ce que paie un
    # vrai trade. Verifier le nom des constantes ne prouvait rien : c'est
    # le passage par simule() qui garantit l'egalite des couts.
    import inspect
    src = inspect.getsource(phase0.z_contre_hasard)
    ok("le temoin applique les memes regles de sortie (etape 6 du protocole)",
       "bt.simule(" in src)
    col = bt.colonnes_numpy(d, bench)
    i = 400
    tir = bt.simule(d, i, "X", bench, col)
    ok("un tirage paie le spread et le slippage a l'entree, comme un vrai",
       tir is None or tir.entree > float(d["open"].iloc[i + 1]))
    ok("un tirage sort par une regle, jamais sur une duree imposee",
       tir is None or tir.motif in ("stop", "regime", "sma50", "ema20",
                                    "duree"))

    # Les DEUX temoins, et le plus defavorable qui decide.
    zd = phase0.z_duree_appariee(trades, {"X": d},
                                 debut="2022-01-01", fin="2026-12-31")
    ok("le temoin a duree appariee reste disponible", np.isfinite(zd))
    ok("le critere 4 retient le plus defavorable des deux",
       phase0.z_retenu({"z": 3.0, "z_duree": 1.0}) == 1.0
       and phase0.z_retenu({"z": 1.0, "z_duree": 3.0}) == 1.0)
    ok("un seul temoin disponible : c'est lui qui sert",
       phase0.z_retenu({"z": 2.5}) == 2.5)
    _o, cr = phase0.verdict({"n": 300, "pf": 1.5, "ev_R": 0.2, "dd": 5.0,
                             "z": 4.0, "z_duree": 1.2})
    ok("un z flatteur ne suffit pas si l'autre temoin rejette",
       not _o and any("z >=" in x[0] and not x[1] for x in cr))

    print("\n— Calibration du critere 4 sur du bruit —")
    from . import calibration as cal
    ok("la graine d'un ticker est stable d'un lancement a l'autre",
       cal._graine("AAPL") == cal._graine("AAPL")
       and cal._graine("AAPL") != cal._graine("MSFT"))
    cours, tickers, btk = cal.univers_bruit(3, rep=0, seances=600)
    a = cours("Z00N00")
    b = cours("Z00N00")
    ok("le meme ticker rend exactement la meme serie",
       float((a["close"] - b["close"]).abs().max()) == 0.0)
    ok("deux titres differents ne rendent pas la meme serie",
       float((cours("Z00N01")["close"] - a["close"]).abs().max()) > 0)
    cours1, _t1, _b1 = cal.univers_bruit(3, rep=1, seances=600)
    ok("deux univers differents ne rendent pas la meme serie",
       float((cours1("Z01N00")["close"] - a["close"]).abs().max()) > 0)
    # Derive nulle : sur 600 seances, la moyenne des variations doit etre
    # indiscernable de zero. Sinon il y aurait quelque chose a trouver.
    var = a["close"].pct_change().dropna()
    ok("la derive est nulle : il n'y a rien a trouver dans ce bruit",
       abs(float(var.mean())) < 3 * float(var.std()) / len(var) ** 0.5 + 1e-4)
    ok("les colonnes attendues par le moteur sont toutes la",
       set(["open", "high", "low", "close", "volume"]) <= set(a.columns))
    ok("high >= close et low <= close, sinon le moteur lit n'importe quoi",
       bool((a["high"] >= a["close"]).all() and (a["low"] <= a["close"]).all()))

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


def test_strategie() -> None:
    """La projection est de l'ARITHMETIQUE : elle se verifie a la main."""
    from . import strategie as sg

    print("\n— Projection de reinvestissement —")
    # 10 000 EUR, 10 %/an, 1 an, sans versement, PFU 30 %, frais 1 %.
    p = sg.projette(10_000, 0.10, 1)
    L = p["lignes"][0]
    ok("capitalisant : 11 000 brut, moins 30 % de 1 000 = 10 700",
       abs(L["capitalisant_net"] - 10_700) < 0.01)
    ok("rotation : 11 000 - 100 de frais - 270 d'impot = 10 630",
       abs(L["rotation_net"] - 10_630) < 0.01
       and abs(L["frais_annee_rotation"] - 100) < 0.01
       and abs(L["impot_annee_rotation"] - 270) < 0.01)
    ok("gains retires : capital 10 000 + 700 nets = 10 700",
       abs(L["retire_capital"] - 10_000) < 0.01
       and abs(L["retire_total"] - 10_700) < 0.01)

    # A rendement nul, seuls les frais de rotation mordent.
    z = sg.projette(10_000, 0.0, 10)
    ok("rendement nul : le capitalisant ne bouge pas",
       abs(z["capitalisant_net"] - 10_000) < 0.01)
    ok("rendement nul : la rotation perd ses frais chaque annee",
       z["rotation_net"] < 9_200)

    # Ordre attendu sur longue periode : l'impot differe travaille.
    g = sg.projette(10_000, 0.08, 20)
    ok("sur 20 ans : capitalisant > rotation > gains retires",
       g["capitalisant_net"] > g["rotation_net"] > g["retire_total"])
    pea = sg.projette(10_000, 0.08, 20, impot=sg.PEA_5ANS)
    ok("une imposition plus faible laisse plus de capital",
       pea["capitalisant_net"] > g["capitalisant_net"])

    ok("la barre a franchir monte avec l'horizon",
       sg.barre_a_franchir(0.08, 20) > sg.barre_a_franchir(0.08, 3)
       > sg.barre_a_franchir(0.08, 1))
    ok("elle est toujours au-dessus du taux de reference",
       all(x["surcout"] > 0 for x in sg.table_friction(0.08)))
    ok("des versements seuls, sans capital de depart, fonctionnent",
       sg.projette(0, 0.06, 10, versement_mensuel=300)["ok"])
    ok("ni capital ni versement : refuse au lieu de rendre zero",
       not sg.projette(0, 0.06, 10)["ok"])

    print("\n— Revue d'une ligne : le cas monte-puis-redescendu —")
    from .indicators import enrich
    r = np.random.default_rng(4)
    c = [9.0]
    for _ in range(299):
        c.append(c[-1] * (1 + 0.0018 + r.normal(0, 0.012)))
    for _ in range(100):
        c.append(c[-1] * (1 - 0.0035 + r.normal(0, 0.012)))
    c = np.array(c)
    idx = pd.bdate_range("2023-01-02", periods=len(c))
    o = np.concatenate([[c[0]], c[:-1]])
    d = pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.006,
                      "low": np.minimum(o, c) * 0.994, "close": c,
                      "volume": r.uniform(2e6, 9e6, len(c))}, index=idx)
    d = enrich(d, bench_close=pd.Series(c * 40, index=idx))
    ligne = {"ticker": "TLX", "quantite": 70, "entree": 11.69,
             "stop": 10.60, "date": str(idx[150].date())}
    rv = sg.revue_ligne(ligne, d, marche_ok=True)

    ok("le plus haut releve est posterieur a l'entree",
       rv["date_plus_haut"] >= rv["depuis"])
    ok("le gain maximum atteint depasse le gain du jour",
       rv["mfe_pct"] > rv["pnl_pct"])
    ok("le recul depuis le sommet est negatif",
       rv["recul_depuis_haut_pct"] < 0)
    ok("la part du gain rendue vaut bien maximum moins aujourd'hui",
       abs(rv["gain_rendu_pct"] - (rv["mfe_pct"] - rv["pnl_pct"])) < 0.01)
    ok("les quatre conditions de sortie de la specification sont rendues",
       len(rv["sorties"]) == 4)
    ok("l'impot d'une vente immediate est chiffre",
       rv["impot_si_vente"] >= 0
       and abs(rv["net_si_vente"]
               - (rv["valeur"] - rv["impot_si_vente"])) < 0.01)

    pm = sg.point_mort_fiscal(rv)
    ok("le handicap du replacement est chiffre et positif",
       pm is not None and pm["handicap_pct"] > 0)

    # La regle absolue du projet : aucun verdict directionnel n'est
    # produit, et le texte le dit au lecteur au lieu de le laisser
    # deviner.
    texte = sg.texte_revue(rv).lower()
    ok("le texte ne rend aucun verdict directionnel",
       not [m for m in ("acheter", "haussier", "baissier", "confiance",
                        "recommand", "score") if m in texte])
    ok("il dit explicitement qu'aucun verdict n'est calcule",
       "aucun verdict" in texte)

    # Sans prix d'entree, le titre est simplement NON DETENU : on rend
    # ce qui ne depend pas d'une position, et rien de plus. Fabriquer une
    # entree fictive donnerait un P&L qui n'a jamais existe.
    print("\n— Examiner un titre qu'on ne detient pas —")
    libre = sg.revue_titre("NVDA", d, marche_ok=True)
    ok("un titre non detenu est examinable", libre["ok"])
    ok("il est marque comme non detenu", libre["detenu"] is False)
    ok("aucun gain latent n'est invente",
       libre["pnl_pct"] is None and libre["mfe_pct"] is None
       and libre["gain_rendu_pct"] is None)
    ok("aucun cout fiscal n'est invente",
       libre["impot_si_vente"] is None
       and sg.point_mort_fiscal(libre) is None)
    ok("le recul depuis le sommet est rendu quand meme",
       libre["recul_depuis_haut_pct"] <= 0)
    ok("le recul depuis le haut 52 semaines est rendu",
       libre["recul_52s_pct"] <= 0)
    ok("les conditions de sortie sont evaluees sans position",
       len(libre["sorties"]) == 4)
    ok("le texte annonce l'absence de position",
       "non detenu" in sg.texte_revue(libre))

    # Avec un prix d'entree fourni a la main, le trajet complet revient.
    avec = sg.revue_titre("NVDA", d, True, entree=11.69, quantite=70)
    ok("un prix d'entree saisi rend le trajet complet",
       avec["detenu"] and avec["pnl_pct"] is not None
       and avec["impot_si_vente"] is not None)


def test_short() -> None:
    """Hypothese n°3 : vente a decouvert. Les conventions de signe sont
    inversees, et c'est exactement la ou l'on se trompe."""
    import hashlib
    from pathlib import Path

    from . import backtest as bt
    from . import short as sh
    from .indicators import enrich

    print("\n— Vente a decouvert : specification gelee —")
    doc = Path(__file__).resolve().parent.parent / "strategie-short-v1.md"
    ok("la specification existe a cote du programme", doc.exists())
    if doc.exists():
        h = hashlib.sha256(doc.read_bytes()).hexdigest()
        ok(f"son empreinte SHA256 est celle citee par le moteur "
           f"({h[:12]}…)", h in (sh.__doc__ or ""))
    ok("les seuils sont ceux du document",
       (sh.CAR3_MAX, sh.RVOL_ANNONCE, sh.PRIX_MIN, sh.DOLLAR_VOL_MIN,
        sh.MAX_BARRES, sh.STOP_ATR, sh.MAX_POS, sh.EMPRUNT_AN)
       == (-0.050, 2.0, 10.0, 50e6, 45, 2.0, 10, 0.020))
    ok("la liquidite exigee est PLUS severe qu'a l'achat",
       sh.DOLLAR_VOL_MIN > 20e6)

    print("\n— Arithmetique d'une vente —")
    t = sh.TradeCourt("X", pd.Timestamp("2024-01-02"),
                      pd.Timestamp("2024-03-06"), entree=100.0, sortie=90.0,
                      stop0=110.0, atr=5.0, barres=45, motif="duree")
    emprunt = 100.0 * sh.EMPRUNT_AN * 45 / sh.SEANCES_AN
    ok("le risque est la distance AU-DESSUS de l'entree",
       abs(t.risque - 10.0) < 1e-9)
    ok("le cout d'emprunt court au prorata du temps de detention",
       abs(t.cout_emprunt - emprunt) < 1e-9)
    ok("vendre a 100 et racheter a 90 gagne, emprunt deduit",
       abs(t.R - (10.0 - emprunt) / 10.0) < 1e-9 and t.R > 0)
    ok("le rendement suit la meme convention",
       abs(t.rendement - (10.0 - emprunt) / 100.0) < 1e-12)

    # Un ecart d'ouverture coute PLUS que le risque prevu : c'est le
    # risque propre a la vente, il doit apparaitre tel quel.
    gap = sh.TradeCourt("X", pd.Timestamp("2024-01-02"),
                        pd.Timestamp("2024-01-20"), 100.0, 112.0, 110.0,
                        5.0, 12, "stop")
    ok("un rachat au-dessus du stop coute plus que le risque prevu",
       gap.R < -1.0)

    print("\n— Le sens de la position traverse le portefeuille —")
    idx = pd.bdate_range("2024-01-02", periods=60)
    baisse = pd.Series(np.linspace(100, 80, 60), index=idx)
    hausse = pd.Series(np.linspace(100, 120, 60), index=idx)
    tb = sh.TradeCourt("X", idx[0], idx[-1], 100.0, 80.0, 110.0, 5.0, 59,
                       "duree")
    th = sh.TradeCourt("Y", idx[0], idx[-1], 100.0, 120.0, 110.0, 5.0, 59,
                       "stop")
    pb = bt.portefeuille([tb], risque=0.01,
                         series={"X": pd.DataFrame({"close": baisse},
                                                   index=idx)})
    ph = bt.portefeuille([th], risque=0.01,
                         series={"Y": pd.DataFrame({"close": hausse},
                                                   index=idx)})
    ok("une vente gagne quand le cours baisse", pb["final"] > 10_000)
    ok("elle perd quand le cours monte", ph["final"] < 10_000)
    ok("la courbe d'une vente gagnante ne plonge pas", pb["dd"] < 0.01)
    ok("la perte latente d'une vente perdante est visible",
       ph["dd"] > 0.01)

    print("\n— Plafond de poids par ligne —")
    # 1 % de risque sur un stop a 0,5 % de l'entree, c'est 200 % du
    # capital sur un seul titre. Le backtest le faisait sans rien dire.
    serre = bt.Trade("S", pd.Timestamp("2024-01-02"),
                     pd.Timestamp("2024-02-01"), 100.0, 104.0, 99.5,
                     1.0, 20, "ema20")
    libre = bt.portefeuille([serre], risque=0.01, capital=10_000.0)
    borne = bt.portefeuille([serre], risque=0.01, capital=10_000.0,
                            max_poids=0.25)
    ok("sans plafond, un stop serre dimensionne au-dela du capital",
       (0.01 * 10_000 / serre.risque) * serre.entree > 10_000)
    ok("le plafond ramene la ligne a 25 % du capital",
       abs(borne["final"] - (10_000 + 25.0 * serre.risque * serre.R)) < 1e-6)
    ok("le plafond reduit le resultat, il ne l'augmente pas",
       borne["final"] < libre["final"])
    ok("la ligne rognee est comptee", borne["lignes_rognees"] == 1)
    large = bt.Trade("L", pd.Timestamp("2024-01-02"),
                     pd.Timestamp("2024-02-01"), 100.0, 110.0, 90.0,
                     5.0, 20, "ema20")
    ok("une ligne deja sous le plafond n'est pas touchee",
       abs(bt.portefeuille([large], risque=0.01)["final"]
           - bt.portefeuille([large], risque=0.01,
                             max_poids=0.25)["final"]) < 1e-9)
    ok("les trois strategies passent desormais leur plafond au portefeuille",
       "max_poids=MAX_POIDS" in (Path(__file__).resolve().parent
                                 / "short.py").read_text(encoding="utf-8")
       and "max_poids=MAX_POIDS" in (Path(__file__).resolve().parent
                                     / "pead.py").read_text(encoding="utf-8")
       and "max_poids=R.MAX_WEIGHT" in (Path(__file__).resolve().parent
                                        / "phase0.py").read_text(encoding="utf-8"))

    print("\n— Le poids atteint est MESURE, pas corrige en douce —")
    jm = pd.bdate_range("2024-01-02", periods=40)
    monte = np.linspace(100.0, 150.0, 40)
    tm = sh.TradeCourt("M", jm[0], jm[-1], 100.0, 150.0, 110.0, 5.0, 39,
                       "stop")
    rm = bt.portefeuille([tm], risque=0.01, max_pos=10, capital=10_000.0,
                         series={"M": pd.DataFrame({"close": monte},
                                                   index=jm)},
                         max_poids=0.20)
    ok("une vente perdante voit son poids grossir toute seule",
       rm["poids_max"] > 0.10)
    ok("le poids atteint est rapporte, pas efface",
       "poids_max" in rm and "seances_au_dessus" in rm)
    ok("aucune reduction en cours de route n'est inventee",
       rm["lignes_rognees"] == 0 and rm["final"] < 10_000)

    print("\n— Un Trade vendu a decouvert n'est plus muet —")
    mv = bt.Trade("V", pd.Timestamp("2024-01-02"), pd.Timestamp("2024-02-01"),
                  100.0, 90.0, 110.0, 5.0, 20, "stop", sens=-1)
    ma = bt.Trade("A", pd.Timestamp("2024-01-02"), pd.Timestamp("2024-02-01"),
                  100.0, 110.0, 90.0, 5.0, 20, "ema20")
    ok("son risque est positif, comme celui d'un achat", mv.risque == 10.0)
    ok("son R n'est plus zero par accident", mv.R > 0)
    ok("le miroir exact rend exactement le meme R",
       abs(mv.R - ma.R) < 1e-12)

    print("\n— Le signal part quand il doit, et pas autrement —")
    n = 400
    jours = pd.bdate_range("2024-01-02", periods=n)

    def serie(car3=-0.09, rvol=3.0, derive=0.0, apres=-0.004):
        c = [100.0]
        for k in range(n - 1):
            r = derive
            if k == 299:
                r = car3
            elif k == 300:
                r = -0.01
            elif k > 300:
                r = apres
            c.append(c[-1] * (1 + r))
        c = np.array(c)
        v = np.full(n, 4e6)
        v[299] = 4e6 * rvol
        o = np.concatenate([[c[0]], c[:-1]])
        d = pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.004,
                          "low": np.minimum(o, c) * 0.996, "close": c,
                          "volume": v}, index=jours)
        b = pd.DataFrame({"open": np.full(n, 400.0),
                          "high": np.full(n, 401.0),
                          "low": np.full(n, 399.0),
                          "close": np.full(n, 400.0),
                          "volume": np.full(n, 1e7)}, index=jours)
        return enrich(d, bench_close=b["close"]), b

    d, b = serie()
    pris, _ = sh.trades_ticker(d, "X", b, [jours[299]],
                               "2024-01-01", "2026-12-31")
    ok("une mauvaise surprise sur un titre en tendance baissiere "
       "declenche", len(pris) == 1)
    if pris:
        tr = pris[0]
        ok("la vente se fait a l'ouverture de J+3",
           d.index.get_loc(tr.entree_d) == 302)
        ok("le stop est AU-DESSUS du prix de vente", tr.stop0 > tr.entree)
        ok("le stop vaut entree + 2 ATR",
           abs(tr.stop0 - (tr.entree + sh.STOP_ATR * tr.atr)) < 1e-9)
        ok("les frais reduisent ce qu'on encaisse a la vente",
           tr.entree < float(d["open"].iloc[302]))

    # Chaque condition doit bloquer pour SA raison.
    for lib, kw, attendu in (
            ("surprise trop faible", {"car3": -0.02},
             "E1 mauvaise surprise"),
            ("volume ordinaire", {"rvol": 1.0}, "E2 volume"),
            ("titre au-dessus de sa SMA200", {"derive": 0.0016},
             "E6 titre sous sa SMA200")):
        dd, bb = serie(**kw)
        evs = sh.evenements(dd, bb, [jours[299]])
        bloque = [k for k, v in sh.passe(evs[0]).items() if not v] if evs else []
        pr, _ = sh.trades_ticker(dd, "X", bb, [jours[299]],
                                 "2024-01-01", "2026-12-31")
        ok(f"{lib} : bloque par {attendu}",
           attendu in bloque and not pr)

    print("\n— Le cout d'emprunt mord vraiment —")
    facile, _ = sh.trades_ticker(d, "X", b, [jours[299]], "2024-01-01",
                                 "2026-12-31", sh.EMPRUNT_AN)
    dur, _ = sh.trades_ticker(d, "X", b, [jours[299]], "2024-01-01",
                              "2026-12-31", sh.EMPRUNT_DIFFICILE)
    ok("un titre difficile a emprunter rapporte moins",
       facile and dur and dur[0].R < facile[0].R)
    ok("lance() refuse une chaine a la place d'une liste",
       _leve_type_error(sh.lance))


def _leve_type_error(fn) -> bool:
    try:
        fn("us")
    except TypeError:
        return True
    except Exception:
        return False
    return False


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

    # Un titre retire de la cote s'arrete des semaines avant l'indice.
    # En SCAN il est mort et ne doit rien produire ; en BACKTEST il doit
    # etre garde, sinon on ne teste que les survivants — le biais meme
    # qu'on cherche a corriger.
    retire = saine.iloc[:-60]
    ok("retrait de cote : refuse pour un scan du soir",
       not ql.controle(retire, bench, "T", exige_recent=True,
                       aujourdhui=jour).utilisable)
    r_bt = ql.controle(retire, bench, "T", exige_recent=False,
                       aujourdhui=jour)
    ok("retrait de cote : CONSERVE pour un backtest (biais du survivant)",
       r_bt.utilisable and any("retrait de cote" in a for a in r_bt.alertes))


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


def test_veto_resultats() -> None:
    """Le veto « resultats inconnus » doit se lever pour les bons titres,
    et pour eux seulement."""
    from . import data as dl
    from . import rules as R
    from .indicators import enrich
    from .scan import resout_resultats

    print("\n— Veto resultats : levee a la demande —")

    # Un titre dont les treize blocs passent : seule la date manque.
    # L'indice est bati sur le MEME calendrier, sinon la force relative
    # se calcule sur une serie recopiee et le cas de reference ne tient
    # plus.
    r = np.random.default_rng(5)
    cb = [400.0]
    for _ in range(419):
        cb.append(cb[-1] * (1 + 0.0004 + r.normal(0, 0.004)))
    c = [100.0]
    for _ in range(414):
        c.append(c[-1] * (1 + 0.0015 + r.normal(0, 0.004)))
    for _ in range(4):
        c.append(c[-1] * (1 - 0.007))
    c.append(c[-1] * 1.016)
    c = np.array(c)
    idx = pd.bdate_range("2022-01-03", periods=len(c))
    o = np.concatenate([[c[0]], c[:-1]])
    v = np.full(len(c), 3e7)
    v[-1] = 3e7 * 1.9
    pret = pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.004,
                         "low": np.minimum(o, c) * 0.996, "close": c,
                         "volume": v}, index=idx)
    bench_close = pd.Series(np.array(cb), index=idx)
    assert len(cb) == len(c), "indice et titre doivent partager le calendrier"
    d_pret = enrich(pret, bench_close=bench_close)
    autre = serie(len(c), seed=62)
    autre.index = idx
    d_autre = enrich(autre, bench_close=bench_close)

    s_pret = R.evaluate(d_pret, "PRET", True, days_to_earnings=None)
    s_autre = R.evaluate(d_autre, "AUTRE", True, days_to_earnings=None)
    ok("cas de reference : treize blocs passes, seul le veto resultats reste",
       all(s_pret.blocks.values()) and len(s_pret.vetos) == 1)

    appels = []
    vrai = dl.days_to_earnings_yf

    def compte(tk):
        appels.append(tk)
        return 30

    dl.days_to_earnings_yf = compte
    try:
        sortie = resout_resultats([s_pret, s_autre],
                                  {"PRET": d_pret, "AUTRE": d_autre}, True)
    finally:
        dl.days_to_earnings_yf = vrai

    ok("la date n'est cherchee QUE pour le titre concerne",
       appels == ["PRET"])
    par_tk = {s.ticker: s for s in sortie}
    ok("le veto leve, le candidat declenche", par_tk["PRET"].fired)
    ok("les autres titres sont rendus intacts",
       par_tk["AUTRE"] is s_autre and not par_tk["AUTRE"].fired)

    # Date introuvable : le veto reste, le titre ne declenche pas.
    dl.days_to_earnings_yf = lambda tk: None
    try:
        reste = resout_resultats([s_pret], {"PRET": d_pret}, True)
    finally:
        dl.days_to_earnings_yf = vrai
    ok("date introuvable : le veto reste entier, aucun declenchement",
       not reste[0].fired
       and any("INCONNUS" in v for v in reste[0].vetos))

    # Publication proche : le veto de blackout remplace celui d'inconnu.
    dl.days_to_earnings_yf = lambda tk: 4
    try:
        proche = resout_resultats([s_pret], {"PRET": d_pret}, True)
    finally:
        dl.days_to_earnings_yf = vrai
    ok("publication dans 4 seances : veto de blackout, pas de declenchement",
       not proche[0].fired
       and any("résultats dans" in v for v in proche[0].vetos))


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
    test_optimisations()
    test_phase0()
    test_pead()
    test_comparatif()
    test_strategie()
    test_short()
    test_qualite()
    test_audit()
    test_robuste()
    test_cache()
    test_resolve_et_app()
    test_veto_resultats()
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
