"""Le dossier d'un titre, et la porte en francais pour y entrer.

LA REGLE QUI REND LA CHOSE HONNETE
----------------------------------
« Que penses-tu de TLX ? » est une invitation a donner un avis. Une IA
branchee sur des cours y repond en inventant : « bien oriente, momentum
qui se retourne, sortie vers 380 ». Aucun de ces mots ne vient d'une
mesure.

Ici, rien n'est genere. Le module fait DEUX choses, et elles sont
separees net :

  1. `constitue()` rassemble ce que les autres modules ont deja
     CALCULE — les 13 blocs et leurs manques chiffres, les quatre
     conditions de sortie et leur etat, le stop, le cout fiscal, les
     figures de chandelier du jour et ce qu'elles ont ete suivies de,
     l'amplitude par horizon, la qualite des donnees. Aucun chiffre
     n'est produit ici.

  2. `comprend()` reconnait ce qui est demande, par une table de motifs
     ecrite ci-dessous. Elle rend une INTENTION, jamais une phrase.
     `repond()` choisit alors la section du dossier qui correspond.

Les phrases affichees sont des gabarits remplis avec les chiffres du
dossier. Si un chiffre n'est pas dans le dossier, aucune phrase ne peut
le sortir — c'est une propriete de construction, pas une consigne.

Et l'intention « avis » ne rend pas un avis : elle rend la fiche
complete, avec le rappel qu'aucune hypothese n'a passe sa Phase 0.

    py -m equity_scanner.dossier "je sors quand sur TLX.DE"
"""

from __future__ import annotations

import argparse
import re
import unicodedata

VERSION = "dossier-v1.0"

# --------------------------------------------------------------------
# La table des intentions. Ecrite ICI, une fois.
#
# L'ordre compte : la premiere qui correspond gagne. Les intentions
# precises passent avant les generales, sinon « que penses-tu de la
# sortie » tomberait sur « avis ».
# --------------------------------------------------------------------
INTENTIONS = [
    ("memoire", r"\b(?:tromp|erreur|appris|apprend|memoire|souvien|"
                r"bilan|loupe|rate)\w*|derniere fois|la fois ou"
                r"|avais dit|disais"),
    # « Je garde deux mois ? » donne une DUREE chiffree : ce que cette
    # duree a donne sur le titre. Avant « je garde ? » (sortie) et avant
    # « combien de temps » (profil), qui ne portent pas de nombre.
    ("detention", r"\b(?:gard|conserv|ten|tiens|deten|reste|laiss)\w*\b"
                  r".{0,40}?\b\d+(?:[.,]\d+)?\s*(?:jours?|semaines?|mois|"
                  r"ans?|annees?)\b"
                  r"|\b\d+(?:[.,]\d+)?\s*(?:jours?|semaines?|mois|ans?|"
                  r"annees?)\b.{0,30}\b(?:gard|conserv|deten|ten)\w*"
                  r"|lundi.{0,30}vendredi"
                  r"|(?:une|1) semaine.{0,40}(?:un|1) (?:mois|an)"),
    # « Il a baisse de 25 %, rebond ? » : ce que les chutes passees de CE
    # titre ont ete suivies de. Avant « acheter » et « sortir », que la
    # question contient souvent aussi.
    ("rebond", r"\brebon\w*|\bremont(?:e|er|era|ent)\b|se relev\w*"
               r"|se repren\w*|\bchut\w*|\bplong\w*|\bdegringol\w*"
               r"|\b(?:a|ont|avait|est) (?:baisse|perdu|recule)"
               r"|\bbaisse de \d|\brecul\w* de \d|\bperdu \d"),
    # « Tesla va sortir un nouveau modele » : l'actualite du titre. Avant
    # « sortie » — « sortir un nouveau modele » y tombait, et le majordome
    # repondait VOUS SORTEZ QUAND a une question sur une annonce.
    ("actualite", r"\bnouveau (?:modele|produit|vehicule|telephone|service)"
                  r"|\blancement|\bannonc\w*|\bactualit\w*|\bnews\b"
                  r"|\bnouvelles\b|\bcommunique\w*|\brumeur\w*"
                  r"|\bsortir (?:un|une|le|la|son|sa|leur)\b"),
    # « Combien de temps on garde » demande une DUREE ; « je garde ? »
    # demande s'il faut sortir. Le premier doit passer avant le second.
    ("profil", r"combien de temps|duree de detention|on garde combien"),
    ("sortie", r"\b(?:sors|sortir|sorti|vend|vends|vendre|solder|clotur|"
               r"liquid|degager)\w*|quand.*(?:sort|vend)|quelles? conditions?"
               r"|\bje (?:la |le |les )?(?:garde|conserve)\b"
               r"|\b(?:garder|conserver) (?:ma|la|mes|cette|ces) "
               r"(?:position|ligne)"),
    ("entree", r"\b(?:achet|rentr|entrer|renforc|rajout|repren|"
               r"positionn)\w*|prendre une ligne"),
    ("risque", r"\b(?:risqu|stop|perdre|pert|dimension|taille)\w*"
               r"|combien.*perd|combien de titres"),
    ("bougies", r"\b(?:chandelier|bougie|figure|marteau|harami|doji|"
                r"avalement|etoile|corbeau|soldat|pendu|nuage|penetrante|"
                r"marubozu)\w*"),
    ("horizon", r"\b(?:horizon|amplitude|bouge|objectif|cible)\w*"
                r"|take.?profit|\btp\b"),
    ("donnees", r"\b(?:fiab|donnee|qualit|confiance|douteu)\w*"),
    ("seance", r"\b(?:heure|horaire|ouvertur|ouvre|ferme|fermetur|"
               r"seance)\w*|bourse ouverte"),
    ("profil", r"\b(?:etf|tracker|volatil|amplitude|nerveu|calme|agit|"
                r"beta|correlation|type|genre|nature|garde|garder|"
                r"conserv|detention|duree|longevite)\w*"
                r"|court terme|long terme|moyen terme|combien de temps"),
    ("avis", r"\b(?:pense|avis|opinion|vaut|interess|interet|comment|"
             r"quoi)\w*|dis.?moi|parle.?moi"),
]

