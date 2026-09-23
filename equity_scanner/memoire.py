"""La memoire : ce que le programme a dit, et ce qui a suivi.

« Quand il a fait des mauvais jugements, il apprend, il les enregistre.
Quand il a loupe des occasions avec de fortes rentabilites parce que les
indicateurs n'etaient pas positifs, il apprend pour la prochaine fois. »

C'est la bonne question, et elle a une mauvaise reponse tres tentante.

La mauvaise reponse
-------------------
Regarder l'action qui a explose alors que le programme disait non, et
assouplir le filtre qui l'a bloquee. Recommencer a chaque fusee manquee.
Au bout de six mois, le filtre ne filtre plus rien : il a ete ajuste,
fusee apres fusee, sur un passe qu'il connait deja. C'est exactement ce
que le protocole interdit — sept parametres a cinq valeurs font 78 125
combinaisons, et environ 3 900 d'entre elles « marchent » par hasard.

Et il y a pire : la memoire humaine n'enregistre que la moitie des cas.
On se souvient de NVIDIA qu'on n'a pas achetee. On ne se souvient pas
des quarante titres au profil identique que le meme filtre a ecartes et
qui se sont effondres. Apprendre des seules occasions manquees, c'est
apprendre d'un echantillon choisi par le regret.

Ce que ce module fait a la place
--------------------------------
Il tient le COMPTE COMPLET. Chaque etat du programme est deja ecrit dans
le journal d'audit AVANT que le titre ne bouge. Ce module va chercher,
pour chacun, ce qui a suivi a des horizons ecrits d'avance, et le range
dans l'une des quatre cases :

    le programme disait OUI, le titre a battu le marche   signal confirme
    le programme disait OUI, il ne l'a pas battu          faux signal
    le programme disait NON, le titre a battu le marche   occasion manquee
    le programme disait NON, il ne l'a pas battu          piege evite

Les occasions manquees ne s'affichent JAMAIS seules : toujours en face
des pieges evites, en meme nombre. Un filtre ne se juge que sur les deux
colonnes ensemble — il « marche » seulement si le taux de reussite
quand il dit oui depasse nettement celui quand il dit non, intervalles
de Wilson a l'appui.

Et vos ordres, lus sur IBKR, sont ranges de la meme facon : pris AVEC le
signal, ou CONTRE lui. Ce qui a suivi dans chacun des deux cas est la
reponse la plus directe a « est-ce que je fais mieux que le programme,
ou moins bien ? ».

Ce que ce module ne fait pas, et pourquoi c'est la condition
------------------------------------------------------------
Il ne touche a AUCUN seuil. Ce qu'il revele devient, au mieux, l'idee
d'une NOUVELLE specification — ecrite avant son test, avec sa propre
empreinte, eprouvee sur une periode que personne n'a regardee. C'est
comme cela qu'un systeme apprend sans se mentir : entre deux
specifications, jamais en deplacant la regle apres avoir vu le resultat.

Il ne pretend pas non plus a une conscience. Il se souvient, il compte,
il compare — et il le fait sans l'oubli selectif qui rend la memoire
humaine si convaincante et si peu fiable.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# Horizons de mesure, en seances, ECRITS AVANT toute mesure. Une semaine,
# un mois, un trimestre. Choisir l'horizon apres avoir vu lequel donne le
# plus beau resultat serait la meme peche que deplacer un seuil.
HORIZONS = (5, 20, 60)
HORIZON_DEFAUT = 20

# Combien d'exemples de chaque cote dans les listes d'extremes. Le MEME
# nombre des deux cotes, toujours : c'est l'antidote au regret selectif.
N_EXTREMES = 6

DOSSIER = Path.home() / ".carruos"
EXECUTIONS = DOSSIER / "executions-ibkr.jsonl"

# Pour rapprocher un ordre d'un etat du programme, on accepte un releve
# datant d'au plus ce nombre de jours calendaires avant l'ordre.
FENETRE_RELEVE = 5

# Un bloc n'est dit « net » qu'a partir de ce nombre de cas : en dessous,
# l'intervalle de Wilson est si large que la comparaison ne dit rien.
MINI_BLOC = 10


def _wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    e = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - e) / d, (c + e) / d)


def _pc(x, dec=1):
    return None if x is None else round(x * 100.0, dec)


# ---------------------------------------------------------------------
# Le journal, lu proprement
# ---------------------------------------------------------------------

def etats(journal: list[dict]) -> list[dict]:
    """Les etats du programme, un par titre et par barre.

    Le journal ajoute sans jamais reecrire : la meme barre peut y
    figurer plusieurs fois (un scan, puis une consultation). On garde la
    PREMIERE ecriture — celle faite le plus tot, donc la plus loin de
    tout resultat connu.
    """
    vus, out = set(), []
    for r in sorted(journal or [], key=lambda x: x.get("horodatage", "")):
        cle = (str(r.get("ticker", "")).upper(), r.get("date_barre", ""))
        if not cle[0] or not cle[1] or cle in vus:
            continue
        vus.add(cle)
        blocs = r.get("blocs") or {}
        out.append({
            "ticker": cle[0], "date": cle[1],
            "oui": bool(r.get("declenche")),
            "n_blocs": sum(1 for v in blocs.values() if v),
            "total_blocs": len(blocs),
            "manquants": list(r.get("blocs_manquants") or []),
            "vetos": list(r.get("vetos") or []),
            "source": r.get("source", ""),
            "empreinte": r.get("empreinte", ""),
        })
    return out


# ---------------------------------------------------------------------
# Ce qui a suivi
# ---------------------------------------------------------------------

def _position(index, date: str):
    """L'indice de la barre de cette date, ou de la derniere avant elle."""
    import pandas as pd
    try:
        t = pd.Timestamp(date)
    except Exception:
        return None
    i = index.searchsorted(t, side="right") - 1
    return int(i) if i >= 0 else None


