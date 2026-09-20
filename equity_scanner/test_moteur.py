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
