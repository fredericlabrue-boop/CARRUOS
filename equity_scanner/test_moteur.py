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
    # La lecture de la specification n°2, ecrite AVANT le passage unique.
    # La retoucher apres le passage serait une retouche de la regle.
    "derive-post-annonce-v1-lecture.md":
        "101d09b5b0ba9f762da0698362ba542034c6909474e5b00efc0fca8953430b8a",
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


def test_marqueurs() -> None:
    """Les fleches du graphique, vectorisees, doivent etre IDENTIQUES.

    La boucle scalaire pesait 3 des 5 secondes de generation de la page.
    Remplacer une boucle par une passe numpy ne vaut que si le resultat
    ne bouge pas d'une fleche — on le verifie sur des series qui en
    produisent vraiment, pas sur une serie qui n'en produit aucune.
    """
    from . import chart
    from .indicators import enrich
    from .rules import evaluate

    print("\n— Fleches de signal : vectorise = scalaire —")
    bo = enrich(serie(1400, seed=211, derive=0.0005, vol=0.008, depart=400.0))
    total, ecarts = 0, []
    for graine in (3, 13, 41, 57):
        d = enrich(serie(1400, seed=graine), bench_close=bo["close"])
        b = bo.reindex(d.index).ffill()
        lent = []
        for i in range(max(210, len(d) - 900), len(d)):
            try:
                marche = bool(b["close"].iloc[i] > b["sma200"].iloc[i])
                if evaluate(d, "X", marche, i=i, days_to_earnings=999).fired:
                    lent.append(d.index[i].strftime("%Y-%m-%d"))
            except Exception:
                pass
        rapide = [m["time"] for m in chart._marqueurs(d, b, 900)]
        total += len(lent)
        if lent != rapide:
            ecarts.append((graine, sorted(set(lent) ^ set(rapide))[:4]))
    ok(f"l'echantillon produit de vraies fleches ({total})", total >= 30)
    ok("aucun ecart entre la passe numpy et la boucle barre a barre",
       not ecarts)
    if ecarts:
        print(f"          -> {ecarts}")
    # Et la forme attendue par la page, pas seulement les dates.
    d = enrich(serie(1400, seed=41), bench_close=bo["close"])
    m = chart._marqueurs(d, bo.reindex(d.index).ffill(), 900)
    ok("chaque fleche porte les champs attendus par le graphique",
       all(set(x) == {"time", "position", "color", "shape", "text"}
           for x in m))


def test_projection_capitalisation() -> None:
    """Ce que l'epargne apporte, et ce que la capitalisation ajoute.

    Le capital final tout nu melange les deux : on ne voit pas le fonds
    prendre le relais. La separation est de l'arithmetique exacte, donc
    elle se verifie exactement.
    """
    from . import strategie as sg

    print("\n— Versements contre capitalisation —")
    p = sg.projette(capital=1000, taux_annuel=0.07, annees=25,
                    versement_mensuel=200)
    ok("verse = capital de depart + 25 ans x 12 x 200",
       abs(p["verse_total"] - (1000 + 25 * 12 * 200)) < 0.01)
    ok("genere = capital final - verse, exactement",
       abs(p["genere_total"]
           - (p["capitalisant_net"] - p["verse_total"])) < 0.01)
    ok("la part generee est coherente avec les deux montants",
       abs(p["part_generee"]
           - p["genere_total"] / p["capitalisant_net"] * 100) < 0.01)
    ok("chaque ligne porte sa propre separation",
       all(abs(l["genere"] - (l["capitalisant_net"] - l["verse"])) < 0.01
           for l in p["lignes"]))
    ok("la part generee croit avec le temps",
       p["lignes"][-1]["part_generee"] > p["lignes"][0]["part_generee"])
    ok(f"l'annee de bascule est reelle ({p['an_bascule']})",
       p["an_bascule"] is not None
       and p["lignes"][p["an_bascule"] - 1]["genere"]
       >= p["lignes"][p["an_bascule"] - 1]["verse"])
    ok("et c'est la PREMIERE annee ou la bascule a lieu",
       all(l["genere"] < l["verse"]
           for l in p["lignes"][:p["an_bascule"] - 1]))

    # Sans rendement, rien n'est genere : la separation doit le dire.
    z = sg.projette(capital=1000, taux_annuel=0.0, annees=10,
                    versement_mensuel=100)
    ok("a rendement nul, le fonds ne genere rien",
       abs(z["genere_total"]) < 0.01 and z["an_bascule"] is None)

    # Sans versement, tout ce qui depasse le capital est genere.
    n = sg.projette(capital=10000, taux_annuel=0.06, annees=10)
    ok("sans versement, verse reste le capital de depart",
       abs(n["verse_total"] - 10000) < 0.01)
    # A 6 % net d'impot, doubler prend seize ans : sur dix ans la
    # bascule n'a PAS lieu, et pretendre le contraire serait une
    # attente fausse — c'est ce que ce test disait au depart.
    ok("a 6 % sur dix ans, les gains ne depassent pas encore la mise",
       n["an_bascule"] is None and n["genere_total"] < n["verse_total"])
    long = sg.projette(capital=10000, taux_annuel=0.06, annees=30)
    ok(f"sur trente ans, la bascule a lieu (annee {long['an_bascule']})",
       long["an_bascule"] == 16)


def test_seance() -> None:
    """Horaires des places. Verifies sur des dates dont on connait la
    reponse : l'heure d'ete et les jours feries sont exactement la ou
    l'on se trompe."""
    import datetime as _d
    from zoneinfo import ZoneInfo

    from . import seance as sn

    print("\n— Paques, qui place le Vendredi saint et le lundi de Paques —")
    for an, att in ((2024, (3, 31)), (2025, (4, 20)),
                    (2026, (4, 5)), (2027, (3, 28))):
        p = sn.paques(an)
        ok(f"Paques {an} tombe le {p}", (p.month, p.day) == att)

    print("\n— Jours feries —")
    us = sn.feries("us", 2026)
    ok("MLK est le 3e lundi de janvier", _d.date(2026, 1, 19) in us)
    ok("Thanksgiving est le 4e jeudi de novembre",
       _d.date(2026, 11, 26) in us)
    ok("le 4 juillet 2026 tombe un samedi : chome le vendredi 3",
       _d.date(2026, 7, 3) in us and _d.date(2026, 7, 4) not in us)
    eu = sn.feries("euronext", 2026)
    ok("Euronext ferme le Vendredi saint et le lundi de Paques",
       _d.date(2026, 4, 3) in eu and _d.date(2026, 4, 6) in eu)
    ok("Euronext ferme le 1er mai, pas les Etats-Unis",
       _d.date(2026, 5, 1) in eu and _d.date(2026, 5, 1) not in us)

    print("\n— L'heure d'ete decale la seance americaine —")

    def ouv(iso):
        return sn.etat("newyork", _d.datetime.fromisoformat(iso))["ouv_paris"]

    ok("en janvier, New York ouvre a 15h30 Paris",
       ouv("2026-01-15T12:00:00+00:00") == "15:30")
    ok("en juin aussi", ouv("2026-06-15T12:00:00+00:00") == "15:30")
    # Entre les deux bascules, l'ecart tombe a cinq heures.
    ok("mi-mars, quand les Etats-Unis sont passes a l'ete et pas "
       "l'Europe, elle ouvre a 14h30",
       ouv("2026-03-15T12:00:00+00:00") == "14:30")

    print("\n— Etat des places a un instant donne —")
    t = _d.datetime(2026, 2, 10, 10, 0, tzinfo=ZoneInfo("Europe/Paris"))
    e = {x["cle"]: x for x in sn.toutes(t)}
    ok("a 10h, Paris et Londres sont ouvertes",
       e["paris"]["code"] == "OUVERTE" and e["londres"]["code"] == "OUVERTE")
    ok("a 10h, New York n'a pas encore ouvert",
       e["newyork"]["code"] == "AVANT OUVERTURE")
    t2 = _d.datetime(2026, 2, 10, 17, 32, tzinfo=ZoneInfo("Europe/Paris"))
    ok("a 17h32, Paris est au fixing de cloture",
       sn.etat("paris", t2)["code"] == "FIXING DE CLOTURE")
    ok("et New York est encore ouverte",
       sn.etat("newyork", t2)["code"] == "OUVERTE")
    t3 = _d.datetime(2026, 2, 14, 11, 0, tzinfo=ZoneInfo("Europe/Paris"))
    ok("le samedi, les neuf places sont en week-end",
       all(x["code"] == "WEEK-END" for x in sn.toutes(t3)))
    t4 = _d.datetime(2026, 5, 1, 16, 0, tzinfo=ZoneInfo("Europe/Paris"))
    ok("le 1er mai, Paris est ferie et New York ouverte",
       sn.etat("paris", t4)["code"] == "FERIE"
       and sn.etat("newyork", t4)["code"] == "OUVERTE")

    print("\n— Le prochain evenement saute week-ends et feries —")
    t5 = _d.datetime(2026, 4, 2, 19, 0, tzinfo=ZoneInfo("Europe/Paris"))
    pr = sn.etat("paris", t5)["prochain"]
    ok("jeudi 2 avril au soir, la prochaine ouverture est le mardi 7 "
       f"(obtenu {pr['jour']})", pr["jour"] == "2026-04-07")

    print("\n— Aucune « meilleure heure » n'est affirmee —")
    q = sn.pourquoi_pas_de_meilleure_heure()
    ok("les quatre reponses sont la", len(q) == 4)
    tout = " ".join(q.values()).lower()
    ok("il dit que la specification execute a l'ouverture",
       "ouverture" in tout)
    ok("il dit que l'intraday n'est pas mesurable avec ces donnees",
       "journali" in tout)
    ok("aucune heure n'est recommandee",
       not any(m in tout for m in ("achetez a ", "vendez a ",
                                   "meilleure heure est",
                                   "l'heure ideale")))
    ok("la date est en francais, quelle que soit la machine",
       sn.date_fr(t) == "mardi 10 fevrier 2026, 10:00")