def suite(etat: dict, close, bench_close, h: int) -> dict | None:
    """Ce qui a suivi un etat, a h seances : rendement du titre, du
    marche, et l'ecart. None si l'horizon n'est pas encore ecoule.

    Mesure de cloture a cloture. La specification, elle, entre a
    l'ouverture du lendemain ; pour classer « le titre a-t-il battu le
    marche », la difference ne change pas de camp une observation
    sur mille, et elle evite de recharger des bougies d'ouverture.
    """
    i = _position(close.index, etat["date"])
    if i is None or i + h >= len(close):
        return None
    c0, c1 = float(close.iloc[i]), float(close.iloc[i + h])
    if not (c0 > 0 and c1 > 0):
        return None
    r = c1 / c0 - 1.0
    rb = None
    if bench_close is not None and len(bench_close):
        j = _position(bench_close.index, etat["date"])
        if j is not None and j + h < len(bench_close):
            b0, b1 = float(bench_close.iloc[j]), float(bench_close.iloc[j + h])
            if b0 > 0 and b1 > 0:
                rb = b1 / b0 - 1.0
    ecart = (r - rb) if rb is not None else None
    return {"rendement": r, "marche": rb, "ecart": ecart, "indice": i}


def observations(liste_etats: list[dict], series: dict, bench: dict,
                 h: int) -> dict:
    """Chaque etat, avec ce qui a suivi a h seances.

    Deux observations du meme titre a trois jours d'intervalle partagent
    presque toute leur fenetre : elles ne sont pas deux preuves, mais
    une seule comptee deux fois. On ne garde donc, pour un meme titre et
    une meme reponse du programme, qu'une observation par fenetre de h
    seances. Sans cela, un titre scanne chaque soir pendant un mois
    peserait vingt fois plus qu'un titre vu une fois.
    """
    garde, attente, sans_donnees = [], 0, 0
    dernier: dict = {}
    for e in sorted(liste_etats, key=lambda x: (x["ticker"], x["date"])):
        s = series.get(e["ticker"])
        if s is None or not len(s):
            sans_donnees += 1
            continue
        b = bench.get(e["ticker"])
        r = suite(e, s, b, h)
        if r is None:
            attente += 1
            continue
        cle = (e["ticker"], e["oui"])
        if cle in dernier and r["indice"] < dernier[cle] + h:
            continue
        dernier[cle] = r["indice"]
        if r["ecart"] is None:
            sans_donnees += 1
            continue
        garde.append({**e, **{k: v for k, v in r.items() if k != "indice"},
                      "bat": r["ecart"] > 0})
    return {"obs": garde, "en_attente": attente, "sans_donnees": sans_donnees,
            "horizon": h}