# Une regle qui ne se maintient pas toute seule finit fausse. Les mots
# qui DECLENCHENT une intention sont, par construction, des mots de la
# question — jamais des tickers. On les reconnait donc avec les memes
# motifs, au lieu de les recopier dans une liste qu'il faudrait penser
# a mettre a jour a chaque intention ajoutee.
_MOTIFS_QUESTION = re.compile("|".join(m for _c, m in INTENTIONS))

# Ces mots ne sont jamais des tickers. Sans cette liste, « QUE » et
# « TLX » se valent aux yeux d'une recherche de jeton.
MOTS_VIDES = {
    "que", "quoi", "qui", "quel", "quelle", "quelles", "quels", "de", "du",
    "des", "le", "la", "les", "un", "une", "et", "ou", "a", "au", "aux",
    "en", "sur", "pour", "avec", "sans", "je", "tu", "il", "on", "me",
    "moi", "mon", "ma", "mes", "ce", "cette", "ces", "est", "sont", "ai",
    "as", "dois", "doit", "peux", "peut", "pense", "penses", "avis",
    "sors", "sortir", "sortie", "vendre", "vends", "acheter", "achete",
    "quand", "comment", "combien", "pourquoi", "condition", "conditions",
    "risque", "stop", "dis", "parle", "fait", "faire", "si", "mais",
    "donc", "alors", "bien", "mal", "plus", "moins", "tres", "trop",
    "action", "titre", "bourse", "cours", "prix", "the", "my",
    "sous", "til", "ca", "cela", "y", "en", "ne", "pas", "plus", "tout",
    "toute", "faut", "veux", "vais", "suis", "sais", "sur", "dans",
    # Les pluriels et les mots des questions generales : « acheter des
    # ACTIONS en chute LIBRE » ne nomme aucun titre, et sur des donnees
    # qui acceptent tout, « ACTIONS » passait pour un ticker.
    "actions", "titres", "entreprises", "societes", "valeurs", "libre",
    "potentiel", "potentiels", "nouveau", "nouvelle", "modele", "modeles",
    "voiture", "produit", "parce", "ils", "elles", "vont", "leur", "leurs",
    "qu", "estce", "ont", "avoir", "etre", "deja", "encore", "aussi",
}

RAPPEL = (
    "Aucune hypothèse n'a passé sa Phase 0. Ce n'est pas un avis : ce "
    "sont les conditions écrites AVANT le test, et leur état aujourd'hui.")


def _sans_accent(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def normalise(q: str) -> str:
    """Minuscules, sans accent. Frederic ecrit en majuscules et vite."""
    return _sans_accent(str(q or "")).lower().strip()


def intention(question: str) -> str:
    """Quelle question est posee. Rend une cle, jamais une phrase."""
    q = normalise(question)
    for cle, motif in INTENTIONS:
        if re.search(motif, q):
            return cle
    return "avis"


def jetons_tickers(question: str) -> list[str]:
    """Les mots de la question qui PEUVENT etre un ticker.

    On ne decide pas ici lequel en est un : `comprend()` le demande aux
    donnees. Deviner a partir de la forme du mot ferait de « QUAND » un
    ticker aussi credible que « TLX ».
    """
    q = str(question or "")
    bruts = re.findall(r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z]{1,3})?", q)
    out = []
    for m in bruts:
        n = normalise(m)
        if n in MOTS_VIDES or _MOTIFS_QUESTION.search(n):
            continue
        if len(m) < 2 or len(m) > 12:
            continue
        out.append(m.upper())
    return list(dict.fromkeys(out))


