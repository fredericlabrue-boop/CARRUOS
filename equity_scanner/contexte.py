"""Contexte d'un titre — version corrigee de forecast.py.

CE QUI A ETE GARDE du module d'origine, parce que c'est bon :
  - la structure "ce qui confirmerait / ce qui invaliderait" ;
  - la separation nette entre technique, marche et actualites ;
  - le refus explicite de passer un ordre ;
  - le bloc pret a afficher pour l'interface.

CE QUI A ETE RETIRE, et pourquoi :

  1. Le score composite sur 100. Il etait construit avec sept poids
     (trend 25, momentum 15, force relative 15, volume 10, volatilite
     10, regime 15, actualites 10). Ces sept nombres ne viennent de
     nulle part : aucun n'a ete teste, aucun n'est mesure. Les
     additionner produit un nombre qui a l'air quantitatif et ne l'est
     pas.

  2. Le libelle de direction. HAUSSIER au-dessus de 65, BAISSIER sous
     35. Quatre seuils, egalement inventes, appliques a un score
     invente. Le resultat s'affichait en titre : "NVDA — HAUSSIER".

  3. La "confiance descriptive" sur 100. Une seconde estimation
     inventee, presentee a cote de la premiere.

  Onze nombres non testes produisaient un verdict directionnel. C'est
  exactement le "ACHAT, confiance 68 %" qu'on refuse depuis le debut :
  la mise en forme change, le defaut est le meme.

CE QUI LES REMPLACE : des faits, chacun avec son seuil et sa source.
Un ecart a l'EMA20 est une mesure. "HAUSSIER" est une opinion habillee
en mesure. Le lecteur conclut lui-meme, et peut verifier chaque ligne.

    py -m equity_scanner.contexte NVDA
"""

from __future__ import annotations

import argparse
import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from . import data as dl
from .indicators import PERIODES, enrich
from .rules import evaluate_exit, market_regime_ok

INDICES = {"us": ("SPY", "S&P 500"), "europe": ("^STOXX", "STOXX 600"),
           "france": ("^FCHI", "CAC 40"), "allemagne": ("^GDAXI", "DAX")}

VERSION = "2.0"
HORIZON = 20          # seances, pour la dispersion


def _f(v: Any) -> float | None:
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _mesure(nom, valeur, seuil, unite="", sens="au-dessus",
            source="calcule") -> dict:
    """Un fait. Valeur, seuil de reference, et de quel cote on se trouve.

    `statut` ne dit pas "bon" ou "mauvais" : il dit de quel cote du
    seuil se trouve la mesure. Juger, c'est le travail du lecteur.
    """
    if valeur is not None:
        valeur = round(float(valeur), 2)
    if seuil is not None:
        seuil = round(float(seuil), 2)
    if valeur is None or seuil is None:
        st = "indisponible"
    elif sens == "au-dessus":
        st = "au-dessus" if valeur >= seuil else "en-dessous"
    else:
        st = "en-dessous" if valeur <= seuil else "au-dessus"
    return {"nom": nom, "valeur": valeur, "seuil": seuil, "unite": unite,
            "statut": st, "source": source}


def dispersion(d: pd.DataFrame, horizon: int = HORIZON) -> dict:
    """Amplitude plausible a `horizon` seances, derive fixee a ZERO.

    Ce n'est pas une anticipation : c'est la largeur du champ des
    possibles, mesuree sur la volatilite realisee. Elle ne dit rien du
    sens et c'est volontaire.
    """
    c = d["close"].dropna()
    if len(c) < 80:
        return {}
    sig = float(np.log(c / c.shift(1)).dropna().tail(120).std())
    if not np.isfinite(sig) or sig <= 0:
        return {}
    e = sig * horizon ** 0.5
    p = float(c.iloc[-1])
    return {"horizon": horizon, "sigma_jour": round(sig * 100, 2),
            "bas68": round(p * float(np.exp(-e)), 2),
            "haut68": round(p * float(np.exp(e)), 2),
            "bas95": round(p * float(np.exp(-2 * e)), 2),
            "haut95": round(p * float(np.exp(2 * e)), 2),
            "ampl68": round((float(np.exp(e)) - 1) * 100, 1),
            "ampl95": round((float(np.exp(2 * e)) - 1) * 100, 1)}