# ---------------------------------------------------------------------
# L'incertitude : deux criteres, et un verdict seulement s'ils s'accordent
# ---------------------------------------------------------------------
#
# Les observations ne sont pas independantes : un meme titre revient
# dans le journal, et un meme indice de reference sert a tous. Deux
# mesures de l'ecart entre le taux « oui » et le taux « non » :
#
# - le non-recouvrement de deux intervalles de Wilson, calcules comme si
#   chaque observation etait independante ;
# - un bootstrap qui tire les TITRES avec remise, et reprend tout
#   l'historique de chaque titre tire : il respecte le regroupement.
#
# Mesure sur 200 journaux de bruit ou chaque titre a son propre taux de
# reussite et sa propre frequence de « oui » : de 0,5 a 1 % de faux
# verdicts pour le premier, de 5,5 a 8,5 % pour le second selon la
# graine. Le non-recouvrement est prudent (deux intervalles a 95 % qui ne
# se touchent pas, c'est bien plus exigeant qu'un test de la difference) ;
# le bootstrap depasse un peu le 5 % nominal, ce qu'on attend d'un
# percentile tire sur vingt-cinq titres seulement.
#
# Un premier journal d'essai avait rendu « filtre nuisible » avec le
# premier critere seul ; j'y ai d'abord vu l'effet du regroupement par
# titre. La mesure ne le confirme pas : c'etait un tirage malchanceux,
# du genre que 2,5 % des journaux de bruit produisent.
#
# Regle retenue, sur le modele de `phase0.z_retenu()` : un verdict n'est
# rendu que si LES DEUX criteres l'accordent, dans le meme sens. Elle ne
# peut que rendre moins de verdicts, jamais plus — impossible a jouer
# dans le bon sens. `test_moteur` la remesure sur du bruit.

TIRAGES = 2000
GRAINE = 7


def _par_titre(obs: list[dict]):
    """Les comptes de chaque titre, en tableaux : (titres, k_oui, n_oui,
    k_non, n_non)."""
    import numpy as np
    d: dict = {}
    for o in obs:
        c = d.setdefault(o["ticker"], [0, 0, 0, 0])
        if o["oui"]:
            c[0] += 1 if o["bat"] else 0
            c[1] += 1
        else:
            c[2] += 1 if o["bat"] else 0
            c[3] += 1
    titres = sorted(d)
    m = np.array([d[t] for t in titres], dtype=float).reshape(-1, 4)
    return titres, m


def _poids(n_titres: int, tirages: int = TIRAGES, graine: int = GRAINE):
    """Combien de fois chaque titre est tire, pour chaque tirage."""
    import numpy as np
    rng = np.random.default_rng(graine)
    return rng.multinomial(n_titres, [1.0 / n_titres] * n_titres,
                           size=tirages).astype(float)


def ecart_bootstrap(obs: list[dict]) -> dict:
    """L'ecart entre le taux « oui » et le taux « non », et son
    intervalle a 95 %, par tirage des TITRES."""
    import numpy as np
    titres, m = _par_titre(obs)
    if len(titres) < 2:
        return {"ecart_pc": None, "intervalle_pc": [None, None],
                "n_titres": len(titres)}
    W = _poids(len(titres))
    k1, n1, k0, n0 = (W @ m[:, i] for i in range(4))
    ok = (n1 > 0) & (n0 > 0)
    if ok.sum() < TIRAGES // 2:
        return {"ecart_pc": None, "intervalle_pc": [None, None],
                "n_titres": len(titres)}
    diff = k1[ok] / n1[ok] - k0[ok] / n0[ok]
    tot = m.sum(axis=0)
    point = (tot[0] / tot[1] - tot[2] / tot[3]) if tot[1] and tot[3] else None
    lo, hi = np.percentile(diff, [2.5, 97.5])
    return {"ecart_pc": _pc(point), "intervalle_pc": [_pc(lo), _pc(hi)],
            "n_titres": len(titres),
            "titres_oui": int((m[:, 1] > 0).sum()),
            "titres_non": int((m[:, 3] > 0).sum())}


# ---------------------------------------------------------------------
# Le tableau a quatre cases
# ---------------------------------------------------------------------

CASES = {
    (True, True): "signal confirmé",
    (True, False): "faux signal",
    (False, True): "occasion manquée",
    (False, False): "piège évité",
}


