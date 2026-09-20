"""Open interest — celui des OPTIONS, parce qu'une action n'en a pas.

POURQUOI CE MODULE EXISTE SEPAREMENT
------------------------------------
Frederic a demande « l'open interest en fonction du mouvement des
prix ». Il faut commencer par une correction, pas par un graphique :

    UNE ACTION N'A PAS D'OPEN INTEREST.

L'open interest compte les contrats OUVERTS et non denoues — c'est une
notion de contrats a terme et d'options. Une action existe en nombre
fixe ; il n'y a rien a ouvrir ni a denouer. Un site qui affiche un
« open interest » sur une action affiche autre chose, generalement le
volume.

Ce qui joue ce role sur une action, c'est le VOLUME rapporte a son
habitude, et `chandeliers.volume_prix()` le mesure deja — avec la meme
comparaison au taux de base que pour les figures.

CE QUE CE MODULE FAIT
---------------------
Les options d'une action, elles, ont un open interest, et il est
lisible. Ce module en tire des FAITS, sans en deduire de direction :

  - l'open interest total des calls et des puts, et leur rapport ;
  - ou se concentre l'open interest : les trois strikes les plus
    charges, en call comme en put, et leur distance au cours ;
  - le « mur » : le strike qui porte le plus d'open interest, toutes
    options confondues.

CE QU'IL NE FAIT PAS
--------------------
Il ne dit pas qu'un rapport put/call eleve est haussier, ni l'inverse.
Cette lecture existe dans les manuels, dans les deux sens selon les
auteurs, et personne ici ne l'a mesuree. Pour la mesurer il faudrait un
historique d'open interest que le programme ne collecte pas : yfinance
ne rend que la photo du jour. Le jour ou cet historique existera, la
mesure se fera comme pour les figures — contre le taux de base.

Le chiffre du jour ne se compare a rien : c'est le defaut principal de
ce module, et il est ecrit en tete du rapport.

    py -m equity_scanner.options NVDA
"""

from __future__ import annotations

import argparse
import datetime as dt

VERSION = "options-v1.0"

RESERVE = (
    "Une photo sans historique ne se compare a rien. Un rapport put/call "
    "de 1,3 n'est ni haut ni bas tant qu'on ne sait pas ce qu'il vaut "
    "d'habitude sur ce titre. Ces chiffres sont du contexte pour la "
    "verification avant l'ordre, pas un signal — comme les actualites.")


def _somme(df, col: str) -> float:
    try:
        return float(df[col].fillna(0).sum())
    except Exception:
        return 0.0


def chaine(ticker: str, echeances: int = 3) -> dict:
    """L'open interest des options, sur les prochaines echeances.

    `echeances` limite le nombre de dates interrogees : chacune est un
    appel reseau, et la chaine complete d'un titre liquide en compte
    une vingtaine.
    """
    import yfinance as yf

    t = yf.Ticker(ticker)
    try:
        dates = list(t.options)[:max(1, int(echeances))]
    except Exception as exc:
        return {"ok": False, "ticker": ticker,
                "erreur": f"chaine d'options indisponible ({exc})"}
    if not dates:
        return {"ok": False, "ticker": ticker,
                "erreur": "aucune option cotee sur ce titre"}

    try:
        cours = float(t.fast_info["last_price"])
    except Exception:
        cours = None

    out = []
    for d in dates:
        try:
            ch = t.option_chain(d)
        except Exception:
            continue
        calls, puts = ch.calls, ch.puts
        oi_c, oi_p = _somme(calls, "openInterest"), _somme(puts, "openInterest")
        out.append({
            "echeance": str(d),
            "oi_calls": round(oi_c), "oi_puts": round(oi_p),
            "vol_calls": round(_somme(calls, "volume")),
            "vol_puts": round(_somme(puts, "volume")),
            "ratio_pc": round(oi_p / oi_c, 2) if oi_c else None,
            "gros_calls": _gros(calls, cours),
            "gros_puts": _gros(puts, cours),
        })
    if not out:
        return {"ok": False, "ticker": ticker,
                "erreur": "aucune echeance lisible"}

    tot_c = sum(x["oi_calls"] for x in out)
    tot_p = sum(x["oi_puts"] for x in out)
    return {
        "ok": True, "version": VERSION, "ticker": ticker,
        "cours": None if cours is None else round(cours, 2),
        "horodatage": dt.datetime.now().isoformat(timespec="seconds"),
        "echeances": out,
        "oi_calls": tot_c, "oi_puts": tot_p,
        "ratio_pc": round(tot_p / tot_c, 2) if tot_c else None,
        "mur": _mur(out),
        "reserve": RESERVE,
    }