# --------------------------------------------------------------------
# Le dossier : rien n'est calcule ici, tout vient des autres modules
# --------------------------------------------------------------------

def _chute(brut):
    """Ou en est le titre sous son dernier sommet : un fait, calcule par
    `rebond.py`. La mesure des chutes passees attend que la question la
    demande (`mesure_chute`)."""
    try:
        from . import rebond as rb
        return rb.etat(brut)
    except Exception:
        return None


def _memoire(tk, serie, bench):
    """Ce que le programme a deja dit de ce titre, et ce qui a suivi."""
    try:
        from . import memoire as me
        return me.pour_titre(tk, serie["close"], bench["close"])
    except Exception:
        return None


def jours_resultats(tk: str, marche: str, av_key: str | None = None):
    """Seances avant les prochains resultats, ou None si inconnu.

    Les resultats sont un VETO de la specification : « inconnu » n'est
    pas « sans risque ». Calendrier Alpha Vantage si une cle existe,
    yfinance sinon pour les titres americains.
    """
    jours = None
    if av_key:
        try:
            from . import news as nw
            cal = nw.earnings_map(av_key)
            if tk in cal:
                jours = nw.seances_avant(cal[tk])
        except Exception:
            jours = None
    if jours is None and marche == "us":
        try:
            from . import data as dl
            jours = dl.days_to_earnings_yf(tk)
        except Exception:
            jours = None
    return jours


def constitue(ticker: str, marche: str | None = None,
              av_key: str | None = None, sleeve: float = 8000.0,
              position: dict | None = None) -> dict:
    """Rassemble ce que les autres modules savent deja de ce titre.

    Aucun chiffre n'est produit ici. Chaque section porte le nom du
    module qui l'a calculee, pour qu'on puisse toujours remonter a la
    source d'une ligne affichee.
    """
    from . import cache as ch
    from . import chandeliers as cd
    from . import chart as gr
    from . import interet as it
    from . import qualite as ql
    from . import rules as R
    from . import strategie as sg
    from .indicators import enrich

    tk = ticker.upper()
    if marche is None:
        from .resolve import SUFFIXES
        marche = "europe" if any(tk.endswith(x) for x in SUFFIXES) else "us"
    bench_tk = "SPY" if marche == "us" else "^STOXX"

    d = {"ok": False, "ticker": tk, "version": VERSION, "marche": marche}
    try:
        brut = ch.charge(tk, annees=10)
        bench_brut = ch.charge(bench_tk, annees=10)
        serie = enrich(brut, bench_close=bench_brut["close"])
        bench = enrich(bench_brut)
    except Exception as exc:
        d["erreur"] = f"{type(exc).__name__}: {exc}"
        return d

    marche_ok = bool(R.market_regime_ok(bench))
    rap = ql.controle(brut, bench=bench_brut, ticker=tk)

    jours = jours_resultats(tk, marche, av_key)
    sig = R.evaluate(serie, tk, marche_ok, days_to_earnings=jours)
    # La memoire : l'etat que le programme montre AUJOURD'HUI, ecrit
    # avant que le titre ne bouge. C'est l'evaluation COMPLETE — veto des
    # resultats compris — et pas celle du graphique, qui l'omet : un
    # « oui » que la specification n'aurait pas donne fausserait tout ce
    # que la memoire comptera ensuite.
    try:
        from . import audit as ad
        ad.enregistre(sig, serie, source="dossier",
                      qualite={"utilisable": rap.utilisable})
    except Exception:
        pass
    sorties = R.evaluate_exit(serie, marche_ok)
    etats = gr._bloc_etats(serie, sig)
    inter = it.lire_unite(serie, bench, sig, sorties, etats,
                          refuse=not rap.utilisable, motifs=rap.bloquants)

    entree = float((position or {}).get("entree") or 0) or None
    revue = sg.revue_titre(tk, serie, marche_ok, entree=entree,
                           quantite=float((position or {}).get("quantite") or 0),
                           depuis=(position or {}).get("date", ""))

    niveaux = None
    if sig.entry > sig.stop > 0:
        taille = R.position_size(sig, float(sleeve))
        par_titre = round(float(sig.entry) - float(sig.stop), 2)
        niveaux = {"entree": round(float(sig.entry), 2),
                   "stop": round(float(sig.stop), 2),
                   "risque_par_titre": par_titre,
                   "risque_pct": round(float(sig.risk_pct) * 100, 2),
                   "atr": round(float(sig.atr), 2),
                   "titres": taille["shares"],
                   "montant": round(taille["notional"]),
                   "risque_eur": round(taille.get("risk_eur", 0.0)),
                   # Le sleeve qu'il faudrait pour qu'UN titre passe le
                   # plafond de risque de 1 %. Calcule ici, pas dans la
                   # phrase qui l'affiche.
                   "sleeve_mini": round(par_titre * 100),
                   "plafonne": bool(taille.get("capped"))}

    try:
        chand = cd.lecture(serie)
    except Exception:
        chand = None
    try:
        from . import horizon as hz
        amplitudes = hz.amplitude(serie)
    except Exception:
        amplitudes = []
    # Le profil : ce qui distingue une action d'un ETF monde, mesure.
    # Calcule ici parce que c'est le point unique ou les faits d'un
    # titre se rassemblent — un second endroit finirait par diverger.
    try:
        from . import profil as pr
        prof = pr.mesures(serie, bench=bench, ticker=tk)
        prof["duree"] = pr.duree_detention(serie, bench, tk)
    except Exception:
        prof = None
    # Ce que chaque duree de detention a donne sur ce titre, contre
    # l'indice : les cinq durees usuelles et « lundi -> vendredi ».
    try:
        from . import detention as dt
        deten = dt.tableau(brut, bench_brut)
        _SERIES[tk] = (brut, bench_brut)
        while len(_SERIES) > 8:
            _SERIES.pop(next(iter(_SERIES)))
    except Exception:
        deten = None
    try:
        from . import seance as sn
        # La place qui compte pour CE titre, pas les neuf.
        cle_place = "paris" if tk.endswith(".PA") else (
            "francfort" if tk.endswith(".DE") else "newyork")
        horaires = sn.etat(cle_place)
    except Exception:
        horaires = None

    d.update({
        "ok": True,
        "cours": round(float(serie["close"].iloc[-1]), 2),
        "date": str(serie.index[-1].date()),
        "devise": sg.devise_du_titre(tk),
        "jours_resultats": jours,
        "marche_ok": marche_ok,
        "qualite": {"utilisable": rap.utilisable,
                    "bloquants": rap.bloquants, "alertes": rap.alertes},
        "interet": inter,
        "niveaux": niveaux,
        "revue": revue,
        "histo": it.historique(gr._perf_signal(serie, tk, bench)),
        "chandeliers": chand,
        "horizons": amplitudes,
        "horaires": horaires,
        "profil": prof,
        "detention": deten,
        "chute": _chute(brut),
        "memoire": _memoire(tk, serie, bench),
        "position": position or None,
        "rappel": RAPPEL,
    })
    return d