def tableau(obs: list[dict]) -> dict:
    """Les quatre cases, et les deux taux qui les resument."""
    n = {c: 0 for c in CASES}
    for o in obs:
        n[(o["oui"], o["bat"])] += 1
    oui = n[(True, True)] + n[(True, False)]
    non = n[(False, True)] + n[(False, False)]
    tout = oui + non
    k_oui, k_non = n[(True, True)], n[(False, True)]
    w_oui, w_non = _wilson(k_oui, oui), _wilson(k_non, non)
    w_base = _wilson(k_oui + k_non, tout)
    bs = ecart_bootstrap(obs)
    lo, hi = bs["intervalle_pc"]
    if oui == 0 or non == 0 or lo is None:
        lecture = "pas_assez"
    elif lo > 0 and w_oui[0] > w_non[1]:
        lecture = "filtre_utile"
    elif hi < 0 and w_oui[1] < w_non[0]:
        lecture = "filtre_nuisible"
    else:
        lecture = "indiscernable"
    return {
        "cases": {CASES[c]: n[c] for c in CASES},
        "oui": {"n": oui, "k": k_oui,
                "taux_pc": _pc(k_oui / oui) if oui else None,
                "wilson_pc": [_pc(w_oui[0]), _pc(w_oui[1])]},
        "non": {"n": non, "k": k_non,
                "taux_pc": _pc(k_non / non) if non else None,
                "wilson_pc": [_pc(w_non[0]), _pc(w_non[1])]},
        "base": {"n": tout, "k": k_oui + k_non,
                 "taux_pc": _pc((k_oui + k_non) / tout) if tout else None,
                 "wilson_pc": [_pc(w_base[0]), _pc(w_base[1])]},
        "ecart": bs,
        "lecture": lecture,
    }


LECTURES = {
    "pas_assez": ("Pas encore de quoi comparer : il faut des observations "
                  "des deux côtés, quand le programme disait oui ET quand "
                  "il disait non."),
    "filtre_utile": ("Quand le programme disait oui, le titre a battu le "
                     "marché plus souvent que quand il disait non — et les "
                     "deux mesures de l'incertitude l'accordent : les "
                     "intervalles ne se recouvrent pas, et l'écart reste "
                     "au-dessus de zéro quand on tire les TITRES au hasard. "
                     "Sur ces décisions-là, le filtre a trié."),
    "filtre_nuisible": ("Quand le programme disait oui, le titre a battu le "
                        "marché MOINS souvent que quand il disait non — et "
                        "les deux mesures de l'incertitude l'accordent. Sur "
                        "ces décisions-là, le filtre a trié à l'envers."),
    "indiscernable": ("Sur ces décisions, dire oui ou dire non n'a pas "
                      "fait de différence mesurable : l'écart entre les deux "
                      "taux ne résiste pas aux deux mesures de "
                      "l'incertitude. C'est ce que la Phase 0 avait déjà "
                      "conclu, et c'est ce qu'une fusée manquée ne suffit "
                      "pas à contredire."),
}


def extremes(obs: list[dict], n: int = N_EXTREMES) -> dict:
    """Les occasions manquees les plus fortes ET les pieges evites les
    plus profonds — toujours en meme nombre.

    Montrer les seules fusees manquees, c'est reproduire l'oubli
    selectif qu'on veut corriger. Le meme nombre des deux cotes, c'est
    la seule mise en page qui ne triche pas.
    """
    manquees = sorted((o for o in obs if not o["oui"] and o["bat"]),
                      key=lambda o: -o["ecart"])
    evites = sorted((o for o in obs if not o["oui"] and not o["bat"]),
                    key=lambda o: o["ecart"])
    k = min(n, len(manquees), len(evites))

    def court(o):
        return {"ticker": o["ticker"], "date": o["date"],
                "ecart_pc": _pc(o["ecart"]), "rendement_pc": _pc(o["rendement"]),
                "n_blocs": o["n_blocs"], "total_blocs": o["total_blocs"],
                "manquants": o["manquants"], "vetos": o["vetos"]}
    return {"manquees": [court(o) for o in manquees[:k]],
            "evites": [court(o) for o in evites[:k]],
            "n_manquees": len(manquees), "n_evites": len(evites)}