def test_horizon() -> None:
    """Amplitude par horizon et objectifs atteignables.

    Verifie sur des series FABRIQUEES dont la reponse est connue d'avance :
    une hausse reguliere, une dent de scie, une serie plate. Un module qui
    rend des pourcentages plausibles sur du bruit peut etre faux ; sur ces
    trois-la, il ne peut pas l'etre sans que ca se voie.
    """
    from . import horizon as hz

    print("\n— Amplitude par horizon —")
    n = 400
    px = 100.0 * 1.01 ** np.arange(n)          # +1 % par seance, sans bruit
    d = pd.DataFrame({"close": px},
                     index=pd.bdate_range("2020-01-02", periods=n))
    a = {x["nom"]: x for x in hz.amplitude(d)}
    ok("+1 %/seance : l'amplitude a 1 jour vaut 1,000 %",
       abs(a["1 jour"]["typique"] - 1.0) < 1e-6)
    ok("a 1 semaine elle vaut 1,01^5 - 1 = 5,101 %",
       abs(a["1 semaine"]["typique"] - (1.01 ** 5 - 1) * 100) < 1e-6)
    ok("a 1 mois elle vaut 1,01^21 - 1 = 23,239 %",
       abs(a["1 mois"]["typique"] - (1.01 ** 21 - 1) * 100) < 1e-6)
    ok("les fenetres independantes sont les fenetres divisees par l'horizon",
       a["1 mois"]["independantes"] == a["1 mois"]["fenetres"] // 21)
    ok("une fenetre qui se chevauche ne compte pas pour une observation",
       a["1 mois"]["independantes"] < a["1 mois"]["fenetres"] / 10)

    plat = pd.DataFrame({"close": np.full(400, 50.0)},
                        index=pd.bdate_range("2020-01-02", periods=400))
    ap = {x["nom"]: x for x in hz.amplitude(plat)}
    ok("une serie plate a une amplitude nulle, pas un petit chiffre",
       ap["1 mois"]["typique"] == 0.0)

    court = pd.DataFrame({"close": np.arange(50, dtype=float) + 100},
                         index=pd.bdate_range("2020-01-02", periods=50))
    ok("un historique trop court ne rend rien plutot qu'un chiffre",
       hz.amplitude(court) == [] and hz.atteinte(court) == [])

    print("\n— Objectif atteignable —")
    r = {x["cible"]: x for x in hz.atteinte(d, (2.0, 5.0, 10.0), seances=5)}
    ok("+2 % est touche par toutes les fenetres", r[2.0]["part"] == 1.0)
    ok("il l'est en 2 seances (1,01^2 = +2,01 %)",
       r[2.0]["seances_medianes"] == 2.0)
    ok("+5 % est touche en 5 seances (1,01^5 = +5,10 %)",
       r[5.0]["part"] == 1.0 and r[5.0]["seances_medianes"] == 5.0)
    ok("+10 % n'est jamais touche en 5 seances",
       r[10.0]["part"] == 0.0 and r[10.0]["seances_medianes"] is None)
    ok("sur une hausse qui ne se retourne pas, rien n'est rendu",
       r[5.0]["part_rendue"] == 0.0)

    # Dent de scie : +10 % en 5 seances, puis retour a 100. Tout est rendu.
    cycle = np.concatenate([np.linspace(100, 110, 6)[1:],
                            np.linspace(110, 100, 6)[1:]])
    dents = pd.DataFrame({"close": np.tile(cycle, 40)},
                         index=pd.bdate_range("2020-01-02", periods=400))
    rs = {x["cible"]: x for x in hz.atteinte(dents, (5.0,), seances=10)}
    ok("un titre qui revient toujours a son point de depart rend tout",
       rs[5.0]["part_rendue"] == 1.0)
    ok("et il touche quand meme son objectif la moitie du temps",
       0.3 < rs[5.0]["part"] < 0.7)

    print("\n— L'entree en euros : que de l'arithmetique —")
    e = hz.entree(prix=100.0, stop=95.0, sleeve=10_000.0)
    ok("1 % de 10 000 / 5 de risque = 20 titres", e["titres"] == 20)
    ok("le risque en euros vaut bien 1 % du sleeve",
       abs(e["risque_eur"] - 100.0) < 1e-9)
    ok("un R vaut le montant risque", e["euro_par_R"] == e["risque_eur"])
    ok("un R net vaut 70 % du brut, PFU deduit",
       abs(e["euro_par_R_net"] - 70.0) < 1e-9)
    ok("le point mort est au-dessus du prix d'entree",
       e["point_mort_prix"] > e["prix"])
    serre = hz.entree(prix=100.0, stop=99.5, sleeve=10_000.0)
    ok("un stop serre est plafonne par le poids maximum",
       serre["plafonne"] and serre["titres"] == 25)
    ok("le plafond tient : 25 titres a 100 = 25 % de 10 000",
       abs(serre["poids"] - 0.25) < 1e-9)
    ok("un stop au-dessus du prix est refuse, pas devine",
       not hz.entree(prix=100.0, stop=101.0, sleeve=10_000.0)["ok"])

    print("\n— Le gain espere refuse de s'inventer —")
    g = hz.gain_espere(e, ev_R=None, n_trades=0, validee=False)
    ok("sans hypothese validee, le gain espere n'est pas chiffrable",
       not g["chiffrable"])
    ok("et il le dit au lieu d'afficher zero euro",
       "avantage demontre" in g["pourquoi"])
    ok("une esperance positive ne suffit pas si la Phase 0 a dit non",
       not hz.gain_espere(e, ev_R=0.4, n_trades=500,
                          validee=False)["chiffrable"])
    g2 = hz.gain_espere(e, ev_R=0.2, n_trades=300, validee=True)
    ok("une hypothese validee donne 0,2 R x 100 EUR = 20 EUR",
       g2["chiffrable"] and abs(g2["euros_par_trade"] - 20.0) < 1e-9)
    ok("le net retranche l'impot", abs(g2["euros_par_trade_net"] - 14.0) < 1e-9)
    ok("le nombre de trades accompagne toujours la moyenne",
       "300 trades" in g2["avertissement"])


def test_cle_av() -> None:
    """La cle Alpha Vantage doit survivre a une mise a jour.

    `.bruce_cache` est cree a cote du programme et ne fait pas partie de
    l'archive livree : installer une nouvelle version dans un dossier neuf
    faisait disparaitre la cle sans un mot.
    """
    import os
    import tempfile
    from pathlib import Path

    from . import app

    print("\n— La cle Alpha Vantage survit a une mise a jour —")
    maison = os.environ.get("HOME")
    envs = {k: os.environ.get(k)
            for k in ("CARRUOS_AV_KEY", "ALPHAVANTAGE_KEY")}
    ici = os.getcwd()
    try:
        bac0 = Path(tempfile.mkdtemp())
        faux = str(bac0 / "home")
        (bac0 / "home").mkdir()
        os.environ["HOME"] = faux
        for k in envs:
            os.environ.pop(k, None)
        # Un arbre a soi : sans cela, la fouille de recuperation trouve
        # les restes des autres essais poses dans /tmp, et le test
        # echoue pour une raison qui n'a rien a voir avec lui.
        v1 = str(bac0 / "Bureau" / "v1")
        Path(v1).mkdir(parents=True)
        os.chdir(v1)
        app._FOUILLE.update({"faite": False, "trouvee": "", "ou": ""})
        ok("aucune cle dans un dossier vierge", app.cle_av() == "")
        app.pose_cle("CLE_DE_TEST_0001")
        ok("la cle enregistree est relue", app.cle_av() == "CLE_DE_TEST_0001")
        ok("elle est posee a cote du programme",
           (Path(v1) / ".bruce_cache" / "cle-alphavantage.txt").exists())
        ok("elle est posee aussi dans le dossier personnel",
           (Path(faux) / ".carruos" / "cle-alphavantage.txt").exists())

        v2 = str(bac0 / "Bureau" / "v2")   # la mise a jour : dossier neuf
        Path(v2).mkdir(parents=True)
        os.chdir(v2)
        ok("nouvelle version : rien a cote du programme",
           not (Path(v2) / ".bruce_cache" / "cle-alphavantage.txt").exists())
        ok("la cle est retrouvee malgre le dossier neuf",
           app.cle_av() == "CLE_DE_TEST_0001")
        ok("et reposee a cote de la nouvelle version",
           (Path(v2) / ".bruce_cache" / "cle-alphavantage.txt").exists())

        app.pose_cle("")
        ok("l'effacer l'efface des deux endroits", app.cle_av() == "")
        # Et la fouille ne doit pas la ramener : le dossier personnel
        # existe, donc le programme a deja ete regle ici.
        app._FOUILLE.update({"faite": False, "trouvee": "", "ou": ""})
        ok("effacee volontairement, elle ne ressuscite pas",
           app.cle_av() == "")
        os.environ["CARRUOS_AV_KEY"] = "PAR_VARIABLE"
        ok("une variable d'environnement reste un recours",
           app.cle_av() == "PAR_VARIABLE")

        # --- Recuperation d'une cle laissee par une installation
        #     precedente. C'est le cas reel : la cle vit dans
        #     .bruce_cache, qui n'est pas livre dans l'archive.
        os.environ.pop("CARRUOS_AV_KEY", None)
        bac = Path(tempfile.mkdtemp())
        os.environ["HOME"] = str(bac / "home")
        (bac / "home").mkdir()
        bureau = bac / "Bureau"
        vieille = bureau / "CARRUOS"
        (vieille / ".bruce_cache").mkdir(parents=True)
        (vieille / ".bruce_cache" / "cle-alphavantage.txt").write_text(
            "CLE_ANCIENNE_INSTALL", encoding="utf-8")
        neuve = bureau / "CARRUOS-neuf"
        neuve.mkdir()
        os.chdir(neuve)
        app._FOUILLE.update({"faite": False, "trouvee": "", "ou": ""})
        ok("une cle laissee par une installation voisine est retrouvee",
           app.retrouve_cle() == "CLE_ANCIENNE_INSTALL")
        ok("et recopiee a cote de la nouvelle version",
           (neuve / ".bruce_cache" / "cle-alphavantage.txt").exists())
        ok("la fouille n'a lieu qu'une fois par lancement",
           app._FOUILLE["faite"] is True)

        # Installation seule : elle ne doit PAS se prendre elle-meme pour
        # une ancienne. Le premier controle comparait le grand-parent, ce
        # qui laissait passer certains chemins.
        bac2 = Path(tempfile.mkdtemp())
        os.environ["HOME"] = str(bac2 / "home")
        (bac2 / "home").mkdir()
        seule = bac2 / "Bureau" / "SOLO"
        (seule / ".bruce_cache").mkdir(parents=True)
        (seule / ".bruce_cache" / "cle-alphavantage.txt").write_text(
            "SA_PROPRE_CLE", encoding="utf-8")
        os.chdir(seule)
        app._FOUILLE.update({"faite": False, "trouvee": "", "ou": ""})
        ok("seule installation : elle ne se trouve pas elle-meme",
           app.retrouve_cle() == "")

        # La fouille ne remonte QU'UN niveau : deux revenaient a balayer
        # tout C:\\Users.
        ici = Path(seule).resolve()
        cands = app._candidats()
        ok("la fouille ne remonte qu'un niveau au-dessus du programme",
           ici.parent.parent not in cands)
    finally:
        os.chdir(ici)
        if maison is not None:
            os.environ["HOME"] = maison
        for k, val in envs.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val


def _univers_pead(graine: int, n_titres: int = 40, derive: float = 0.0,
                  n: int = 1100) -> dict:
    """Un univers synthetique dont on CONNAIT la reponse.

    Une publication tous les trimestres environ, a une heure tiree parmi
    avant l'ouverture, apres la cloture et inconnue. Sur la seance qui
    reagit : un saut tire au hasard et un volume triple. `derive` ajoute,
    apres chaque surprise de +5 % ou plus, une derive quotidienne pendant
    quarante seances — c'est l'effet cherche, plante a la main. Sans
    elle, l'univers est du bruit : le test ne doit rien y trouver.
    """
    from .indicators import enrich
    rng = np.random.default_rng(graine)
    idx = pd.bdate_range("2019-01-02", periods=n)
    b = 300 * np.exp(np.cumsum(rng.normal(0.0006, 0.007, n)))
    bb = pd.DataFrame({"open": b, "high": b * 1.004, "low": b * 0.996,
                       "close": b, "volume": 1e8}, index=idx)
    series, dates = {}, {}
    for t in range(n_titres):
        r = rng.normal(0.0004, 0.014, n)
        v = rng.uniform(1.5e6, 3e6, n)
        ann = []
        k = int(rng.integers(30, 90))
        while k < n - 5:
            h = [7, 16, None][int(rng.integers(0, 3))]
            j = k + 1 if h == 16 else k
            saut = rng.normal(0.0, 0.06)
            r[j] += saut
            v[j] *= 3.5
            if saut >= 0.05 and derive:
                r[j + 3:j + 43] += derive
            ann.append(f"{idx[k].date()}T{h:02d}:00:00" if h is not None
                       else str(idx[k].date()))
            k += int(rng.integers(58, 68))
        c = 50 * np.exp(np.cumsum(r))
        o = np.r_[50.0, c[:-1]] * (1 + rng.normal(0, 0.002, n))
        d = pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.005,
                          "low": np.minimum(o, c) * 0.995, "close": c,
                          "volume": v}, index=idx)
        series[f"T{t}"] = enrich(d, bench_close=bb["close"])
        dates[f"T{t}"] = ann
    return {"series": series, "dates": dates, "bench_brut": bb,
            "bo": enrich(bb), "ecartes": {}, "ref": bb["close"],
            "instantane": {"tickers": list(series), "annonces": dates,
                           "collecte": "2026-09-23T00:00:00",
                           "sans_dates": []}}