# --------------------------------------------------------------------
# Les reponses : des gabarits remplis avec les chiffres du dossier
# --------------------------------------------------------------------

def _n(x, dec=2, suffixe=""):
    if x is None:
        return "—"
    try:
        return f"{float(x):.{dec}f}".replace(".", ",") + suffixe
    except (TypeError, ValueError):
        return str(x)


def _sortie(d: dict) -> list[str]:
    """Les quatre conditions de la specification, et leur etat.

    La specification ferme a la PREMIERE condition atteinte. Le dire est
    citer sa propre regle ; ajouter « vends » en ferait un verdict.
    """
    r = d.get("revue") or {}
    sorties = r.get("sorties") or {}
    L = []
    actives = [k for k, v in sorties.items() if v]
    L.append(f"{len(actives)} condition(s) de sortie sur "
             f"{len(sorties)} sont actives." if sorties
             else "Conditions de sortie non évaluables.")
    for nom, actif in sorties.items():
        L.append(("● " if actif else "○ ") + nom
                 + ("   ACTIVE" if actif else "   dormante"))
    L.append("La spécification ferme à la PREMIÈRE condition atteinte.")
    n = d.get("niveaux") or {}
    if n.get("stop"):
        L.append(f"Le stop de la spécification serait à {_n(n['stop'])} "
                 f"({_n(n['risque_pct'], 2, ' %')} sous le cours).")
    if r.get("stop"):
        L.append(f"Votre stop enregistré : {_n(r['stop'])}"
                 + (f", soit {_n(r.get('marge_stop_pct'), 1, ' %')} de marge"
                    if r.get("marge_stop_pct") is not None else ""))
    if r.get("detenu"):
        L.append(f"Position : {_n(r.get('quantite'), 0)} titres à "
                 f"{_n(r.get('entree'))}, soit "
                 f"{_n(r.get('pnl_pct'), 2, ' %')} "
                 f"({_n(r.get('pnl_eur'), 0)}).")
        if r.get("recul_depuis_haut_pct") is not None:
            L.append(f"Plus haut atteint {_n(r.get('plus_haut'))}, "
                     f"recul depuis ce sommet "
                     f"{_n(r.get('recul_depuis_haut_pct'), 1, ' %')}, "
                     f"part du gain rendue "
                     f"{_n(r.get('gain_rendu_pct'), 1, ' %')}.")
    return L