def par_bloc(obs: list[dict]) -> dict:
    """Ce que chaque bloc a coute, et ce qu'il a epargne.

    Pour chaque bloc, parmi les fois ou le programme disait NON et ou CE
    bloc etait en echec : combien de fois le titre a battu le marche
    (occasions que ce bloc a fait manquer), combien de fois non (pieges
    qu'il a fait eviter). Un bloc qui ecarte autant de fusees que de
    pieges ne trie rien.

    C'est ICI que se trouvent les pistes d'une future specification —
    et ICI que le piege des comparaisons multiples est le plus grand :
    treize blocs, trois horizons, trente-neuf comparaisons, donc environ
    deux « ecarts nets » attendus par le seul hasard. Le compte est
    affiche avec le tableau.
    """
    base = [o for o in obs if not o["oui"]]
    k_base = sum(1 for o in base if o["bat"])
    taux_base = k_base / len(base) if base else None
    out = {}
    for o in base:
        for b in o["manquants"]:
            d = out.setdefault(b, {"n": 0, "k": 0})
            d["n"] += 1
            d["k"] += 1 if o["bat"] else 0
    lignes = []
    for b, d in out.items():
        w = _wilson(d["k"], d["n"])
        net = (taux_base is not None and d["n"] >= MINI_BLOC
               and (w[0] > taux_base or w[1] < taux_base))
        lignes.append({"bloc": b, "n": d["n"], "manquees": d["k"],
                       "evites": d["n"] - d["k"],
                       "taux_pc": _pc(d["k"] / d["n"]),
                       "wilson_pc": [_pc(w[0]), _pc(w[1])],
                       "net": bool(net)})
    lignes.sort(key=lambda x: -x["n"])
    return {"lignes": lignes, "taux_base_pc": _pc(taux_base),
            "n_comparaisons": len(lignes) * len(HORIZONS),
            "mini": MINI_BLOC}


# ---------------------------------------------------------------------
# Vos ordres, lus sur IBKR
# ---------------------------------------------------------------------

def lit_executions(fichier: Path | None = None) -> list[dict]:
    f = fichier or EXECUTIONS
    out, vus = [], set()
    try:
        with f.open(encoding="utf-8") as fp:
            for l in fp:
                try:
                    r = json.loads(l)
                except ValueError:
                    continue
                if r.get("id") in vus:
                    continue
                vus.add(r.get("id"))
                out.append(r)
    except FileNotFoundError:
        pass
    return out