def test_pead() -> None:
    import json
    from pathlib import Path

    from . import backtest as bt_mod
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

    # --- la seance qui reagit (note de lecture, point 1) ---------------
    ix = pd.bdate_range("2024-01-01", periods=10)      # lundi 1er janvier
    lun, mar = ix[0], ix[1]
    ok("publiee apres la cloture : c'est la seance SUIVANTE qui reagit",
       pead.seance_de_reaction(ix, lun, 16) == 1)
    ok("publiee avant l'ouverture : le jour meme",
       pead.seance_de_reaction(ix, mar, 7) == 1)
    ok("heure inconnue : le jour du calendrier, et c'est dit",
       pead.seance_de_reaction(ix, mar, None) == 1
       and pead.moment(ix, mar, None) == "inconnue")
    ok("un samedi : la seance suivante, pas la precedente",
       pead.seance_de_reaction(ix, pd.Timestamp("2024-01-06"), 10) == 5
       and pead.moment(ix, pd.Timestamp("2024-01-06"), 10) == "hors_seance")
    ok("l'heure est lue sur l'horloge de New York",
       pead._normalise(pd.Timestamp("2024-10-30 16:00", tz="America/New_York"))
       ["heure"] == 16
       and pead._normalise(pd.Timestamp("2024-10-30 20:00", tz="UTC"))
       ["heure"] == 16
       and pead._normalise("2024-10-30")["heure"] is None)

    # Un titre construit a la main : publication un lundi APRES LA
    # CLOTURE, reaction le mardi (+9 %, volume x4).
    n = 400
    ix = pd.bdate_range("2023-01-02", periods=n)
    r = np.zeros(n)
    r[1:] = 0.0005
    vol = np.full(n, 2e6)
    k = 300                                   # lundi de la publication
    r[k + 1] += 0.09
    vol[k + 1] *= 4
    c = 50 * np.exp(np.cumsum(r))
    brut = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": vol}, index=ix)
    bb = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0,
                       "close": 100.0, "volume": 1e8}, index=ix)
    d1 = enrich(brut, bench_close=bb["close"])
    ev_n = pead.evenements(d1, bb, [f"{ix[k].date()}T16:00:00"])
    ok("apres la cloture : J est la seance de la reaction",
       len(ev_n) == 1 and ev_n[0]["i"] == k + 1)
    ok("et le volume mesure est celui de la reaction (E2 passe)",
       len(ev_n) == 1 and ev_n[0]["rvol"] >= pead.RVOL_ANNONCE
       and ev_n[0]["car3"] >= pead.CAR3_MIN)
    ev_l = pead.evenements(d1, bb, [str(ix[k].date())])
    ok("la lecture litterale ratait ce volume (le defaut corrige)",
       len(ev_l) == 1 and ev_l[0]["rvol"] < pead.RVOL_ANNONCE)

    # --- E6 a la cloture de J+2 (point 2) ------------------------------
    J = k + 1
    bo_e6 = pd.DataFrame({"close": 100.0, "sma200": 101.0}, index=ix)
    bo_e6.iloc[J + 2:, 0] = 102.0             # l'indice repasse au-dessus a J+2
    _, _, inf = pead.trades_ticker(d1, "X", bb, bo_e6,
                                   [f"{ix[k].date()}T16:00:00"],
                                   str(ix[0].date()), str(ix[-1].date()),
                                   simule=False)
    ok("E6 se lit a la cloture de J+2, pas a J",
       inf["conditions"]["E6 regime"] == 1 and inf["candidats"] == 1)

    # --- les sorties (points 3 et 4) -----------------------------------
    bo_ok = pd.DataFrame({"close": 102.0, "sma200": 100.0}, index=ix)
    i0 = J + pead.DELAI_EXEC
    t = pead.simule_pead(d1, J, "X", bo_ok, prochaine=ix[J + 20])
    ok("entree a l'ouverture de J+3",
       t is not None and t.entree_d == ix[i0])
    ok("S3 : sortie a la cloture de la VEILLE de l'annonce suivante",
       t is not None and t.motif == "annonce" and t.sortie_d == ix[J + 19])
    t = pead.simule_pead(d1, J, "X", bo_ok, prochaine=None)
    ok("S1 : 45 seances, puis sortie",
       t is not None and t.motif == "duree" and t.barres == pead.MAX_BARRES)
    t = pead.simule_pead(d1.iloc[:J + 20], J, "X", bo_ok.iloc[:J + 20])
    ok("donnees finies avant toute sortie : position OUVERTE, pas un trade",
       t is not None and t.motif == "ouvert")
    t = pead.simule_pead(d1.iloc[:J + 20], J, "X", bo_ok.iloc[:J + 20],
                         prochaine=ix[J + 30])
    ok("une annonce apres la derniere barre ne ferme pas la position ici",
       t is not None and t.motif == "ouvert")
    bo_ko = bo_ok.copy()
    bo_ko.iloc[i0 + 5:, 0] = 90.0
    t = pead.simule_pead(d1, J, "X", bo_ko)
    ok("S4 : l'indice passe sous sa MM200, on sort",
       t is not None and t.motif == "regime" and t.sortie_d == ix[i0 + 5])
    chute = d1.copy()
    chute.iloc[i0 + 3:, chute.columns.get_loc("close")] *= 0.7
    t = pead.simule_pead(chute, J, "X", bo_ok)
    ok("S2 : cloture sous le stop, on sort",
       t is not None and t.motif == "stop" and t.sortie_d == ix[i0 + 3])
    with pead.conditions(False, 0.0, 0.0):
        t = pead.simule_pead(d1, J, "X", bo_ok)
    ok("ligne 1 des couts : entree a la cloture de J+2, sans frais",
       t is not None and t.entree_d == ix[J + 2]
       and abs(t.entree - d1["close"].iloc[J + 2]) < 1e-9)
    ok("et les reglages du moteur sont remis en place ensuite",
       bt_mod.EXECUTION_J1 and bt_mod.COUT_PAR_COTE == 0.0010)

    # --- le test lui-meme, sur des univers dont on CONNAIT la reponse ----
    rien = lambda *_: None                              # noqa: E731
    don = _univers_pead(1, derive=0.004)
    res = pead.evalue(don, "2020-01-01", "2023-06-30", rien)
    ok(f"une derive plantee apres les surprises est trouvee "
       f"(z = {res['z']['z']:+.1f})", (res["z"]["z"] or 0) >= 3)
    # Les lignes 2 a 4 ne different que par les frais : l'esperance ne peut
    # que baisser. La ligne 1 change le PRIX d'entree, pas seulement les
    # frais — elle n'a pas d'ordre garanti avec la 2.
    ok("les quatre lignes de couts, et les frais ne font que retrancher",
       len(res["couts"]) == 4
       and res["couts"][1]["ev"] >= res["couts"][2]["ev"]
       >= res["couts"][3]["ev"])
    zs = []
    for g in range(8):
        r_ = pead.evalue(_univers_pead(100 + g), "2020-01-01", "2023-06-30",
                         rien)
        zs.append(r_["z"]["z"])
    ok(f"sur 8 univers de bruit pur, z moyen {np.mean(zs):+.2f} "
       f"et aucun au-dessus de 2", abs(np.mean(zs)) < 0.8
       and max(zs) < 2.0)
    ok("sur du bruit, aucun GO", r_["verdict"] == "NO-GO")
    # Le meme univers, titres presentes dans un autre ordre (celui d'arrivee
    # des telechargements paralleles) : le z doit etre IDENTIQUE.
    u = _univers_pead(107)
    u2 = {**u, "series": dict(reversed(list(u["series"].items())))}
    za = pead.evalue(u, "2020-01-01", "2023-06-30", rien)["z"]["z"]
    zb = pead.evalue(u2, "2020-01-01", "2023-06-30", rien)["z"]["z"]
    ok("le z ne depend pas de l'ordre d'arrivee des titres",
       abs(za - zb) < 1e-9)

    # Assez de titres pour 200 trades : les cinq criteres passent. Puis la
    # meme chose avec des frais ecrasants sur la ligne 4 : la regle « si
    # l'avantage ne survit pas a la derniere ligne, il n'existe pas » doit
    # renverser le verdict a elle seule.
    grand = _univers_pead(2, n_titres=120, derive=0.004)
    rg_ = pead.evalue(grand, "2020-01-01", "2023-06-30", rien)
    ok(f"une derive plantee sur {rg_['m']['n']} trades passe les cinq "
       f"criteres", all(c[1] for c in rg_["criteres"])
       and rg_["verdict"] != "NO-GO")
    ligne4 = pead.COUTS[pead.LIGNE_ELIMINATOIRE]
    pead.COUTS[pead.LIGNE_ELIMINATOIRE] = (ligne4[0], True, 0.05, 0.05)
    try:
        rk = pead.evalue(grand, "2020-01-01", "2023-06-30", rien)
    finally:
        pead.COUTS[pead.LIGNE_ELIMINATOIRE] = ligne4
    ok("mais si la derniere ligne des couts l'efface : NO-GO",
       all(c[1] for c in rk["criteres"]) and not rk["survit"]
       and rk["verdict"] == "NO-GO")
    # La note de lecture est gelee par son empreinte ; ses nombres doivent
    # etre ceux du moteur, sinon l'un des deux ment.
    note = pead.LECTURE.read_text(encoding="utf-8")
    cites = {"heure de cloture": f"{pead.HEURE_CLOTURE} h",
             "tirages": f"{pead.TIRAGES:,} tirages".replace(",", " "),
             "graine": f"graine {pead.GRAINE}",
             "temoins minimum": f"{pead.TEMOINS_MIN} annonces témoins",
             "univers minimum": f"**{pead.UNIVERS_MIN}** titres",
             "part des dates": f"**{pead.PART_DATES_MIN * 100:.0f} %**",
             "part exploitable": f"**{pead.PART_EXPLOITABLES_MIN * 100:.0f} %**",
             "part des heures": f"**{pead.PART_HEURES_MIN * 100:.0f} %**"}
    absents = [k for k, v in cites.items() if v not in note]
    ok("la note de lecture cite les nombres qui tournent", not absents)
    for k in absents:
        print(f"          -> {k} : la note ne contient pas {cites[k]!r}")
    ok("chaque condition s'affiche avec le seuil que le moteur teste",
       pead.LIBELLES["E1 surprise"].endswith(f"+{pead.CAR3_MIN * 100:.0f} %")
       and set(pead.LIBELLES) == set(pead.CONDITIONS))
    lignes = pead.rapport(res, don, "ESSAI", [])
    ok("le taux de gagnants ne s'affiche qu'avec son intervalle de Wilson",
       any("intervalle de Wilson" in l for l in lignes)
       and not any("taux de reussite" in l for l in lignes))

    # --- le passage unique, et le registre -----------------------------
    import tempfile as _tf3
    tmp = Path(_tf3.mkdtemp())
    et, md = tmp / "reg.json", tmp / "reg.md"
    don = _univers_pead(3)
    r0 = pead.valide(don, rien, etat=et, md=md, dossier=tmp)
    ok("sur un univers tronque (40 titres), le passage NE PART PAS, et "
       "rien n'est inscrit", r0.get("incomplet") and not md.exists()
       and not et.exists())
    sans_h = {**don, "instantane": {**don["instantane"], "annonces": {
        tk: [x[:10] for x in v]
        for tk, v in don["instantane"]["annonces"].items()}}}
    ok("ni sur des dates privees de leur heure (le defaut corrige)",
       any("l'heure n'est connue" in m_ for m_ in pead.incomplet(sans_h)))
    r1 = pead.valide(don, rien, etat=et, md=md, dossier=tmp, controle=False)
    ok("le passage est inscrit, puis ferme avec son resultat",
       not r1.get("refuse") and md.read_text(encoding="utf-8").count(
           pead.HYPOTHESE) == 2)
    r2 = pead.valide(don, rien, etat=et, md=md, dossier=tmp, controle=False)
    ok("un second passage sur la meme periode est REFUSE", r2.get("refuse"))
    r3 = pead.valide(don, rien, second_regard="essai du test", etat=et,
                     md=md, dossier=tmp, controle=False)
    ok("sauf demande explicite, ecrite au registre comme SECOND REGARD",
       not r3.get("refuse")
       and "SECOND REGARD : essai du test" in md.read_text(encoding="utf-8"))
    ok("le registre porte l'empreinte des constantes ET du code",
       all(e["details"].get("moteur") and e["empreinte"] ==
           pead.empreintes()["constantes"]
           for e in json.loads(et.read_text(encoding="utf-8"))))


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


def test_interet() -> None:
    """La carte INTERET : une echelle qui compte, et qui ne conseille pas."""
    from . import chart as gr
    from . import interet as it
    from . import rules as R
    from .dashboard import LABELS
    from .indicators import enrich

    print("\n— Carte d'interet —")

    # --- l'echelle est exhaustive et son ordre est celui qui est ecrit
    marches = set()
    for refuse in (False, True):
        for n_na in (0, 1):
            for vet in ([], ["prix < 10 $"]):
                for n_out in (0, 2):
                    for n_ko in range(14):
                        marches.add(it.niveau(n_ko, n_na, n_out, vet, refuse))
    ok("les sept marches sont toutes atteignables",
       marches == set(it.TITRES))
    ok("un refus qualite prime sur tout le reste",
       it.niveau(0, 1, 2, ["v"], True) == "refus")
    ok("des indicateurs non calculables priment sur un veto",
       it.niveau(0, 1, 0, ["v"], False) == "na")
    # LE defaut corrige : un titre a 13/13 que la specification interdit
    # s'affichait ACHAT, avec entree, stop et nombre de titres.
    ok("un veto de la specification declasse un 13/13",
       it.niveau(0, 0, 0, ["volume dollar 20j < 20 M$"], False) == "hors")
    ok("sans veto ni manque, 13/13 donne LES 13 BLOCS PASSENT",
       it.niveau(0, 0, 0, [], False) == "complet")
    ok("1 ou 2 blocs manquants : IL MANQUE PEU ; 3 : SIGNAL ABSENT",
       it.niveau(1, 0, 0, [], False) == "proche"
       and it.niveau(2, 0, 0, [], False) == "proche"
       and it.niveau(3, 0, 0, [], False) == "loin")
    ok("chaque marche a sa classe CSS et son mot court",
       all(c in gr.VERDICT_CSS and c in gr.VERDICT_MOT for c in it.TITRES))

    # --- Wilson : les memes bornes que la page, sur 3 320 couples
    ecarts = [(k, n) for n in range(1, 81) for k in range(n + 1)
              if max(abs(it.wilson(k, n)[0] - gr._wilson(k, n)[0]),
                     abs(it.wilson(k, n)[2] - gr._wilson(k, n)[2])) > 1e-9]
    ok("l'intervalle de Wilson est celui de la page (3 320 couples)",
       not ecarts)
    ok("un intervalle est toujours rendu, jamais un taux seul",
       set(it.historique({"n": 11, "gagnants": 5})) >= {"bas", "haut", "phrase"})
    ok("sous 30 trades, la reserve est ecrite noir sur blanc",
       "trop large" in it.historique({"n": 11, "gagnants": 5})["reserve"]
       and it.historique({"n": 40, "gagnants": 22})["reserve"] == "")

    # --- les 13 mesures existent et nomment leurs deux nombres
    brut, bb = serie(n=1200, seed=3, derive=0.0006), serie(n=1200, seed=9)
    d = enrich(brut, bench_close=bb["close"])
    b = enrich(bb)
    m = it.mesures(d, b)
    ok("les 13 blocs ont chacun leur mesure et son seuil", len(m) == 13)
    ok("aucun texte de mesure n'est vide",
       all(v["texte"] and "{" not in v["texte"] for v in m.values()))

    # --- le vocabulaire suit l'unite de temps : « la veille » est faux
    #     sur l'onglet 1 MOIS.
    mm = it.mesures(d, b, cle="mois", periodes=gr.periodes_unite("mois"))
    ok("sur l'unite MOIS, la barre precedente est le mois precedent",
       "mois précédent" in mm["3c"]["texte"] and "veille" not in mm["3c"]["texte"])
    ok("et le genitif se contracte (« du mois precedent »)",
       "de le " not in mm["3c"]["texte"])

    # --- un bloc manquant retrouve toujours son code
    ok2 = bool(R.market_regime_ok(b))
    sig = R.evaluate(d, "TEST", ok2, days_to_earnings=999)
    sor = R.evaluate_exit(d, ok2)
    et = gr._bloc_etats(d, sig)
    u = it.lire_unite(d, b, sig, sor, et)
    ok("chaque bloc manquant est nomme ET chiffre",
       u["manquants"] and all(x["code"] != "?" and x["texte"]
                              for x in u["manquants"]))

    # --- « resultats inconnus » n'est pas un defaut du titre
    class Sig13:
        vetos = ["RÉSULTATS INCONNUS — à vérifier à la main"]
    et13 = [{"nom": lab, "etat": "ok"} for lab in LABELS.values()]
    u13 = it.lire_unite(d, b, Sig13(), {k: False for k in sor}, et13)
    ok("un calendrier de resultats absent ne declasse pas le titre",
       u13["niveau"] == "complet" and u13["vigilance"])

    class SigVeto:
        vetos = ["volume dollar 20j < 20 M$"]
    uv = it.lire_unite(d, b, SigVeto(), {k: False for k in sor}, et13)
    ok("mais un veto de la specification, oui",
       uv["niveau"] == "hors" and gr.VERDICT_MOT[uv["niveau"]] == "HORS CRITÈRES")
    ok("et le sous-titre NOMME le veto au lieu de dire « veto »",
       gr._sous_verdict(uv) == "volume dollar 20j < 20 M$")

    # --- un refus qualite dit POURQUOI
    ur = it.lire_unite(d, b, sig, sor, et, refuse=True,
                       motifs=["derniere barre au 2020-01-01"])
    ok("un refus qualite remonte son motif exact",
       ur["niveau"] == "refus"
       and "2020-01-01" in gr._sous_verdict(ur))

    # --- l'accord des unites n'invente aucune ponderation
    a = it.accord([("jour", "1 JOUR", {"interet": {"compte": "13 / 13",
                                                   "niveau": "complet",
                                                   "titre": "x", "ok": 13,
                                                   "total": 13, "ko": 0}}),
                   ("an", "1 AN", None)])
    ok("une unite sans historique n'est pas comptee comme un echec",
       a["mesurables"] == 1 and a["pleines"] == 1
       and a["lignes"][1]["compte"] == "—")

    # --- les deux rappels permanents
    ok("le rappel de Phase 0 est present et parle d'absence d'avantage",
       "Phase 0" in it.RAPPEL_PHASE0 and "avantage" in it.RAPPEL_PHASE0)
    ok("la carte dit explicitement que ce n'est pas un avis",
       it.PAS_UN_AVIS.startswith("Ce n'est pas un avis"))
    # Le point qui compte vraiment : aucun mot d'ordre nulle part.
    textes = " ".join(list(it.TITRES.values()) + list(it.MOTIFS.values())
                      + [it.PAS_UN_AVIS, it.RAPPEL_PHASE0]).lower()
    ok("aucun impératif d'achat ou de vente dans les libelles",
       not any(w in textes for w in ("achetez", "vendez", "achète",
                                     "conseill", "recommand", "il faut acheter")))


