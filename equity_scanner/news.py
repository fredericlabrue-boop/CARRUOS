"""Alpha Vantage : calendrier des resultats + actualites.

Cle gratuite en 30 secondes : https://www.alphavantage.co/support/#api-key

QUOTA GRATUIT : 25 appels par jour. C'est peu, donc la conception en tient
compte :
  - le calendrier des resultats = 1 SEUL appel pour tout le marche US,
    mis en cache 24 h sur le disque ;
  - les actualites = uniquement pour les candidats retenus (5 max).
Soit 6 appels par jour. Tu restes largement dans le quota.

Stdlib uniquement, aucune dependance en plus.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.alphavantage.co/query"
CACHE = Path(".bruce_cache")
QUOTA_JOUR = 25            # limite du plan gratuit Alpha Vantage


def _compteur(incr: int = 0) -> int:
    """Appels consommes aujourd'hui. Sans ce compteur, on epuise le quota
    sans le savoir et les actualites tombent en panne sans explication."""
    f = CACHE / "quota.json"
    j = dt.date.today().isoformat()
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("jour") != j:
            d = {"jour": j, "n": 0}
    except Exception:
        d = {"jour": j, "n": 0}
    if incr:
        d["n"] += incr
        try:
            CACHE.mkdir(exist_ok=True)
            f.write_text(json.dumps(d), encoding="utf-8")
        except Exception:
            pass
    return int(d["n"])


def reste_quota() -> int:
    return max(0, QUOTA_JOUR - _compteur())


def _get(params: dict, timeout: int = 25) -> bytes:
    _compteur(1)
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


# --- Calendrier des resultats ----------------------------------------
def earnings_map(api_key: str, horizon: str = "3month") -> dict[str, dt.date]:
    """Un appel pour tout le marche US. Renvoie {ticker: date de publication}.

    Cache disque valable la journee : relancer Bruce dix fois ne consomme
    qu'un seul appel.
    """
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"earnings-{dt.date.today()}.json"
    if f.exists():
        return {k: dt.date.fromisoformat(v) for k, v in json.loads(f.read_text()).items()}

    raw = _get({"function": "EARNINGS_CALENDAR", "horizon": horizon,
                "apikey": api_key}).decode("utf-8", "replace")
    if "symbol" not in raw[:200].lower():
        raise RuntimeError(f"reponse inattendue d'Alpha Vantage : {raw[:180]}")

    out: dict[str, dt.date] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        tk, d = (row.get("symbol") or "").strip(), (row.get("reportDate") or "").strip()
        if not tk or not d:
            continue
        try:
            date = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if tk not in out or date < out[tk]:
            out[tk] = date

    f.write_text(json.dumps({k: v.isoformat() for k, v in out.items()}))
    return out


def seances_avant(date: dt.date | None) -> int | None:
    """Nombre de seances ouvrees d'ici la publication. None si inconnu."""
    if date is None:
        return None
    today = dt.date.today()
    if date < today:
        return None
    import pandas as pd
    return max(0, len(pd.bdate_range(today, date)) - 1)


# --- Actualites -------------------------------------------------------
def news(api_key: str, ticker: str, limit: int = 4) -> list[dict]:
    """Dernieres actualites d'un titre, avec score de sentiment.

    Ce n'est PAS une regle d'entree : aucun filtre automatique n'est
    applique dessus. C'est un panneau de contexte pour ta verification
    finale avant de passer l'ordre.
    """
    # Chaque ouverture de page graphique brulait un appel sur 25. Cache
    # de 6 h par titre : une dizaine de titres consultes ne coute plus
    # qu'une dizaine d'appels par demi-journee au lieu de cinquante.
    f = CACHE / f"news-{ticker.replace('/', '_').replace('.', '_')}.json"
    try:
        if time.time() - f.stat().st_mtime < 6 * 3600:
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    try:
        data = json.loads(_get({
            "function": "NEWS_SENTIMENT", "tickers": ticker,
            "limit": str(max(limit, 10)), "sort": "LATEST", "apikey": api_key,
        }))
    except Exception as e:
        return [{"titre": f"actualites indisponibles ({type(e).__name__})",
                 "url": "", "source": "", "quand": "", "score": None}]

    # Alpha Vantage ne renvoie pas d'erreur HTTP : il renvoie 200 avec un
    # message dans "Information", "Note" ou "Error Message". Sans ca, on
    # voit "rien a afficher" sans jamais savoir pourquoi.
    for cle_msg in ("Information", "Note", "Error Message"):
        if data.get(cle_msg):
            return [{"titre": str(data[cle_msg])[:300], "url": "",
                     "source": "ALPHA VANTAGE", "quand": "", "score": None,
                     "sujets": "", "erreur": True}]
    if not data.get("feed"):
        return [{"titre": "Alpha Vantage a repondu sans aucune actualite. "
                          "Cle acceptee mais flux vide, ou quota du jour "
                          "epuise (25 appels).",
                 "url": "", "source": "ALPHA VANTAGE", "quand": "",
                 "score": None, "sujets": "", "erreur": True}]

    out = []
    for it in (data.get("feed") or [])[:limit]:
        score = None
        for ts in it.get("ticker_sentiment") or []:
            if ts.get("ticker") == ticker:
                try:
                    score = float(ts.get("ticker_sentiment_score"))
                except (TypeError, ValueError):
                    score = None
        quand = (it.get("time_published") or "")[:8]
        if len(quand) == 8:
            quand = f"{quand[6:8]}/{quand[4:6]}"
        out.append({"titre": (it.get("title") or "")[:130], "url": it.get("url") or "",
                    "source": it.get("source") or "", "quand": quand, "score": score})
    try:
        if out:
            f.parent.mkdir(exist_ok=True)
            f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return out