def vos_ordres(executions: list[dict], liste_etats: list[dict],
               series: dict, bench: dict, h: int) -> dict:
    """Vos achats, ranges selon ce que disait le programme ce jour-la.

    On ne reconstruit PAS l'etat du programme apres coup : seul compte
    un etat releve AVANT l'ordre, dans le journal d'audit, au plus
    FENETRE_RELEVE jours plus tot. Un ordre sans releve est compte a
    part — le reconstituer aujourd'hui serait le juger avec un regard qui
    connait deja la suite.
    """
    import pandas as pd
    par_titre: dict = {}
    for e in liste_etats:
        par_titre.setdefault(e["ticker"], []).append(e)
    for v in par_titre.values():
        v.sort(key=lambda x: x["date"])

    classes = {"avec": [], "contre": []}
    sans_releve, en_attente = 0, 0
    for x in executions:
        if x.get("sens") != "achat" or not x.get("ticker"):
            continue
        jour = str(x.get("quand", ""))[:10]
        cand = [e for e in par_titre.get(x["ticker"], []) if e["date"] <= jour]
        if not cand:
            sans_releve += 1
            continue
        e = cand[-1]
        try:
            ecart_j = (pd.Timestamp(jour) - pd.Timestamp(e["date"])).days
        except Exception:
            ecart_j = FENETRE_RELEVE + 1
        if ecart_j > FENETRE_RELEVE:
            sans_releve += 1
            continue
        s = series.get(x["ticker"])
        r = suite({"date": jour}, s, bench.get(x["ticker"]), h) if s is not None else None
        if r is None or r["ecart"] is None:
            en_attente += 1
            continue
        classes["avec" if e["oui"] else "contre"].append(
            {"ticker": x["ticker"], "date": jour, "ecart": r["ecart"],
             "bat": r["ecart"] > 0, "n_blocs": e["n_blocs"]})

    def resume(lst):
        n, k = len(lst), sum(1 for o in lst if o["bat"])
        w = _wilson(k, n)
        med = sorted(o["ecart"] for o in lst)[n // 2] if n else None
        return {"n": n, "k": k, "taux_pc": _pc(k / n) if n else None,
                "wilson_pc": [_pc(w[0]), _pc(w[1])],
                "ecart_median_pc": _pc(med)}
    return {"avec": resume(classes["avec"]), "contre": resume(classes["contre"]),
            "sans_releve": sans_releve, "en_attente": en_attente,
            "fenetre_jours": FENETRE_RELEVE,
            "n_achats": sum(1 for x in executions if x.get("sens") == "achat")}


# ---------------------------------------------------------------------
# Tout ensemble
# ---------------------------------------------------------------------

def bench_de(ticker: str) -> str:
    from .resolve import SUFFIXES
    return "^STOXX" if any(ticker.endswith(s) for s in SUFFIXES) else "SPY"


def bilan(h: int = HORIZON_DEFAUT, journal=None, executions=None,
          charge=None) -> dict:
    """Le bilan complet, a un horizon donne. `charge(tk)` rend une serie
    de clotures ; par defaut, le cache disque du programme."""
    from . import audit as ad
    if h not in HORIZONS:
        h = HORIZON_DEFAUT
    journal = ad.lit() if journal is None else journal
    executions = lit_executions() if executions is None else executions
    le = etats(journal)
    tickers = sorted({e["ticker"] for e in le}
                     | {x["ticker"] for x in executions if x.get("ticker")})

    if charge is None:
        from . import cache as ch
        # charge_lot rend (series, echecs) : un titre retire de la cote
        # ressort avec son motif au lieu de faire tomber tout le bilan.
        lots, _echecs = (ch.charge_lot(tickers + ["SPY", "^STOXX"], annees=10)
                         if tickers else ({}, []))

        def charge(tk):
            d = lots.get(tk)
            return None if d is None or not len(d) else d["close"]

    series = {t: charge(t) for t in tickers}
    reperes = {b: charge(b) for b in ("SPY", "^STOXX")}
    bench = {t: reperes.get(bench_de(t)) for t in tickers}

    ob = observations(le, series, bench, h)
    return {
        "horizon": h, "horizons": list(HORIZONS),
        "n_etats": len(le), "n_titres": len({e["ticker"] for e in le}),
        "en_attente": ob["en_attente"], "sans_donnees": ob["sans_donnees"],
        "n_obs": len(ob["obs"]),
        "tableau": tableau(ob["obs"]),
        "extremes": extremes(ob["obs"]),
        "par_bloc": par_bloc(ob["obs"]),
        "vos_ordres": vos_ordres(executions, le, series, bench, h),
        "lectures": LECTURES, "rappel": RAPPEL, "rappel_blocs": RAPPEL_BLOCS,
    }


def pour_titre(ticker: str, close, bench_close, journal=None) -> dict:
    """La memoire d'UN titre, pour le dossier du majordome : ce que le
    programme en a dit, et ce qui a suivi. Pas de telechargement : les
    series sont celles que le dossier a deja chargees."""
    from . import audit as ad
    tk = ticker.upper()
    journal = ad.lit(ticker=tk) if journal is None else journal
    le = [e for e in etats(journal) if e["ticker"] == tk]
    out = []
    for e in le[-12:]:
        ligne = {"date": e["date"], "programme": "oui" if e["oui"] else "non",
                 "blocs": f"{e['n_blocs']}/{e['total_blocs']}"}
        for h in HORIZONS:
            r = suite(e, close, bench_close, h)
            ligne[f"ecart_{h}_pc"] = None if r is None or r["ecart"] is None \
                else _pc(r["ecart"])
        out.append(ligne)
    return {"releves": out, "n": len(le)}


RAPPEL = (
    "La mémoire ne touche à aucun seuil. Ce qu'elle révèle peut devenir "
    "l'idée d'une NOUVELLE spécification — écrite avant son test, avec sa "
    "propre empreinte, éprouvée sur une période que personne n'a "
    "regardée. Assouplir un filtre parce qu'une action a explosé, c'est "
    "l'ajuster sur un passé qu'il connaît déjà : il finit par ne plus rien "
    "filtrer. Les occasions manquées s'affichent toujours en face des "
    "pièges évités, en même nombre.")

RAPPEL_BLOCS = (
    "Chaque bloc est une comparaison, chaque horizon en est une autre : "
    "environ une sur vingt ressort « nette » par le seul hasard. Un écart "
    "net isolé ne vaut rien ; il ne devient une piste que s'il tient aux "
    "trois horizons, et une piste ne devient une règle qu'après une "
    "nouvelle spécification.")