def test_chandeliers() -> None:
    """Les figures : geometrie verifiable, et rien de plus."""
    from . import chandeliers as cd
    from .indicators import enrich

    print("\n— Lecture des chandeliers —")

    # Les seuils sont ecrits AVANT toute mesure. Les deplacer apres
    # avoir regarde un resultat serait la meme peche que sur les
    # parametres de strategie : avec dix seuils on finit toujours par
    # faire briller une figure.
    ok("les seuils de forme sont ceux qui ont ete ecrits",
       (cd.SEUILS["doji_corps"], cd.SEUILS["petit_corps"],
        cd.SEUILS["grand_corps"], cd.SEUILS["marubozu"],
        cd.SEUILS["ombre_longue"], cd.SEUILS["ombre_opposee"],
        cd.SEUILS["corps_tiers"], cd.SEUILS["tendance_barres"],
        cd.SEUILS["tendance_seuil"], cd.SEUILS["etendue_mini_atr"],
        cd.SEUILS["etendue_mini_pct"])
       == (0.10, 0.35, 0.60, 0.90, 2.0, 0.15, 0.66, 5, 0.02, 0.30, 0.0015))
    ok("les horizons de suivi sont 1, 5, 10 et 20 barres",
       cd.HORIZONS == (1, 5, 10, 20) and cd.MINI_CAS == 10)

    # --- chaque figure est construite A LA MAIN et doit etre trouvee
    def bougies(lig, avant=None):
        out = []
        if avant:
            sens, nb = avant
            prix = 100.0
            for _ in range(nb):
                suiv = prix * (1 + sens)
                out.append((prix, max(prix, suiv) * 1.002,
                            min(prix, suiv) * 0.998, suiv))
                prix = suiv
            ech = prix / lig[0][0]
            lig = [tuple(x * ech for x in b) for b in lig]
        out += list(lig)
        idx = pd.bdate_range("2020-01-02", periods=len(out))
        df = pd.DataFrame(out, columns=["open", "high", "low", "close"],
                          index=idx)
        df["volume"] = 1e6
        df["atr14"] = (df["high"] - df["low"]).rolling(5, min_periods=1).mean()
        return df

    CAS = [
        ("doji", [(100, 103, 97, 100.1)], None),
        ("marubozu_hausse", [(100, 110.2, 99.8, 110)], None),
        ("marubozu_baisse", [(110, 110.2, 99.8, 100)], None),
        ("marteau", [(105, 105.6, 95, 105.4)], (-0.01, 8)),
        ("pendu", [(105, 105.6, 95, 105.4)], (0.01, 8)),
        ("etoile_filante", [(100, 110, 99.6, 100.3)], (0.01, 8)),
        ("marteau_inverse", [(100, 110, 99.6, 100.3)], (-0.01, 8)),
        ("harami_hausse", [(110, 110.5, 99.5, 100), (103, 106, 102, 105)], None),
        ("harami_baisse", [(100, 110.5, 99.5, 110), (106, 108, 102, 103)], None),
        ("avalement_hausse", [(105, 106, 102, 103), (101, 110, 100.5, 109)], None),
        ("avalement_baisse", [(103, 106, 102, 105), (109, 110, 100.5, 101)], None),
        ("penetrante", [(110, 110.5, 99.5, 100), (98, 106.5, 97.5, 106)], None),
        ("nuage_noir", [(100, 110.5, 99.5, 110), (112, 112.5, 103, 103.5)], None),
        ("etoile_matin", [(110, 110.5, 99.5, 100), (99, 100.5, 98, 99.5),
                          (100, 107, 99.5, 106)], None),
        ("etoile_soir", [(100, 110.5, 99.5, 110), (110.5, 112, 110, 111),
                         (110, 110.5, 103, 104)], None),
        ("trois_soldats", [(100, 105.2, 99.8, 105), (105, 110.2, 104.8, 110),
                           (110, 115.2, 109.8, 115)], None),
        ("trois_corbeaux", [(115, 115.2, 109.8, 110), (110, 110.2, 104.8, 105),
                            (105, 105.2, 99.8, 100)], None),
    ]
    manquantes = [nom for nom, lig, av in CAS
                  if not cd.figures(bougies(lig, av))[nom][-1]]
    ok(f"les {len(CAS)} figures sont detectees sur une bougie construite "
       f"a la main", not manquantes)
    for m in manquantes:
        print(f"          -> {m} non detectee")
    ok("chaque figure detectee a un nom et une definition ecrite",
       all(c in cd.NOMS and c in cd.FORMES
           for c in cd.figures(bougies([(100, 103, 97, 100.1)]))
           if c not in ("",)))

    # Une seance ou le titre n'a pas bouge ne porte aucune figure : tous
    # les rapports d'ombre y explosent.
    plate = bougies([(100, 100.02, 99.98, 100.0)])
    ok("une bougie quasi plate ne porte aucune figure",
       not any(m[-1] for m in cd.figures(plate).values()))

    # --- le point qui compte : sur du BRUIT, tout doit etre indiscernable
    nets = mesures = 0
    for graine in range(6):
        d = enrich(serie(n=2200, seed=graine, derive=0.0, vol=0.014))
        r = cd.lecture(d)
        for bloc in (r["figures"], r["volume_prix"]):
            for f in bloc:
                for x in f["suivi"]:
                    if not x.get("assez"):
                        continue
                    mesures += 1
                    nets += bool(not x["indiscernable"])
    part = nets / max(1, mesures) * 100
    # L'intervalle est a 95 % : environ 5 % de faux positifs sont
    # ATTENDUS. Beaucoup plus voudrait dire que la comparaison au taux
    # de base est mal faite et que le module fabrique un avantage.
    ok(f"sur du bruit pur, {part:.1f} % des mesures ressortent nettes "
       f"(5 % attendus, {mesures} mesures)", part < 12.0)

    # Et le piege des comparaisons multiples doit etre AFFICHE, pas tu.
    d = enrich(serie(n=1500, seed=3, derive=0.0004))
    r = cd.lecture(d)
    ok("le rapport compte ses propres mesures et dit combien sont "
       "attendues par hasard",
       r["comptage"]["mesures"] > 0
       and "hasard" in r["comptage"]["phrase"]
       and str(round(r["comptage"]["mesures"] * 0.05)) in
           r["comptage"]["phrase"])
    ok("le rappel dit que le nom d'une figure n'est pas une preuve",
       "verifiee ici" in cd.RAPPEL or "vérifiée ici" in cd.RAPPEL)
    txt = cd.texte(r)
    ok("le texte nomme le taux de base a cote de chaque taux",
       "base" in txt and "indiscernable" in txt)
    ok("et dit qu'une action n'a pas d'open interest",
       "pas d'open interest" in txt)


def test_options() -> None:
    """L'open interest des OPTIONS, et le refus d'en inventer un pour
    l'action elle-meme."""
    import sys
    import types

    print("\n— Open interest des options —")

    class Chaine:
        def __init__(self, c, p):
            self.calls, self.puts = c, p

    def faux_ticker(dates):
        class T:
            options = dates
            fast_info = {"last_price": 120.0}

            def option_chain(self, _d):
                c = pd.DataFrame({"strike": [100, 110, 120, 130, 140],
                                  "openInterest": [500, 1200, 9000, 3400, 800],
                                  "volume": [50, 120, 900, 340, 80]})
                pu = pd.DataFrame({"strike": [100, 110, 120, 130, 140],
                                   "openInterest": [4200, 2600, 1500, 300, 100],
                                   "volume": [420, 260, 150, 30, 10]})
                return Chaine(c, pu)
        return T()

    vrai = sys.modules.get("yfinance")
    faux = types.ModuleType("yfinance")
    faux.Ticker = lambda _tk: faux_ticker(["2026-10-16", "2026-11-20"])
    sys.modules["yfinance"] = faux
    try:
        from . import options as op
        r = op.chaine("NVDA", echeances=2)
        ok("la chaine d'options se lit", bool(r.get("ok")))
        ok("l'open interest total est la somme des echeances",
           r["oi_calls"] == 2 * (500 + 1200 + 9000 + 3400 + 800)
           and r["oi_puts"] == 2 * (4200 + 2600 + 1500 + 300 + 100))
        ok("le rapport put/call est calcule",
           abs(r["ratio_pc"] - round(r["oi_puts"] / r["oi_calls"], 2)) < 1e-9)
        ok("le strike le plus charge est trouve",
           r["mur"] and r["mur"]["strike"] == 120.0)
        ok("l'ecart de chaque strike au cours est donne",
           all(c["ecart_pct"] is not None
               for e in r["echeances"] for c in e["gros_calls"]))
        t = op.texte(r)
        # LE point du module : ne pas laisser croire qu'une action a un
        # open interest.
        ok("le rapport dit qu'une action n'a pas d'open interest",
           "N'A PAS D'OPEN INTEREST" in t.upper())
        ok("et renvoie vers la notion voisine pour l'action",
           "chandeliers" in t)
        ok("la reserve sur l'absence d'historique est ecrite",
           "ne se compare a rien" in t)
        # Aucune direction dans ce qui est AFFICHE. On ne regarde pas la
        # docstring : elle contient « il ne dit pas qu'un rapport
        # put/call eleve est haussier », qui REFUSE la lecture au lieu
        # de la faire. Un controle qui ne distingue pas une affirmation
        # de sa negation punit la bonne documentation.
        bas = (t + op.RESERVE).lower()
        ok("aucune lecture directionnelle affichee du rapport put/call",
           not any(w in bas for w in ("est haussier", "est baissier",
                                      "signal d'achat", "signal de vente",
                                      "anticipe", "annonce une")))
        faux.Ticker = lambda _tk: faux_ticker([])
        ok("un titre sans option cotee ressort avec son motif",
           not op.chaine("XXX").get("ok"))
    finally:
        if vrai is not None:
            sys.modules["yfinance"] = vrai
        else:
            sys.modules.pop("yfinance", None)


def test_palmares() -> None:
    """MA LISTE : le decoupage des tickers, les groupes, et l'ordre."""
    from . import palmares as pm

    print("\n— Ma liste : decoupage et classement —")

    # --- le decoupage ne coupe QUE sur les separateurs
    ok("les espaces, virgules et points-virgules separent",
       pm.decoupe("COIN, HOOD ; TLX.DE") == ["COIN", "HOOD", "TLX.DE"])
    ok("un point ne separe pas tout seul : MC.PA reste entier",
       pm.decoupe("MC.PA OR.PA") == ["MC.PA", "OR.PA"])
    ok("les doublons partent, l'ordre de saisie reste",
       pm.decoupe("hood COIN hood") == ["HOOD", "COIN"])

    # --- l'eclatement demande AUX DONNEES, il ne devine pas
    REELS = {"COIN", "HOOD", "EPXD", "TLX", "TLX.DE", "MC.PA", "OR.PA"}
    vus = []

    def existe(t):
        vus.append(t)
        return t in REELS

    ok("un jeton qui EST un ticker n'est pas touche",
       pm.eclate("MC.PA", existe) == ["MC.PA"])
    ok("un collage de tickers se coupe",
       pm.eclate("COIN.TLX.HOOD.EPXD", existe)
       == ["COIN", "TLX", "HOOD", "EPXD"])
    # LE cas qui a fait echouer la premiere version : « .MC » est le
    # suffixe de Madrid, donc « HOOD.MC » est plausible — et pourtant
    # Frederic voulait « HOOD » puis « MC.PA ». Seules les donnees
    # tranchent.
    ok("« COIN.HOOD.MC.PA.TLX.DE » rend COIN, HOOD, MC.PA, TLX.DE",
       pm.eclate("COIN.HOOD.MC.PA.TLX.DE", existe)
       == ["COIN", "HOOD", "MC.PA", "TLX.DE"])
    vus.clear()
    pm.eclate("COIN.HOOD.MC.PA.TLX.DE", existe)
    ok(f"et il a fallu interroger les donnees ({len(vus)} fois), "
       f"pas deviner", 0 < len(vus) <= 12)
    ok("un jeton entierement inconnu se coupe quand meme",
       pm.eclate("ZZZZ.YYYY", existe) == ["ZZZZ", "YYYY"])
    ok("un jeton sans point n'interroge rien",
       pm.eclate("COIN", lambda _t: (_ for _ in ()).throw(
           AssertionError("ne doit pas etre appele"))) == ["COIN"])

    # --- les tris portent chacun sur UN fait, jamais sur une somme
    ok("cinq tris proposes, tous decrits",
       set(pm.TRIS) == {"spec", "blocs", "risque", "mesure", "alpha"}
       and all(isinstance(v[0], str) and v[0] for v in pm.TRIS.values()))
    ok("le tri par defaut est celui de la specification",
       pm.TRI_DEFAUT == "spec"
       and "force relative" in pm.TRIS["spec"][0])
    faux = [
        {"ticker": "B", "rs_6m": 0.5, "ok": 13,
         "niveaux": {"risque": 2.0}, "histo": {"evR": 0.1}},
        {"ticker": "A", "rs_6m": 1.5, "ok": 9,
         "niveaux": {"risque": 5.0}, "histo": {"evR": -0.3}},
        {"ticker": "C", "rs_6m": None, "ok": 11,
         "niveaux": None, "histo": None},
    ]
    attendu = {
        "spec": ["A", "B", "C"],      # force relative decroissante
        "blocs": ["B", "C", "A"],     # le plus de blocs d'abord
        "risque": ["B", "A", "C"],    # le risque le plus faible d'abord
        "mesure": ["B", "A", "C"],    # le R moyen le plus eleve d'abord
        "alpha": ["A", "B", "C"],
    }
    mauvais = []
    for cle, att in attendu.items():
        got = [x["ticker"] for x in sorted(faux, key=pm.TRIS[cle][1])]
        if got != att:
            mauvais.append(f"{cle}: {got} au lieu de {att}")
    ok("chaque tri range comme il l'annonce", not mauvais)
    for m in mauvais:
        print(f"          -> {m}")
    # Un tri doit etre STABLE : deux titres a egalite sortent toujours
    # dans le meme ordre, sinon la page change a chaque rafraichissement.
    ega = [{"ticker": "Z", "rs_6m": 1.0, "ok": 5, "niveaux": None,
            "histo": None},
           {"ticker": "A", "rs_6m": 1.0, "ok": 5, "niveaux": None,
            "histo": None}]
    ok("a egalite, le ticker departage : l'ordre ne bouge plus",
       [x["ticker"] for x in sorted(ega, key=pm.TRIS["spec"][1])] == ["A", "Z"])

    # --- les groupes couvrent toutes les marches de l'echelle d'interet
    from . import interet as it
    cles = {g for g, _ in pm.GROUPES}
    ok("un groupe existe pour chaque marche d'interet, plus les illisibles",
       set(it.TITRES) | {"erreur"} == cles)
    ok("le groupe des 13 blocs vient en premier",
       pm.GROUPES[0][0] == "complet")

    # --- et les deux avertissements, sans lesquels la page ment
    ok("la page dit qu'il n'y a PAS de ratio risque/gain, et pourquoi",
       "aucun objectif de gain" in pm.AVERTISSEMENT_RATIO
       and "take-profit" in pm.AVERTISSEMENT_RATIO)
    ok("et que le tri de la specification est un departage non valide",
       "DÉPARTAGE" in pm.AVERTISSEMENT_TRI
       and "Phase 0" in pm.AVERTISSEMENT_TRI)
    # Aucun score composite nulle part.
    src = open(pm.__file__, encoding="utf-8").read().lower()
    ok("aucune ponderation dans le module",
       not any(w in src for w in ("poids =", "score =", "note =",
                                  "* 0.25 +", "* 0.3 +")))


