"""Le compte IBKR en ligne de commande, en LECTURE SEULE.

    py -m equity_scanner.portefeuille               # TWS, simulation
    py -m equity_scanner.portefeuille --port 7496   # TWS, compte reel
    py -m equity_scanner.portefeuille --mode gateway-papier

Ce module ne parle PAS a IBKR lui-meme. Il passe par `ibkr.py`, la seule
porte du programme vers le compte — et une porte qui ne s'ouvre qu'en
lecture. Il en avait une autre, a lui, jusqu'a cette version ; elle
etait bien en `readonly=True`, mais deux portes font deux verrous a
surveiller, et `test_moteur` refuse desormais toute seconde porte.

La reecriture a corrige deux defauts de l'ancienne version, trouves en
la relisant pour la brancher :

- une place absente de sa petite table retombait sur un ticker SANS
  suffixe, c'est-a-dire americain : une ligne cotee sur une place non
  prevue devenait un autre titre, et son controle de sortie portait sur
  le mauvais cours. `ibkr.vers_ticker()` ne devine pas, il le dit ;
- le libelle du compte se deduisait du port — 7497 « PAPIER », tout le
  reste « REEL » — si bien qu'IB Gateway en simulation (port 4002)
  s'affichait REEL. Il se lit maintenant sur le numero de compte, qui
  est la seule source sure.

Et une troisieme chose, qui n'etait pas un defaut de code mais de
principe : chaque ligne portait un verdict CONSERVER / SURVEILLER /
SORTIE. C'est exactement l'avis « garder / vendre » que le projet
refuse d'afficher. Le rapport donne maintenant le COMPTE — combien des
quatre conditions de sortie de la specification sont actives, et
lesquelles — et rappelle que la specification ferme a la premiere
atteinte. Citer sa propre regle n'est pas un verdict ; ecrire « vends »
en serait un.
"""

from __future__ import annotations

import time

from . import ibkr as ik

PORTS = {"tws-papier": 7497, "tws-reel": 7496,
         "gateway-papier": 4002, "gateway-reel": 4001}

# Le temps laisse a TWS pour ouvrir la session et livrer le portefeuille.
ATTENTE_MAX = 20.0


def lit_compte(port: int, hote: str = "127.0.0.1", client: int = 72) -> dict:
    """Ouvre une session en lecture seule, attend la premiere photo, ferme.

    Numero de client distinct de celui de l'onglet IBKR (71) : les deux
    peuvent tourner en meme temps sans que TWS refuse le second.
    """
    liaison = ik.Liaison()
    liaison.demarre(hote, port, client)
    t0, photo = time.time(), liaison.photo()
    try:
        while time.time() - t0 < ATTENTE_MAX:
            time.sleep(0.25)
            photo = liaison.photo()
            if photo.get("etat") == "connecte" and photo.get("quand"):
                break
            if photo.get("etat") == "erreur" and time.time() - t0 > 3:
                break
    finally:
        liaison.arrete()
    return photo


def conditions_sortie(lignes: list[dict]) -> dict:
    """L'etat des quatre conditions de sortie, ligne par ligne.

    Rend, pour chaque ticker CARRUOS, les conditions et leur etat — ou
    le motif pour lequel on n'a pas pu les evaluer. Jamais de verdict.
    """
    from . import cache as ch
    from .indicators import enrich
    from .rules import evaluate_exit, market_regime_ok

    out = {}
    try:
        bench_brut = ch.charge("SPY", annees=3)
        marche_ok = bool(market_regime_ok(enrich(bench_brut)))
    except Exception as exc:
        return {"_erreur": f"indice de reference indisponible : {exc}"}
    for l in lignes:
        tk = l.get("ticker")
        if not tk:
            continue
        try:
            d = enrich(ch.charge(tk, annees=3),
                       bench_close=bench_brut["close"])
            if len(d) < 220:
                out[tk] = {"erreur": f"historique trop court ({len(d)} séances)"}
                continue
            out[tk] = {"conditions": evaluate_exit(d, marche_ok)}
        except Exception as exc:
            out[tk] = {"erreur": f"{type(exc).__name__}: {exc}"}
    return out


def rapport(port: int) -> None:
    photo = lit_compte(port)
    if photo.get("etat") != "connecte":
        print(f"\n  {photo.get('message') or 'Connexion impossible.'}\n")
        return

    print(f"\n  COMPTE {photo.get('numero')} — "
          f"{'SIMULATION' if photo.get('simulation') else 'RÉEL'}")
    lib = dict(ik.CHAMPS_COMPTE)
    for cle, v in (photo.get("compte") or {}).items():
        dev = "" if v.get("devise") == "BASE" else v.get("devise", "")
        if v.get("valeur") is not None:
            print(f"    {lib.get(cle, cle):<24}{v['valeur']:>14,.0f} {dev}")

    lignes = photo.get("lignes") or []
    if not lignes:
        print("\n  Aucune position.\n")
        return
    etats = conditions_sortie(lignes)
    print(f"\n  {len(lignes)} POSITION(S)")
    print(f"    {'TITRE':<12}{'QTÉ':>7}{'PRU':>10}{'COURS':>10}  "
          f"{'TYPE DE COURS':<16}CONDITIONS DE SORTIE")
    for l in lignes:
        nom = l.get("ticker") or l.get("libelle", "?")
        e = etats.get(l.get("ticker") or "", {})
        if e.get("conditions"):
            actives = [k for k, v in e["conditions"].items() if v]
            etat = f"{len(actives)} sur {len(e['conditions'])} actives"
        elif e.get("erreur"):
            actives, etat = [], e["erreur"]
        else:
            actives, etat = [], "sans correspondance sûre avec un ticker"
        print(f"    {nom:<12}{(l.get('quantite') or 0):>7.0f}"
              f"{(l.get('prix_revient') or 0):>10.2f}"
              f"{(l.get('cours') or 0):>10.2f}  "
              f"{l.get('type_cours_libelle', ''):<16}{etat}")
        for a in actives:
            print(f"                 · {a}")
    if etats.get("_erreur"):
        print(f"\n  {etats['_erreur']}")
    print("\n  La spécification ferme à la PREMIÈRE condition atteinte.")
    print(f"  {ik.RAPPEL}\n")


if __name__ == "__main__":
    import argparse
    a = argparse.ArgumentParser(description="Le compte IBKR, en lecture seule")
    a.add_argument("--mode", choices=list(PORTS), default="tws-papier")
    a.add_argument("--port", type=int, default=None,
                   help="port explicite, prioritaire sur --mode")
    o = a.parse_args()
    p = o.port or PORTS[o.mode]
    print(f"  Connexion sur le port {p} ({ik.libelle_port(p)})")
    rapport(p)
