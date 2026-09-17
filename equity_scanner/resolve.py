"""Resolution de ticker : ISIN, mnemonique Euronext, ou ticker brut.

yfinance ne comprend qu'un seul format : le ticker Yahoo, avec suffixe de
place ("MC.PA"). Ce module traduit ce que tu tapes vers ce format.

Strategie, dans l'ordre du moins cher au plus cher :
  1. tel quel              -> "AAPL", "MC.PA" passent directement
  2. ISIN                  -> table locale, puis annuaire Yahoo
  3. mnemonique sans place  -> essai des suffixes un par un
  4. nom d'entreprise      -> Alpha Vantage SYMBOL_SEARCH (1 appel de quota)

Tout resultat est mis en cache sur disque : la deuxieme fois est instantanee
et ne consomme rien.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CACHE = Path(".bruce_cache") / "symboles.json"

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

# Ordre d'essai des places. Les plus probables pour un francais d'abord.
SUFFIXES = [".PA", ".DE", ".AS", ".MI", ".MC", ".BR", ".L", ".SW", ".LS", ".VI"]

# Prefixe ISIN -> places a tester en priorite. Reduit le nombre d'essais.
PAYS = {
    "FR": [".PA"], "DE": [".DE"], "NL": [".AS"], "IT": [".MI"], "ES": [".MC"],
    "BE": [".BR"], "GB": [".L"], "CH": [".SW"], "PT": [".LS"], "AT": [".VI"],
    "IE": [".L", ".PA"], "FI": [".HE"], "US": [""],
}


def _cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except Exception:
        return {}


def _memoriser(cle: str, valeur: str) -> None:
    CACHE.parent.mkdir(exist_ok=True)
    c = _cache()
    c[cle] = valeur
    CACHE.write_text(json.dumps(c, indent=1, sort_keys=True))


def est_isin(s: str) -> bool:
    return bool(ISIN_RE.match(s.strip().upper()))


def _isin_via_yahoo(isin: str) -> str | None:
    """Annuaire ISIN de yfinance. Non documente et instable selon les
    versions : on echoue en silence plutot que de planter le scan."""
    for chemin, nom in [("yfinance.utils", "get_ticker_by_isin"),
                        ("yfinance.utils", "get_all_by_isin")]:
        try:
            mod = __import__(chemin, fromlist=[nom])
            r = getattr(mod, nom)(isin)
            if isinstance(r, dict):
                r = r.get("symbol") or r.get("Symbol")
            if isinstance(r, str) and r.strip():
                return r.strip().upper()
        except Exception:
            continue
    return None


def candidats(saisie: str) -> list[str]:
    """Liste ordonnee de tickers Yahoo a essayer pour cette saisie."""
    s = saisie.strip().upper()
    if not s:
        return []
    # La table ALIAS existait depuis le debut et n'etait JAMAIS consultee
    # ici : « SANOFI » partait en onze telechargements (SANOFI, SANOFI.PA,
    # SANOFI.DE...) qui echouaient tous, alors que la reponse — SAN.PA —
    # etait ecrite en bas de ce fichier. Elle passe maintenant en tete.
    direct = par_alias(s)
    if direct:
        return [direct]
    if "." in s or "-" in s or "^" in s:
        return [s]                                  # deja qualifie
    if est_isin(s):
        return [x for x in (_isin_via_yahoo(s),) if x]
    # Mnemonique nu : Yahoo d'abord (marche pour les US), puis les places EU.
    return [s] + [s + suf for suf in SUFFIXES]


def resoudre(saisie: str, load_fn, av_key: str | None = None,
             journal=print) -> tuple[str | None, list[dict]]:
    """Renvoie (ticker_trouve, suggestions).

    load_fn(ticker) doit lever une exception si le ticker n'existe pas.
    """
    s = saisie.strip().upper()
    cache = _cache()
    if s in cache:
        return cache[s], []

    liste = candidats(s)
    if liste and liste[0] != s and par_alias(s):
        journal(f"  {s} -> {liste[0]}")
    if est_isin(s) and not liste:
        journal(f"  ISIN {s} : annuaire Yahoo muet.")
    elif est_isin(s):
        journal(f"  ISIN {s} -> {liste[0]}")

    # Un ISIN commence par le code pays : on remonte sa place en tete.
    if est_isin(s) and (pref := PAYS.get(s[:2])):
        liste = sorted(liste, key=lambda t: 0 if any(
            t.endswith(p) for p in pref if p) else 1)

    for i, tk in enumerate(liste):
        try:
            df = load_fn(tk)
            if df is not None and len(df) > 30:
                if i > 0:
                    journal(f"  {s} -> {tk}")
                _memoriser(s, tk)
                return tk, []
        except Exception:
            continue

    if av_key:
        from .news import chercher_symbole
        sugg = chercher_symbole(av_key, s)
        if sugg:
            journal(f"  {s} introuvable. Suggestions :")
            for m in sugg[:5]:
                journal(f"    {m['symbole']:12s} {m['nom'][:34]:34s} {m['region']}")
        return None, sugg

    journal(f"  {s} introuvable. Essaie avec le suffixe de place "
            f"(.PA Paris, .DE Francfort, .AS Amsterdam, .MI Milan, .MC Madrid).")
    return None, []


# ---------------------------------------------------------------------
# Codes qui ne sont pas ceux de Yahoo.
#
# Cas vecu : Sanofi se cherche "SASY" chez Refinitiv, "SAN FP" chez
# Bloomberg, mais "SAN.PA" chez Yahoo. Sans cette table, la recherche
# ne rend rien et on croit que le titre n'existe pas.
# ---------------------------------------------------------------------

ALIAS = {
    # France
    "SASY": "SAN.PA", "SAN FP": "SAN.PA", "SANOFI": "SAN.PA",
    "MC FP": "MC.PA", "LVMH": "MC.PA", "OREP": "OR.PA", "LOREAL": "OR.PA",
    "TTEF": "TTE.PA", "TOTAL": "TTE.PA", "TOTALENERGIES": "TTE.PA",
    "AIR": "AIR.PA", "AIRBUS": "AIR.PA", "SCHN": "SU.PA",
    "SCHNEIDER": "SU.PA", "BNPP": "BNP.PA", "AXAF": "CS.PA", "AXA": "CS.PA",
    "DANO": "BN.PA", "DANONE": "BN.PA", "PERP": "RI.PA", "PERNOD": "RI.PA",
    "STM": "STMPA.PA", "SGEF": "DG.PA", "VINCI": "DG.PA",
    "SGOB": "SGO.PA", "HRMS": "RMS.PA", "HERMES": "RMS.PA",
    "EDEN": "EDEN.PA", "CAPP": "CAP.PA", "CAPGEMINI": "CAP.PA",
    "ESLX": "EL.PA", "ESSILOR": "EL.PA", "KER": "KER.PA", "KERING": "KER.PA",
    "ENGIE": "ENGI.PA", "ORAN": "ORA.PA", "ORANGE": "ORA.PA",
    "MICP": "ML.PA", "MICHELIN": "ML.PA", "LEGD": "LR.PA",
    "SAF": "SAF.PA", "SAFRAN": "SAF.PA", "THLS": "HO.PA", "THALES": "HO.PA",
    "VIE": "VIE.PA", "VEOLIA": "VIE.PA", "CARR": "CA.PA", "CARREFOUR": "CA.PA",
    # Allemagne
    "SIEGN": "SIE.DE", "SIEMENS": "SIE.DE", "SAPG": "SAP.DE",
    "ALVG": "ALV.DE", "ALLIANZ": "ALV.DE", "DBKGN": "DBK.DE",
    "BMWG": "BMW.DE", "VOWG_P": "VOW3.DE", "VOLKSWAGEN": "VOW3.DE",
    "MBGN": "MBG.DE", "MERCEDES": "MBG.DE", "BAYGN": "BAYN.DE",
    "BASFN": "BAS.DE", "BASF": "BAS.DE", "ADSGN": "ADS.DE", "ADIDAS": "ADS.DE",
    "IFXGN": "IFX.DE", "INFINEON": "IFX.DE", "MUVGN": "MUV2.DE",
    # Pays-Bas, Belgique, Espagne, Italie
    "ASML": "ASML.AS", "ASMLA": "ASML.AS", "PRX": "PRX.AS",
    "AD": "AD.AS", "AHOLD": "AD.AS", "INGA": "INGA.AS",
    "ABI": "ABI.BR", "ANHEUSER": "ABI.BR", "UCB": "UCB.BR",
    "SAN MC": "SAN.MC", "SANTANDER": "SAN.MC", "IBE": "IBE.MC",
    "ITX": "ITX.MC", "INDITEX": "ITX.MC", "TEF": "TEF.MC",
    "ENI": "ENI.MI", "ISP": "ISP.MI", "ENEL": "ENEL.MI",
    "RACE": "RACE.MI", "FERRARI": "RACE.MI", "STLAM": "STLAM.MI",
    "STELLANTIS": "STLAM.MI",
    # Suisse, Royaume-Uni, Nordiques
    "NESN": "NESN.SW", "NESTLE": "NESN.SW", "NOVN": "NOVN.SW",
    "NOVARTIS": "NOVN.SW", "ROG": "ROG.SW", "ROCHE": "ROG.SW",
    "UBSG": "UBSG.SW", "ZURN": "ZURN.SW", "ABBN": "ABBN.SW",
    "AZN": "AZN.L", "ASTRAZENECA": "AZN.L", "SHEL": "SHEL.L",
    "SHELL": "SHEL.L", "ULVR": "ULVR.L", "UNILEVER": "ULVR.L",
    "HSBA": "HSBA.L", "HSBC": "HSBA.L", "BP": "BP.L", "GSK": "GSK.L",
    "RIO": "RIO.L", "NOVOB": "NOVO-B.CO", "NOVO": "NOVO-B.CO",
    "ERICB": "ERIC-B.ST", "ERICSSON": "ERIC-B.ST", "VOLVB": "VOLV-B.ST",
    "NOKIA": "NOKIA.HE", "EQNR": "EQNR.OL",
}


def par_alias(terme: str) -> str | None:
    """Rend le ticker Yahoo si le terme est un code d'un autre fournisseur."""
    return ALIAS.get(terme.strip().upper().replace("  ", " "))
