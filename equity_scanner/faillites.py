"""Les societes cotees en faillite, et ce qui a suivi.

A QUOI CA REPOND

« Scanne toutes les entreprises US et europeennes en faillite qui ont des
plans de relance, pour faire comme le trader japonais qui gagne beaucoup
d'argent. » La liste se dresse avec des FAITS publics ; le « potentiel »
ne se mesure pas, et rien ici ne le chiffre.

D'OU VIENNENT LES FAITS

Etats-Unis — la SEC. Toute societe cotee qui se place sous la protection
du tribunal des faillites doit le declarer dans un formulaire 8-K, a
l'item 1.03 (« Bankruptcy or Receivership »). La recherche plein texte
d'EDGAR rend ces depots, avec les items declares. On en tire, societe par
societe : la date du depot, la confirmation d'un plan de reorganisation
par le tribunal quand un 8-K la rapporte, et l'item 3.03 (« Material
Modification to Rights of Security Holders ») quand il est declare — c'est
le plus souvent a l'entree en vigueur du plan, et c'est la que se decide
ce que deviennent les actions existantes. Chaque ligne porte le lien vers
le depot : c'est lui qui fait foi.

Europe — il n'existe pas de registre public unique qui dise quelles
societes COTEES sont en procedure (sauvegarde, redressement, plan). En
France, les jugements paraissent au BODACC, en Allemagne sur
insolvenzbekanntmachungen.de, mais sans lien avec la cote. Les titres
europeens s'ajoutent donc a la main, avec une note ; le programme leur
applique les memes mesures de cours.

CE QUE LE PROGRAMME REFUSE, ET POURQUOI

* Un classement par « potentiel » ou un « banger » : aucune hypothese sur
  ces titres n'a ete specifiee ni testee. Les tris portent chacun sur un
  seul fait — la date du depot, la variation depuis, le nom.
* La liste des gagnants seule. On entend parler du titre qui a ete
  multiplie par dix, pas des dizaines qui ont fini a zero. La liste est
  COMPLETE, et le compte de ce qui a suivi l'accompagne — y compris les
  titres sans cotation, le plus souvent radies, qu'oublier flatterait le
  tableau.
* L'idee que « l'entreprise se relance » veut dire « l'action se
  relance ». Dans un Chapter 11, le plan decide ce que recoivent les
  anciens actionnaires, et c'est souvent rien : le capital de la societe
  reorganisee va aux creanciers.

    py -m equity_scanner.faillites
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RECHERCHE = "https://efts.sec.gov/LATEST/search-index"
DOCUMENT = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/{fichier}"
FICHE = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
         "&CIK={cik}&type=8-K&dateb=&owner=include&count=40")

ITEM_FAILLITE = "1.03"      # Bankruptcy or Receivership
ITEM_DROITS = "3.03"        # Material Modification to Rights of Security Holders

MOIS = 18                   # la fenetre regardee, en mois
PAGE = 100                  # la SEC rend cent resultats par page
PAGES_MAX = 30              # 3 000 depots au plus ; au-dela, on le DIT
CACHE_HEURES = 12

# La requete des depots de faillite, et celle des plans confirmes. Ce sont
# des phrases EXACTES des depots, pas des mots-cles.
Q_FAILLITE = '"Item 1.03"'
Q_PLAN = '"order confirming" "plan of reorganization"'

# Un seul fait par tri. Aucun tri sur une combinaison.
TRIS = ("date", "variation", "nom")

CACHE = Path(".bruce_cache") / "faillites-us.json"
EUROPE = Path.home() / ".carruos" / "restructurations-europe.json"

RAPPEL_ACTIONS = (
    "Dans un Chapter 11, c'est le plan qui décide ce que deviennent les "
    "actions existantes — et c'est souvent rien : le capital de la société "
    "réorganisée va aux créanciers. L'entreprise peut se relancer sans que "
    "l'action que vous achetez aujourd'hui en profite. Lisez le dépôt avant "
    "tout ordre ; il fait foi, pas cette page.")
RAPPEL_COMPTE = (
    "On entend parler du titre multiplié par dix, pas de ceux qui ont fini "
    "à zéro. La liste est complète, et le compte de ce qui a suivi "
    "l'accompagne — y compris les titres sans cotation, le plus souvent "
    "radiés.")
RAPPEL_AVIS = (
    "Aucun classement de « potentiel » : aucune hypothèse sur ces titres "
    "n'a été spécifiée ni testée. Ce n'est pas un avis.")
RAPPEL_FILIALE = (
    "L'item 1.03 se déclare aussi quand c'est une FILIALE qui se place sous "
    "la protection du tribunal, ou pour une restructuration de dette sans "
    "effet sur le capital. « Plan confirmé » signifie qu'un 8-K postérieur "
    "cite l'ordonnance de confirmation ; « droits modifiés » (item 3.03), "
    "que le dépôt déclare une modification des droits des porteurs — le "
    "plus souvent, l'annulation des anciennes actions. Le lien fait foi.")
RAPPEL_EUROPE = (
    "Il n'existe pas de registre européen qui dise quelles sociétés COTÉES "
    "sont en procédure. En France, les jugements (sauvegarde, redressement, "
    "plans) paraissent au BODACC ; en Allemagne, sur "
    "insolvenzbekanntmachungen.de. Ajoutez ici les titres que vous suivez : "
    "ils reçoivent les mêmes mesures de cours.")


class RefusSEC(RuntimeError):
    pass


# ---------------------------------------------------------------------
# La recherche EDGAR
# ---------------------------------------------------------------------

def _entetes(contact: str = "") -> dict:
    # La SEC demande que chaque programme se nomme. Une adresse de contact
    # n'est ajoutee que si le proprietaire l'a donnee lui-meme.
    ua = "CARRUOS-ALICE/1.0 (outil personnel)"
    if contact:
        ua += f" {contact}"
    return {"User-Agent": ua, "Accept": "application/json"}


def _contact() -> str:
    try:
        return json.loads((Path.home() / ".carruos" / "sec.json")
                          .read_text(encoding="utf-8")).get("contact", "")
    except Exception:
        return ""


def _get(params: dict) -> dict:
    url = RECHERCHE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_entetes(_contact()))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise RefusSEC(
                "La SEC a refusé la requête (code %d). Elle demande que "
                "chaque programme se présente avec une adresse de contact : "
                "indiquez la vôtre dans le champ « contact SEC » de la page, "
                "puis ACTUALISER." % exc.code) from exc
        raise


def recherche(q: str, debut: str, fin: str, getter=None,
              infos: dict | None = None) -> list[dict]:
    """Tous les 8-K qui contiennent la phrase `q` entre deux dates.

    `infos` recoit le total annonce par la SEC et le nombre recu : au-dela
    de PAGES_MAX pages, la liste serait TRONQUEE, et la page doit le dire
    plutot que de presenter comme complete une liste qui ne l'est pas."""
    getter = getter or _get
    out, depart, total = [], 0, 0
    for _ in range(PAGES_MAX):
        j = getter({"q": q, "forms": "8-K", "dateRange": "custom",
                    "startdt": debut, "enddt": fin, "from": depart})
        h = (j or {}).get("hits") or {}
        lot = h.get("hits") or []
        out += lot
        total = ((h.get("total") or {}).get("value")) or 0
        depart += len(lot)
        if not lot or depart >= total:
            break
    if infos is not None:
        infos["total"], infos["recu"] = max(total, len(out)), len(out)
    return out


