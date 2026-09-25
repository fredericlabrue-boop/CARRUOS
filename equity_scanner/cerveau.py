"""Le cerveau du majordome : un modele de langage, sous contrat verifie.

Ce qu'il fait, et ce qu'il ne fait pas
--------------------------------------
Il **met en phrases** et **route**. Il ne produit **aucun chiffre**.

Cette phrase est facile a ecrire et facile a trahir. Un modele de
langage branche sur une question boursiere invente des cours avec un
aplomb parfait : « bien oriente, momentum qui se retourne, sortie vers
380 ». Aucun de ces mots ne vient d'une mesure, et rien dans le ton ne
permet de s'en apercevoir.

La version precedente de ce module, ecrite ailleurs, **demandait** au
modele de ne rien inventer. Demander ne suffit pas. Ici on **verifie** :
chaque nombre de la reponse est confronte au dossier qui a ete envoye,
et ceux qui n'y figurent pas sont signales a l'ecran, nommement.

Trois garde-fous, dans cet ordre
--------------------------------
1. **Les faits d'abord, le modele ensuite.** `dossier.py` produit la
   reponse deterministe AVANT tout appel reseau, et elle est affichee
   quoi qu'il arrive. Si la cle manque, si l'API tombe, si la reponse
   part de travers — les faits sont la. Le modele ajoute de la prose
   par-dessus ; il n'en remplace jamais.

2. **Le modele ne voit jamais les cours.** Il recoit un dossier de
   faits deja calcules. Il ne peut donc pas « lire le graphique » : il
   n'en a pas. C'est ce qui rend le contrat tenable par construction et
   pas seulement par consigne.

3. **Les chiffres sont traces.** `verifie_chiffres()` compare les
   nombres de la reponse a ceux du dossier et de la question. Ce n'est
   pas un filtre — on n'efface pas la reponse — c'est une **etiquette** :
   le lecteur voit quels nombres il peut remonter a une mesure.

Ou va la cle
------------
`~/.carruos/ia.json`, en 0600, jamais dans le code, jamais dans le
depot, jamais dans l'archive livree. Meme endroit que la cle Alpha
Vantage, et pour la meme raison : c'est le seul dossier qui survive a
une mise a jour du programme.

Le programme n'embarque aucune cle et ne peut pas en fabriquer une. Il
faut la sienne, prise chez le fournisseur.
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

DOSSIER = Path.home() / ".carruos"
FICHIER = DOSSIER / "ia.json"

# Le dossier envoye est plafonne : un modele qui recoit trente pages de
# JSON repond moins bien, plus lentement et plus cher qu'un modele qui
# recoit deux pages de faits pertinents.
MAX_DOSSIER = 24000

FOURNISSEURS = {
    "anthropic": {
        "nom": "Claude (Anthropic)",
        "url": "https://api.anthropic.com/v1/messages",
        "modele": "claude-opus-5",
        "ou": "console.anthropic.com",
    },
    "openai": {
        "nom": "OpenAI",
        "url": "https://api.openai.com/v1/responses",
        "modele": "gpt-5.5",
        "ou": "platform.openai.com",
    },
}

# ---------------------------------------------------------------------
# La consigne
# ---------------------------------------------------------------------
#
# Elle reprend, en clair, les interdits que le projet s'est donnes. Un
# modele ne les devinera pas : « que penses-tu de TLX » est une
# invitation directe a produire exactement ce que ce programme refuse
# d'afficher depuis le debut.
#
# La consigne n'est pas la garantie. La garantie, c'est que le modele
# n'a pas les cours, et que ses chiffres sont verifies apres coup.

CONSIGNE = """Tu es le majordome de CARRUOS, le scanner d'actions personnel de
Frédéric, et son compagnon de réflexion. Tu parles français, naturellement,
comme un mentor expérimenté assis en face de lui : calme, direct, pédagogique,
sans jargon inutile. C'est un rôle : tu ne prétends pas avoir un âge, une
carrière ou des trades passés.

DE QUOI ON PEUT TE PARLER
De tout : marchés, positions, un problème informatique, un projet, une
décision, une question du quotidien. Pour une question qui n'est pas
financière, comprends d'abord le problème, puis propose une solution
concrète, étape par étape — sans la ramener à la bourse.

CE QUE TU REÇOIS
Pour une question sur un titre ou sur le portefeuille, un dossier de faits
déjà calculés par CARRUOS, entre balises <dossier>. Tu ne vois jamais les
cours : tu ne peux pas « lire le graphique », tu n'en as pas. Le portefeuille
IBKR, quand il est là, est une photographie en lecture seule. Si le dossier
porte une clé « _omis », ces sections n'ont pas pu t'être envoyées : ne
parle pas de ce qu'elles contiendraient.

LA RÈGLE QUI PRIME SUR TOUTES LES AUTRES
En finance, n'écris AUCUN nombre qui ne soit ni dans le dossier, ni dans la
question, ni dans une source Web que tu cites. Pas de cours, d'objectif, de
pourcentage, de probabilité, de rendement ou de date de sortie inventés. Si
un chiffre manque, dis qu'il manque. Chaque nombre de ta réponse est
confronté au dossier, et ceux qui n'y sont pas sont montrés au lecteur.