def test_dossier() -> None:
    """Le majordome : il route une question, il n'invente jamais."""
    from . import dossier as ds

    print("\n— Dossier d'un titre : la porte en francais —")

    # --- la reconnaissance d'intention
    CAS = [
        ("QUE PENSE TU DE TLX", "avis"),
        ("je sors quand sur TLX.DE", "sortie"),
        ("JE SORS SOUS QUELLE CONDITION", "sortie"),
        ("je vends quand", "sortie"),
        ("je peux renforcer ?", "entree"),
        ("je rentre sur COIN ?", "entree"),
        ("combien je peux perdre", "risque"),
        ("quel stop sur COIN", "risque"),
        ("y a t il une figure sur la derniere bougie", "bougies"),
        ("un marteau sur HOOD ?", "bougies"),
        ("ca bouge combien", "horizon"),
        ("les donnees sont fiables ?", "donnees"),
        ("a quelle heure ferme la bourse", "seance"),
        # « je garde ? » demande s'il faut sortir : c'est la revue des
        # conditions de sortie qui repond, pas la duree de detention.
        ("je garde ma position ?", "sortie"),
        ("JE LA GARDE OU PAS", "sortie"),
        ("on garde combien de temps", "profil"),
        ("combien de temps je garde", "profil"),
    ]
    faux = [(q, ds.intention(q), att) for q, att in CAS
            if ds.intention(q) != att]
    ok(f"les {len(CAS)} questions sont reconnues", not faux)
    for q, eu, att in faux:
        print(f"          -> {q!r} : {eu} au lieu de {att}")

    # Les mots de la question ne doivent jamais passer pour des tickers.
    bruit = []
    for q, _a in CAS:
        for j in ds.jetons_tickers(q):
            if ds.normalise(j) in ("sors", "vends", "perdre", "figure",
                                   "bouge", "donnees", "heure", "stop",
                                   "renforcer", "condition", "marteau"):
                bruit.append((q, j))
    ok("aucun mot de la question ne se presente comme un ticker",
       not bruit)
    for q, j in bruit[:3]:
        print(f"          -> {q!r} propose {j!r}")

    # --- le ticker est tranche PAR LES DONNEES, pas par la forme du mot
    REELS = {"TLX.DE", "COIN", "HOOD", "NVDA"}
    demandes = []

    def existe(t):
        demandes.append(t)
        return t in REELS

    ok("le titre nomme dans la question est retrouve",
       ds.comprend("je sors quand sur TLX.DE", existe)[1] == "TLX.DE")
    ok("sans titre nomme, le titre courant sert de defaut",
       ds.comprend("je sors quand", existe, "COIN")[1] == "COIN")
    ok("et il a fallu interroger les donnees, pas deviner", demandes)
    ok("un titre inconnu ne produit pas de reponse inventee",
       ds.comprend("que penses-tu de ZZZZ", existe)[1] is None)

    # --- une section par intention, aucune orpheline
    ok("chaque intention a sa section",
       {c for c, _m in ds.INTENTIONS} <= set(ds.SECTIONS))
    ok("et chaque section sait se fabriquer",
       all(callable(f) for _t, f in ds.SECTIONS.values()))

    # --- LE POINT QUI COMPTE : TOUT chiffre affiche vient du dossier
    #
    # Premiere version de ce controle : passer un dossier VIDE et
    # exiger qu'aucun nombre n'en sorte. Elle ne valait rien — un
    # dossier vide sort par les chemins de repli (« indisponible »), et
    # le code qui met les chiffres en forme n'est jamais atteint. Le
    # test passait meme apres avoir glisse « Objectif suggere :
    # +12,50 % » dans une section.
    #
    # Le vrai controle : un dossier REMPLI, et chaque nombre affiche doit
    # se retrouver soit dans les valeurs du dossier, soit parmi les
    # nombres ecrits en dur dans les gabarits du module. Rien d'autre
    # n'a le droit d'apparaitre.
    import re as _re

    src_ds = open(ds.__file__, encoding="utf-8").read()
    # Les nombres qui appartiennent aux phrases elles-memes : « 1 % du
    # sleeve », « ATR 14 », « 25 % par ligne »... On les releve dans le
    # source au lieu de les recopier, sinon la liste derive.
    en_dur = set(_re.findall(r"\d+(?:[.,]\d+)?", src_ds))

    def _valeurs(o, acc):
        if isinstance(o, dict):
            for v in o.values():
                _valeurs(v, acc)
        elif isinstance(o, (list, tuple)):
            for v in o:
                _valeurs(v, acc)
        elif isinstance(o, bool):
            pass
        elif isinstance(o, (int, float)):
            for f in (f"{o:g}", f"{o:.0f}", f"{o:.1f}", f"{o:.2f}"):
                acc.add(f)
                acc.add(f.replace(".", ","))
        elif isinstance(o, str):
            for n in _re.findall(r"\d+(?:[.,]\d+)?", o):
                acc.add(n)
                acc.add(n.replace(",", "."))
                acc.add(n.replace(".", ","))
        return acc

    # Des cours synthetiques a la place du reseau. `data.loader()`
    # resout la fonction a l'appel, donc la substitution prend.
    from . import data as _dl
    _vrai = _dl.load_yf

    def _faux(tk, years=3, **_kw):
        import zlib
        g = zlib.crc32(tk.encode()) % 9999
        return serie(n=1400, seed=g % 500, derive=0.0005,
                     debut=(pd.bdate_range(
                         end=pd.Timestamp.today().normalize(),
                         periods=1400)[0]).date().isoformat())

    _dl.load_yf = _faux
    try:
        d_plein = ds.constitue("AAA")
    finally:
        _dl.load_yf = _vrai
    ok("un dossier se constitue sur les donnees d'essai",
       bool(d_plein.get("ok")))
    if not d_plein.get("ok"):
        print(f"          -> {d_plein.get('erreur')}")
    if d_plein.get("ok"):
        connus = _valeurs(d_plein, set()) | en_dur
        inventes = {}
        for cle in ds.SECTIONS:
            rep = ds.repond({"sortie": "je sors quand", "entree": "je rentre",
                             "risque": "combien je perds",
                             "bougies": "une figure ?", "horizon": "ca bouge",
                             "donnees": "fiable ?", "seance": "quelle heure",
                             "profil": "on garde combien de temps",
                             "memoire": "tu t es trompe ?",
                             "avis": "que penses-tu"}[cle], d_plein)
            txt = " ".join(rep["lignes"])
            hors = sorted({n for n in _re.findall(r"\d+(?:[.,]\d+)?", txt)
                           if n not in connus
                           and n.replace(",", ".") not in connus})
            if hors:
                inventes[cle] = hors
        ok("aucun chiffre affiche ne vient d'ailleurs que du dossier",
           not inventes)
        for cle, n in inventes.items():
            print(f"          -> {cle} sort {n[:4]} qui n'est pas au dossier")

    # CE QUE LE CONTROLE CI-DESSUS NE PEUT PAS VOIR, et le controle qui
    # le complete.
    #
    # Un nombre ECRIT EN DUR dans un gabarit est indiscernable d'une
    # constante legitime : « ATR 14 » et « Objectif suggere : +12,50 % »
    # se ressemblent pour une expression reguliere. Verifie : glisser un
    # objectif invente dans une section ne fait PAS tomber le test
    # ci-dessus.
    #
    # Ce qui se verifie par construction, en revanche, c'est qu'aucune
    # section ne CALCULE. Une phrase a le droit de lire `n['stop']` ;
    # elle n'a pas le droit d'ecrire `n['entree'] - n['stop']`. C'etait
    # le vrai defaut : le risque par titre etait calcule au moment
    # d'ecrire la phrase, donc il n'etait nulle part au dossier.
    import ast as _ast

    arbre = _ast.parse(src_ds)
    noms_sections = {f.__name__ for _t, f in ds.SECTIONS.values()}
    calculs = []
    for noeud in _ast.walk(arbre):
        if not isinstance(noeud, _ast.FunctionDef):
            continue
        if noeud.name not in noms_sections:
            continue
        for inner in _ast.walk(noeud):
            if not isinstance(inner, _ast.BinOp):
                continue
            # Une operation dont l'un des cotes lit le dossier.
            cotes = [inner.left, inner.right]
            if any(isinstance(x, _ast.Subscript) for x in cotes):
                calculs.append(
                    f"{noeud.name} ligne {inner.lineno} : "
                    f"{_ast.unparse(inner)[:60]}")
    ok("aucune section ne CALCULE : elles lisent le dossier, "
       "elles ne l'arithmetisent pas", not calculs)
    for c in calculs:
        print(f"          -> {c}")

    # Et le dossier vide ne doit rien fabriquer non plus, ni planter.
    vide = {"ok": True, "ticker": "X", "rappel": ds.RAPPEL}
    casse = []
    for cle in ds.SECTIONS:
        try:
            ds.repond("que penses-tu", vide)
            ds.repond({"sortie": "je sors quand", "entree": "je rentre",
                       "risque": "combien je perds", "bougies": "une figure ?",
                       "horizon": "ca bouge", "donnees": "fiable ?",
                       "seance": "quelle heure",
                       "profil": "on garde combien de temps",
                             "memoire": "tu t es trompe ?",
                       "avis": "que penses-tu"}[cle],
                      vide)
        except Exception as exc:
            casse.append(f"{cle}: {type(exc).__name__}")
    ok("un dossier vide ne fait planter aucune section", not casse)
    for c in casse:
        print(f"          -> {c}")

    # --- le rappel voyage avec chaque reponse
    rep = ds.repond("je sors quand", vide)
    ok("chaque reponse porte le rappel de Phase 0",
       "Phase 0" in rep["rappel"] and "pas un avis" in rep["rappel"])
    ok("l'intention « avis » ne rend PAS un avis mais la fiche",
       ds.SECTIONS["avis"][0] == "LA FICHE COMPLÈTE")
    # Aucun mot d'ordre nulle part dans les gabarits.
    src = open(ds.__file__, encoding="utf-8").read().lower()
    ok("aucun imperatif d'achat ou de vente dans les gabarits",
       not any(w in src for w in ("achetez", "vendez", "il faut acheter",
                                  "il faut vendre", "je conseille",
                                  "je recommande")))
    ok("la voix rend une phrase, pas un tableau",
       isinstance(ds.phrase(rep), str) and "\n" not in ds.phrase(rep))


