"""Journal d'audit des signaux. Chantier n°3 du registre.

A QUOI CA SERT, CONCRETEMENT

Dans six mois, une ligne aura ete prise et se sera mal passee. La question
ne sera pas « qu'est-ce que j'aurais du faire », elle sera : QUE DISAIENT
LES CHIFFRES CE SOIR-LA. Sans trace ecrite, la reponse se reconstruit de
memoire, et la memoire arrange toujours les choses dans le sens du
resultat connu.

Chaque signal evalue laisse donc ici une ligne, ecrite AVANT de savoir ce
que le titre a fait ensuite :

  - un identifiant unique et reproductible ;
  - l'horodatage UTC de l'evaluation ;
  - la date de la barre evaluee, qui n'est pas la meme chose ;
  - les treize blocs, un par un, avec leur resultat ;
  - les vetos declenches, en toutes lettres ;
  - la valeur de chaque indicateur au moment du signal ;
  - la version de la strategie ET l'empreinte des parametres geles.

CE QUE L'EMPREINTE PROTEGE

Elle est calculee sur les valeurs effectives des parametres au moment de
l'evaluation. Si une seule constante bouge, l'empreinte change et toutes
les lignes ecrites apres deviennent distinguables de celles d'avant. Un
resultat ne peut donc plus etre attribue par erreur a un jeu de
parametres qui ne l'a pas produit — ce qui est exactement ce que le
protocole de validation exige.

Format : JSONL, une ligne par signal, jamais reecrite. On ajoute, on ne
modifie pas. Un journal qu'on peut retoucher ne prouve rien.

    py -m equity_scanner.audit                 # les 20 dernieres lignes
    py -m equity_scanner.audit --verifie       # coherence du journal
    py -m equity_scanner.audit --ticker AAPL
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from pathlib import Path

import numpy as np

FICHIER = Path(".bruce_cache") / "audit-signaux.jsonl"
VERSION_STRATEGIE = "repli-en-tendance-v1.0"
_VERROU = threading.Lock()

# Indicateurs releves a chaque signal. Ce sont les entrees des regles :
# de quoi rejouer la decision a la main, plus tard, sans les cours.
COLONNES = ["close", "open", "high", "low", "volume", "sma200", "sma50",
            "ema20", "atr14", "rsi14", "macd", "macd_sig", "macd_hist",
            "bb_mid", "bb_up", "bb_low", "bb_width", "rvol", "vol_ma20",
            "sma50_slope20", "bars_since_high60", "gap_pct", "dollar_vol20",
            "rs", "rs_ma50", "rs_6m"]


# ---------------------------------------------------------------------
# Empreinte des parametres geles
# ---------------------------------------------------------------------
def parametres() -> dict:
    """Toutes les valeurs qui definissent la strategie, a cet instant."""
    from . import rules as R
    from .indicators import PERIODES

    return {
        "periodes": {k: list(v) if isinstance(v, tuple) else v
                     for k, v in sorted(PERIODES.items())},
        "regles": {
            "PULLBACK_WINDOW": R.PULLBACK_WINDOW,
            "RSI_ZONE": list(R.RSI_ZONE),
            "RSI_FLOOR": R.RSI_FLOOR,
            "EMA_BAND_ATR": R.EMA_BAND_ATR,
            "RVOL_MIN": R.RVOL_MIN,
            "GAP_VETO": R.GAP_VETO,
            "GAP_LOOKBACK": R.GAP_LOOKBACK,
            "EARNINGS_BLACKOUT": R.EARNINGS_BLACKOUT,
            "STOP_ATR_MULT": R.STOP_ATR_MULT,
            "STOP_SWING_BUFFER": R.STOP_SWING_BUFFER,
            "MIN_PRICE": R.MIN_PRICE,
            "MIN_DOLLAR_VOL": R.MIN_DOLLAR_VOL,
            "RISK_PER_TRADE": R.RISK_PER_TRADE,
            "MAX_POSITIONS": R.MAX_POSITIONS,
            "MAX_WEIGHT": R.MAX_WEIGHT,
        },
        "version": VERSION_STRATEGIE,
    }


def empreinte() -> str:
    """SHA256 des parametres. Change des qu'une seule constante bouge."""
    brut = json.dumps(parametres(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def identifiant(ticker: str, date_barre: str, emp: str) -> str:
    """Identifiant reproductible d'un signal.

    Deterministe a dessein : rescanner le meme titre sur la meme barre
    avec les memes parametres rend le MEME identifiant. Deux lignes de
    meme identifiant et de contenu different signalent alors un probleme
    reel — pas un doublon anodin.
    """
    graine = f"{VERSION_STRATEGIE}|{emp}|{ticker.upper()}|{date_barre}"
    return hashlib.sha256(graine.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------
# Ecriture
# ---------------------------------------------------------------------
def _nombre(v):
    """Valeur JSON propre : NaN et infini n'existent pas en JSON strict."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, 6) if np.isfinite(x) else None


def ligne(sig, d=None, source: str = "scan", univers: str = "",
          qualite: dict | None = None, extra: dict | None = None) -> dict:
    """Construit l'enregistrement d'un signal. N'ecrit rien."""
    emp = empreinte()
    date_barre = str(getattr(sig.date, "date", lambda: sig.date)())
    releve = {}
    if d is not None and len(d):
        try:
            r = d.loc[sig.date] if sig.date in d.index else d.iloc[-1]
            releve = {c: _nombre(r.get(c)) for c in COLONNES if c in d.columns}
        except Exception:
            releve = {}
    rec = {
        "id": identifiant(sig.ticker, date_barre, emp),
        "horodatage": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"),
        "ticker": sig.ticker,
        "date_barre": date_barre,
        "declenche": bool(sig.fired),
        "blocs": {k: bool(v) for k, v in sig.blocks.items()},
        "blocs_manquants": list(sig.failed_blocks),
        "vetos": list(sig.vetos),
        "entree": _nombre(sig.entry),
        "stop": _nombre(sig.stop),
        "atr": _nombre(sig.atr),
        "risque_pct": _nombre(sig.risk_pct),
        "rs_6m": _nombre(sig.rs_6m),
        "indicateurs": releve,
        "version": VERSION_STRATEGIE,
        "empreinte": emp,
        "source": source,
        "univers": univers,
    }
    if qualite:
        rec["qualite"] = qualite
    if extra:
        rec["extra"] = extra
    return rec


def enregistre(sig, d=None, source: str = "scan", univers: str = "",
               qualite: dict | None = None, extra: dict | None = None,
               fichier: Path | None = None) -> dict:
    """Ajoute une ligne au journal. Ne leve jamais : un journal qui casse
    le scan serait pire que pas de journal du tout."""
    rec = ligne(sig, d, source, univers, qualite, extra)
    f = fichier or FICHIER
    try:
        with _VERROU:
            f.parent.mkdir(parents=True, exist_ok=True)
            with f.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"  audit : ecriture impossible ({type(exc).__name__}: {exc})")
    return rec


def enregistre_lot(signaux, series: dict | None = None, source: str = "scan",
                   univers: str = "", fichier: Path | None = None) -> int:
    """Journalise une passe de scan entiere. Rend le nombre de lignes."""
    n = 0
    for s in signaux:
        d = (series or {}).get(s.ticker)
        enregistre(s, d, source, univers, fichier=fichier)
        n += 1
    return n


# ---------------------------------------------------------------------
# Lecture et verification
# ---------------------------------------------------------------------
def lit(fichier: Path | None = None, ticker: str = "",
        depuis: str = "", declenche: bool | None = None) -> list[dict]:
    f = fichier or FICHIER
    out = []
    try:
        with f.open(encoding="utf-8") as fp:
            for l in fp:
                l = l.strip()
                if not l:
                    continue
                try:
                    rec = json.loads(l)
                except Exception:
                    continue
                if ticker and rec.get("ticker", "").upper() != ticker.upper():
                    continue
                if depuis and rec.get("date_barre", "") < depuis:
                    continue
                if declenche is not None and bool(rec.get("declenche")) != declenche:
                    continue
                out.append(rec)
    except FileNotFoundError:
        return []
    return out


def verifie(fichier: Path | None = None) -> dict:
    """Coherence du journal. Trois questions, trois reponses.

    1. Toutes les lignes ont-elles ete produites par les MEMES parametres
       que ceux en vigueur aujourd'hui ?
    2. Deux lignes portent-elles le meme identifiant avec un contenu
       different — c'est-a-dire une decision qui a change sans que les
       parametres bougent ?
    3. Les identifiants sont-ils reproductibles a partir du contenu ?
    """
    lignes = lit(fichier)
    actuelle = empreinte()
    empreintes: dict[str, int] = {}
    vus: dict[str, str] = {}
    conflits, faux_id = [], []
    for rec in lignes:
        emp = rec.get("empreinte", "")
        empreintes[emp] = empreintes.get(emp, 0) + 1
        attendu = identifiant(rec.get("ticker", ""),
                              rec.get("date_barre", ""), emp)
        if attendu != rec.get("id"):
            faux_id.append(rec.get("id"))
        sig = json.dumps({k: rec.get(k) for k in
                          ("declenche", "blocs", "vetos", "entree", "stop")},
                         sort_keys=True)
        cle = rec.get("id", "")
        if cle in vus and vus[cle] != sig:
            conflits.append(cle)
        vus[cle] = sig
    return {
        "lignes": len(lignes),
        "empreinte_actuelle": actuelle,
        "empreintes": empreintes,
        "parametres_changes": bool(empreintes) and set(empreintes) != {actuelle},
        "identifiants_incoherents": sorted(set(faux_id)),
        "decisions_contradictoires": sorted(set(conflits)),
        "signaux_declenches": sum(1 for r in lignes if r.get("declenche")),
    }


def resume(fichier: Path | None = None, n: int = 20) -> str:
    lignes = lit(fichier)
    if not lignes:
        return ("\n  Journal d'audit vide. Il se remplit a chaque scan.\n"
                f"  Emplacement prevu : {fichier or FICHIER}\n")
    v = verifie(fichier)
    L = [f"\n  JOURNAL D'AUDIT — {v['lignes']} signal(aux) evalue(s), "
         f"{v['signaux_declenches']} declenche(s)",
         f"  empreinte des parametres en vigueur : {v['empreinte_actuelle'][:16]}…"]
    if v["parametres_changes"]:
        L.append("  ATTENTION : le journal contient plusieurs empreintes. "
                 "Les parametres ont change en cours de route —")
        L.append("  les lignes d'avant et d'apres ne se comparent pas.")
        for e, k in sorted(v["empreintes"].items(), key=lambda x: -x[1]):
            L.append(f"      {e[:16]}…  {k} ligne(s)"
                     + ("   <- en vigueur" if e == v["empreinte_actuelle"] else ""))
    if v["decisions_contradictoires"]:
        L.append(f"  ATTENTION : {len(v['decisions_contradictoires'])} signal(aux) "
                 f"ont change de resultat a parametres identiques.")
    if v["identifiants_incoherents"]:
        L.append(f"  ATTENTION : {len(v['identifiants_incoherents'])} "
                 f"identifiant(s) non reproductible(s) — journal modifie ?")
    L.append("")
    L.append(f"  {'ID':<18}{'BARRE':<12}{'TITRE':<10}{'ETAT':<12}MANQUE / VETO")
    for r in lignes[-n:]:
        etat = "DECLENCHE" if r.get("declenche") else "non"
        pourquoi = ", ".join(r.get("blocs_manquants") or []) or \
                   "; ".join(r.get("vetos") or []) or "-"
        L.append(f"  {r.get('id', ''):<18}{r.get('date_barre', ''):<12}"
                 f"{r.get('ticker', ''):<10}{etat:<12}{pourquoi[:44]}")
    L.append("")
    return "\n".join(L)


def main() -> None:
    import argparse
    a = argparse.ArgumentParser(description="Journal d'audit des signaux")
    a.add_argument("--verifie", action="store_true")
    a.add_argument("--ticker", default="")
    a.add_argument("--depuis", default="", help="date de barre minimale")
    a.add_argument("-n", type=int, default=20)
    a.add_argument("--parametres", action="store_true",
                   help="affiche les parametres geles et leur empreinte")
    o = a.parse_args()
    if o.parametres:
        print(json.dumps(parametres(), indent=2, ensure_ascii=False))
        print(f"\n  empreinte SHA256 : {empreinte()}\n")
        return
    if o.verifie:
        v = verifie()
        print(f"\n  {v['lignes']} ligne(s)")
        print(f"  empreinte en vigueur : {v['empreinte_actuelle']}")
        print(f"  parametres changes en cours de journal : "
              f"{'OUI' if v['parametres_changes'] else 'non'}")
        print(f"  decisions contradictoires : "
              f"{len(v['decisions_contradictoires'])}")
        print(f"  identifiants non reproductibles : "
              f"{len(v['identifiants_incoherents'])}\n")
        return
    if o.ticker or o.depuis:
        for r in lit(ticker=o.ticker, depuis=o.depuis)[-o.n:]:
            print(json.dumps(r, ensure_ascii=False))
        return
    print(resume(n=o.n))


if __name__ == "__main__":
    main()