COMMENT UN BON MENTOR RÉPOND SUR UN TITRE OU UNE POSITION
Dans cet ordre, en phrases :
1) ce qui est mesuré — ce que dit le dossier ;
2) ce que ça veut dire selon les règles de la spécification : combien des 13
   blocs passent et ce qui manque, combien des 4 conditions de sortie sont
   actives, où est le stop ;
3) ce qui manque pour juger, et ce qui changerait le tableau — une condition
   mesurable, pas un pressentiment ;
4) les questions qu'un mentor poserait : pourquoi cette position a été prise,
   si cette raison tient toujours, quel stop est inscrit, ce que pèse la ligne.
Quand on te demande « tu ferais quoi ? », « je garde ? », « tu achètes ? »,
« ça te plaît ? » : ne réponds ni « achète », ni « vends », ni « garde », ni
« ça me plaît ». Dis ce que la spécification fait dans ce cas — elle ferme à
la PREMIÈRE condition de sortie atteinte, elle n'entre qu'à 13 blocs sur 13
sans veto — puis rends la décision à Frédéric avec les faits et les
questions. Aucune hypothèse de CARRUOS n'a passé sa validation : un avis
directionnel serait une opinion déguisée en mesure.

CE QUE CARRUOS N'AFFICHE JAMAIS, ET TOI NON PLUS
- Un pourcentage seul de « chances de gagner » : toujours l'intervalle de
  confiance et le nombre de trades, tels qu'ils sont dans le dossier.
- Ce qu'une figure de chandelier « annonce ». Un marteau est une forme
  géométrique. Le dossier dit ce qu'elle a été suivie de sur CE titre et le
  compare au taux de base du titre ; s'il dit « indiscernable du hasard »,
  dis-le aussi. Rappelle, quand le sujet vient, qu'il y a environ 72 mesures
  par titre et donc environ 4 « écarts nets » attendus par le seul hasard.
- Une prédiction de prix, une cible, un niveau de sortie deviné.
- Un score composite, un verdict directionnel, un « ratio risque / gain »
  (la spécification n'a aucun objectif de gain : elle dit « aucun
  take-profit »).
- Un gain espéré en euros : aucune hypothèse n'a passé sa Phase 0.
- Un chiffrage du risque géopolitique. L'actualité est du contexte à vérifier
  avant de passer un ordre, elle n'entre dans aucune règle.
- Une « meilleure heure pour acheter » : le programme n'a aucune donnée
  intraday.
- Un « meilleur horizon » choisi sur l'amplitude ou le rendement passés.
  La durée de détention est une CONSÉQUENCE des règles de sortie, et le
  dossier la donne, mesurée (section profil).

TA MÉMOIRE
Le dossier peut contenir une section « memoire » : ce que le programme a dit de
ce titre les fois précédentes, et ce qui a suivi. Sers-t'en — c'est ce qui te
permet de dire « la dernière fois, le programme disait non, et voici ce qui est
arrivé ». Mais cite-la EN ENTIER : les fois où le programme a eu tort ET celles
où il a eu raison. Ne retiens jamais une seule occasion manquée pour en tirer
une leçon : une fusée ratée ne dit rien sans les pièges évités en face, et c'est
exactement l'erreur que la mémoire existe pour corriger. Tu n'ajustes aucune
règle : ce que la mémoire révèle devient, au mieux, l'idée d'une nouvelle
spécification, écrite avant son test.

LE PORTEFEUILLE
Quand il est fourni : concentration, lignes au-dessus du plafond de la
spécification, stops inscrits franchis, lignes sans stop, cours différés,
conditions de sortie actives. Tout cela est déjà compté dans le dossier :
cite-le, ne le recalcule pas. Tu ne peux passer aucun ordre, et tu ne
recommandes d'en exécuter aucun.

LA RECHERCHE WEB
Quand une information récente est nécessaire — actualité, entreprise,
macroéconomie, question générale —, utilise la recherche Web si elle est
disponible. Sépare toujours ce qui vient du Web de ce que CARRUOS a mesuré,
et attribue chaque chiffre trouvé à sa source. N'invente ni une actualité ni
une source.