def monde(api_key: str, limit: int = 12,
          force: bool = False) -> list[dict]:
    """Actualites de marche, tous titres confondus.

    Meme avertissement que pour `news` : rien de tout cela n'entre dans
    une decision. Une information publique est deja dans les cours. C'est
    du contexte pour ta verification avant de passer l'ordre, pas un
    signal.

    Le resultat est mis en cache pour la journee : le quota gratuit est
    de 25 appels, il ne faut pas le bruler sur un rafraichissement.
    """
    # Rafraichissement toutes les 2 heures plutot qu'une fois par jour :
    # cela fait 5 a 8 appels par jour au plus, largement sous le quota de
    # 25, et les actualites sont a jour a chaque ouverture ou presque.
    cache = CACHE / "monde.json"
    try:
        age = time.time() - cache.stat().st_mtime
        if not force and age < 2 * 3600:
            return json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        pass
    try:
        data = json.loads(_get({
            "function": "NEWS_SENTIMENT", "sort": "LATEST",
            "limit": str(max(limit, 20)),
            "topics": ("financial_markets,economy_macro,economy_monetary,"
                       "finance,technology"),
            "apikey": api_key,
        }))
    except Exception as e:
        # `erreur` manquait ici : la page traitait donc « actualites
        # indisponibles » comme un titre de presse ordinaire, et
        # l'affichait entre deux vraies depeches sans rien signaler.
        return [{"titre": f"actualites indisponibles ({type(e).__name__})",
                 "url": "", "source": "", "quand": "", "score": None,
                 "sujets": "", "erreur": True}]
    # Alpha Vantage ne renvoie pas d'erreur HTTP : il renvoie 200 avec un
    # message dans "Information", "Note" ou "Error Message". Sans ca, on
    # voit "rien a afficher" sans jamais savoir pourquoi.
    for cle_msg in ("Information", "Note", "Error Message"):
        if data.get(cle_msg):
            return [{"titre": str(data[cle_msg])[:300], "url": "",
                     "source": "ALPHA VANTAGE", "quand": "", "score": None,
                     "sujets": "", "erreur": True}]
    if not data.get("feed"):
        return [{"titre": "Alpha Vantage a repondu sans aucune actualite. "
                          "Cle acceptee mais flux vide, ou quota du jour "
                          "epuise (25 appels).",
                 "url": "", "source": "ALPHA VANTAGE", "quand": "",
                 "score": None, "sujets": "", "erreur": True}]

    out = []
    for it in (data.get("feed") or [])[:limit]:
        try:
            score = float(it.get("overall_sentiment_score"))
        except (TypeError, ValueError):
            score = None
        q = (it.get("time_published") or "")
        quand = f"{q[6:8]}/{q[4:6]} {q[9:11]}h{q[11:13]}" if len(q) >= 13 else ""
        sujets = ", ".join(s.get("topic", "") for s in (it.get("topics") or [])[:2])
        # Les titres que la SOURCE dit concernes par l'article, et ses
        # themes complets. Ce sont des faits enonces par le fournisseur,
        # pas des interpretations : `veille.py` s'en sert pour rapprocher
        # une actualite des lignes du proprietaire.
        #
        # Le score de sentiment par titre n'est PAS repris. C'est un
        # score composite dont nous ne connaissons pas les poids, et le
        # projet en refuse deja par principe — en importer un d'un
        # fournisseur serait pire, puisqu'il ne serait meme pas
        # verifiable.
        tickers = sorted({(ts.get("ticker") or "").upper()
                          for ts in (it.get("ticker_sentiment") or [])
                          if ts.get("ticker")})
        themes = sorted({s.get("topic", "") for s in (it.get("topics") or [])
                         if s.get("topic")})
        out.append({"titre": (it.get("title") or "")[:150],
                    "url": it.get("url") or "", "source": it.get("source") or "",
                    "quand": quand, "score": score, "sujets": sujets,
                    "tickers": tickers, "themes": themes})
    try:
        if out and not out[0].get("erreur"):
            cache.parent.mkdir(exist_ok=True)
            cache.write_text(json.dumps(out, ensure_ascii=False),
                             encoding="utf-8")
    except Exception:
        pass
    return out


def libelle_sentiment(score: float | None) -> str:
    if score is None:
        return "neutre"
    if score <= -0.35:
        return "tres negatif"
    if score <= -0.15:
        return "negatif"
    if score < 0.15:
        return "neutre"
    if score < 0.35:
        return "positif"
    return "tres positif"


# --- Recherche de symbole ---------------------------------------------
def chercher_symbole(api_key: str, terme: str, limite: int = 6) -> list[dict]:
    """Trouve le ticker exact a partir d'un nom ("LVMH" -> "MC.PA").

    Coute 1 appel du quota. Utilise seulement quand un ticker echoue.
    """
    try:
        data = json.loads(_get({"function": "SYMBOL_SEARCH", "keywords": terme,
                                "apikey": api_key}))
    except Exception:
        return []
    out = []
    for m in (data.get("bestMatches") or [])[:limite]:
        out.append({"symbole": m.get("1. symbol", ""), "nom": m.get("2. name", ""),
                    "region": m.get("4. region", ""), "devise": m.get("8. currency", "")})
    return out
