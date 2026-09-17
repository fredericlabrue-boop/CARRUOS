"""Recherche de ticker par nom d'entreprise.

    py -m equity_scanner.find lvmh
    py -m equity_scanner.find "banco santander"
    py -m equity_scanner.find nvidia

Deux sources :
  1. l'annuaire Yahoo Finance — GRATUIT, sans cle, et c'est exactement la
     meme base que celle ou Bruce va chercher les cours ;
  2. Alpha Vantage en secours si une cle est fournie.

Le ticker affiche est directement utilisable dans l'option 1 de Bruce.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request

YAHOO = "https://query2.finance.yahoo.com/v1/finance/search"
# Sans User-Agent, Yahoo renvoie 403.
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# suffixe -> (place, pays, devise)
TABLE = [
    ("",     "USA",         "Etats-Unis",   "USD"),
    (".PA",  "Paris",       "France",       "EUR"),
    (".AS",  "Amsterdam",   "Pays-Bas",     "EUR"),
    (".BR",  "Bruxelles",   "Belgique",     "EUR"),
    (".LS",  "Lisbonne",    "Portugal",     "EUR"),
    (".IR",  "Dublin",      "Irlande",      "EUR"),
    (".DE",  "Xetra",       "Allemagne",    "EUR"),
    (".F",   "Francfort",   "Allemagne",    "EUR"),
    (".MI",  "Milan",       "Italie",       "EUR"),
    (".MC",  "Madrid",      "Espagne",      "EUR"),
    (".VI",  "Vienne",      "Autriche",     "EUR"),
    (".HE",  "Helsinki",    "Finlande",     "EUR"),
    (".ST",  "Stockholm",   "Suede",        "SEK"),
    (".OL",  "Oslo",        "Norvege",      "NOK"),
    (".CO",  "Copenhague",  "Danemark",     "DKK"),
    (".L",   "Londres",     "Royaume-Uni",  "GBp"),
    (".SW",  "Zurich",      "Suisse",       "CHF"),
    (".TO",  "Toronto",     "Canada",       "CAD"),
    (".V",   "TSX Venture", "Canada",       "CAD"),
    (".HK",  "Hong Kong",   "Hong Kong",    "HKD"),
    (".T",   "Tokyo",       "Japon",        "JPY"),
    (".AX",  "Sydney",      "Australie",    "AUD"),
    (".NZ",  "Auckland",    "Nouvelle-Zel", "NZD"),
    (".SI",  "Singapour",   "Singapour",    "SGD"),
    (".KS",  "Seoul",       "Coree du Sud", "KRW"),
    (".TW",  "Taipei",      "Taiwan",       "TWD"),
    (".NS",  "Mumbai NSE",  "Inde",         "INR"),
    (".BO",  "Mumbai BSE",  "Inde",         "INR"),
    (".SS",  "Shanghai",    "Chine",        "CNY"),
    (".SZ",  "Shenzhen",    "Chine",        "CNY"),
    (".SA",  "Sao Paulo",   "Bresil",       "BRL"),
    (".MX",  "Mexico",      "Mexique",      "MXN"),
    (".JO",  "Johannesburg","Afrique du S", "ZAR"),
]
PLACES = {s: p for s, p, _, _ in TABLE if s}
DEVISES = {s: d for s, _, _, d in TABLE if s}


def place(ticker: str) -> str:
    for suf in sorted(PLACES, key=len, reverse=True):
        if ticker.endswith(suf):
            return PLACES[suf]
    return "USA"


def devise(ticker: str) -> str:
    for suf in sorted(DEVISES, key=len, reverse=True):
        if ticker.endswith(suf):
            return DEVISES[suf]
    return "USD"


def memo() -> None:
    print("\n  MEMO DES PLACES BOURSIERES — suffixe a coller apres le ticker\n")
    print(f"  {'SUFFIXE':<10}{'PLACE':<15}{'PAYS':<16}DEVISE")
    print("  " + "-" * 52)
    for suf, pl, pays, dev in TABLE:
        print(f"  {(suf or '(aucun)'):<10}{pl:<15}{pays:<16}{dev}")
    print("""
  EXEMPLES
    MC.PA      LVMH a Paris            SAP.DE     SAP a Xetra
    ASML.AS    ASML a Amsterdam        ENI.MI     ENI a Milan
    ITX.MC     Inditex a Madrid        NESN.SW    Nestle a Zurich
    NVDA       Nvidia aux Etats-Unis   SHEL.L     Shell a Londres

  PIEGE A CONNAITRE — Londres cote en PENCE (GBp), pas en livres.
  Un titre affiche a 2500 vaut 25 livres. Ton calcul de position serait
  faux d'un facteur 100. Bruce t'avertit si tu scannes un ticker en .L.

  Une meme societe peut etre cotee sur plusieurs places. Prends TOUJOURS
  la cotation principale (celle du pays du siege) : c'est la plus liquide,
  donc celle dont le volume et le RVOL ont un sens.
