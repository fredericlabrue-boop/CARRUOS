"""Journal des operations closes.

Ce que tu as gagne, ce que tu dois au fisc, ce que tu as reinvesti, ce
que tu as retire. Et surtout : ce que le reinvestissement change
reellement, calcule et non estime.

Une regle de conception : le gain affiche est TOUJOURS le gain net.
Montrer "+54 EUR" quand 16 EUR sont dus au titre du PFU serait un
chiffre faux, et c'est exactement le genre de chiffre qui pousse a
surestimer ses resultats.

    py -m equity_scanner.journal ajouter TLX 70 11.69 12.46
    py -m equity_scanner.journal retrait 500
    py -m equity_scanner.journal
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

FICHIER = Path(".bruce_cache") / "journal.json"
PFU = 0.30
FRAIS_ORDRE = 1.50        # cout moyen d'un ordre chez IBKR, aller OU retour


def _lire() -> dict:
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
        d.setdefault("operations", [])
        d.setdefault("mouvements", [])
        d.setdefault("capital_initial", 0.0)
        return d
    except Exception:
        return {"operations": [], "mouvements": [], "capital_initial": 0.0}


def _ecrire(d: dict) -> dict:
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(d, indent=1, ensure_ascii=False),
                       encoding="utf-8")
    return d


def ajouter(ticker: str, qte: float, entree: float, sortie: float,
            date_entree: str | None = None, date_sortie: str | None = None,
            motif: str = "") -> dict:
    """Enregistre une position CLOSE. Les frais des deux ordres et le PFU
    sont comptes ici, pas ailleurs : le net est le seul chiffre affiche."""
    d = _lire()
    brut = (sortie - entree) * qte
    frais = 2 * FRAIS_ORDRE
    gain = brut - frais
    impot = max(0.0, gain) * PFU
    d["operations"].append({
        "ticker": ticker.upper(), "qte": float(qte),
        "entree": round(float(entree), 4), "sortie": round(float(sortie), 4),
        "engage": round(entree * qte, 2),
        "brut": round(brut, 2), "frais": round(frais, 2),
        "gain": round(gain, 2), "impot": round(impot, 2),
        "net": round(gain - impot, 2),
        "date_entree": date_entree or "", "motif": motif,
        "date_sortie": date_sortie or dt.date.today().isoformat(),
    })
    return _ecrire(d)


def mouvement(genre: str, montant: float, note: str = "") -> dict:
    """apport, retrait ou reinvestissement."""
    if genre not in ("apport", "retrait", "reinvestissement"):
        raise ValueError("genre : apport, retrait ou reinvestissement")
    d = _lire()
    d["mouvements"].append({"genre": genre, "montant": round(float(montant), 2),
                            "date": dt.date.today().isoformat(), "note": note})
    if genre == "apport":
        d["capital_initial"] += float(montant)
    return _ecrire(d)


def bilan() -> dict:
    d = _lire()
    ops = d["operations"]
    n = len(ops)
    brut = sum(o["brut"] for o in ops)
    frais = sum(o["frais"] for o in ops)
    impot = sum(o["impot"] for o in ops)
    net = sum(o["net"] for o in ops)
    gagnants = [o for o in ops if o["net"] > 0]
    perdants = [o for o in ops if o["net"] <= 0]
    retire = sum(m["montant"] for m in d["mouvements"] if m["genre"] == "retrait")
    apport = sum(m["montant"] for m in d["mouvements"] if m["genre"] == "apport")
    reinv = net - retire
    engage_moy = (sum(o["engage"] for o in ops) / n) if n else 0.0
    return {
        "n": n, "brut": round(brut, 2), "frais": round(frais, 2),
        "impot": round(impot, 2), "net": round(net, 2),
        "gagnants": len(gagnants), "perdants": len(perdants),
        "taux": round(len(gagnants) / n * 100, 1) if n else 0.0,
        "moy_gagnant": round(sum(o["net"] for o in gagnants) / len(gagnants), 2)
        if gagnants else 0.0,
        "moy_perdant": round(sum(o["net"] for o in perdants) / len(perdants), 2)
        if perdants else 0.0,
        "apport": round(apport, 2), "retire": round(retire, 2),
        "reinvesti": round(reinv, 2), "engage_moyen": round(engage_moy, 2),
        "capital": round(apport + net - retire, 2),
    }


def projection(capital: float, net_par_an: float, annees: int = 10) -> list:
    """Reinvestir ou retirer : la difference, calculee.

    Hypothese assumee : le taux de gain net constate se reproduit. C'est
    une PROJECTION ARITHMETIQUE, pas une prevision. Avec deux trades
    d'historique, le taux constate ne vaut rien — la colonne de droite
    montre precisement de combien l'incertitude porte.
    """
    if capital <= 0:
        return []
    taux = net_par_an / capital
    out = []
    c_reinv, c_retire = capital, capital
    cumul_retire = 0.0
    for an in range(1, annees + 1):
        c_reinv *= (1 + taux)
        gain = c_retire * taux
        cumul_retire += gain
        out.append({"an": an,
                    "reinvesti": round(c_reinv, 0),
                    "retire_capital": round(c_retire, 0),
                    "retire_cumule": round(cumul_retire, 0),
                    "retire_total": round(c_retire + cumul_retire, 0),
                    "ecart": round(c_reinv - c_retire - cumul_retire, 0)})
    return out


def rapport(journal=print) -> None:
    d = _lire()
    b = bilan()
    if not b["n"]:
        journal("\n  Aucune operation close enregistree.")
        journal("  Ajoute-en une : py -m equity_scanner.journal ajouter "
                "TLX 70 11.69 12.46\n")
        return

    journal(f"\n  {'=' * 64}")
    journal(f"  JOURNAL DES OPERATIONS — {b['n']} position(s) close(s)")
    journal(f"  {'=' * 64}")
    journal(f"    {'TITRE':<9}{'QTE':>6}{'ENTREE':>9}{'SORTIE':>9}"
            f"{'BRUT':>10}{'IMPOT':>9}{'NET':>10}")
    for o in d["operations"]:
        journal(f"    {o['ticker']:<9}{o['qte']:>6.0f}{o['entree']:>9.2f}"
                f"{o['sortie']:>9.2f}{o['brut']:>+10.2f}{-o['impot']:>9.2f}"
                f"{o['net']:>+10.2f}")

    journal(f"\n  RESULTAT")
    journal(f"    {'Plus-value brute':<30}{b['brut']:>+12,.2f} EUR")
    journal(f"    {'Frais de courtage':<30}{-b['frais']:>12,.2f} EUR")
    journal(f"    {'PFU a 30 %':<30}{-b['impot']:>12,.2f} EUR")
    journal(f"    {'GAIN NET':<30}{b['net']:>+12,.2f} EUR")
    journal(f"\n    {'Reussite':<30}{b['taux']:>11.0f} %"
            f"   ({b['gagnants']} / {b['n']})")
    if b["gagnants"] and b["perdants"]:
        journal(f"    {'Gain moyen':<30}{b['moy_gagnant']:>+12,.2f} EUR")
        journal(f"    {'Perte moyenne':<30}{b['moy_perdant']:>+12,.2f} EUR")

    journal(f"\n  CIRCULATION DE L'ARGENT")
    journal(f"    {'Apports':<30}{b['apport']:>12,.2f} EUR")
    journal(f"    {'Retire du compte':<30}{b['retire']:>12,.2f} EUR")
    journal(f"    {'Reinvesti (gains gardes)':<30}{b['reinvesti']:>+12,.2f} EUR")
    journal(f"    {'Capital actuel estime':<30}{b['capital']:>12,.2f} EUR")

    if b["capital"] > 0 and b["net"] != 0:
        journal(f"\n  REINVESTIR OU RETIRER")
        journal(f"    Hypothese : {b['net']:+,.0f} EUR nets par an se "
                f"reproduisent sur {b['capital']:,.0f} EUR")
        p = projection(b["capital"], b["net"])
        journal(f"    {'an':<5}{'si tu reinvestis':>19}"
                f"{'si tu retires':>17}{'ecart':>12}")
        for x in p:
            if x["an"] in (1, 3, 5, 10):
                journal(f"    {x['an']:<5}{x['reinvesti']:>19,.0f}"
                        f"{x['retire_total']:>17,.0f}{x['ecart']:>+12,.0f}")
        journal("    Le retrait garde le capital fixe : les gains ne "
                "travaillent plus.")
        journal("    ATTENTION : cette projection suppose que le resultat "
                "passe se")
        journal(f"    reproduit. Avec {b['n']} operation(s), il ne prouve "
                "rien du tout.")
    journal("")


def main() -> None:
    a = argparse.ArgumentParser()
    s = a.add_subparsers(dest="cmd")
    p1 = s.add_parser("ajouter", help="enregistrer une position close")
    p1.add_argument("ticker")
    p1.add_argument("qte", type=float)
    p1.add_argument("entree", type=float)
    p1.add_argument("sortie", type=float)
    p1.add_argument("--motif", default="")
    for g in ("apport", "retrait", "reinvestissement"):
        p = s.add_parser(g)
        p.add_argument("montant", type=float)
        p.add_argument("--note", default="")
    o = a.parse_args()
    if o.cmd == "ajouter":
        ajouter(o.ticker, o.qte, o.entree, o.sortie, motif=o.motif)
    elif o.cmd in ("apport", "retrait", "reinvestissement"):
        mouvement(o.cmd, o.montant, o.note)
    rapport()


if __name__ == "__main__":
    main()