def mesures_titre(d: pd.DataFrame, marche_ok: bool) -> list[dict]:
    """Les faits, avec les seuils de la strategie — ceux qui sont geles."""
    r = d.iloc[-1]
    c, atr = _f(r["close"]), _f(r["atr14"])
    out = [
        _mesure("Marche au-dessus de sa MM200", 1.0 if marche_ok else 0.0,
                1.0, "", "au-dessus", "regle 1a"),
        _mesure("Ecart a la SMA200",
                None if (c is None or not _f(r["sma200"]))
                else round((c / _f(r["sma200"]) - 1) * 100, 2),
                0.0, "%", "au-dessus", "regle 1b"),
        _mesure("Pente SMA50 sur 20 seances", _f(r["sma50_slope20"]),
                0.0, "", "au-dessus", "regle 1c"),
        _mesure("Ligne MACD", _f(r["macd"]), 0.0, "", "au-dessus", "regle 1e"),
        _mesure("Ecart a l'EMA20 en ATR",
                None if (c is None or not _f(r["ema20"]) or not atr)
                else round(abs(c - _f(r["ema20"])) / atr, 2),
                0.5, "ATR", "en-dessous", "regle 2a"),
        _mesure("RSI 14", _f(r["rsi14"]), 40.0, "", "au-dessus", "regle 2b"),
        _mesure("Seances depuis le plus haut 60 j",
                _f(r["bars_since_high60"]), 10.0, "j", "en-dessous",
                "regle 2d"),
        _mesure("Volume relatif", _f(r["rvol"]), 1.20, "x", "au-dessus",
                "regle 4a"),
        _mesure("Volatilite quotidienne (ATR)",
                None if (not atr or not c) else round(atr / c * 100, 2),
                None, "%", "au-dessus", "mesure"),
    ]
    return out


def confirmerait(mes: list[dict], sorties: dict) -> list[str]:
    """Ce qui manque, nomme precisement. Aucune promesse de resultat.

    (La premiere version construisait une liste avec une condition
    `if False else False` — toujours vide — avant de l'ecraser par la
    ligne suivante. Le resultat etait juste par accident ; il est
    maintenant juste par construction.)
    """
    manque = [m for m in mes
              if m["source"].startswith("regle") and m["statut"] == "en-dessous"]
    out = [f"{m['nom']} : {m['valeur']}{m['unite']} -> il faut "
           f"{m['seuil']}{m['unite']}" for m in manque]
    indispo = [m["nom"] for m in mes
               if m["source"].startswith("regle") and m["statut"] == "indisponible"]
    if indispo:
        out.append("NON MESURE, donc non concluant : " + ", ".join(indispo))
    return out or ["Toutes les conditions mesurees sont deja remplies."]


def invaliderait(sorties: dict) -> list[str]:
    """Les conditions de sortie ecrites dans la strategie, telles quelles."""
    actives = [k for k, v in sorties.items() if v]
    dorm = [k for k, v in sorties.items() if not v]
    out = [f"{k} (deja active)" for k in actives]
    out += [f"{k}" for k in dorm]
    return out