def test_brain2() -> None:
    """BRAIN 2.0 et le contrat du cerveau. Aucun appel reseau : chaque
    fournisseur est remplace par une reponse ecrite ici, au format de
    son API."""
    import json
    import tempfile
    import urllib.error
    from pathlib import Path

    from . import brain2 as b2
    from . import cerveau as cv

    print("\n— BRAIN 2.0 : le contrat du cerveau —")
    # --- la consigne garde les lignes rouges du projet ----------------
    lignes_rouges = {
        "pas de verdict": "ne réponds ni « achète », ni « vends », ni « garde »",
        "il ne voit pas les cours": "Tu ne vois jamais les",
        "aucun chiffre invente": "n'écris AUCUN nombre",
        "comparaisons multiples": "environ 72 mesures",
        "memoire en entier": "cite-la EN ENTIER",
        "pas de prediction": "Une prédiction de prix",
        "pas de gain espere": "Un gain espéré en euros",
        "pas de meilleur horizon": "Un « meilleur horizon »",
        "sources web": "attribue chaque chiffre trouvé à sa source",
    }
    manque = [k for k, v in lignes_rouges.items() if v not in cv.CONSIGNE]
    ok("la consigne du modele garde les lignes rouges du projet",
       not manque)
    for k in manque:
        print(f"          -> absente : {k}")

    # --- le dossier est reduit, jamais coupe --------------------------
    gros = {"question": "q", "portefeuille": {"lignes": [
                {"titre": f"T{i}", "poids_pc": 12.5} for i in range(8)]},
            "chandeliers": {"liste": [{"nom": "x" * 40, "k": i}
                                      for i in range(900)]},
            "horizons": [{"typique": 1.5} for _ in range(300)],
            # Un dictionnaire ne se raccourcit pas : s'il est trop lourd,
            # il tombe en entier, et c'est dit dans « _omis ».
            "annexe": {f"cle_{i}": 4321.5 + i for i in range(3000)},
            "_proteges": ["question", "portefeuille"]}
    env = cv.compacte(gros)
    txt = json.dumps(env, ensure_ascii=False, indent=1, default=str)
    ok(f"un dossier de {cv._taille(gros)} caracteres passe sous le plafond "
       f"({len(txt)})", len(txt) <= cv.MAX_DOSSIER)
    ok("et reste du JSON entier, portefeuille compris",
       json.loads(txt)["portefeuille"] == gros["portefeuille"])
    ok("la liste des protections ne part pas chez le fournisseur",
       "_proteges" not in env)
    petit = {"a": 1, "_proteges": ["a"]}
    ok("un petit dossier part tel quel", cv.compacte(petit) == {"a": 1})

    # --- les chiffres se verifient sur ce qui a ete ENVOYE ------------
    tmp = Path(tempfile.mkdtemp())
    sauve = (cv.FICHIER, cv.DOSSIER, dict(cv.APPELS),
             {k: os.environ.get(k) for k in ("CARRUOS_ANTHROPIC_API_KEY",
              "CARRUOS_OPENAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
              "CARRUOS_IA_FOURNISSEUR", "CARRUOS_IA_MODELE")})
    cv.FICHIER, cv.DOSSIER = tmp / "ia.json", tmp
    for k in sauve[3]:
        os.environ.pop(k, None)
    try:
        recu = {}

        def faux(msgs, modele, cle):
            recu["contenu"] = msgs[-1]["content"]
            return "Le poids est de 12,5 %, et 4321,5 aussi.", []
        cv.APPELS["anthropic"] = faux
        os.environ["CARRUOS_ANTHROPIC_API_KEY"] = "cle-essai-1234"
        r = cv.demande("q", dossier=gros)
        ok("le portefeuille arrive jusqu'au modele",
           '"portefeuille"' in recu.get("contenu", "")
           and len(recu.get("contenu", "")) < cv.MAX_DOSSIER + 200)
        ok("un chiffre present seulement dans ce qui n'a PAS ete envoye "
           "n'est pas « verifie »",
           "4321,5" in r["chiffres"]["hors_dossier"]
           and "12,5" not in r["chiffres"]["hors_dossier"]
           and "annexe" in r.get("omis", []))
        v = cv.verifie_chiffres(
            "Voir https://exemple.org/2026/09/25/depeche-12 : 12,4 %", {})
        ok("les chiffres d'une adresse Web ne sont pas des mesures",
           v["hors_dossier"] == ["12,4"])

        # --- les cles : la specifique d'abord, la generique en dernier
        os.environ.pop("CARRUOS_ANTHROPIC_API_KEY", None)
        os.environ["OPENAI_API_KEY"] = "generique-aaaa"
        e = cv.etat()
        ok("une cle generique sert quand aucune n'est enregistree, et la "
           "page dit d'ou elle vient",
           e["fournisseur"] == "openai" and e["source"] == "OPENAI_API_KEY")
        os.environ["CARRUOS_OPENAI_API_KEY"] = "specifique-bbbb"
        ok("la cle propre a CARRUOS l'emporte sur la generique",
           cv._config()["cles"]["openai"] == "specifique-bbbb")
        cv.configure(fournisseur="openai")
        ecrit = cv.FICHIER.read_text(encoding="utf-8")
        ok("une cle venue de l'environnement n'est jamais ecrite sur le "
           "disque", "specifique" not in ecrit and "generique" not in ecrit)
    finally:
        cv.FICHIER, cv.DOSSIER = sauve[0], sauve[1]
        cv.APPELS.clear()
        cv.APPELS.update(sauve[2])
        for k, val in sauve[3].items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val

    # --- la recherche Web, aux deux formats d'OpenAI ------------------
    vrai_poste = cv._poste
    envois = []

    def poste_openai(url, charge, entetes, delai=180):
        envois.append(charge)
        return {"output": [
            {"type": "web_search_call", "status": "completed"},
            {"type": "message", "content": [{
                "type": "output_text", "text": "Selon Reuters, 3 usines.",
                "annotations": [
                    {"type": "url_citation", "url": "https://a.org/x",
                     "title": "A"},
                    {"type": "url_citation",
                     "url_citation": {"url": "https://b.org/y",
                                      "title": "B"}}]}]}]}
    cv._poste = poste_openai
    try:
        t, src = cv._openai([{"role": "user", "content": "q"}], "m", "k")
        ok("OpenAI : texte lu, et les deux formes de citation donnent leur "
           "source", t == "Selon Reuters, 3 usines."
           and [x["url"] for x in src] == ["https://a.org/x",
                                           "https://b.org/y"])
        ok("OpenAI : l'outil de recherche est demande",
           envois[-1].get("tools") == [{"type": "web_search"}])

        def poste_refus(url, charge, entetes, delai=180):
            envois.append(charge)
            if "tools" in charge:
                raise urllib.error.HTTPError(url, 400, "outil", {}, None)
            return {"output": [{"type": "message", "content": [
                {"type": "output_text", "text": "sans outil"}]}]}
        cv._poste = poste_refus
        t, _s = cv._openai([{"role": "user", "content": "q"}], "m", "k")
        ok("un modele qui refuse l'outil repond quand meme, sans lui",
           t == "sans outil")

        # --- Anthropic : reprise apres pause, citations, refus -------
        etapes = []

        def poste_anthropic(url, charge, entetes, delai=180):
            etapes.append((charge, entetes))
            if len(etapes) == 1:
                return {"stop_reason": "pause_turn", "content": [
                    {"type": "server_tool_use", "name": "web_search"}]}
            return {"stop_reason": "end_turn", "content": [
                {"type": "text", "text": "Selon la dépêche, ",
                 "citations": [{"type": "web_search_result_location",
                                "url": "https://c.org/z", "title": "C"}]},
                {"type": "text", "text": "rien d'autre."}]}
        cv._poste = poste_anthropic
        try:
            t, src = cv._anthropic([{"role": "user", "content": "q"}],
                                   "claude-opus-5", "k")
        except RuntimeError:
            t, src = "", []
        ok("Anthropic : la recherche interrompue reprend, et le texte cite "
           "se recolle", t == "Selon la dépêche, rien d'autre."
           and len(etapes) == 2 and src and src[0]["url"] == "https://c.org/z")
        c0, h0 = etapes[0]
        ok("Anthropic : outil de recherche du modele, et repli en cas de "
           "refus", c0["tools"][0]["type"] == "web_search_20260209"
           and c0.get("fallbacks") == "default"
           and h0.get("anthropic-beta") == "server-side-fallback-2026-07-01")
        cv._poste = lambda *a, **k: {"stop_reason": "refusal",
                                     "stop_details": {"explanation": "x"},
                                     "content": []}
        try:
            cv._anthropic([{"role": "user", "content": "q"}], "m", "k")
            decline = False
        except RuntimeError as exc:
            decline = "décliné" in str(exc)
        ok("un refus du modele est dit, pas rendu comme une reponse vide",
           decline)
    finally:
        cv._poste = vrai_poste

    # --- les faits du portefeuille, comptes par le programme ---------
    photo = {"etat": "connecte", "simulation": False, "numero": "U7654321",
             "hote": "127.0.0.1", "port": 7496, "quand": "10:00:00",
             "lignes": [
                 {"ticker": "AAA", "devise": "USD", "quantite": 10,
                  "prix_revient": 100, "cours": 150, "valeur": 1500,
                  "latent": 500, "type_cours_libelle": "TEMPS RÉEL"},
                 {"ticker": "BBB", "devise": "USD", "quantite": 10,
                  "prix_revient": 50, "cours": 40, "valeur": 400,
                  "latent": -100, "type_cours_libelle": "DIFFÉRÉ"},
                 {"ticker": "CCC", "devise": "USD", "quantite": 1,
                  "prix_revient": 100, "cours": 100, "valeur": 100,
                  "latent": 0, "type_cours_libelle": "TEMPS RÉEL"}],
             "franchissements": [{"ticker": "BBB"}],
             "sans_fraicheur": ["BBB"]}
    reg = [{"ticker": "AAA", "stop": 120}, {"ticker": "BBB", "stop": 45}]
    f = b2.faits_portefeuille(photo, reg, conditions=False)
    poids = {x["titre"]: x["poids_pc"] for x in f["lignes"]}
    ok("les poids se comptent, et font 100 %",
       poids == {"AAA": 75.0, "BBB": 20.0, "CCC": 5.0})
    ok("une seule devise : le plafond de 25 % se verifie",
       f["plafond_verifiable"] and f["au_dessus_du_plafond"] == ["AAA"])
    ok("stops franchis, lignes sans stop et cours differes sont comptes",
       f["stops_franchis"] == ["BBB"] and f["sans_stop_inscrit"] == ["CCC"]
       and f["cours_non_temps_reel"] == ["BBB"])
    ok("le gain latent se rapporte au prix de revient",
       [x["latent_pc"] for x in f["lignes"]] == [50.0, -20.0, 0.0])
    deux = {**photo, "lignes": photo["lignes"] + [
        {"ticker": "DDD.PA", "devise": "EUR", "quantite": 1, "cours": 10,
         "valeur": 10, "latent": 0}]}
    f2 = b2.faits_portefeuille(deux, reg, conditions=False)
    ok("deux devises sans taux de change : le plafond n'est PAS verifie, "
       "et c'est dit", not f2["plafond_verifiable"]
       and not f2["au_dessus_du_plafond"]
       and any("ne se vérifie pas" in l for l in b2.lignes_portefeuille(f2)))
    ctx = json.dumps(b2.contexte("q", None, f), default=str)
    ok("ni le numero de compte, ni l'hote, ni le port ne partent au modele",
       "U7654321" not in ctx and "7496" not in ctx
       and "127.0.0.1" not in ctx)
    # Deux couches, testees chacune : les faits n'en portent pas, et le
    # filtre les retirerait s'ils en portaient.
    ok("les faits du portefeuille ne portent aucun identifiant de session",
       not set(b2.SECRETS) & set(f))
    ok("et le filtre les retire d'une photo qui en porterait",
       not set(b2.SECRETS) & set(b2._sans_secrets(photo)))

    # --- le majordome reconnait une question sur le portefeuille -----
    vrai = b2.faits_portefeuille
    b2.faits_portefeuille = lambda *a, **k: f
    try:
        r = cv.repond("que penses tu de mon portefeuille IBKR ?",
                      existe=lambda t: t == "IBKR", avec_modele=False)
    finally:
        b2.faits_portefeuille = vrai
    ok("« mon portefeuille IBKR » : le courtier, pas le titre Interactive "
       "Brokers", r["ticker"] is None
       and (r["faits"] or {}).get("ticker") == "PORTEFEUILLE")