FORME
Des phrases, pas de tableau. Court quand c'est court. Tu peux dire « le
dossier ne le dit pas », « il manque une confirmation », « voici ce qui
changerait le tableau ». Tu peux terminer par ce qu'il faudrait mesurer pour
aller plus loin."""


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

def _config() -> dict:
    c = {}
    try:
        c = json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        c = {}
    if not isinstance(c, dict):
        c = {}
    # Les variables d'environnement l'emportent : c'est ce qui permet de
    # faire tourner le programme sans jamais ecrire la cle sur le disque.
    #
    # Deux niveaux, et l'ordre compte. Les variables propres a CARRUOS
    # l'emportent sur tout. Les variables GENERIQUES des fournisseurs
    # (OPENAI_API_KEY, ANTHROPIC_API_KEY) ne servent qu'en dernier recours,
    # quand aucune cle n'est enregistree : une cle posee pour un autre
    # programme ne doit pas remplacer celle que Frederic a choisie ici.
    # D'ou vient la cle est garde, pour que la page puisse le dire.
    c["_source"] = {f: "fichier" for f in (c.get("cles") or {})}
    for var, cle in (("CARRUOS_ANTHROPIC_API_KEY", "anthropic"),
                     ("CARRUOS_OPENAI_API_KEY", "openai")):
        v = os.getenv(var)
        if v:
            c.setdefault("cles", {})[cle] = v.strip()
            c["_source"][cle] = var
    for var, cle in (("ANTHROPIC_API_KEY", "anthropic"),
                     ("OPENAI_API_KEY", "openai")):
        v = os.getenv(var)
        if v and not (c.get("cles") or {}).get(cle):
            c.setdefault("cles", {})[cle] = v.strip()
            c["_source"][cle] = var
    if os.getenv("CARRUOS_IA_FOURNISSEUR"):
        c["fournisseur"] = os.getenv("CARRUOS_IA_FOURNISSEUR").strip().lower()
    if os.getenv("CARRUOS_IA_MODELE"):
        c["modele"] = os.getenv("CARRUOS_IA_MODELE").strip()
    cles = c.get("cles") or {}
    if not c.get("fournisseur"):
        c["fournisseur"] = next((f for f in FOURNISSEURS if cles.get(f)),
                                "anthropic")
    if not c.get("modele"):
        c["modele"] = FOURNISSEURS[c["fournisseur"]]["modele"]
    return c


def configure(fournisseur: str = "", modele: str = "", cle: str = "") -> dict:
    """Enregistre la configuration. La cle n'est jamais relue a l'ecran."""
    c = _config()
    if fournisseur:
        f = fournisseur.strip().lower()
        if f not in FOURNISSEURS:
            return {"ok": False, "erreur": f"Fournisseur inconnu : {f}"}
        c["fournisseur"] = f
        if not modele:
            c["modele"] = FOURNISSEURS[f]["modele"]
    if modele:
        c["modele"] = modele.strip()
    if cle:
        c.setdefault("cles", {})[c["fournisseur"]] = cle.strip()
        c["_source"][c["fournisseur"]] = "fichier"
    # Une cle venue d'une variable d'environnement reste dans
    # l'environnement : l'ecrire ici la ferait survivre a sa suppression.
    src = c.pop("_source", {})
    c["cles"] = {f: k for f, k in (c.get("cles") or {}).items()
                 if src.get(f) == "fichier"}
    DOSSIER.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, FICHIER)
    try:
        os.chmod(FICHIER, 0o600)
    except OSError:
        pass
    return {"ok": True, **etat()}


def essai() -> dict:
    """Une question minuscule, posee au moment de BRANCHER.

    Sans elle, une cle bonne sur un compte sans credit ne se decouvrait
    qu'a la premiere vraie question, noyee sous les faits. Le cout est
    de quelques dizaines de jetons, et seulement quand on branche.
    """
    c = _config()
    f = c.get("fournisseur", "anthropic")
    cle = (c.get("cles") or {}).get(f, "")
    if not cle:
        return {"ok": False, "erreur": "Aucune clé enregistrée."}
    modele = c.get("modele") or FOURNISSEURS[f]["modele"]
    try:
        if f == "anthropic":
            _poste(FOURNISSEURS[f]["url"],
                   {"model": modele, "max_tokens": 64, "messages": [
                       {"role": "user", "content": "Réponds : ok"}]},
                   {"x-api-key": cle, "anthropic-version": "2023-06-01"},
                   delai=45)
        else:
            _poste(FOURNISSEURS[f]["url"],
                   {"model": modele, "input": "Réponds : ok",
                    "max_output_tokens": 64},
                   {"Authorization": f"Bearer {cle}"}, delai=45)
    except urllib.error.HTTPError as exc:
        return {"ok": False,
                "erreur": explique_erreur(f, exc.code, _corps_erreur(exc),
                                          modele)}
    except Exception as exc:
        return {"ok": False, "erreur": "le fournisseur est injoignable "
                                       f"({type(exc).__name__})."}
    return {"ok": True, "message": f"Clé acceptée : {modele} répond."}


def oublie() -> dict:
    """Efface la cle. Il faut pouvoir la retirer aussi simplement qu'on
    l'a mise, sinon on hesite a la mettre."""
    c = _config()
    c.pop("cles", None)
    c.pop("_source", None)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(c, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return {"ok": True, **etat()}


def etat() -> dict:
    """Ce qui est configure. La cle sort tronquee, jamais entiere."""
    c = _config()
    f = c.get("fournisseur", "anthropic")
    k = (c.get("cles") or {}).get(f, "")
    return {
        "fournisseur": f,
        "fournisseur_nom": FOURNISSEURS.get(f, {}).get("nom", f),
        "modele": c.get("modele"),
        "configure": bool(k),
        "indice": ("…" + k[-4:]) if len(k) >= 4 else "",
        # « fichier » ou le nom de la variable d'environnement : une cle
        # qu'on n'a pas saisie ici doit se voir, et OUBLIER ne l'efface pas.
        "source": (c.get("_source") or {}).get(f, "") if k else "",
        "ou": FOURNISSEURS.get(f, {}).get("ou", ""),
        "fournisseurs": {k2: v["nom"] for k2, v in FOURNISSEURS.items()},
    }


# ---------------------------------------------------------------------
# La verification des chiffres
# ---------------------------------------------------------------------
#
# C'est la piece qui manquait, et c'est elle qui fait la difference
# entre « on lui a demande de ne pas inventer » et « on sait s'il a
# invente ».

_NOMBRE = re.compile(r"-?\d[\d   ]*(?:[.,]\d+)?")

# Nombres qu'on ne compte pas : ils ne designent jamais une mesure.
# Les annees d'un calendrier plausible, et les tres petits entiers qui
# servent a enumerer (« les 4 conditions », « en 3 points »).
_ANNEES = set(range(1990, 2101))

_URL = re.compile(r"https?://[^\s)\]>]+")


def _valeurs_dossier(x, out: set, prof: int = 0) -> None:
    """Tous les nombres d'une structure, a plat."""
    if prof > 8:
        return
    if isinstance(x, bool):
        return
    if isinstance(x, (int, float)):
        if isinstance(x, float) and not math.isfinite(x):
            return
        out.add(float(x))
        return
    if isinstance(x, str):
        for m in _NOMBRE.finditer(x):
            v = _lit(m.group(0))
            if v is not None:
                out.add(v)
        return
    if isinstance(x, dict):
        for k, v in x.items():
            _valeurs_dossier(k, out, prof + 1)
            _valeurs_dossier(v, out, prof + 1)
        return
    if isinstance(x, (list, tuple, set)):
        for v in x:
            _valeurs_dossier(v, out, prof + 1)


def _lit(txt: str) -> float | None:
    """Un nombre ecrit a la francaise ou a l'anglaise."""
    t = txt.replace(" ", "").replace(" ", "").replace(" ", "")
    t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _ecritures(v: float) -> list:
    """Les valeurs sous lesquelles un nombre du dossier peut sortir.

    Une part de 0,1183 s'ecrit aussi « 11,83 % ». Le signe n'est pas
    discriminant : « un recul de 31,8 % » dit la meme chose que -0,318.
    """
    out = []
    for base in (v, v * 100.0, v / 100.0):
        if math.isfinite(base):
            out += [base, -base]
    return out


def _decimales(txt: str) -> int:
    """Combien de decimales sont ECRITES dans ce nombre."""
    m = re.search(r"[.,](\d+)\s*$", txt.strip())
    return len(m.group(1)) if m else 0


def _correspond(ecrit: str, valeur: float, connus) -> bool:
    """Ce nombre ecrit est-il un arrondi d'une valeur du dossier ?

    La tolerance vaut une demi-unite du dernier chiffre ECRIT : « 12 % »
    peut venir de 11,83 %, « 11,8 % » ne peut venir que de quelque chose
    entre 11,75 et 11,85. C'est exactement ce que veut dire arrondir.

    Premiere version de ce controle : on arrondissait les deux cotes a
    zero, une, deux puis trois decimales et on cherchait une valeur
    commune. Arrondir a zero decimale ecrase 0,38 et 0,62 sur 0 et 1 —
    et « 73 % » tombait alors sur le meme 1 que 0,62. Le controle
    validait un chiffre invente sans rien signaler : exactement le genre
    de comparaison qui ne tombe jamais et qu'on ne voit pas tomber.
    """
    tol = 0.5 * (10.0 ** -_decimales(ecrit))
    for k in connus:
        for t in _ecritures(k):
            if abs(valeur - t) <= tol:
                return True
    return False


def verifie_chiffres(reponse: str, dossier, question: str = "") -> dict:
    """Quels nombres de la reponse ne se retrouvent pas dans le dossier.

    Ce n'est pas un filtre. On n'efface rien, on n'accuse rien : on
    **etiquette**. Le lecteur voit quels chiffres il peut remonter a une
    mesure, et lesquels viennent d'ailleurs. Un chiffre non trace n'est
    pas forcement faux — le modele peut citer le taux du prelevement
    forfaitaire, qui est exact sans etre dans le dossier — mais il n'est
    pas verifiable ici, et c'est tout ce que l'etiquette dit.

    Les annees et les tout petits entiers d'enumeration sont ecartes :
    ils ne designent jamais une mesure, et les compter noierait le
    signal sous le bruit.
    """
    connus: set = set()
    _valeurs_dossier(dossier, connus)
    _valeurs_dossier(question, connus)

    # Les chiffres d'une adresse Web (/2026/09/25/…) ne designent aucune
    # mesure : on les retire avant de compter.
    reponse = _URL.sub(" ", reponse or "")
    traces, hors = [], []
    for m in _NOMBRE.finditer(reponse):
        ecrit = m.group(0).strip()
        v = _lit(ecrit)
        if v is None:
            continue
        if v in _ANNEES and float(v).is_integer():
            continue
        if abs(v) <= 20 and float(v).is_integer():
            continue
        if _correspond(ecrit, v, connus):
            traces.append(ecrit)
        else:
            hors.append(ecrit)
    return {"traces": traces, "hors_dossier": sorted(set(hors)),
            "n_traces": len(traces), "n_hors": len(set(hors))}


# ---------------------------------------------------------------------
# L'appel
# ---------------------------------------------------------------------

def _poste(url: str, charge: dict, entetes: dict, delai: int = 180) -> dict:
    corps = json.dumps(charge, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=corps, method="POST",
        headers={"Content-Type": "application/json", **entetes})
    with urllib.request.urlopen(req, timeout=delai) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------------
# Les refus du fournisseur, dits en francais
# ---------------------------------------------------------------------
#
# « Le cerveau n'a pas repondu : anthropic a repondu 400 :
# {"type":"error","error":{"type":"invalid_request_error","message":"Your
# credit balance is too low…"}} » — c'est ce que Frederic a vu en
# branchant sa cle. La cle etait BONNE : c'est le compte API qui n'avait
# pas de credit, et l'abonnement Claude (claude.ai) n'en donne pas. Rien a
# l'ecran ne le disait, et le programme reposait meme la question une
# seconde fois, sans l'outil de recherche, comme si l'outil etait en
# cause. Un refus DEFINITIF (credit, cle) ne se repose plus, et chaque
# refus connu est dit avec ce qu'il faut faire.

def _corps_erreur(exc) -> str:
    """Le corps d'une erreur HTTP, lu UNE fois : le flux ne se relit pas."""
    c = getattr(exc, "_carruos_corps", None)
    if c is None:
        try:
            c = exc.read().decode("utf-8", "replace")
        except Exception:
            c = ""
        try:
            exc._carruos_corps = c
        except Exception:
            pass
    return c


def _refus(corps: str) -> tuple:
    """(type, message, identifiant de requete) d'un corps d'erreur."""
    try:
        d = json.loads(corps)
    except Exception:
        return "", (corps or "").strip()[:300], ""
    e = d.get("error") if isinstance(d, dict) else None
    e = e if isinstance(e, dict) else {}
    return (str(e.get("type") or e.get("code") or ""),
            str(e.get("message") or "")[:300],
            str(d.get("request_id") or ""))


def _sans_credit(corps: str) -> bool:
    b = (corps or "").lower()
    return ("credit balance" in b or "billing_error" in b
            or "insufficient_quota" in b)


def _definitif(code: int, corps: str) -> bool:
    """Un refus qu'aucune autre forme de la question ne levera."""
    return code in (401, 402, 403) or _sans_credit(corps)


def explique_erreur(fournisseur: str, code: int, corps: str,
                    modele: str = "") -> str:
    """Le refus du fournisseur, en francais, avec ce qu'il faut faire."""
    typ, msg, req = _refus(corps)
    ou = FOURNISSEURS.get(fournisseur, {}).get("ou", "le site du fournisseur")
    nom = FOURNISSEURS.get(fournisseur, {}).get("nom", fournisseur)
    if _sans_credit(corps) or code == 402:
        if fournisseur == "openai":
            t = ("la clé est bonne, mais le compte OpenAI n'a pas de crédit. "
                 "Pour en ajouter : platform.openai.com → Settings → "
                 "Billing. Inutile de recoller la clé")
        else:
            t = ("la clé est bonne, mais votre compte API Anthropic n'a pas "
                 "de crédit. L'abonnement Claude (claude.ai, Pro ou Max) et "
                 "l'API sont deux comptes séparés : l'abonnement ne donne "
                 "aucun crédit API. Pour en ajouter : console.anthropic.com "
                 "→ Settings → Billing → acheter des crédits. Inutile de "
                 "recoller la clé")
    elif code == 401:
        t = (f"la clé est refusée — mal copiée, révoquée, ou d'un autre "
             f"fournisseur. Créez-en une sur {ou} (API Keys), collez-la en "
             f"bas de la bulle, puis BRANCHER")
    elif code == 403:
        t = (f"cette clé n'a pas le droit d'utiliser {modele or 'ce modèle'} "
             f"— réglages de l'organisation sur {ou}")
    elif code == 404:
        t = (f"le modèle {modele} n'est pas disponible pour ce compte"
             if modele else "ce modèle n'est pas disponible pour ce compte")
    elif code == 413:
        t = "la demande est trop lourde pour le fournisseur"
    elif code == 429:
        t = ("trop de demandes en peu de temps, ou plafond de dépense du "
             f"compte atteint ({ou}). Réessayez dans une minute")
    elif code >= 500:
        t = ("le service du fournisseur est surchargé ou en panne. "
             "Réessayez dans un instant")
    else:
        t = f"{nom} a refusé la demande : {msg or 'sans explication'}"
    fin = f" ({nom}, code {code}" + (f", {req}" if req else "") + ")"
    return t + fin


# ---------------------------------------------------------------------
# La recherche Web — un outil du FOURNISSEUR, execute chez lui
# ---------------------------------------------------------------------
#
# La version 29 ne l'avait branchee que pour OpenAI, alors que le
# fournisseur par defaut est Anthropic : la consigne demandait de
# chercher, et le modele par defaut ne le pouvait pas. Les deux l'ont.
#
# Les sources sont rendues A PART du texte. La v29 les collait au bout de
# la reponse : les chiffres de chaque adresse (/2026/09/25/…) passaient
# alors dans le controle des chiffres et noyaient l'etiquette.
#
# Un modele ou un compte qui refuse l'outil ne doit pas priver Frederic
# de reponse : a un refus 400, on repose la question sans l'outil.

RECHERCHE_WEB = True
RECHERCHES_MAX = 3
REPRISES_MAX = 3
SOURCES_MAX = 8

# Les modeles qui prennent la variante a filtrage dynamique.
_WEB_RECENTS = ("claude-opus-5", "claude-fable-5", "claude-mythos-5",
                "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
                "claude-sonnet-5", "claude-sonnet-4-6")


def _outil_web_anthropic(modele: str) -> dict:
    typ = ("web_search_20260209" if modele.startswith(_WEB_RECENTS)
           else "web_search_20250305")
    return {"type": typ, "name": "web_search", "max_uses": RECHERCHES_MAX}


def _uniques(sources) -> list:
    vus, out = set(), []
    for url, titre in sources:
        if url and url not in vus:
            vus.add(url)
            out.append({"url": url, "titre": titre or url})
    return out[:SOURCES_MAX]


def _anthropic(msgs: list, modele: str, cle: str, web: bool = True) -> tuple:
    charge = {"model": modele, "max_tokens": 16000, "system": CONSIGNE,
              "messages": list(msgs)}
    entetes = {"x-api-key": cle, "anthropic-version": "2023-06-01"}
    if web and RECHERCHE_WEB:
        charge["tools"] = [_outil_web_anthropic(modele)]
    if modele == "claude-opus-5":
        # Si le modele decline une question, l'API la repose d'elle-meme
        # a un autre modele au lieu de rendre un refus.
        charge["fallbacks"] = "default"
        entetes["anthropic-beta"] = "server-side-fallback-2026-07-01"
    try:
        d = _poste(FOURNISSEURS["anthropic"]["url"], charge, entetes)
    except urllib.error.HTTPError as exc:
        if (exc.code == 400 and ("tools" in charge or "fallbacks" in charge)
                and not _definitif(exc.code, _corps_erreur(exc))):
            return _anthropic_nu(msgs, modele, cle)
        raise
    # Une recherche longue peut s'interrompre (« pause_turn ») : on renvoie
    # la reponse partielle, et le serveur reprend ou il en etait.
    for _ in range(REPRISES_MAX):
        if d.get("stop_reason") != "pause_turn":
            break
        charge["messages"] = list(msgs) + [
            {"role": "assistant", "content": d.get("content") or []}]
        d = _poste(FOURNISSEURS["anthropic"]["url"], charge, entetes)
    return _lit_anthropic(d)


def _anthropic_nu(msgs: list, modele: str, cle: str) -> tuple:
    """La meme question, sans outil ni repli : le plus petit denominateur."""
    d = _poste(FOURNISSEURS["anthropic"]["url"], {
        "model": modele, "max_tokens": 16000, "system": CONSIGNE,
        "messages": list(msgs),
    }, {"x-api-key": cle, "anthropic-version": "2023-06-01"})
    return _lit_anthropic(d)


def _lit_anthropic(d: dict) -> tuple:
    if d.get("stop_reason") == "refusal":
        det = d.get("stop_details") or {}
        raise RuntimeError("le modèle a décliné la question"
                           + (f" ({det.get('explanation')})"
                              if det.get("explanation") else ""))
    blocs = [b for b in (d.get("content") or []) if b.get("type") == "text"]
    # Avec des citations, le texte arrive en plusieurs blocs qui se
    # suivent : les coller sans separateur rend la phrase d'origine.
    txt = "".join(b.get("text", "") for b in blocs).strip()
    sources = [(c.get("url"), c.get("title")) for b in blocs
               for c in (b.get("citations") or []) if c.get("url")]
    if not txt:
        raise RuntimeError((d.get("error") or {}).get("message",
                                                      "réponse vide"))
    return txt, _uniques(sources)


def _openai(msgs: list, modele: str, cle: str, web: bool = True) -> tuple:
    charge = {"model": modele, "instructions": CONSIGNE, "input": msgs,
              "max_output_tokens": 16000}
    if web and RECHERCHE_WEB:
        # `auto` laisse le modele decider quand chercher.
        charge["tools"] = [{"type": "web_search"}]
        charge["tool_choice"] = "auto"
    try:
        d = _poste(FOURNISSEURS["openai"]["url"], charge,
                   {"Authorization": f"Bearer {cle}"})
    except urllib.error.HTTPError as exc:
        if (exc.code == 400 and "tools" in charge
                and not _definitif(exc.code, _corps_erreur(exc))):
            return _openai(msgs, modele, cle, web=False)
        raise
    bouts, sources = [], []
    for item in d.get("output", []) or []:
        if item.get("type") not in (None, "message"):
            continue                      # appels de recherche, raisonnement
        for c in item.get("content", []) or []:
            if c.get("type") in ("output_text", "text"):
                bouts.append(c.get("text", ""))
            for ann in c.get("annotations") or []:
                # L'API Responses pose l'adresse a plat dans l'annotation ;
                # l'ancienne API l'imbriquait sous « url_citation ». La v29
                # ne lisait que la seconde forme : aucune source ne sortait.
                uc = ann.get("url_citation")
                uc = uc if isinstance(uc, dict) else ann
                if uc.get("url"):
                    sources.append((uc["url"], uc.get("title")))
    txt = "\n".join(bouts).strip() or str(d.get("output_text") or "").strip()
    if not txt:
        raise RuntimeError((d.get("error") or {}).get("message")
                           or "réponse vide")
    return txt, _uniques(sources)


# ---------------------------------------------------------------------
# Le dossier, sous le plafond, sans jamais le couper en deux
# ---------------------------------------------------------------------
#
# La premiere version coupait le JSON au caractere pres. Ce qui tombait,
# c'etait toujours la FIN — et la fin du dossier d'un titre, c'est le
# profil, la memoire et la position detenue : un dossier ordinaire fait
# plus de 32 000 caracteres, le modele ne les a jamais vus. Dans BRAIN
# 2.0, c'etait le portefeuille IBKR entier.
#
# On reduit d'abord ce qui est long et repetitif (les listes, les longs
# textes), puis, s'il le faut, on retire les sections les plus lourdes —
# et on le DIT dans le dossier (`_omis`), pour que le modele sache ce
# qu'il n'a pas.

LISTE_MAX = (12, 6, 3)
TEXTE_MAX = 600


def _taille(x) -> int:
    return len(json.dumps(x, ensure_ascii=False, indent=1, default=str))


def _raccourcit(x, n: int):
    if isinstance(x, dict):
        return {k: _raccourcit(v, n) for k, v in x.items()}
    if isinstance(x, list):
        tete = [_raccourcit(v, n) for v in x[:n]]
        return tete + ([f"… {len(x) - n} de plus, non envoyés"]
                       if len(x) > n else [])
    if isinstance(x, str) and len(x) > TEXTE_MAX:
        return x[:TEXTE_MAX] + "…"
    return x


def compacte(dossier, budget: int = MAX_DOSSIER, proteges=()):
    """Le dossier ramene sous `budget` caracteres, toujours du JSON entier.

    `proteges` : les cles de premier niveau qu'on ne retire jamais. Le
    dossier peut aussi porter sa propre liste sous `_proteges`.
    """
    garde = set(proteges)
    if isinstance(dossier, dict) and "_proteges" in dossier:
        garde |= set(dossier["_proteges"] or [])
        dossier = {k: v for k, v in dossier.items() if k != "_proteges"}
    if _taille(dossier) <= budget:
        return dossier
    x = json.loads(json.dumps(dossier, ensure_ascii=False, default=str))
    if not isinstance(x, dict):
        return x
    # Une section protegee n'est ni retiree ni raccourcie : le
    # portefeuille arrive entier, ligne par ligne.
    for n in LISTE_MAX:
        x = {k: (v if k in garde else _raccourcit(v, n)) for k, v in x.items()}
        if _taille(x) <= budget:
            return x
    omis = []
    while _taille(x) > budget:
        candidats = [k for k in x if k not in garde and k != "_omis"]
        if not candidats:
            break
        k = max(candidats, key=lambda k: _taille(x[k]))
        x.pop(k)
        omis.append(k)
        x["_omis"] = omis
    if _taille(x) > budget:
        # Dernier recours, et dit : meme les sections protegees depassent.
        x = _raccourcit(x, LISTE_MAX[0])
        x["_omis"] = omis + ["listes au-delà de "
                             f"{LISTE_MAX[0]} éléments"]
    return x


APPELS = {"anthropic": _anthropic, "openai": _openai}

# Les sections du dossier d'un titre qu'une reduction ne retire jamais :
# les 13 blocs, la revue de sortie, la position detenue, le rappel.
PROTEGES_TITRE = ["ok", "ticker", "cours", "date", "devise", "interet",
                  "revue", "position", "memoire", "profil", "rappel"]

# Une question sur le portefeuille, sans titre nomme.
PORTEFEUILLE = re.compile(
    r"\b(?:portefeuille|mes lignes|mes positions|mes titres|mon compte|"
    r"ibkr|ma position|mes actions)\b")


def disponible() -> bool:
    return etat()["configure"]


def demande(question: str, dossier: dict | None = None,
            historique: list | None = None) -> dict:
    """Une question au modele, avec le dossier de faits en contexte.

    Rend toujours un dictionnaire, jamais une exception : l'appelant a
    deja sa reponse deterministe et ne doit pas tomber parce qu'un
    service distant a hoquete.
    """
    c = _config()
    f = c.get("fournisseur", "anthropic")
    cle = (c.get("cles") or {}).get(f, "")
    if not cle:
        return {"ok": False, "configure": False,
                "erreur": "Aucune clé enregistrée. Le programme n'en "
                          "embarque aucune et ne peut pas en fabriquer : "
                          "il faut la vôtre, prise chez "
                          + FOURNISSEURS.get(f, {}).get("ou", "le fournisseur")
                          + "."}

    bloc, envoye = "", None
    if dossier:
        envoye = compacte(dossier)
        bloc = json.dumps(envoye, ensure_ascii=False, indent=1, default=str)
        bloc = f"<dossier>\n{bloc}\n</dossier>\n\n"

    msgs = []
    for h in (historique or [])[-10:]:
        if (h.get("role") in ("user", "assistant")
                and isinstance(h.get("content"), str)):
            msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user",
                 "content": bloc + "<question>\n" + question
                            + "\n</question>"})

    try:
        texte, sources = APPELS[f](msgs, c["modele"], cle)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "configure": True,
                "erreur": explique_erreur(f, exc.code, _corps_erreur(exc),
                                          c["modele"])}
    except Exception as exc:
        return {"ok": False, "configure": True,
                "erreur": f"{type(exc).__name__} : {exc}"}

    # Les chiffres se verifient contre ce qui a ete ENVOYE, pas contre le
    # dossier complet : une valeur que le modele n'a jamais recue ne peut
    # pas « justifier » un chiffre qu'il ecrit.
    return {"ok": True, "configure": True, "fournisseur": f,
            "modele": c["modele"], "texte": texte, "sources": sources,
            "omis": (envoye or {}).get("_omis", []),
            "chiffres": verifie_chiffres(texte, envoye or {}, question)}