def _entree(d: dict) -> list[str]:
    u = d.get("interet") or {}
    L = [f"{u.get('compte', '—')} blocs de la spécification sont remplis "
         f"— {u.get('titre', '')}."]
    for m in (u.get("manquants") or [])[:5]:
        L.append(f"Il manque : {m['nom']} — {m['texte']}")
    for v in u.get("vetos") or []:
        L.append(f"VETO de la spécification : {v}")
    for v in u.get("vigilance") or []:
        L.append(f"À vérifier à la main : {v}")
    n = d.get("niveaux") or {}
    if n.get("titres"):
        L.append(f"Si la ligne était prise au prix et au stop de la règle : "
                 f"{n['titres']} titre(s) pour {n['montant']}, "
                 f"{n['risque_eur']} de perte si le stop saute"
                 + (" (taille réduite par le plafond de poids)"
                    if n.get("plafonne") else "") + ".")
    h = d.get("histo")
    if h:
        L.append(f"Ce signal sur ce titre : {h['phrase']}")
        if h.get("reserve"):
            L.append(h["reserve"])
    return L


def _risque(d: dict) -> list[str]:
    n = d.get("niveaux") or {}
    if not n:
        return ["Le stop de la spécification n'est pas calculable : "
                "l'ATR manque."]
    L = [f"Entrée {_n(n['entree'])}, stop {_n(n['stop'])}, soit "
         f"{_n(n['risque_par_titre'])} de risque par titre "
         f"({_n(n['risque_pct'], 2, ' %')}).",
         f"ATR 14 : {_n(n['atr'])} — l'amplitude d'une séance typique."]
    if n["titres"] <= 0:
        # « 0 titre pour 0 » sans explication laisse croire a une panne.
        # C'est de l'arithmetique : le risque d'UN SEUL titre depasse
        # deja le 1 % du sleeve, donc la regle n'en autorise aucun.
        L.append(f"La règle n'autorise AUCUN titre : le risque d'un seul "
                 f"({_n(n['risque_par_titre'])}) dépasse déjà le 1 % du "
                 f"sleeve. Il faudrait un sleeve d'au moins "
                 f"{_n(n['sleeve_mini'], 0)} pour en prendre un.")
    else:
        L.append(f"Au risque de 1 % du sleeve : {n['titres']} titre(s) pour "
                 f"{n['montant']}, {n['risque_eur']} de perte si le stop "
                 f"saute.")
    if n.get("plafonne"):
        L.append("La taille a été réduite par le plafond de poids de "
                 "25 % par ligne.")
    L.append("Il n'y a PAS de ratio risque / gain : la spécification "
             "n'a aucun objectif de gain, elle dit « aucun take-profit ».")
    h = d.get("histo")
    if h:
        L.append(f"Ce que ce signal a rendu ici : {h['phrase']}")
    return L


def _bougies(d: dict) -> list[str]:
    c = d.get("chandeliers")
    if not c:
        return ["Lecture des chandeliers indisponible."]
    ici = [f for f in c.get("figures", []) if f.get("aujourdhui")]
    if not ici:
        return ["Aucune figure répertoriée sur la dernière bougie.",
                c.get("comptage", {}).get("phrase", "")]
    L = []
    for f in ici:
        L.append(f"{f['nom']} — {f['forme']}")
        for x in f.get("suivi", []):
            if not x.get("assez"):
                continue
            mot = "dans le bruit" if x["indiscernable"] else "écart net"
            L.append(f"   à {x['horizon']} barres : {x['taux']:.0f} % de "
                     f"hausses contre {x['base']:.0f} % un jour quelconque "
                     f"— {mot}, {x['n']} cas")
    L.append(c.get("comptage", {}).get("phrase", ""))
    return [x for x in L if x]


def _horizon(d: dict) -> list[str]:
    a = d.get("horizons") or []
    if not a:
        return ["Amplitude par horizon indisponible."]
    L = ["Ce que ce titre bouge, SANS DIRECTION — c'est une propriété du "
         "titre, pas un signal."]
    for x in a:
        typ = x.get("typique") if isinstance(x, dict) else None
        nom = x.get("nom") if isinstance(x, dict) else str(x)
        if typ is None:
            continue
        L.append(f"   {nom} : {_n(typ, 1, ' %')} d'amplitude typique")
    return L


def _donnees(d: dict) -> list[str]:
    q = d.get("qualite") or {}
    L = ["Les données de ce titre sont EXPLOITABLES."
         if q.get("utilisable") else
         "Les données de ce titre sont REFUSÉES : aucun signal n'en sort."]
    for m in q.get("bloquants") or []:
        L.append(f"   refus : {m}")
    for m in q.get("alertes") or []:
        L.append(f"   alerte : {m}")
    if not (q.get("bloquants") or q.get("alertes")):
        L.append("Aucune anomalie détectée.")
    return L