def _gros(df, cours, n: int = 3) -> list:
    """Les n strikes les plus charges, avec leur distance au cours."""
    try:
        t = df.nlargest(n, "openInterest")
    except Exception:
        return []
    lignes = []
    for _, r in t.iterrows():
        k = float(r.get("strike", 0) or 0)
        oi = int(r.get("openInterest", 0) or 0)
        if oi <= 0:
            continue
        lignes.append({
            "strike": round(k, 2), "oi": oi,
            "ecart_pct": (None if not cours or not k
                          else round((k / cours - 1) * 100, 1)),
        })
    return lignes


def _mur(echeances: list) -> dict | None:
    """Le strike qui porte le plus d'open interest, calls et puts confondus.

    C'est un FAIT : la ou le plus de contrats sont ouverts. Ce n'est pas
    une prediction que le cours s'y arretera — cette lecture existe, elle
    n'est pas verifiee ici.
    """
    par_strike: dict[float, int] = {}
    for e in echeances:
        for c in e["gros_calls"] + e["gros_puts"]:
            par_strike[c["strike"]] = par_strike.get(c["strike"], 0) + c["oi"]
    if not par_strike:
        return None
    k = max(par_strike, key=par_strike.get)
    return {"strike": k, "oi": par_strike[k]}


def texte(r: dict) -> str:
    if not r.get("ok"):
        return f"\n  {r.get('ticker')} : {r.get('erreur')}\n"
    L = [f"\n  {r['ticker']} — OPEN INTEREST DES OPTIONS",
         f"  cours {r['cours']}   ·   {r['horodatage'][:16]}", ""]
    L.append("  UNE ACTION N'A PAS D'OPEN INTEREST. Ce qui suit porte sur")
    L.append("  ses OPTIONS. Pour l'action elle-meme, la notion voisine est")
    L.append("  le volume rapporte a son habitude :")
    L.append("      py -m equity_scanner.chandeliers " + r["ticker"])
    L.append("")
    L.append(f"  open interest total    calls {r['oi_calls']:>10,}".replace(",", " "))
    L.append(f"                          puts {r['oi_puts']:>10,}".replace(",", " "))
    if r["ratio_pc"] is not None:
        L.append(f"  rapport put / call           {r['ratio_pc']:>10.2f}")
    if r["mur"]:
        L.append(f"  strike le plus charge        {r['mur']['strike']:>10}"
                 f"   ({r['mur']['oi']:,} contrats)".replace(",", " "))
    L.append("")
    for e in r["echeances"]:
        L.append(f"  ÉCHÉANCE {e['echeance']}")
        rp = "—" if e["ratio_pc"] is None else f"{e['ratio_pc']:.2f}"
        L.append(f"    calls  OI {e['oi_calls']:>9,}   volume {e['vol_calls']:>8,}"
                 .replace(",", " "))
        L.append(f"    puts   OI {e['oi_puts']:>9,}   volume {e['vol_puts']:>8,}"
                 .replace(",", " "))
        L.append(f"    rapport put/call {rp}")
        for nom, cle in (("calls", "gros_calls"), ("puts", "gros_puts")):
            if e[cle]:
                bouts = "  ".join(
                    f"{c['strike']}"
                    + ("" if c["ecart_pct"] is None
                       else f" ({c['ecart_pct']:+.1f} %)")
                    + f" : {c['oi']:,}".replace(",", " ")
                    for c in e[cle])
                L.append(f"    plus charges en {nom} : {bouts}")
        L.append("")
    L.append("  " + RESERVE)
    return "\n".join(L) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(
        description="Open interest des options d'un titre")
    p.add_argument("ticker")
    p.add_argument("--echeances", type=int, default=3)
    a = p.parse_args()
    print(texte(chaine(a.ticker.upper(), a.echeances)))


if __name__ == "__main__":
    main()