_NOM = re.compile(r"^(?P<nom>.*?)\s*(?:\((?P<tk>[A-Z0-9.,\s-]+)\))?\s*"
                  r"\(CIK\s*(?P<cik>\d+)\)\s*$")


def lit_nom(affiche: str) -> dict:
    """« QVC INC  (QVCCQ, QVCDQ)  (CIK 0001254699) » ->
    nom, tickers, cik. Une societe sans ticker cote en garde une liste vide."""
    m = _NOM.match(affiche or "")
    if not m:
        return {"nom": (affiche or "").strip(), "tickers": [], "cik": ""}
    tks = [t.strip() for t in (m.group("tk") or "").split(",") if t.strip()]
    return {"nom": m.group("nom").strip(), "tickers": tks,
            "cik": m.group("cik").lstrip("0")}


def _lien(hit: dict, cik: str) -> str:
    adsh, _, fichier = (hit.get("_id") or "").partition(":")
    if not adsh or not fichier or not cik:
        return FICHE.format(cik=cik)
    return DOCUMENT.format(cik=cik, adsh=adsh.replace("-", ""),
                           fichier=fichier)


def regroupe(faillite: list[dict], plans: list[dict]) -> list[dict]:
    """Societe par societe. Ne garde que celles dont un depot declare
    l'item 1.03 : une phrase trouvee dans un autre contexte ne fait pas
    une faillite.

    Un depot (un numero d'enregistrement) compte une fois, meme quand la
    recherche le rend par son 8-K ET par ses pieces jointes ; le lien
    retenu est celui du 8-K lui-meme."""
    soc: dict = {}
    for source, hits in (("faillite", faillite), ("plan", plans)):
        for h in hits:
            s = h.get("_source") or {}
            items = list(s.get("items") or [])
            noms = s.get("display_names") or []
            ciks = s.get("ciks") or []
            lieux = s.get("biz_locations") or [""]
            sics = s.get("sics") or [""]
            adsh = (s.get("adsh") or (h.get("_id") or "").partition(":")[0])
            principal = str(s.get("file_type") or "").upper().startswith("8-K")
            for k, cik_brut in enumerate(ciks):
                cik = str(cik_brut).lstrip("0")
                info = lit_nom(noms[k] if k < len(noms) else "")
                e = soc.setdefault(cik, {
                    "cik": cik, "nom": info["nom"], "tickers": [],
                    "lieu": lieux[min(k, len(lieux) - 1)],
                    "sic": sics[min(k, len(sics) - 1)],
                    "depots": {}, "fiche": FICHE.format(cik=cik)})
                for t in info["tickers"]:
                    if t not in e["tickers"]:
                        e["tickers"].append(t)
                d = e["depots"].get(adsh)
                if d is None:
                    d = e["depots"][adsh] = {
                        "date": s.get("file_date", ""), "items": items,
                        "lien": _lien(h, cik), "principal": principal,
                        "cite_plan": False}
                elif principal and not d["principal"]:
                    d["lien"], d["principal"] = _lien(h, cik), True
                if source == "plan":
                    d["cite_plan"] = True
    out = []
    for e in soc.values():
        depots = sorted(e["depots"].values(), key=lambda x: x["date"])
        f = [x["date"] for x in depots if ITEM_FAILLITE in x["items"]]
        if not f:
            continue
        e["premier_depot"], e["dernier_depot"] = f[0], f[-1]
        # La confirmation du plan : un 8-K item 1.03 qui cite l'ordonnance
        # de confirmation, et qui SUIT le premier depot de faillite. Le
        # depot qui annonce la faillite cite souvent la confirmation qu'il
        # va DEMANDER : le compter ferait d'une requete un fait accompli.
        conf = [x for x in depots if x["cite_plan"]
                and ITEM_FAILLITE in x["items"] and x["date"] > f[0]]
        e["plan_confirme"] = ({"date": conf[-1]["date"],
                               "lien": conf[-1]["lien"]} if conf else None)
        droits = [x for x in depots if ITEM_DROITS in x["items"]]
        e["droits_modifies"] = ({"date": droits[0]["date"],
                                 "lien": droits[0]["lien"]}
                                if droits else None)
        e["depots"] = [{"date": x["date"], "items": x["items"],
                        "lien": x["lien"]} for x in depots]
        out.append(e)
    out.sort(key=lambda e: (e["premier_depot"], e["nom"]), reverse=True)
    return out