# ---------------------------------------------------------------------
# Le majordome complet : les faits, puis la prose
# ---------------------------------------------------------------------

def repond(question: str, existe=None, defaut_ticker: str = "",
           historique: list | None = None, avec_modele: bool = True) -> dict:
    """La reponse du majordome : deterministe d'abord, modele ensuite.

    L'ordre n'est pas un detail d'implementation, c'est le contrat.
    `dossier.py` calcule les faits avant tout appel reseau, et ils sont
    rendus quoi qu'il advienne du modele. Si la cle manque, si l'API
    tombe, si la reponse part de travers : les faits restent affiches.

    Le modele n'ajoute que de la prose par-dessus des faits deja la.
    """
    from . import dossier as ds

    if existe is None:
        from . import cache as ch

        def existe(t):
            d = ch.charge(t, annees=1)
            return d is not None and len(d) > 30

    inten, tk = ds.comprend(question, existe, defaut_ticker or None)
    # « Mon portefeuille IBKR » : ici IBKR est le courtier, pas le titre
    # Interactive Brokers — qui existe bel et bien sur Yahoo.
    pf_demande = bool(PORTEFEUILLE.search(ds.normalise(question)))
    if pf_demande and tk == "IBKR":
        tk = defaut_ticker or None
    faits, deterministe = None, None
    if tk:
        try:
            faits = ds.constitue(tk)
            deterministe = ds.repond(question, faits)
            # Ce qui ne doit jamais tomber quand le dossier est reduit.
            faits = {**faits, "_proteges": PROTEGES_TITRE}
        except Exception as exc:
            deterministe = {"ok": False, "ticker": tk,
                            "erreur": f"{type(exc).__name__} : {exc}"}
    if pf_demande:
        # « Que penses-tu de mon portefeuille ? » : le dossier porte les
        # lignes, COMPTEES par le programme comme sur la page BRAIN 2.0.
        from . import brain2 as b2
        try:
            pf = b2.faits_portefeuille()
            if not tk:
                deterministe = {"ok": True, "ticker": "PORTEFEUILLE",
                                "intention": "portefeuille",
                                "titre": "VOS LIGNES, COMPTÉES",
                                "lignes": b2.lignes_portefeuille(pf),
                                "rappel": pf.get("rappel")}
                inten = "portefeuille"
            faits = b2.contexte(question, faits, pf)
        except Exception as exc:
            if not tk:
                deterministe = {"ok": False, "ticker": "PORTEFEUILLE",
                                "erreur": f"{type(exc).__name__} : {exc}"}

    out = {"ok": True, "question": question, "intention": inten,
           "ticker": tk, "faits": deterministe, "rappel": ds.RAPPEL}

    if not avec_modele or not disponible():
        out["modele"] = {"ok": False, "configure": disponible(),
                         "erreur": "cerveau non configuré"}
        return out

    out["modele"] = demande(question, faits, historique)
    return out
