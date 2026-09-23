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
        "modele": "gpt-5.6-sol",
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
Frédéric. Tu parles français, avec calme et précision, et tu peux discuter de
n'importe quel sujet. En finance et en marchés, tu es rigoureux plutôt que
confiant.

CE QUE TU REÇOIS
Un dossier de faits déjà calculés par CARRUOS, entre balises <dossier>. Tu ne
vois jamais les cours eux-mêmes : tu ne peux pas « lire le graphique », tu n'en
as pas. Tout ce que tu sais du titre est dans ce dossier.

LA RÈGLE QUI PRIME SUR TOUTES LES AUTRES
N'écris AUCUN nombre qui ne soit pas dans le dossier ou dans la question. Pas un
cours, pas un objectif, pas un pourcentage, pas une probabilité, pas un
rendement, pas une date de sortie. Si un chiffre manque, dis qu'il manque. Chaque
nombre de ta réponse est vérifié contre le dossier et ceux qui n'y sont pas
seront signalés au lecteur, donc un chiffre inventé ne passera pas inaperçu — il
te décrédibilisera.

CE QUE CARRUOS N'AFFICHE JAMAIS, ET TOI NON PLUS
- Un avis « achète » ou « vends », même quand la question en demande un. Réponds
  par le compte : combien des 13 blocs passent, lesquels manquent et de combien,
  quelles conditions de sortie sont actives. « Trois conditions sur quatre sont
  actives » se vérifie ; « vends » est une opinion déguisée.
- Un pourcentage seul de « chances de gagner ». Toujours l'intervalle de
  confiance et le nombre de trades, tels qu'ils sont dans le dossier.
- Ce qu'une figure de chandelier « annonce ». Un marteau est une forme
  géométrique. Le dossier dit ce qu'elle a été suivie de sur CE titre et le
  compare au taux de base du titre ; s'il dit « indiscernable du hasard », dis-le
  aussi. Rappelle, quand le sujet vient, qu'il y a environ 72 mesures par titre
  et donc environ 4 « écarts nets » attendus par le seul hasard.
- Une prédiction de prix, une cible, un niveau de sortie deviné.
- Un score composite, un verdict directionnel, un « ratio risque / gain » (la
  spécification n'a aucun objectif de gain : elle dit « aucun take-profit »).
- Un gain espéré en euros : aucune hypothèse n'a passé sa Phase 0.
- Un chiffrage du risque géopolitique. L'actualité est du contexte à vérifier
  avant de passer un ordre, elle n'entre dans aucune règle.
- Une « meilleure heure pour acheter ». Le programme n'a aucune donnée intraday.

CE QUE TU FAIS TRÈS BIEN
Expliquer. Relier ce que le dossier contient. Dire ce qui manque et pourquoi ça
manque. Poser la question que Frédéric n'a pas posée et qui compte. Nommer ce
qui invaliderait une lecture. Répondre franchement quand la réponse est « le
dossier ne le dit pas ».

Si la question n'est pas financière, réponds normalement, sans dossier, sans
faire semblant d'en avoir un.

FORME
Des phrases, pas de tableau. Court quand c'est court. Tu peux terminer par ce
qu'il faudrait mesurer pour aller plus loin."""


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
    for var, cle in (("CARRUOS_ANTHROPIC_API_KEY", "anthropic"),
                     ("CARRUOS_OPENAI_API_KEY", "openai")):
        v = os.getenv(var)
        if v:
            c.setdefault("cles", {})[cle] = v.strip()
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


def oublie() -> dict:
    """Efface la cle. Il faut pouvoir la retirer aussi simplement qu'on
    l'a mise, sinon on hesite a la mettre."""
    c = _config()
    c.pop("cles", None)
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

    traces, hors = [], []
    for m in _NOMBRE.finditer(reponse or ""):
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

def _poste(url: str, charge: dict, entetes: dict, delai: int = 90) -> dict:
    corps = json.dumps(charge, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=corps, method="POST",
        headers={"Content-Type": "application/json", **entetes})
    with urllib.request.urlopen(req, timeout=delai) as r:
        return json.loads(r.read().decode("utf-8"))


def _anthropic(msgs: list, modele: str, cle: str) -> str:
    d = _poste(FOURNISSEURS["anthropic"]["url"], {
        "model": modele, "max_tokens": 3000,
        "system": CONSIGNE, "messages": msgs,
    }, {"x-api-key": cle, "anthropic-version": "2023-06-01"})
    txt = "\n".join(b.get("text", "") for b in (d.get("content") or [])
                    if b.get("type") == "text").strip()
    if not txt:
        raise RuntimeError((d.get("error") or {}).get("message",
                                                      "réponse vide"))
    return txt


def _openai(msgs: list, modele: str, cle: str) -> str:
    d = _poste(FOURNISSEURS["openai"]["url"], {
        "model": modele, "instructions": CONSIGNE, "input": msgs,
        "max_output_tokens": 3000,
    }, {"Authorization": f"Bearer {cle}"})
    if d.get("output_text"):
        return d["output_text"].strip()
    bouts = []
    for item in d.get("output", []):
        for c in item.get("content", []):
            if c.get("type") in ("output_text", "text"):
                bouts.append(c.get("text", ""))
    txt = "\n".join(bouts).strip()
    if not txt:
        raise RuntimeError("réponse vide")
    return txt


APPELS = {"anthropic": _anthropic, "openai": _openai}


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

    bloc = ""
    if dossier:
        bloc = json.dumps(dossier, ensure_ascii=False, indent=1,
                          default=str)[:MAX_DOSSIER]
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
        texte = APPELS[f](msgs, c["modele"], cle)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:400]
        except Exception:
            detail = str(exc)
        return {"ok": False, "configure": True,
                "erreur": f"{f} a répondu {exc.code} : {detail}"}
    except Exception as exc:
        return {"ok": False, "configure": True,
                "erreur": f"{type(exc).__name__} : {exc}"}

    return {"ok": True, "configure": True, "fournisseur": f,
            "modele": c["modele"], "texte": texte,
            "chiffres": verifie_chiffres(texte, dossier or {}, question)}


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
    faits, deterministe = None, None
    if tk:
        try:
            faits = ds.constitue(tk)
            deterministe = ds.repond(question, faits)
        except Exception as exc:
            deterministe = {"ok": False, "ticker": tk,
                            "erreur": f"{type(exc).__name__} : {exc}"}

    out = {"ok": True, "question": question, "intention": inten,
           "ticker": tk, "faits": deterministe, "rappel": ds.RAPPEL}

    if not avec_modele or not disponible():
        out["modele"] = {"ok": False, "configure": disponible(),
                         "erreur": "cerveau non configuré"}
        return out

    out["modele"] = demande(question, faits, historique)
    return out