""")


def chercher_yahoo(terme: str, limite: int = 10) -> list[dict]:
    # Un code Refinitiv ou Bloomberg ne rend rien chez Yahoo : on le
    # traduit d'abord. "SASY" -> "SAN.PA".
    try:
        from .resolve import par_alias
        vrai = par_alias(terme)
    except Exception:
        vrai = None
    if vrai:
        terme = vrai
    url = f"{YAHOO}?{urllib.parse.urlencode({'q': terme, 'quotesCount': limite, 'newsCount': 0})}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    out = []
    for q in data.get("quotes", []):
        tk = q.get("symbol")
        if not tk:
            continue
        out.append({
            "ticker": tk,
            "nom": q.get("longname") or q.get("shortname") or "",
            "type": (q.get("quoteType") or "").upper(),
            "place": place(tk),
            "bourse": q.get("exchDisp") or "",
        })
    return out


def afficher(res: list[dict]) -> None:
    if not res:
        print("\n  Aucun resultat.")
        print("  Si la societe n'est pas cotee en bourse (SpaceX, OpenAI, Michelin")
        print("  avant introduction...), il n'existe aucun ticker : pas de cours,")
        print("  donc pas d'analyse technique possible.\n")
        return
    print(f"\n  {'TICKER':<14}{'TYPE':<10}{'PLACE':<13}{'DEVISE':<8}NOM")
    print("  " + "-" * 76)
    for r in sorted(res, key=lambda x: (x["type"] != "EQUITY", x["place"])):
        print(f"  {r['ticker']:<14}{r['type']:<10}{r['place']:<13}"
              f"{devise(r['ticker']):<8}{r['nom'][:30]}")
    actions = [r for r in res if r["type"] in ("EQUITY", "ETF")]
    if actions:
        print(f"\n  A utiliser dans l'option 1 de Bruce : {actions[0]['ticker']}")
    print()


def main() -> None:
    p = argparse.ArgumentParser(description="Trouve le ticker d'une societe cotee")
    p.add_argument("terme", nargs="*", help="nom de la societe")
    p.add_argument("--memo", action="store_true",
                   help="affiche le tableau des places et suffixes")
    p.add_argument("--av-key", default=None, help="cle Alpha Vantage (secours)")
    a = p.parse_args()
    if a.memo or not a.terme:
        memo()
        if not a.terme:
            return
    terme = " ".join(a.terme)

    try:
        res = chercher_yahoo(terme)
    except Exception as exc:
        print(f"  Annuaire Yahoo indisponible ({type(exc).__name__}).")
        res = []

    if not res and a.av_key:
        from .news import chercher_symbole
        res = [{"ticker": m["symbole"], "nom": m["nom"], "type": "",
                "place": m["region"], "bourse": ""}
               for m in chercher_symbole(a.av_key, terme)]

    afficher(res)


if __name__ == "__main__":
    main()
