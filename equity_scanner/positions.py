"""Registre des positions, tenu a la main.

Carruos decide, IBKR execute. Ce module est le pont entre les deux : tu y
notes ce que tu detiens, et chaque soir il te dit quelles lignes ont
declenche une condition de sortie.

Aucune connexion broker. Un fichier JSON dans .bruce_cache, c'est tout.

Deux usages :
  - le veto "titre deja en portefeuille" devient automatique ;
  - le controle des sorties se fait sur tes vraies lignes, pas sur une
    watchlist theorique.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

FICHIER = Path(".bruce_cache") / "positions.json"


def charge() -> list[dict]:
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _ecrit(lignes: list[dict]) -> list[dict]:
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(lignes, indent=1, ensure_ascii=False),
                       encoding="utf-8")
    return lignes


def ajoute(ticker: str, quantite: float, entree: float,
           stop: float | None = None, date: str | None = None) -> list[dict]:
    tk = ticker.strip().upper()
    if not tk:
        raise ValueError("ticker vide")
    lignes = [l for l in charge() if l["ticker"] != tk]
    lignes.append({"ticker": tk, "quantite": float(quantite),
                   "entree": round(float(entree), 4),
                   "stop": round(float(stop), 4) if stop else None,
                   "date": date or dt.date.today().isoformat()})
    return _ecrit(sorted(lignes, key=lambda l: l["ticker"]))


def retire(ticker: str) -> list[dict]:
    tk = ticker.strip().upper()
    return _ecrit([l for l in charge() if l["ticker"] != tk])


def tickers() -> tuple:
    return tuple(l["ticker"] for l in charge())


def controle(charge_fn, bench_tk="SPY") -> list[dict]:
    """Passe chaque ligne detenue au crible des regles de sortie.

    Le stop note a l'ouverture sert de reference : on affiche la distance
    qui t'en separe, en pourcentage. Si elle devient negative, le stop est
    depasse et la sortie ne se discute plus.
    """
    from .indicators import enrich
    from .rules import evaluate_exit, market_regime_ok

    lignes = charge()
    if not lignes:
        return []
    try:
        bench_brut = charge_fn(bench_tk)
        bench = enrich(bench_brut)
        marche_ok = bool(market_regime_ok(bench))
    except Exception as exc:
        for l in lignes:
            l["erreur"] = f"indice indisponible : {exc}"
        return lignes

    for l in lignes:
        l["erreur"] = ""
        l["sorties"] = {}
        try:
            d = enrich(charge_fn(l["ticker"]), bench_close=bench_brut["close"])
            if len(d) < 220:
                l["erreur"] = f"historique trop court ({len(d)} seances)"
                continue
            c = float(d["close"].iloc[-1])
            l["cours"] = round(c, 2)
            l["pnl_pct"] = round((c / l["entree"] - 1) * 100, 2)
            l["valeur"] = round(c * l["quantite"], 2)
            l["sorties"] = evaluate_exit(d, marche_ok)
            if l.get("stop"):
                l["marge_stop"] = round((c / l["stop"] - 1) * 100, 1)
            l["atr"] = round(float(d["atr14"].iloc[-1]), 2)
        except Exception as exc:
            l["erreur"] = f"{type(exc).__name__}: {exc}"

    for l in lignes:
        n = sum(1 for v in (l.get("sorties") or {}).values() if v)
        l["n_sorties"] = n
        if l["erreur"]:
            l["verdict"] = "INDISPONIBLE"
        elif l.get("marge_stop") is not None and l["marge_stop"] <= 0:
            l["verdict"] = "STOP TOUCHE"
        elif n >= 2:
            l["verdict"] = "SORTIE"
        elif n == 1:
            l["verdict"] = "SURVEILLER"
        else:
            l["verdict"] = "CONSERVER"
    return sorted(lignes, key=lambda l: (-l["n_sorties"], l["ticker"]))


def rapport(charge_fn=None) -> None:
    """    py -m equity_scanner.positions"""
    from . import data as dl
    charge_fn = charge_fn or (lambda tk: dl.load_yf(tk, years=3))
    lignes = controle(charge_fn)
    if not lignes:
        print("\n  Aucune position enregistree.")
        print("  Ajoute-les depuis la page d'accueil de Carruos.\n")
        return
    print(f"\n  {len(lignes)} POSITION(S)")
    print(f"    {'TITRE':<12}{'QTE':>6}{'ENTREE':>10}{'COURS':>10}"
          f"{'P&L':>9}{'STOP':>9}   VERDICT")
    for l in lignes:
        stop = "--" if l.get("marge_stop") is None else f'{l["marge_stop"]:+.1f}%'
        print(f"    {l['ticker']:<12}{l['quantite']:>6.0f}{l['entree']:>10.2f}"
              f"{l.get('cours', 0):>10.2f}{l.get('pnl_pct', 0):>8.1f}%"
              f"{stop:>9}   {l['verdict']}")
        actives = [k for k, v in (l.get("sorties") or {}).items() if v]
        if actives:
            print(f"                 -> {', '.join(actives)}")
        if l["erreur"]:
            print(f"                 -> {l['erreur']}")
    print("\n  Carruos decide, tu passes les ordres sur IBKR.\n")


if __name__ == "__main__":
    rapport()