def _seance(d: dict) -> list[str]:
    h = d.get("horaires")
    if not h:
        return ["Horaires indisponibles pour ce titre."]
    L = [f"{h.get('nom', '')} — {h.get('code', '')}.",
         f"Ouverture {h.get('ouv_paris', '?')}, clôture "
         f"{h.get('clo_paris', '?')}, fixing {h.get('fix_paris', '?')} "
         f"(heure de Paris).",
         "Les règles s'évaluent sur CLÔTURE ; la spécification exécute à "
         "l'ouverture de la séance suivante.",
         "Il n'y a pas de « meilleure heure » : cela demanderait des "
         "données intraday que le programme n'a pas."]
    return L


def _avis(d: dict) -> list[str]:
    """La fiche complete. Ce n'est PAS un avis, et la derniere ligne le dit."""
    u = d.get("interet") or {}
    L = [f"{d['ticker']} — {_n(d.get('cours'))} {d.get('devise', '')} "
         f"au {d.get('date', '')}.",
         "",
         "CE QUE DIT LA SPÉCIFICATION"]
    L += ["  " + x for x in _entree(d)]
    L += ["", "VOUS SORTEZ QUAND ?"]
    L += ["  " + x for x in _sortie(d)]
    q = d.get("qualite") or {}
    if not q.get("utilisable"):
        L += ["", "DONNÉES"] + ["  " + x for x in _donnees(d)]
    return L


def _memoire_titre(d: dict) -> list[str]:
    """Ce que le programme a dit de ce titre, et ce qui a suivi.

    Les releves sont tous donnes, dans l'ordre — ceux ou le programme a
    eu raison comme ceux ou il a eu tort. Choisir lesquels montrer, ce
    serait refaire l'oubli selectif que la memoire existe pour corriger.
    """
    m = d.get("memoire") or {}
    rel = m.get("releves") or []
    if not rel:
        return ["Aucun état de ce titre n'a encore été relevé. La mémoire "
                "commence à la première consultation : chaque fois que le "
                "titre est ouvert, l'état du programme est écrit avant que "
                "le titre ne bouge."]
    out = [f"{m.get('n', len(rel))} état(s) relevé(s) sur ce titre ; "
           f"les derniers :"]
    from . import memoire as me
    for r in rel:
        bouts = []
        for h in me.HORIZONS:
            v = r.get(f"ecart_{h}_pc")
            bouts.append(f"{h} séances : "
                         + ("en attente" if v is None else _n(v, 1, " %")))
        out.append(f"● {r['date']} — le programme disait {r['programme'].upper()} "
                   f"({r['blocs']} blocs). Écart au marché : "
                   + " · ".join(bouts) + ".")
    out.append("")
    out.append(me.RAPPEL)
    return out


def _profil(d: dict) -> list[str]:
    """Ce qui distingue ce titre d'un autre, mesure.

    « On ne traite pas Tesla comme un ETF monde » : c'est vrai, et
    verifiable. Les lignes viennent de `profil.py`, qui a mesure
    l'amplitude, le pire recul, le lien au repere — et la duree REELLE
    des positions que les regles de la specification produisent sur ce
    titre. L'horizon n'est pas un choix : c'est une consequence des
    quatre conditions de sortie.
    """
    pr = d.get("profil")
    if not pr:
        return ["Le profil n'a pas pu être mesuré sur ce titre."]
    from . import profil as pf
    out = [f"{lib} : {val}" for lib, val in pf.lignes(pr, pr.get("duree"))]
    out.append("")
    out.append(pf.RAPPEL)
    if (pr.get("declare") or {}).get("disponible"):
        out.append(pf.RAPPEL_DECLARE)
    return out


# Les series du dernier dossier constitue, par titre : une duree nommee
# dans la question se mesure sur les MEMES cours que le reste du dossier,
# sans nouveau telechargement. Quelques titres seulement.
_SERIES: dict = {}


_DUREE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(jours?|semaines?|mois|ans?|annees?)\b")
_UNITE = {"jour": "jours", "jours": "jours", "semaine": "semaines",
          "semaines": "semaines", "mois": "mois", "an": "ans", "ans": "ans",
          "annee": "ans", "annees": "ans"}


def mesure_demandee(question: str, d: dict) -> None:
    """La duree que la question NOMME, mesuree et posee DANS le dossier :
    les phrases ne citent que ce qu'il contient, et le modele recoit la
    meme chose."""
    m = _DUREE.search(normalise(question))
    dt_ = d.get("detention")
    if not m or not dt_ or not d.get("ok"):
        return
    from . import cache as ch
    from . import detention as dt
    n = dt.seances(float(m.group(1).replace(",", ".")), _UNITE[m.group(2)])
    bench_tk = "SPY" if d.get("marche") == "us" else "^STOXX"
    try:
        brut, bb = _SERIES.get(d["ticker"]) or (
            ch.charge(d["ticker"], annees=10), ch.charge(bench_tk, annees=10))
        dt_["demande"] = dt.mesure(brut, n, bb)
    except Exception as exc:
        dt_["demande"] = {"libelle": dt.libelle(n), "periodes": 0,
                          "erreur": type(exc).__name__}