def contexte_titre(ticker: str, marche: str = "us",
                   av_key: str | None = None) -> dict:
    bench_tk, bench_nom = INDICES.get(marche, INDICES["us"])
    try:
        brut = dl.load_yf(ticker)
        bench_brut = dl.load_yf(bench_tk)
        d = enrich(brut, bench_close=bench_brut["close"])
        bo = enrich(bench_brut)
    except Exception as exc:
        return {"ok": False, "ticker": ticker,
                "erreur": f"{type(exc).__name__}: {exc}"}
    if len(d) < 220:
        return {"ok": False, "ticker": ticker,
                "erreur": f"historique trop court ({len(d)} seances)"}

    marche_ok = bool(market_regime_ok(bo))
    mes = mesures_titre(d, marche_ok)
    sorties = evaluate_exit(d, marche_ok)
    remplies = sum(1 for m in mes
                   if m["source"].startswith("regle") and m["statut"] == "au-dessus")
    total = sum(1 for m in mes if m["source"].startswith("regle"))

    actus = []
    if av_key:
        try:
            from . import news as nw
            actus = nw.news(av_key, ticker, limit=5)
        except Exception:
            actus = []

    return {
        "ok": True, "version": VERSION, "ticker": ticker,
        "horodatage": dt.datetime.now().isoformat(timespec="seconds"),
        "date_barre": str(d.index[-1].date()),
        "prix": round(float(d["close"].iloc[-1]), 4),
        "indice": bench_nom, "marche_ok": marche_ok,
        "conditions_remplies": f"{remplies} / {total}",
        "mesures": mes,
        "dispersion": dispersion(d),
        "confirmerait": confirmerait(mes, sorties),
        "invaliderait": invaliderait(sorties),
        # Les actualites sont du CONTEXTE, jamais une regle. Aucun score
        # d'actualite n'entre dans un calcul ici.
        "actualites": [{"titre": a.get("titre", ""), "source": a.get("source", ""),
                        "quand": a.get("quand", "")} for a in actus[:5]],
        "avertissement": (
            "Aucun verdict directionnel. La strategie 'repli en tendance' "
            "a rendu NO-GO en Phase 0 : les conditions ci-dessus sont "
            "mesurees, pas validees comme predictives."),
    }


def texte(r: dict) -> str:
    if not r.get("ok"):
        return f"  {r.get('ticker')} : {r.get('erreur')}"
    L = [f"\n  {r['ticker']}  {r['prix']}  —  {r['date_barre']}",
         f"  Indice {r['indice']} : {'RISK-ON' if r['marche_ok'] else 'RISK-OFF'}"
         f"   ·   conditions remplies {r['conditions_remplies']}", ""]
    L.append(f"  {'MESURE':<34}{'VALEUR':>10}{'SEUIL':>10}   ETAT")
    for m in r["mesures"]:
        v = "—" if m["valeur"] is None else f"{m['valeur']}{m['unite']}"
        s = "—" if m["seuil"] is None else f"{m['seuil']}{m['unite']}"
        L.append(f"  {m['nom']:<34}{v:>10}{s:>10}   {m['statut']}")
    d = r.get("dispersion") or {}
    if d:
        L += ["", f"  DISPERSION A {d['horizon']} SEANCES  "
                  f"(volatilite {d['sigma_jour']} %/j, derive nulle)",
              f"    68 % des cas : {d['bas68']} a {d['haut68']}  "
              f"(±{d['ampl68']} %)",
              f"    95 % des cas : {d['bas95']} a {d['haut95']}  "
              f"(±{d['ampl95']} %)"]
    L += ["", "  CE QUI MANQUE"]
    L += [f"    · {x}" for x in r["confirmerait"]]
    L += ["", "  CE QUI FERAIT SORTIR"]
    L += [f"    · {x}" for x in r["invaliderait"]]
    if r.get("actualites"):
        L += ["", "  CONTEXTE (n'entre dans aucune regle)"]
        L += [f"    · {a['quand']} {a['source']} — {a['titre'][:70]}"
              for a in r["actualites"]]
    L += ["", f"  {r['avertissement']}", ""]
    return "\n".join(L)


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("ticker")
    a.add_argument("--marche", default="us", choices=list(INDICES))
    a.add_argument("--av-key", default=None)
    o = a.parse_args()
    print(texte(contexte_titre(o.ticker, o.marche, o.av_key)))


if __name__ == "__main__":
    main()