# ---------------------------------------------------------------------
# Les cours : ce qui a suivi
# ---------------------------------------------------------------------

def _date(x: str):
    try:
        return _dt.date.fromisoformat(str(x)[:10])
    except (ValueError, TypeError):
        return None


def _mesure(tk: str, d, t0, coupe) -> dict | None:
    if d is None or "close" not in getattr(d, "columns", []):
        return None
    c = d["close"].dropna()
    c = c[c > 0]
    if coupe is not None:
        c = c[c.index.date < coupe]
    if len(c) < 2:
        return None
    out = {"ticker": tk, "dernier": round(float(c.iloc[-1]), 4),
           "date": str(c.index[-1].date())}
    if coupe is not None:
        out["coupe"] = coupe.isoformat()
    if t0 is not None:
        avant, apres = c[c.index.date < t0], c[c.index.date >= t0]
        if len(avant):
            p0 = float(avant.iloc[-1])
            out["avant"] = round(p0, 4)
            out["date_avant"] = str(avant.index[-1].date())
        # Une variation demande un cours AVANT et un cours APRES. Un item
        # 3.03 le jour meme du depot ne laisse aucun « apres » : ecrire 0 %
        # rangerait parmi les titres stables une action peut-etre annulee.
        if len(avant) and len(apres):
            out["variation"] = round((float(c.iloc[-1]) / p0 - 1) * 100, 1)
            out["plus_haut_depuis"] = round(float(apres.max()), 4)
            out["plus_haut_pct"] = round(
                (float(apres.max()) / p0 - 1) * 100, 1)
    if "volume" in d.columns:
        v = (d["close"] * d["volume"]).dropna()
        if coupe is not None:
            v = v[v.index.date < coupe]
        v = v.tail(20)
        if len(v):
            out["volume_dollar_20j"] = round(float(v.mean()))
    return out