def _detention(d: dict) -> list[str]:
    """Ce que chaque duree de detention a donne sur ce titre.

    « Tesla, je garde deux mois : c'est bien ? » La premiere moitie se
    mesure ; la seconde est un avis, et la reponse le dit.
    """
    t = d.get("detention")
    if not t:
        return ["La détention n'a pas pu être mesurée sur ce titre."]
    from . import detention as dt
    out = []
    if t.get("demande"):
        out += dt.lignes(t["demande"]) + [""]
    out.append("Les durées usuelles, dans l'ordre des durées :")
    out += [dt.resume(m) for m in t.get("horizons", [])]
    out.append(dt.ligne_lundi(t.get("lundi_vendredi") or {}))
    out += ["", dt.RAPPEL_BIEN, dt.RAPPEL]
    return out


def mesure_chute(question: str, d: dict) -> None:
    """La chute que la question NOMME (« baisse de 25 % »), sinon celle du
    titre aujourd'hui : chaque episode passe, et ce qui a suivi. Posee
    DANS le dossier, comme les autres faits."""
    from . import cache as ch
    from . import rebond as rb
    try:
        brut = (_SERIES.get(d["ticker"]) or (None,))[0]
        if brut is None:
            brut = ch.charge(d["ticker"], annees=10)
        s = rb.seuil_de(normalise(question), d.get("chute"))
        d["rebond"] = rb.apres_chute(brut, s)
    except Exception as exc:
        d["rebond"] = {"erreur": type(exc).__name__}


def _rebond(d: dict) -> list[str]:
    """« Rebond ? » : ce que les chutes passees de ce titre ont ete
    suivies de, contre un jour quelconque. Jamais « il va rebondir »."""
    from . import rebond as rb
    return rb.lignes(d.get("chute"), d.get("rebond"))


# L'actualite : des TITRES d'articles, avec leur source et leur date. Le
# ton du fournisseur n'entre pas ici — rien ne s'en sert, et le dossier du
# majordome moins que tout autre chose.
RAPPEL_ACTU = (
    "Une annonce publique est connue de tous les acheteurs et vendeurs au "
    "même moment : elle est dans les cours quand on la lit. Ces titres "
    "sont du contexte avant un ordre, pas un signal, et le programme ne "
    "les chiffre pas.")


def actualite(d: dict, av_key: str | None) -> None:
    if not av_key:
        d["actus"] = {"sans_cle": True}
        return
    try:
        from . import news as nw
        brut = nw.news(av_key, d["ticker"], limit=5)
        d["actus"] = {"articles": [
            {"titre": a.get("titre", ""), "source": a.get("source", ""),
             "quand": a.get("quand", ""), "erreur": bool(a.get("erreur"))}
            for a in brut]}
    except Exception as exc:
        d["actus"] = {"erreur": type(exc).__name__}


def _actualite(d: dict) -> list[str]:
    a = d.get("actus") or {}
    if a.get("sans_cle"):
        out = ["Aucune clé Alpha Vantage : pas d'actualités pour ce titre. "
               "La clé se colle sur l'accueil."]
    elif a.get("erreur"):
        out = [f"Actualités indisponibles ({a['erreur']})."]
    else:
        out = []
        for x in a.get("articles") or []:
            src = f" — {x['source']}" if x.get("source") else ""
            qd = f", {x['quand']}" if x.get("quand") else ""
            out.append(f"· {x.get('titre', '')}{src}{qd}")
        out = out or ["Aucun article récent sur ce titre."]
    return out + ["", RAPPEL_ACTU]


# Les questions GENERALES, posees sans titre : « est-ce bien d'acheter ce
# qui a chute ? ». Elles ont une reponse ecrite d'avance, qui dit ce qui se
# mesure et comment le demander — jamais « oui » ni « non ».
def general(intention_cle: str) -> dict | None:
    from . import rebond as rb
    textes = {
        "rebond": ("ACHETER CE QUI A CHUTÉ ?", [rb.RAPPEL_GENERAL,
                                                "", rb.RAPPEL_SURVIVANT]),
        "actualite": ("UNE ANNONCE, UN NOUVEAU MODÈLE", [
            "Nommez le titre : « Tesla, nouveau modèle ? ». Le majordome "
            "rend les derniers articles qui le nomment, et, si le cerveau "
            "est branché, cherche sur le Web avec ses sources.",
            "", RAPPEL_ACTU]),
    }
    if intention_cle not in textes:
        return None
    t, L = textes[intention_cle]
    return {"ok": True, "ticker": "", "intention": intention_cle,
            "titre": t, "lignes": L, "rappel": RAPPEL}