def test_memo() -> None:
    """Le memo cite des seuils : ils doivent etre ceux qui tournent.

    Un memo qui derive du code est pire qu'aucun memo — il donne
    confiance dans un chiffre faux. Chaque nombre cite est donc
    reconfronte a la constante d'ou il vient.
    """
    from pathlib import Path

    from . import chandeliers as cd
    from . import qualite as ql
    from . import rules as R
    from .indicators import PERIODES

    from . import brain2 as b2_
    from . import carnet as cn
    from . import cerveau as cv
    from . import ibkr as ik_
    from . import objectif as ob
    from . import pead as pd_
    from . import profil as pr
    from . import strategie as sg
    # ------------------------------------------------------------------
    # La veille : un rapprochement, et RIEN de plus
    # ------------------------------------------------------------------
    print("\n— Veille : le rapprochement —")
    import json
    import re as _re

    from . import veille as vl

    ACTUS = [
        {"titre": "OPEC output cut as Saudi Arabia weighs sanctions "
                  "on Russia", "source": "R", "quand": "1", "url": "",
         "tickers": ["TTE.PA", "XOM"],
         "themes": ["energy_transportation", "economy_macro"]},
        {"titre": "Taiwan semiconductor export curbs tighten supply chain",
         "source": "F", "quand": "2", "url": "",
         "tickers": ["TSM"], "themes": ["technology", "manufacturing"]},
        {"titre": "Fed holds rates steady", "source": "W", "quand": "3",
         "url": "", "tickers": ["SPY"], "themes": ["economy_monetary"]},
        {"titre": "actualites indisponibles (URLError)", "erreur": True},
    ]
    LIGNES = ["NVDA", "TTE.PA", "MC.PA"]
    SECT = {"NVDA": "Technology", "TTE.PA": "Energy",
            "MC.PA": "Consumer Cyclical"}
    r = vl.rapproche(ACTUS, LIGNES, SECT)

    ok("niveau 1 : le titre nomme par la source ressort",
       any("TTE.PA" in a["titres"] for a in r["nommes"]))
    ok("un titre qui n'est pas a lui ne ressort pas",
       not any("XOM" in a["titres"] or "TSM" in a["titres"]
               for a in r["nommes"]))
    ok("niveau 2 : meme secteur declare, par la table ecrite d'avance",
       any("NVDA" in v for a in r["sectoriels"]
           for v in a["secteurs"].values()))
    # Un titre deja NOMME ne doit pas etre repete au niveau sectoriel :
    # la meme information deux fois, sous deux forces differentes, ferait
    # croire a deux rapprochements.
    ok("un titre nomme n'est pas repete au niveau sectoriel",
       not any("TTE.PA" in v for a in r["sectoriels"]
               for v in a["secteurs"].values()))
    # Les themes macro ne pointent vers aucun secteur : ils concernent
    # tout le marche, les rattacher a un secteur serait faux.
    ok("un theme macro ne fabrique aucun rapprochement sectoriel",
       all("Fed holds" not in a["titre"] for a in r["sectoriels"]))
    ok("une depeche en erreur n'est jamais rapprochee",
       all("indisponible" not in a["titre"]
           for cle in ("nommes", "sectoriels", "geo") for a in r[cle]))
    ok("niveau 3 : les mots du titre sont releves",
       any("Russia" in a["mots"].get("pays", []) for a in r["geo"]))

    # La regle qui tient tout : AUCUN chiffre ne sort de la veille. Un
    # score, un compte agrege ou un classement ferait exactement ce que
    # le projet refuse — ressembler a une mesure sans en etre une.
    #
    # La veille a le droit de RECOPIER ce que la depeche contient — son
    # titre, sa source, son horodatage. Ce qu'elle n'a pas le droit de
    # faire, c'est d'en PRODUIRE un. On retire donc d'abord tout ce
    # qu'elle recopie, puis les deux seuls comptes legitimes (combien
    # d'actualites, combien de titres), et on regarde ce qui reste.
    _txt = " ".join(vl.texte(r))
    for _a in ACTUS:
        for _cle in ("titre", "source", "quand"):
            if _a.get(_cle):
                _txt = _txt.replace(str(_a[_cle]), " ")
    _sans_ref = _re.sub(r"\b\d+ (?:actualites|de vos titres)\b", "", _txt)
    _chiffres = _re.findall(r"\d+(?:[.,]\d+)?", _sans_ref)
    ok("aucun chiffre n'est produit par la veille elle-meme",
       not _chiffres)
    for c in _chiffres[:5]:
        print(f"          -> la veille sort le nombre {c!r}")
    ok("le score de sentiment du fournisseur n'est jamais repris",
       "score" not in json.dumps(r))
    ok("le rappel voyage avec le resultat",
       "RAPPROCHEMENT" in r["rappel"] and "pas une analyse" in r["rappel"])
    ok("et le rappel dit que le risque geopolitique n'est pas chiffre",
       "pas chiffré" in vl.RAPPEL_MOTS)
    ok("le secteur est presente comme DECLARE, pas mesure",
       "DÉCLARÉ" in vl.RAPPEL_SECTEUR)
    # La table est ecrite AVANT usage et doit rester affichable : une
    # correspondance qu'on ne peut pas lire ne peut pas se contester.
    ok("la table de correspondance voyage avec le resultat",
       isinstance(r.get("table"), dict) and r["table"])
    ok("les deux vues partent de la MEME jointure",
       [a["titres"] for a in r["nommes"]]
       == [d["vous"]["titres"] for d in vl.decore(ACTUS, LIGNES, SECT)
           if d.get("vous", {}).get("titres")])

    # ------------------------------------------------------------------
    # Tout ce qui s'affiche est en francais
    # ------------------------------------------------------------------
    #
    # Le programme est en francais, mais il lit des sources anglaises :
    # les motifs de sortie du moteur (`stop`, `regime`, `sma50`), les
    # secteurs de yfinance (« Consumer Cyclical ») et les themes
    # d'Alpha Vantage (« energy_transportation ») sont des CLES
    # anglaises. Elles doivent le rester — elles indexent les rapports
    # et le journal d'audit — mais aucune ne doit atteindre l'ecran
    # telle quelle.
    #
    # Les trois listes attendues sont DERIVEES du code, jamais recopiees
    # a la main : une cle ajoutee demain sans son libelle fait tomber le
    # test au lieu de s'afficher en anglais.
    print("\n— Tout ce qui s'affiche est en francais —")
    import re as _rf

    from . import backtest as _bt
    from . import veille as _v2

    src_bt = Path(_bt.__file__).read_text(encoding="utf-8")
    emis = set(_rf.findall(r', "([a-z0-9_]+)"\)\n', src_bt))
    emis |= set(_rf.findall(r'j - i0, "([a-z0-9_]+)"\)', src_bt))
    sans_libelle = sorted(m for m in emis if m not in _bt.MOTIFS_FR)
    ok(f"les {len(emis)} motifs de sortie du moteur ont leur libelle",
       bool(emis) and not sans_libelle)
    for m_ in sans_libelle:
        print(f"          -> motif sans libelle francais : {m_}")

    themes_nus = sorted(t for t in _v2.THEME_SECTEURS if t not in _v2.THEMES_FR)
    ok("chaque theme de la veille a son libelle francais", not themes_nus)
    for t in themes_nus:
        print(f"          -> theme sans libelle : {t}")

    secteurs_nus = sorted({s for secs in _v2.THEME_SECTEURS.values()
                           for s in secs if s not in _v2.SECTEURS_FR})
    ok("chaque secteur cite par la table a son libelle francais",
       not secteurs_nus)
    for s_ in secteurs_nus:
        print(f"          -> secteur sans libelle : {s_}")

    # Et les libelles eux-memes doivent etre du francais, pas la cle
    # recopiee : « technology » n'est pas une traduction de
    # « technology ».
    # Quelques mots s'ecrivent de la meme facon dans les deux langues.
    # Les exempter NOMMEMENT plutot que d'assouplir la regle : une
    # exemption se lit et se conteste, un test relache ne se voit plus.
    IDENTIQUES = {"finance"}
    copies = sorted(k for k, v in _v2.THEMES_FR.items()
                    if k == v and k not in IDENTIQUES)
    copies += sorted(k for k, v in _v2.SECTEURS_FR.items()
                     if k == v and k not in IDENTIQUES)
    copies += sorted(k for k, v in _bt.MOTIFS_FR.items()
                     if k == v and k not in IDENTIQUES)
    ok("aucun libelle n'est la cle anglaise recopiee", not copies)
    for c in copies:
        print(f"          -> libelle identique a sa cle : {c}")

    # ------------------------------------------------------------------
    # IBKR : CARRUOS lit le compte, il ne PEUT PAS y passer d'ordre
    # ------------------------------------------------------------------
    #
    # « Je n'acheterai ni ne vendrai sur CARRUOS. » Une promesse ne tient
    # pas face a une ligne de code ajoutee un soir de fatigue ; un test,
    # si. On lit le module comme un ARBRE SYNTAXIQUE — pas comme du texte,
    # sinon la liste des noms interdits, qui les contient, se ferait
    # refuser elle-meme — et on refuse tout usage d'un nom d'ordre.
    print("\n— IBKR : lecture seule, par construction —")
    import ast as _ast

    from . import ibkr as _ik

    src_ik = Path(_ik.__file__).read_text(encoding="utf-8")
    arbre = _ast.parse(src_ik)
    usages = set()
    for n in _ast.walk(arbre):
        if isinstance(n, _ast.Name) and n.id in _ik.ORDRES_INTERDITS:
            usages.add(n.id)
        elif isinstance(n, _ast.Attribute) and n.attr in _ik.ORDRES_INTERDITS:
            usages.add(n.attr)
        elif isinstance(n, (_ast.Import, _ast.ImportFrom)):
            for al in n.names:
                if al.name.split(".")[-1] in _ik.ORDRES_INTERDITS:
                    usages.add(al.name)
    ok("aucun nom d'ordre n'est utilise dans le module IBKR", not usages)
    for u in sorted(usages):
        print(f"          -> nom d'ordre trouve : {u}")

    # Chaque ouverture de session porte readonly=True, en toutes lettres.
    connexions = [n for n in _ast.walk(arbre)
                  if isinstance(n, _ast.Call)
                  and isinstance(n.func, _ast.Attribute)
                  and n.func.attr == "connect"]
    def _lecture_seule(n):
        return any(k.arg == "readonly" and isinstance(k.value, _ast.Constant)
                   and k.value.value is True for k in n.keywords)
    ok("chaque connexion a IBKR est ouverte en readonly=True",
       bool(connexions) and all(_lecture_seule(n) for n in connexions))

    # Et ce module est la SEULE porte : aucun autre fichier n'importe la
    # bibliotheque IBKR. Sinon le verrou ci-dessus se contournerait par
    # le fichier d'a cote.
    portes = []
    for f in sorted(Path(_ik.__file__).parent.glob("*.py")):
        if f.name in ("ibkr.py", "data.py") or f.name.startswith("test_"):
            continue
        t = f.read_text(encoding="utf-8")
        if _re.search(r"^\s*(?:from|import)\s+(?:ib_async|ib_insync|ibapi)\b",
                      t, _re.M):
            portes.append(f.name)
    ok("aucun autre module n'importe la bibliotheque IBKR", not portes)
    for f in portes:
        print(f"          -> seconde porte vers IBKR : {f}")
    # data.load_ibkr lit des historiques : il doit, lui aussi, etre en
    # lecture seule.
    src_data = Path(_ik.__file__).with_name("data.py").read_text(encoding="utf-8")
    ok("le chargeur d'historique IBKR est lui aussi en lecture seule",
       "readonly=True" in src_data)

    # --- Le comportement, contre un faux TWS -------------------------
    from types import SimpleNamespace as _NS

    class _Tick:
        def __init__(self, p, t):
            self._p, self.marketDataType = p, t

        def marketPrice(self):
            return self._p

    class _FauxIB:
        vu = []

        def __init__(self):
            self._co, self._n = False, 0

        def connect(self, hote, port, clientId, readonly, timeout):
            _FauxIB.vu.append(readonly)
            self._co = True

        def isConnected(self):
            self._n += 1
            return self._co and self._n < 5

        def managedAccounts(self):
            return ["U7654321"]

        def reqMarketDataType(self, t):
            pass

        def reqPnL(self, a):
            return _NS(dailyPnL=-40.0, unrealizedPnL=500.0, realizedPnL=0.0)

        def portfolio(self, a=None):
            def mk(sym, ex, cur, cid, q, px, avg):
                return _NS(contract=_NS(symbol=sym, primaryExchange=ex,
                                        exchange="SMART", currency=cur,
                                        conId=cid, secType="STK"),
                           position=q, marketPrice=px, marketValue=q * px,
                           averageCost=avg, unrealizedPNL=q * (px - avg),
                           realizedPNL=0.0, account=a)
            return [mk("TLX", "IBIS", "EUR", 1, 10, 300.0, 331.5),
                    mk("NVDA", "NASDAQ", "USD", 2, 5, 180.0, 120.0)]

        def reqMktData(self, c):
            return {1: _Tick(296.4, 1), 2: _Tick(181.2, 3)}[c.conId]

        def reqPnLSingle(self, a, m, cid):
            return _NS(dailyPnL=-36.0 if cid == 1 else 6.0)

        def accountValues(self, a=None):
            return [_NS(tag="NetLiquidation", value="25480", currency="BASE")]

        def sleep(self, s):
            time.sleep(0.02)

        def disconnect(self):
            self._co = False

    import time
    _ik.FABRIQUE = _FauxIB
    try:
        _L = _ik.Liaison()
        _L.demarre("127.0.0.1", 7496, 71)
        _ph = None
        for _ in range(100):
            time.sleep(0.02)
            _ph = _L.photo()
            if _ph.get("lignes"):
                break
        _L.arrete()
    finally:
        _ik.FABRIQUE = None
    ok("la session s'ouvre en lecture seule, verifie a l'appel",
       _FauxIB.vu and all(v is True for v in _FauxIB.vu))
    ok("un compte « U… » est reconnu comme REEL, pas comme simulation",
       _ph and _ph.get("simulation") is False)
    ok("la photo dit sur quel port la session est REELLEMENT ouverte",
       _ph and _ph.get("port") == 7496)
    _par = {l["ticker"]: l for l in (_ph or {}).get("lignes", [])}
    ok("les contrats IBKR sont traduits en tickers CARRUOS",
       set(_par) == {"TLX.DE", "NVDA"})
    ok("un cours en temps reel est dit TEMPS REEL",
       _par.get("TLX.DE", {}).get("type_cours") == "reel")
    ok("un cours differe est dit DIFFERE, jamais presente comme frais",
       _par.get("NVDA", {}).get("type_cours") == "differe")
    ok("le cours retenu est celui du tick, pas celui du flux compte",
       _par.get("TLX.DE", {}).get("cours") == 296.4)
    ok("le P&L du jour de chaque ligne est lu",
       _par.get("TLX.DE", {}).get("pnl_jour") == -36.0)

    _reg = [{"ticker": "TLX.DE", "quantite": 10, "stop": 297.0},
            {"ticker": "MC.PA", "quantite": 3, "stop": None}]
    _fr = _ik.franchissements(list(_par.values()), _reg)
    ok("le cours sous le stop INSCRIT est signale, avec le type du cours",
       len(_fr) == 1 and _fr[0]["ticker"] == "TLX.DE"
       and _fr[0]["type_cours"] == "TEMPS RÉEL")
    _rp = _ik.rapproche(list(_par.values()), _reg)
    ok("le rapprochement nomme ce que le registre ignore et ce qu'il croit",
       _rp["absents_registre"] == ["NVDA"] and _rp["absents_ibkr"] == ["MC.PA"])
    ok("une place absente de la table n'est pas devinee",
       _ik.vers_ticker("SAP", "SMART", "EUR") is None
       and _ik.vers_ticker("XYZ", "LUNE", "EUR") is None)
    ok("une option ou un contrat a terme n'est pas pris pour une action",
       _ik.vers_ticker("ES", "CME", "USD", "FUT") is None)

    # ------------------------------------------------------------------
    # La memoire : le compte COMPLET, jamais le regret selectif
    # ------------------------------------------------------------------
    print("\n— Memoire : ce que le programme a dit, et ce qui a suivi —")
    import tempfile as _tf
    from types import SimpleNamespace as _NS2

    import pandas as _pd2

    from . import memoire as _me

    _idx = _pd2.bdate_range("2025-01-02", periods=300)

    def _s(pente):
        return _pd2.Series(100 * np.exp(pente * np.arange(300)), index=_idx)

    _mk = _s(0.0005)
    _ser = {"FUSEE": _s(0.004), "PLOMB": _s(-0.003), "TIEDE": _s(0.0003),
            "BON": _s(0.003)}
    _ben = {t: _mk for t in _ser}

    def _l(tk, i, oui, manq=()):
        bl = {f"b{k}": True for k in range(13)}
        for m_ in manq:
            bl[m_] = False
        d_ = str(_idx[i].date())
        return {"ticker": tk, "date_barre": d_, "declenche": oui, "blocs": bl,
                "blocs_manquants": list(manq), "horodatage": d_ + "T20:00:00"}
    _jr = [_l("FUSEE", 10, False, ["b3"]), _l("FUSEE", 12, False, ["b3"]),
           _l("FUSEE", 12, False, ["b3"]), _l("PLOMB", 10, False, ["b3"]),
           _l("PLOMB", 40, False, ["b7"]), _l("TIEDE", 10, False, ["b7"]),
           _l("BON", 10, True), _l("PLOMB", 80, True), _l("BON", 290, True)]
    _et = _me.etats(_jr)
    ok("un doublon exact du journal ne compte qu'une fois", len(_et) == 8)
    _ob = _me.observations(_et, _ser, _ben, 20)
    ok("deux releves dans la meme fenetre ne font pas deux preuves",
       sum(1 for o in _ob["obs"] if o["ticker"] == "FUSEE") == 1)
    ok("un horizon pas encore ecoule est mis en attente, pas devine",
       _ob["en_attente"] == 1)
    _tb = _me.tableau(_ob["obs"])
    ok("les quatre cases sont comptees juste",
       _tb["cases"] == {"signal confirmé": 1, "faux signal": 1,
                        "occasion manquée": 1, "piège évité": 3})
    _ex = _me.extremes(_ob["obs"])
    ok("occasions manquees et pieges evites : toujours en MEME nombre",
       len(_ex["manquees"]) == len(_ex["evites"]) == 1
       and _ex["n_evites"] == 3)
    # Sur un echantillon plus large, l'egalite doit tenir quel que soit le
    # desequilibre des deux cotes.
    _gros = ([{"oui": False, "bat": True, "ecart": 0.01 * k, "ticker": "A",
               "date": "d", "rendement": 0.0, "n_blocs": 12, "total_blocs": 13,
               "manquants": [], "vetos": []} for k in range(9)]
             + [{"oui": False, "bat": False, "ecart": -0.01 * k, "ticker": "B",
                 "date": "d", "rendement": 0.0, "n_blocs": 12, "total_blocs": 13,
                 "manquants": [], "vetos": []} for k in range(1, 3)])
    _ex2 = _me.extremes(_gros)
    ok("meme quand les fusees sont plus nombreuses que les pieges",
       len(_ex2["manquees"]) == len(_ex2["evites"]) == 2)
    _pb = {l["bloc"]: l for l in _me.par_bloc(_ob["obs"])["lignes"]}
    ok("chaque bloc dit ce qu'il a coute ET ce qu'il a epargne",
       _pb["b3"]["manquees"] == 1 and _pb["b3"]["evites"] == 1
       and _pb["b7"]["manquees"] == 0 and _pb["b7"]["evites"] == 2)
    _ordres = [{"id": "1", "ticker": "FUSEE", "sens": "achat",
                "quand": str(_idx[11].date()) + "T15:00"},
               {"id": "2", "ticker": "BON", "sens": "achat",
                "quand": str(_idx[11].date()) + "T15:00"},
               {"id": "3", "ticker": "TIEDE", "sens": "achat",
                "quand": str(_idx[200].date()) + "T15:00"}]
    _vo = _me.vos_ordres(_ordres, _et, _ser, _ben, 20)
    ok("un ordre est range AVEC ou CONTRE le signal du jour",
       _vo["avec"]["n"] == 1 and _vo["contre"]["n"] == 1)
    ok("un ordre sans etat releve n'est pas juge apres coup",
       _vo["sans_releve"] == 1)

    # Le verdict de la memoire, mis a l'epreuve sur du bruit. Chaque
    # titre a son propre taux de reussite ET sa propre frequence de
    # « oui » : c'est le regroupement qui rend les observations
    # dependantes. Le « oui » n'y apporte rien — un verdict est donc
    # toujours faux. On exige au plus 5 % de faux verdicts, et qu'un
    # filtre qui apporte vraiment quelque chose soit reconnu.
    def _bruit(rng, effet=0.0):
        obs = []
        for t in range(25):
            base, p_oui = rng.uniform(0.3, 0.7), rng.uniform(0.05, 0.6)
            for _ in range(int(rng.integers(8, 40))):
                oui = bool(rng.random() < p_oui)
                obs.append({"ticker": f"T{t}", "oui": oui, "bat": bool(
                    rng.random() < min(1.0, base + (effet if oui else 0.0)))})
        return obs
    _rng = np.random.default_rng(21)
    _faux = sum(_me.tableau(_bruit(_rng))["lecture"]
                in ("filtre_utile", "filtre_nuisible") for _ in range(200))
    ok(f"sur 200 journaux de bruit, {_faux} faux verdicts (au plus 10)",
       _faux <= 10)
    _rng = np.random.default_rng(12)
    _vus = sum(_me.tableau(_bruit(_rng, 0.15))["lecture"] == "filtre_utile"
               for _ in range(40))
    ok(f"un filtre qui apporte 15 points est reconnu {_vus} fois sur 40 "
       f"(au moins 25)", _vus >= 25)

    # La memoire ne touche a AUCUN seuil : elle ne modifie l'attribut
    # d'aucun module. (L'empreinte des parametres geles, plus haut, le
    # verifie aussi par l'autre bout.)
    _arb = _ast.parse(Path(_me.__file__).read_text(encoding="utf-8"))
    _ecrit = [n for n in _ast.walk(_arb)
              if (isinstance(n, _ast.Attribute) and isinstance(n.ctx, _ast.Store))
              or (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
                  and n.func.id == "setattr")]
    ok("la memoire ne modifie l'attribut d'aucun module", not _ecrit)

    # Les executions IBKR : ajout seul, dedoublonne, lecture de ce qui a
    # DEJA ete execute.
    import datetime as _dt2
    _fx = Path(_tf.mkdtemp()) / "ex.jsonl"

    def _fill(i, cote):
        return _NS2(time=_dt2.datetime(2026, 9, 23, 15, 31), commissionReport=None,
                    contract=_NS2(symbol="TLX", primaryExchange="IBIS",
                                  exchange="SMART", currency="EUR",
                                  secType="STK"),
                    execution=_NS2(execId=i, side=cote, shares=10, price=296.4,
                                   acctNumber="U1"))
    _n1 = _ik.consigne([_fill("a", "BOT"), _fill("b", "SLD")], _fx)
    _n2 = _ik.consigne([_fill("a", "BOT"), _fill("c", "BOT")], _fx)
    _lus = _me.lit_executions(_fx)
    ok("une execution deja consignee ne l'est pas deux fois",
       _n1 == 2 and _n2 == 1 and len(_lus) == 3)
    ok("le sens et le ticker CARRUOS sont ecrits",
       [(r["sens"], r["ticker"]) for r in _lus]
       == [("achat", "TLX.DE"), ("vente", "TLX.DE"), ("achat", "TLX.DE")])
    _recus = []
    _ik.consigne([_fill("c", "BOT"), _fill("d", "BOT")], _fx,
                 apres=_recus.extend)
    ok("seules les executions NOUVELLES sont passees au releve",
       [r["id"] for r in _recus] == ["d"])

    # L'etat compare a un ordre du jour D est celui de la cloture de
    # D-1 : rien du jour de l'ordre, ni d'apres, ne doit y entrer.
    from . import app as _app2
    from . import audit as _ad2
    from . import cache as _ch2
    from . import data as _dl2

    def _faux2(tk, years=3, **_kw):
        import zlib
        return serie(n=900, seed=zlib.crc32(tk.encode()) % 500, derive=0.0005,
                     debut=(_pd2.bdate_range(
                         end=_pd2.Timestamp.today().normalize(),
                         periods=900)[0]).date().isoformat())
    _vrai2 = _dl2.load_yf
    _dl2.load_yf = _faux2
    _ch2.oublie()
    try:
        _jx = Path(_tf.mkdtemp()) / "audit.jsonl"
        _d_ordre = str((_pd2.Timestamp.today().normalize()
                        - _pd2.tseries.offsets.BDay(30)).date())
        _app2._releve_etat("AAA", "execution", _d_ordre + "T15:31:00",
                           fichier=_jx)
        _rl = _ad2.lit(_jx)
    finally:
        _dl2.load_yf = _vrai2
        _ch2.oublie()
    ok("un ordre est compare a l'etat de la VEILLE, jamais du jour meme",
       len(_rl) == 1 and _rl[0]["date_barre"] < _d_ordre
       and _rl[0]["source"] == "execution")
    ok("et cet etat tombe dans la fenetre que la memoire accepte",
       len(_rl) == 1 and (_pd2.Timestamp(_d_ordre)
                          - _pd2.Timestamp(_rl[0]["date_barre"])).days
       <= _me.FENETRE_RELEVE)

    print("\n— Memo de lecture —")
    f = Path(__file__).resolve().parent.parent / "MEMO-LECTURE.md"
    ok("MEMO-LECTURE.md existe a la racine", f.exists())
    if not f.exists():
        return
    m = f.read_text(encoding="utf-8")

    def _fr(x, dec=None):
        """Un nombre comme le memo l'ecrit : virgule, sans zero inutile.

        Le memo est en francais. Comparer « 0.5 » a « 0,5 » ferait
        echouer ce test sur une difference de typographie, pas sur une
        derive — et un test qui crie pour rien finit par etre ignore.
        """
        if dec is not None:
            return f"{x:.{dec}f}".replace(".", ",")
        return (f"{x:g}").replace(".", ",")

    # (ce que le memo doit contenir, la valeur qui tourne vraiment)
    ATTENDU = [
        ("RSI 14", f"**{PERIODES['rsi']}**"),
        ("MACD", f"**{PERIODES['macd'][0]} / {PERIODES['macd'][1]} / "
                 f"{PERIODES['macd'][2]}**"),
        ("Bollinger", f"**{PERIODES['bb'][0]}** séances, "
                      f"**{PERIODES['bb'][1]:.0f}** écarts-types"),
        ("SMA longue", f"**{PERIODES['sma_longue']}** séances"),
        ("SMA moyenne", f"**{PERIODES['sma_moyenne']}** séances"),
        ("EMA courte", f"**{PERIODES['ema_courte']}** séances"),
        ("plus haut de reference", f"**{PERIODES['haut']}** séances"),
        ("zone RSI", f"entre **{R.RSI_ZONE[0]:.0f} et "
                     f"{R.RSI_ZONE[1]:.0f}**"),
        ("plancher RSI", f"sous **{R.RSI_FLOOR:.0f}**"),
        ("bande EMA", f"**{_fr(R.EMA_BAND_ATR)} × ATR**"),
        ("fenetre de repli", f"**{R.PULLBACK_WINDOW}** séances"),
        ("RVOL", f"**{_fr(R.RVOL_MIN, 2)}**"),
        ("prix plancher", f"**{R.MIN_PRICE:.0f} $**"),
        ("volume dollar", f"**{R.MIN_DOLLAR_VOL / 1e6:.0f} M$**"),
        ("gap", f"**{R.GAP_VETO * 100:.0f} %** sur **{R.GAP_LOOKBACK}**"),
        ("blackout resultats", f"**{R.EARNINGS_BLACKOUT}** séances"),
        ("positions", f"**{R.MAX_POSITIONS}** positions"),
        ("risque par trade", f"**{R.RISK_PER_TRADE * 100:.0f} %**"),
        ("plafond de poids", f"**{R.MAX_WEIGHT * 100:.0f} %**"),
        ("stop ATR", f"**{_fr(R.STOP_ATR_MULT)} × ATR**"),
        ("stop swing", f"**{_fr(R.STOP_SWING_BUFFER)} × ATR**"),
        ("historique minimum", f"**{ql.HISTOIRE_MIN}** barres"),
        ("trous", f"**{ql.TROUS_MAX * 100:.0f} %**"),
        ("saut suspect", f"**{_fr(ql.SAUT_SUSPECT)}**"),
        ("doji", f"**{cd.SEUILS['doji_corps'] * 100:.0f} %**"),
        ("petit corps", f"**{cd.SEUILS['petit_corps'] * 100:.0f} %**"),
        ("grand corps", f"**{cd.SEUILS['grand_corps'] * 100:.0f} %**"),
        ("marubozu", f"**{cd.SEUILS['marubozu'] * 100:.0f} %**"),
        ("ombre longue", f"**{cd.SEUILS['ombre_longue']:.0f} ×**"),
        ("ombre opposee", f"**{cd.SEUILS['ombre_opposee'] * 100:.0f} %**"),
        ("corps dans le tiers", f"**{cd.SEUILS['corps_tiers'] * 100:.0f} %**"),
        ("contexte", f"**±{cd.SEUILS['tendance_seuil'] * 100:.0f} %** sur "
                     f"**{cd.SEUILS['tendance_barres']}**"),
        ("barre etroite ATR", f"**{_fr(cd.SEUILS['etendue_mini_atr'])} × ATR**"),
        ("barre etroite %",
         f"**{_fr(cd.SEUILS['etendue_mini_pct'] * 100, 2)} %**"),
        ("cas minimum", f"**moins de {cd.MINI_CAS} cas**"),
        # --- profil.py : les bandes d'amplitude, ecrites avant mesure
        ("seances par an", f"racine de **{pr.SEANCES_AN}** séances"),
        ("barres minimum du profil", f"Sous **{pr.MINI_BARRES}** barres"),
        ("bande tres calme", f"sous **{pr.BANDES[0][1] * 100:.0f} %**"),
        ("bande calme", f"**{pr.BANDES[1][0] * 100:.0f}** à "
                        f"**{pr.BANDES[1][1] * 100:.0f} %**"),
        ("bande moyenne", f"**{pr.BANDES[2][0] * 100:.0f}** à "
                          f"**{pr.BANDES[2][1] * 100:.0f} %**"),
        ("bande agitee", f"**{pr.BANDES[3][0] * 100:.0f}** à "
                         f"**{pr.BANDES[3][1] * 100:.0f} %**"),
        ("bande tres agitee", f"**{pr.BANDES[4][0] * 100:.0f}** à "
                              f"**{pr.BANDES[4][1] * 100:.0f} %**"),
        ("bande extreme", f"au-delà de **{pr.BANDES[4][1] * 100:.0f} %**"),
        # --- objectif.py
        ("prelevement forfaitaire", f"**{sg.PFU * 100:.0f} %** sur le gain"),
        ("plafond de recherche", f"**{ob.MOIS_MAX}** mois"),
        # --- carnet.py et cerveau.py
        ("plafond du carnet", f"**{cn.MAX_ENTREES}** entrées"),
        ("plafond du dossier", f"**{cv.MAX_DOSSIER}** caractères"),
        ("listes reduites", f"ramenées à **{cv.LISTE_MAX[0]}**, puis "
                            f"{cv.LISTE_MAX[1]}, puis {cv.LISTE_MAX[2]}"),
        ("textes reduits", f"longs textes à **{cv.TEXTE_MAX}** caractères"),
        ("recherches web", f"**{cv.RECHERCHES_MAX}** recherches au"),
        ("sources affichees", f"**{cv.SOURCES_MAX}** sources au"),
        ("lignes relevees", f"pour **{b2_.LIGNES_MAX}** lignes au plus"),
        ("plafond par ligne", f"plafond de **{b2_.MAX_WEIGHT * 100:.0f} %** "
                              f"par ligne"),
        # --- ibkr.py : les ports et la reprise, cites dans le memo
        ("port TWS simulation", f"| **{ik_.PORTS[0][0]}** | TWS | simulation |"),
        ("port TWS reel", f"| **{ik_.PORTS[1][0]}** | TWS | réel |"),
        ("port Gateway simulation",
         f"| **{ik_.PORTS[2][0]}** | IB Gateway | simulation |"),
        ("port Gateway reel", f"| **{ik_.PORTS[3][0]}** | IB Gateway | réel |"),
        ("premiere reprise", f"attendant **{ik_.REPRISE[0]}**, puis"),
        ("derniere reprise", f"**{ik_.REPRISE[-1]}** secondes"),
        # --- pead.py : les constantes gelees et la lecture
        ("E1 surprise", f"**≥ +{pd_.CAR3_MIN * 100:.0f} %**"),
        ("E2 volume", f"**≥ {pd_.RVOL_ANNONCE:g}**"),
        ("E4 prix", f"**≥ {pd_.PRIX_MIN:g}**"),
        ("E5 liquidite", f"**≥ {pd_.DOLLAR_VOL_MIN / 1e6:g} M**"),
        ("heure de cloture", f"**{pd_.HEURE_CLOTURE} h**"),
        ("duree maximale", f"**{pd_.MAX_BARRES}** séances ;"),
        ("stop ATR", f"**{pd_.STOP_ATR:g}** × ATR"),
        ("univers minimum", f"moins de **{pd_.UNIVERS_MIN}** titres"),
        ("part des dates", f"**{pd_.PART_DATES_MIN * 100:.0f} %** rendus"),
        ("part exploitable", f"**{pd_.PART_EXPLOITABLES_MIN * 100:.0f} %** sont"),
        ("part des heures", f"moins de **{pd_.PART_HEURES_MIN * 100:.0f} %** des"),
        ("tirages du temoin", f"**{pd_.TIRAGES}** tirages"),
        ("temoins minimum", f"Moins de **{pd_.TEMOINS_MIN}** annonces"),
        # --- memoire.py
        ("horizons de la memoire",
         f"**{_me.HORIZONS[0]}**, **{_me.HORIZONS[1]}** et "
         f"**{_me.HORIZONS[2]}** séances"),
        ("tirages du bootstrap", f"**{_me.TIRAGES}** tirages"),
        ("extremes affiches", f"Les **{_me.N_EXTREMES}** plus fortes"),
        ("extremes en face", f"à côté des **{_me.N_EXTREMES}**"),
        ("cas minimum par bloc", f"à partir de **{_me.MINI_BLOC}** cas"),
        ("fenetre du releve", f"au plus **{_me.FENETRE_RELEVE}** jours"),
    ]
    absents = [(nom, val) for nom, val in ATTENDU if val not in m]
    ok(f"les {len(ATTENDU)} seuils cites dans le memo sont ceux qui "
       f"tournent", not absents)
    for nom, val in absents:
        print(f"          -> {nom} : le memo ne contient pas {val!r}")

    # Le memo doit nommer les figures avec les memes mots que le code.
    oublis = [n for n in cd.NOMS.values()
              if n.startswith(("Doji", "Marteau", "Pendu", "Étoile",
                               "Harami", "Avalement", "Pénétrante",
                               "Nuage", "Trois", "Marubozu"))
              and n not in m]
    ok("chaque figure du code est nommee dans le memo", not oublis)
    for n in oublis:
        print(f"          -> figure absente du memo : {n}")
    # La table de la veille est une CONVENTION : le memo doit la citer
    # en entier, sinon on lirait un rapprochement sans pouvoir verifier
    # d'ou il vient. Liste derivee du code, jamais recopiee a la main.
    from . import veille as _vl
    themes_oublies = [t for t, secs in _vl.THEME_SECTEURS.items()
                      if secs and t not in m]
    ok("chaque theme de la table de veille est cite dans le memo",
       not themes_oublies)
    for t in themes_oublies:
        print(f"          -> theme absent du memo : {t}")
    ok("le memo dit que les themes macro ne pointent vers aucun secteur",
       all(t in m for t, secs in _vl.THEME_SECTEURS.items() if not secs
           and t.startswith("economy")))

    ok("le memo dit qu'une action n'a pas d'open interest",
       "pas d'open interest" in m.lower())
    ok("et rappelle les 72 mesures et les faux positifs attendus",
       "une mesure sur\nvingt" in m or "une mesure sur vingt" in m)


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
    test_marqueurs()
    test_projection_capitalisation()
    test_seance()
    test_horizon()
    test_cle_av()
    test_interet()
    test_chandeliers()
    test_options()
    test_palmares()
    test_dossier()
    test_brain2()
    test_memo()

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