def cours(tickers: list[str], depuis: str, charge,
          coupe: str | None = None) -> dict:
    """Le cours avant le depot, le dernier, et entre les deux.

    Une societe en faillite change souvent de ticker (le suffixe Q des
    titres en faillite) : chaque ticker est essaye, et celui qui couvre
    AVANT et APRES le depot l'emporte, puis le plus recent.

    `coupe` est la date de l'item 3.03. Au-dela, le cours peut etre celui
    d'actions NOUVELLES, emises aux creanciers, que l'ancien actionnaire
    n'a pas forcement recues : la mesure s'arrete a la veille. Sans
    aucune donnee, on le DIT."""
    t0, fin = _date(depuis), _date(coupe) if coupe else None
    vus = []
    for tk in tickers or []:
        try:
            m = _mesure(tk, charge(tk), t0, fin)
        except Exception:
            m = None
        if m is not None:
            vus.append(m)
    if vus:
        vus.sort(key=lambda m: (m.get("variation") is not None, m["date"]),
                 reverse=True)
        return vus[0]
    return {"ticker": (tickers or [""])[0], "absent": True,
            "sans_ticker": not tickers}


def compte(societes: list[dict]) -> dict:
    """Le compte COMPLET de ce qui a suivi, sans oublier ceux qui n'ont
    plus de cours : ce sont souvent les pires. Les cases se partagent le
    total, sans reste — la page le verifie."""
    n = len(societes)
    c = [s.get("cours") or {} for s in societes]
    var = [x["variation"] for x in c
           if not x.get("absent") and x.get("variation") is not None]
    sans_ticker = sum(1 for s in societes if not s.get("tickers"))
    sans_cours = sum(1 for s, x in zip(societes, c)
                     if s.get("tickers") and x.get("absent"))
    return {
        "total": n,
        "avec_variation": len(var),
        "sans_ticker": sans_ticker,
        "sans_cours": sans_cours,
        "sans_variation": n - len(var) - sans_ticker - sans_cours,
        "sous_moins_90": sum(1 for v in var if v <= -90),
        "entre": sum(1 for v in var if -90 < v <= 0),
        "en_hausse": sum(1 for v in var if v > 0),
        "double": sum(1 for v in var if v >= 100),
        "plan_confirme": sum(1 for s in societes if s.get("plan_confirme")),
        "droits_modifies": sum(1 for s in societes
                               if s.get("droits_modifies")),
    }


# ---------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------

def _charge_lot(tickers: list[str]):
    """Tous les cours d'un coup, en parallele, par le cache du programme.
    Un titre que les donnees ne connaissent pas (souvent : radie) leve
    KeyError, et `cours` le range dans « sans cours »."""
    from . import cache as ch
    series, _echecs = ch.charge_lot(tickers, annees=3)

    def charge(tk):
        return series[tk]
    return charge