SECTIONS = {
    "rebond": ("APRÈS UNE CHUTE : CE QUI A SUIVI, SUR CE TITRE", _rebond),
    "actualite": ("L'ACTUALITÉ DU TITRE", _actualite),
    "detention": ("CE QUE CETTE DURÉE A DONNÉ SUR CE TITRE", _detention),
    "sortie": ("VOUS SORTEZ QUAND ?", _sortie),
    "entree": ("CE QUE DIT LA SPÉCIFICATION POUR ENTRER", _entree),
    "risque": ("LE RISQUE, TEL QUE LA SPÉCIFICATION LE DÉFINIT", _risque),
    "bougies": ("LA DERNIÈRE BOUGIE", _bougies),
    "horizon": ("CE QUE CE TITRE BOUGE", _horizon),
    "donnees": ("LES DONNÉES SONT-ELLES EXPLOITABLES ?", _donnees),
    "seance": ("LA SÉANCE", _seance),
    "profil": ("CE QUE CET INSTRUMENT EST, ET COMBIEN DE TEMPS "
               "LA SPÉCIFICATION LE GARDE", _profil),
    "memoire": ("CE QUE LE PROGRAMME A DIT DE CE TITRE, ET CE QUI A SUIVI",
                _memoire_titre),
    "avis": ("LA FICHE COMPLÈTE", _avis),
}


def repond(question: str, d: dict, av_key: str | None = None) -> dict:
    """La section du dossier qui repond a la question posee."""
    if not d.get("ok"):
        return {"ok": False, "ticker": d.get("ticker"),
                "erreur": d.get("erreur", "dossier indisponible")}
    cle = intention(question)
    if cle == "detention":
        mesure_demandee(question, d)
    elif cle == "rebond":
        mesure_chute(question, d)
    elif cle == "actualite":
        actualite(d, av_key)
    titre, fabrique = SECTIONS.get(cle, SECTIONS["avis"])
    return {"ok": True, "ticker": d["ticker"], "intention": cle,
            "titre": titre, "lignes": [x for x in fabrique(d)],
            "rappel": d.get("rappel", RAPPEL)}


def comprend(question: str, existe, defaut: str | None = None,
             detenus=()) -> tuple:
    """(intention, ticker). Le ticker est tranche PAR LES DONNEES.

    `existe(tk)` doit rendre vrai si le ticker se charge. `defaut` sert
    quand la question n'en nomme aucun — typiquement le titre deja
    ouvert a l'ecran.

    Deux dictionnaires passent avant la cote : les lignes que le
    proprietaire DETIENT (« j'ai achete du TLX » quand il detient TLX.DE :
    c'est Talanx, pas Telix a New York), puis la table des noms de
    `resolve.py` (« Tesla » -> TSLA). Ni l'un ni l'autre ne devine : ce
    sont des correspondances ecrites.
    """
    from .resolve import par_alias
    inten = intention(question)
    racines = {}
    for t in detenus or ():
        t = (t or "").upper()
        if t:
            racines.setdefault(t.split(".")[0], t)
            racines[t] = t
    for j in jetons_tickers(question):
        for c in (racines.get(j), par_alias(j), j):
            if not c:
                continue
            try:
                if existe(c):
                    return inten, c
            except Exception:
                continue
    return inten, defaut


def phrase(rep: dict, maxi: int = 3) -> str:
    """Une seule phrase, pour la voix du majordome.

    La voix ne lit pas un tableau : elle donne la tete du dossier et
    renvoie a l'ecran pour le detail.
    """
    if not rep.get("ok"):
        return f"Je n'ai pas pu ouvrir le dossier : {rep.get('erreur', '')}"
    bouts = [x.strip() for x in rep.get("lignes", []) if x.strip()]
    bouts = [x for x in bouts if not x.startswith(("●", "○", "  "))]
    return " ".join([rep["titre"] + "."] + bouts[:maxi])


def texte(rep: dict) -> str:
    if not rep.get("ok"):
        return f"\n  {rep.get('ticker')} : {rep.get('erreur')}\n"
    L = [f"\n  {rep['ticker']} — {rep['titre']}", ""]
    L += ["  " + x if x else "" for x in rep["lignes"]]
    L += ["", "  " + rep["rappel"], ""]
    return "\n".join(L)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Pose une question en francais sur un titre")
    p.add_argument("question", nargs="+")
    p.add_argument("--ticker", default=None,
                   help="si la question n'en nomme pas")
    a = p.parse_args()
    q = " ".join(a.question)

    from . import cache as ch

    def existe(t):
        try:
            ch.charge(t, annees=1)
            return True
        except Exception:
            return False

    inten, tk = comprend(q, existe, a.ticker)
    if not tk:
        print(f"\n  Intention reconnue : {inten}. Mais aucun titre nomme.")
        print("  Exemple : py -m equity_scanner.dossier "
              "\"je sors quand sur TLX.DE\"\n")
        return
    print(texte(repond(q, constitue(tk))))


if __name__ == "__main__":
    main()
