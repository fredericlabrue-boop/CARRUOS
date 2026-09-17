"""Portefeuille IBKR, en LECTURE SEULE.

Connexion a TWS ou IB Gateway via ib_insync.

    py -m pip install ib_insync

Dans TWS : Global Configuration > API > Settings > Enable ActiveX and
Socket Clients. Ports :

    7497  compte PAPIER   <- commence par la, toujours
    7496  compte REEL

CE MODULE NE PASSE AUCUN ORDRE. La connexion est ouverte en readonly=True,
ce qui interdit l'envoi cote IBKR lui-meme et pas seulement dans ce code.
Un systeme non valide qui place des ordres tout seul est la facon la plus
rapide de perdre de l'argent ; le jour ou l'execution automatique aura du
sens, ce sera une decision separee et explicite.

Ce module n'a PAS pu etre teste ici : il faut TWS en face. Lance-le d'abord
sur le compte papier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# TWS et IB Gateway n'ecoutent PAS sur les memes ports. C'est la cause
# numero un des echecs de connexion.
PORT_PAPIER = 7497          # TWS papier
PORT_REEL = 7496            # TWS reel
PORT_GW_PAPIER = 4002       # IB Gateway papier
PORT_GW_REEL = 4001         # IB Gateway reel

PORTS = {"tws-papier": PORT_PAPIER, "tws-reel": PORT_REEL,
         "gateway-papier": PORT_GW_PAPIER, "gateway-reel": PORT_GW_REEL}


@dataclass
class Position:
    ticker: str
    quantite: float
    prix_moyen: float
    cours: float
    devise: str
    valeur: float
    pnl: float
    pnl_pct: float
    sorties: dict = field(default_factory=dict)
    erreur: str = ""

    @property
    def n_sorties(self) -> int:
        return sum(1 for v in self.sorties.values() if v)

    @property
    def verdict(self) -> str:
        if self.erreur:
            return "DONNEES INDISPONIBLES"
        n = self.n_sorties
        if n >= 2:
            return "SORTIE"
        if n == 1:
            return "SURVEILLER"
        return "CONSERVER"


def connecte(port=PORT_PAPIER, host="127.0.0.1", cid=23):
    from ib_insync import IB
    ib = IB()
    # readonly=True : IBKR refusera tout ordre venant de cette session.
    ib.connect(host, port, clientId=cid, readonly=True, timeout=12)
    return ib


def resume_compte(ib) -> dict:
    vals = {}
    for v in ib.accountSummary():
        if v.tag in ("NetLiquidation", "TotalCashValue", "AvailableFunds",
                     "GrossPositionValue", "UnrealizedPnL", "RealizedPnL"):
            try:
                vals[v.tag] = float(v.value)
            except ValueError:
                pass
        if v.tag == "NetLiquidation":
            vals["devise"] = v.currency
    return vals


def positions(ib) -> list[Position]:
    from ib_insync import util
    out = []
    for p in ib.portfolio():
        c = p.contract
        if c.secType != "STK":
            continue
        suf = {"SBF": ".PA", "IBIS": ".DE", "AEB": ".AS", "BVME": ".MI",
               "BM": ".MC", "LSE": ".L", "EBS": ".SW"}.get(
                   c.primaryExchange or "", "")
        moyen = float(p.averageCost or 0)
        cours = float(p.marketPrice or 0)
        out.append(Position(
            ticker=(c.symbol + suf).upper(),
            quantite=float(p.position), prix_moyen=round(moyen, 2),
            cours=round(cours, 2), devise=c.currency,
            valeur=round(float(p.marketValue), 2),
            pnl=round(float(p.unrealizedPNL or 0), 2),
            pnl_pct=round((cours / moyen - 1) * 100, 2) if moyen else 0.0))
    util  # silence linter
    return out


def controle_sorties(pos: list[Position], charge_fn, bench_tk="SPY") -> list[Position]:
    """Passe chaque ligne detenue au crible des regles de sortie.

    C'est le seul usage vraiment utile du portefeuille tant que la Phase 0
    n'a rien valide : Carruos ne te dit pas quoi acheter, il te dit si une
    ligne que tu detiens deja a declenche une condition de sortie.
    """
    from .indicators import enrich
    from .rules import evaluate_exit, market_regime_ok
    try:
        bench_brut = charge_fn(bench_tk)
        bench = enrich(bench_brut)
        marche_ok = bool(market_regime_ok(bench))
    except Exception as exc:
        for p in pos:
            p.erreur = f"indice indisponible : {exc}"
        return pos

    for p in pos:
        try:
            d = enrich(charge_fn(p.ticker), bench_close=bench_brut["close"])
            if len(d) < 220:
                p.erreur = f"historique trop court ({len(d)} seances)"
                continue
            p.sorties = evaluate_exit(d, marche_ok)
        except Exception as exc:
            p.erreur = f"{type(exc).__name__}: {exc}"
    return pos


def etat(port=PORT_PAPIER, charge_fn=None) -> dict:
    """Point d'entree unique : ouvre, lit, ferme."""
    from . import data as dl
    charge_fn = charge_fn or (lambda tk: dl.load_yf(tk, years=3))
    ib = connecte(port)
    try:
        compte = resume_compte(ib)
        pos = controle_sorties(positions(ib), charge_fn)
    finally:
        ib.disconnect()
    return {"compte": compte, "positions": pos,
            "mode": "PAPIER" if port == PORT_PAPIER else "REEL"}