def liste_us(force: bool = False, getter=None, charge=None,
             aujourdhui: _dt.date | None = None) -> dict:
    """Les faillites US des MOIS derniers mois, avec leurs cours."""
    fin = aujourdhui or _dt.date.today()
    debut = fin - _dt.timedelta(days=int(MOIS * 30.5))
    brut = None
    if not force and getter is None:
        try:
            if time.time() - CACHE.stat().st_mtime < CACHE_HEURES * 3600:
                brut = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            brut = None
    if brut is None:
        i_f, i_p = {}, {}
        try:
            f = recherche(Q_FAILLITE, debut.isoformat(), fin.isoformat(),
                          getter, i_f)
            p = recherche(Q_PLAN, debut.isoformat(), fin.isoformat(),
                          getter, i_p)
        except RefusSEC as exc:
            return {"ok": False, "erreur": str(exc), "contact_demande": True}
        except Exception as exc:
            return {"ok": False, "erreur": "La SEC n'a pas répondu "
                                           f"({type(exc).__name__})."}
        tronque = [f"{nom} : {i['recu']} dépôts lus sur {i['total']}"
                   for nom, i in (("faillites", i_f), ("plans", i_p))
                   if i.get("recu", 0) < i.get("total", 0)]
        brut = {"quand": _dt.datetime.now().isoformat(timespec="minutes"),
                "debut": debut.isoformat(), "fin": fin.isoformat(),
                "tronque": tronque, "societes": regroupe(f, p)}
        if getter is None:
            try:
                CACHE.parent.mkdir(exist_ok=True)
                CACHE.write_text(json.dumps(brut, ensure_ascii=False),
                                 encoding="utf-8")
            except OSError:
                pass
    if charge is None:
        charge = _charge_lot([t for s in brut["societes"]
                              for t in s["tickers"]])
    for s in brut["societes"]:
        s["cours"] = cours(s["tickers"], s["premier_depot"], charge,
                           (s.get("droits_modifies") or {}).get("date"))
    return {"ok": True, **brut, "compte": compte(brut["societes"]),
            "rappels": [RAPPEL_ACTIONS, RAPPEL_COMPTE, RAPPEL_FILIALE,
                        RAPPEL_AVIS],
            "tris": list(TRIS)}


def europe(charge=None, fichier: Path | None = None) -> dict:
    f = fichier or EUROPE
    try:
        lignes = json.loads(f.read_text(encoding="utf-8"))
        lignes = lignes if isinstance(lignes, list) else []
    except Exception:
        lignes = []
    if charge is None:
        charge = _charge_lot([l.get("ticker", "") for l in lignes])
    for l in lignes:
        l["cours"] = cours([l.get("ticker", "")], l.get("depuis", ""), charge)
    return {"lignes": lignes, "rappel": RAPPEL_EUROPE}


def europe_pose(ticker: str, note: str = "", depuis: str = "",
                retire: bool = False, fichier: Path | None = None) -> dict:
    f = fichier or EUROPE
    tk = (ticker or "").strip().upper()
    if not tk or len(tk) > 20 or not re.fullmatch(r"[A-Z0-9.^=-]+", tk):
        return {"ok": False, "erreur": "ticker illisible : ORP.PA, VAR1.DE"}
    if depuis:
        try:
            _dt.date.fromisoformat(depuis)
        except ValueError:
            return {"ok": False, "erreur": "date illisible (AAAA-MM-JJ)"}
    try:
        lignes = json.loads(f.read_text(encoding="utf-8"))
        lignes = lignes if isinstance(lignes, list) else []
    except Exception:
        lignes = []
    lignes = [l for l in lignes if l.get("ticker") != tk]
    if not retire:
        lignes.append({"ticker": tk, "note": (note or "").strip()[:300],
                       "depuis": depuis})
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(lignes, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return {"ok": True, "n": len(lignes)}


def pose_contact(contact: str) -> dict:
    """L'adresse que la SEC demande, donnee par le proprietaire lui-meme."""
    c = (contact or "").strip()[:120]
    f = Path.home() / ".carruos" / "sec.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"contact": c}), encoding="utf-8")
    return {"ok": True}


def main() -> None:
    r = liste_us(force=True)
    if not r.get("ok"):
        print("  " + r.get("erreur", "échec"))
        return
    for s in r["societes"]:
        c = s.get("cours") or {}
        v = ("sans cours" if c.get("absent") else
             f"{c.get('variation', '?')} % depuis le dépôt")
        print(f"  {s['premier_depot']}  {s['nom'][:40]:<40} "
              f"{','.join(s['tickers'])[:14]:<14} {v}")
    k = r["compte"]
    print(f"\n  {k['total']} sociétés : {k['sous_moins_90']} à −90 % ou pire, "
          f"{k['en_hausse']} en hausse depuis le dépôt, {k['sans_cours']} "
          f"sans cours.")
    for t in r["rappels"]:
        print("\n  " + t)


if __name__ == "__main__":
    main()