def rapport(port=PORT_PAPIER) -> None:
    """    py -m equity_scanner.portefeuille"""
    try:
        e = etat(port)
    except Exception as exc:
        print(f"\n  Connexion impossible sur le port {port} : "
              f"{type(exc).__name__}: {exc}")
        print("\n  A verifier, dans l'ordre :")
        print("    1. TWS ou IB Gateway est bien LANCE et connecte")
        print("    2. l'API est activee (Settings > API > Enable Socket Clients)")
        print("    3. le port correspond au programme utilise :")
        print("         TWS         papier 7497   reel 7496")
        print("         IB Gateway  papier 4002   reel 4001")
        print("       -> py -m equity_scanner.portefeuille --port 4002")
        return

    c = e["compte"]
    dev = c.get("devise", "")
    print(f"\n  COMPTE {e['mode']}")
    print(f"    valeur nette      {c.get('NetLiquidation', 0):,.0f} {dev}")
    print(f"    liquidites        {c.get('TotalCashValue', 0):,.0f} {dev}")
    print(f"    disponible        {c.get('AvailableFunds', 0):,.0f} {dev}")
    print(f"    plus-value latente {c.get('UnrealizedPnL', 0):+,.0f} {dev}")

    pos = e["positions"]
    if not pos:
        print("\n  Aucune position en actions.\n")
        return
    print(f"\n  {len(pos)} POSITION(S)")
    print(f"    {'TITRE':<12}{'QTE':>7}{'MOYEN':>10}{'COURS':>10}"
          f"{'P&L':>11}{'':>3}VERDICT")
    for p in sorted(pos, key=lambda x: -x.n_sorties):
        print(f"    {p.ticker:<12}{p.quantite:>7.0f}{p.prix_moyen:>10.2f}"
              f"{p.cours:>10.2f}{p.pnl_pct:>10.1f}%   {p.verdict}")
        actives = [k for k, v in p.sorties.items() if v]
        if actives:
            print(f"                 -> {', '.join(actives)}")
        if p.erreur:
            print(f"                 -> {p.erreur}")
    print("\n  Lecture seule. Aucun ordre n'est passe par ce programme.\n")


if __name__ == "__main__":
    import argparse
    a = argparse.ArgumentParser()
    a.add_argument("--mode", choices=list(PORTS), default="tws-papier",
                   help="quel programme et quel compte")
    a.add_argument("--port", type=int, default=None,
                   help="port explicite, prioritaire sur --mode")
    a.add_argument("--reel", action="store_true", help="raccourci pour tws-reel")
    o = a.parse_args()
    port = o.port or (PORT_REEL if o.reel else PORTS[o.mode])
    print(f"  Connexion sur le port {port} "
          f"({'REEL' if port in (PORT_REEL, PORT_GW_REEL) else 'PAPIER'})")
    rapport(port)
