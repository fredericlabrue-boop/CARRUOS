"""Le compte IBKR, lu en direct. En LECTURE SEULE — et c'est verifiable.

« Je n'acheterai ni ne vendrai sur CARRUOS, mais sur IBKR. C'est pour
etre plus reactif. » Ce module fait donc une seule chose : lire le
compte, en continu, et le poser a cote de ce que CARRUOS sait deja.

Trois verrous contre un ordre passe par erreur
----------------------------------------------
Une promesse ne suffit pas, surtout pas sur un compte d'argent reel.

1. **La connexion est ouverte en `readonly=True`.** C'est le drapeau de
   l'API d'IBKR elle-meme : une session ouverte ainsi ne peut pas
   transmettre d'ordre, TWS les refuse. On peut ajouter le sien cote
   TWS — « Read-Only API », dans les reglages de l'API — et il vaut
   mieux le faire : deux verrous independants valent mieux qu'un.

2. **Aucune fonction d'ordre n'est appelee dans ce fichier.** Ni
   `placeOrder`, ni `cancelOrder`, ni la construction d'un objet
   `Order`. Pas « on ne s'en sert pas » : elles n'y sont pas.

3. **Un test le prouve.** `test_moteur` lit ce fichier comme un arbre
   syntaxique, refuse tout appel ou import d'un nom de la liste
   `ORDRES_INTERDITS`, et exige `readonly=True` sur la connexion. Il
   verifie aussi qu'aucun autre fichier du programme n'importe la
   bibliotheque IBKR : ce module est la seule porte.

Ce que « temps reel » veut dire ici
-----------------------------------
IBKR ne donne un cours en temps reel que si le compte a l'abonnement de
donnees de la place concernee. Sans lui, il donne un cours DIFFERE de
15 a 20 minutes, ou un cours FIGE hors seance. Afficher un cours
differe sans le dire serait mentir sur la seule chose qui compte ici,
la fraicheur : chaque cours porte donc son TYPE, tel que TWS le
declare, en toutes lettres a cote du chiffre.

Le flux « compte » d'IBKR — valeurs de portefeuille, plus-values
latentes — ne se met a jour qu'environ toutes les trois minutes. Pour
etre reellement reactif, chaque ligne est donc aussi abonnee a son
cours (tick par tick) et a son P&L du jour (`reqPnLSingle`), qui eux
suivent le marche.

Ce qui n'est PAS ici
--------------------
Aucun conseil, aucun signal, aucun « il faudrait vendre ». Le module
lit des faits et en rapproche deux autres, deja declares par vous : le
stop que vous avez inscrit dans le registre, et les lignes que le
registre connait. « Le cours est sous le stop que vous avez ecrit » est
un fait ; ce que vous en faites se decide sur IBKR.

Rien n'est stocke d'autre que l'adresse de TWS, son port et un numero
de client, dans `~/.carruos/ibkr.json`. Aucun identifiant, aucun mot de
passe : c'est TWS qui tient la session, CARRUOS ne la voit jamais.
"""

from __future__ import annotations

import asyncio
import json
import math
import threading
import time
from pathlib import Path

DOSSIER = Path.home() / ".carruos"
FICHIER = DOSSIER / "ibkr.json"

# Les noms d'API qui passent, modifient ou annulent un ordre. Aucun ne
# doit apparaitre dans ce fichier — `test_moteur` le verifie sur l'arbre
# syntaxique. La liste est large exprès : mieux vaut refuser un nom
# inoffensif que laisser passer celui qui ne l'est pas.
ORDRES_INTERDITS = frozenset({
    "placeOrder", "cancelOrder", "reqGlobalCancel", "cancelAllOrders",
    "modifyOrder", "bracketOrder", "oneCancelsAll", "whatIfOrder",
    "whatIfOrderAsync", "exerciseOptions",
    "Order", "MarketOrder", "LimitOrder", "StopOrder", "StopLimitOrder",
    "TrailingStopOrder", "Trade",
})

# Les ports usuels. Le PAPIER et le REEL ne sont pas sur le meme port :
# se tromper de port, c'est regarder un autre compte que celui qu'on
# croit — le libelle le dit donc en clair.
PORTS = (
    (7497, "TWS — compte de simulation"),
    (7496, "TWS — compte réel"),
    (4002, "IB Gateway — compte de simulation"),
    (4001, "IB Gateway — compte réel"),
)

DEFAUT = {"hote": "127.0.0.1", "port": 7497, "client": 71, "auto": False}

# Le type de cours tel que TWS le declare (champ `marketDataType`).
TYPES_COURS = {
    1: ("reel", "TEMPS RÉEL"),
    2: ("fige", "FIGÉ"),
    3: ("differe", "DIFFÉRÉ"),
    4: ("differe_fige", "DIFFÉRÉ FIGÉ"),
}

# Les valeurs du compte qu'on affiche, et leur nom francais.
CHAMPS_COMPTE = (
    ("NetLiquidation", "Valeur nette"),
    ("TotalCashValue", "Liquidités"),
    ("GrossPositionValue", "Valeur des positions"),
    ("BuyingPower", "Pouvoir d'achat"),
    ("AvailableFunds", "Fonds disponibles"),
    ("ExcessLiquidity", "Excédent de liquidité"),
    ("MaintMarginReq", "Marge de maintien"),
)

# Attente entre deux tentatives de reconnexion, en secondes. TWS se
# relance tout seul une fois par jour : sans reconnexion automatique,
# l'onglet serait mort chaque matin sans rien dire.
REPRISE = (3, 6, 15, 30, 60)


# ---------------------------------------------------------------------
# D'un contrat IBKR a un ticker CARRUOS
# ---------------------------------------------------------------------
#
# IBKR nomme une action par (symbole, place, devise). CARRUOS, comme
# Yahoo, par un ticker suffixe : LVMH est « MC » sur SBF chez IBKR et
# « MC.PA » ici. La table est ECRITE D'AVANCE ; une place absente ne se
# devine pas — la ligne s'affiche alors avec son nom IBKR et la mention
# qu'elle n'a pas de correspondance, plutot qu'avec un ticker invente
# qui ouvrirait le graphique d'un autre titre.
PLACES = {
    # Etats-Unis : pas de suffixe.
    "NASDAQ": "", "NYSE": "", "ARCA": "", "AMEX": "", "BATS": "",
    "ISLAND": "", "IEX": "", "NYSENAT": "", "PINK": "",
    # Europe
    "SBF": ".PA", "AEB": ".AS", "ENEXT.BE": ".BR", "BVL": ".LS",
    "IBIS": ".DE", "IBIS2": ".DE", "XETRA": ".DE", "FWB": ".F",
    "FWB2": ".F", "GETTEX": ".DE", "TGATE": ".DE",
    "LSE": ".L", "LSEETF": ".L",
    "BVME": ".MI", "BVME.ETF": ".MI",
    "BM": ".MC",
    "EBS": ".SW", "SWX": ".SW",
    "SFB": ".ST", "CPH": ".CO", "OSE": ".OL", "HEX": ".HE",
    "VSE": ".VI", "WSE": ".WA",
    # Ailleurs
    "TSE": ".TO", "VENTURE": ".V", "ASX": ".AX", "SEHK": ".HK",
    "TSEJ": ".T",
}


def vers_ticker(symbole: str, place: str, devise: str = "",
                genre: str = "STK") -> str | None:
    """Le ticker CARRUOS d'un contrat IBKR, ou None s'il n'est pas sur.

    Seules les actions et les ETF ont un graphique ici : une option ou
    un contrat a terme rend None, et c'est voulu.
    """
    if genre not in ("STK", "ETF"):
        return None
    sym = (symbole or "").strip().upper()
    if not sym:
        return None
    pl = (place or "").strip().upper()
    if pl not in PLACES:
        # « SMART » seul ne dit pas la place. En dollars, c'est une
        # cotation americaine dans l'immense majorite des cas ; dans
        # une autre devise, on ne devine pas.
        if pl in ("", "SMART") and (devise or "").upper() == "USD":
            suf = ""
        else:
            return None
    else:
        suf = PLACES[pl]
    # Classe d'action : « BRK B » chez IBKR, « BRK-B » ici.
    sym = sym.replace(" ", "-")
    if suf == ".HK" and sym.isdigit():
        sym = sym.zfill(4)
    return sym + suf


# ---------------------------------------------------------------------
# Le rapprochement avec ce que CARRUOS sait deja
# ---------------------------------------------------------------------

def rapproche(lignes: list[dict], registre: list[dict]) -> dict:
    """Ce qui differe entre le compte IBKR et le registre local.

    Trois listes, trois faits : les lignes que le compte a et que le
    registre ignore, celles que le registre croit tenir et que le compte
    n'a plus, et celles dont la quantite differe. Le registre porte le
    STOP que vous avez choisi ; sans ce rapprochement, un stop inscrit
    sur une ligne vendue depuis continuerait de s'afficher.
    """
    reg = {(r.get("ticker") or "").upper(): r for r in registre or []}
    chez_ibkr = {}
    for l in lignes or []:
        tk = l.get("ticker")
        if tk:
            chez_ibkr[tk] = l
    absents_registre = sorted(t for t in chez_ibkr if t not in reg)
    absents_ibkr = sorted(t for t in reg if t not in chez_ibkr)
    ecarts = []
    for t in sorted(set(chez_ibkr) & set(reg)):
        qi = float(chez_ibkr[t].get("quantite") or 0)
        qr = float(reg[t].get("quantite") or 0)
        if abs(qi - qr) > 1e-9:
            ecarts.append({"ticker": t, "ibkr": qi, "registre": qr})
    sans_ticker = sorted(l.get("libelle", "?") for l in lignes or []
                         if not l.get("ticker"))
    return {"absents_registre": absents_registre,
            "absents_ibkr": absents_ibkr,
            "ecarts_quantite": ecarts,
            "sans_correspondance": sans_ticker,
            "accord": not (absents_registre or absents_ibkr or ecarts)}


def franchissements(lignes: list[dict], registre: list[dict]) -> list[dict]:
    """Les lignes dont le cours est passe sous le stop INSCRIT.

    Le stop n'est pas calcule ici : c'est celui que vous avez ecrit dans
    le registre. Le comparer au cours est un fait, pas un conseil — et
    le type du cours voyage avec, parce qu'un cours differe de quinze
    minutes sous un stop n'est pas la meme information qu'un cours en
    temps reel sous ce stop.
    """
    reg = {(r.get("ticker") or "").upper(): r for r in registre or []}
    out = []
    for l in lignes or []:
        tk = l.get("ticker")
        r = reg.get(tk or "")
        if not r or not r.get("stop"):
            continue
        c = l.get("cours")
        if c is None:
            continue
        stop = float(r["stop"])
        sens = 1 if float(l.get("quantite") or 0) >= 0 else -1
        # Vendeur a decouvert : le stop est AU-DESSUS du cours.
        if (sens > 0 and c <= stop) or (sens < 0 and c >= stop):
            out.append({"ticker": tk, "cours": c, "stop": stop,
                        "ecart_pct": round((c / stop - 1.0) * 100.0, 2),
                        "type_cours": l.get("type_cours_libelle", "")})
    return out


def consigne(fills, fichier: Path | None = None, vus: set | None = None,
             apres=None) -> int:
    """Ecrit vos executions dans la memoire de CARRUOS. Rend le nombre
    de nouvelles lignes.

    L'API d'IBKR ne rend que les executions du JOUR (sept jours au plus
    si TWS est regle pour les garder). Pour qu'elles servent un jour a
    comparer vos decisions a celles du programme, il faut donc les
    ecrire au fil de l'eau : c'est ce que fait cette fonction, a chaque
    tour de la liaison. Fichier en ajout seul, jamais reecrit, et
    dedoublonne par l'identifiant d'execution d'IBKR.

    C'est une LECTURE de ce qui a deja ete execute sur IBKR. Rien ne
    part vers le compte.

    `apres`, s'il est donne, recoit les lignes nouvellement ecrites :
    l'application s'en sert pour relever l'etat du programme a la veille
    de chaque ordre, pendant que c'est encore le jour de l'ordre.
    """
    from . import memoire as me
    f = fichier or me.EXECUTIONS
    if vus is None:
        vus = {r.get("id") for r in me.lit_executions(f)}
    n = 0
    lignes = []
    for fl in fills or []:
        ex = getattr(fl, "execution", None)
        c = getattr(fl, "contract", None)
        if ex is None or c is None:
            continue
        ident = str(getattr(ex, "execId", "") or "")
        if not ident or ident in vus:
            continue
        vus.add(ident)
        place = getattr(c, "primaryExchange", "") or getattr(c, "exchange", "")
        cote = str(getattr(ex, "side", "")).upper()
        quand = getattr(fl, "time", None) or getattr(ex, "time", None)
        lignes.append({
            "id": ident,
            "quand": quand.isoformat() if hasattr(quand, "isoformat") else str(quand),
            "ticker": vers_ticker(getattr(c, "symbol", ""), place,
                                  getattr(c, "currency", ""),
                                  getattr(c, "secType", "STK")),
            "symbole": getattr(c, "symbol", ""), "place": place,
            "devise": getattr(c, "currency", ""),
            "sens": "achat" if cote in ("BOT", "BUY") else
                    ("vente" if cote in ("SLD", "SELL") else cote.lower()),
            "quantite": _num(getattr(ex, "shares", None)),
            "prix": _num(getattr(ex, "price", None)),
            "compte": getattr(ex, "acctNumber", ""),
        })
    if lignes:
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fp:
            for l in lignes:
                fp.write(json.dumps(l, ensure_ascii=False) + "\n")
        n = len(lignes)
        if apres is not None:
            try:
                apres(lignes)
            except Exception as exc:
                print(f"  ibkr : releve apres execution impossible ({exc})")
    return n


def sans_fraicheur(lignes: list[dict]) -> list[str]:
    """Les lignes dont le cours n'est PAS en temps reel. Dit a l'ecran."""
    return sorted(l.get("ticker") or l.get("libelle", "?")
                  for l in lignes or [] if l.get("type_cours") != "reel")


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

def config() -> dict:
    c = dict(DEFAUT)
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            c.update({k: d[k] for k in DEFAUT if k in d})
    except Exception:
        pass
    return c


def pose_config(hote=None, port=None, client=None, auto=None) -> dict:
    c = config()
    if hote:
        c["hote"] = str(hote).strip()
    if port:
        c["port"] = int(port)
    if client:
        c["client"] = int(client)
    if auto is not None:
        c["auto"] = bool(auto)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(c, indent=1), encoding="utf-8")
    return c


def libelle_port(port: int) -> str:
    return dict(PORTS).get(int(port), "port personnalisé")


# ---------------------------------------------------------------------
# La liaison : un fil d'execution qui tient la session et la surveille
# ---------------------------------------------------------------------
#
# Le serveur HTTP de CARRUOS repond sur plusieurs fils ; la bibliotheque
# IBKR, elle, vit dans UNE boucle d'evenements. On lui donne donc son
# propre fil, qui possede la session, et les pages ne font que lire une
# photo du compte, protegee par un verrou. Aucune page n'appelle IBKR
# directement : il n'y a qu'une seule porte, et elle est ici.

def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _diagnostic(exc: Exception, port: int) -> str:
    """Ce qui a echoue, dit pour quelqu'un qui n'est pas informaticien."""
    t = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, ConnectionRefusedError) or "refused" in t.lower():
        return (f"Rien n'écoute sur le port {port}. TWS ou IB Gateway "
                f"n'est pas lancé, ou l'API n'est pas activée : dans TWS, "
                f"Fichier → Configuration globale → API → Paramètres, "
                f"cocher « Enable ActiveX and Socket Clients », et vérifier "
                f"que le port est bien {port}.")
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in t.lower():
        return ("TWS a été joint mais n'a pas répondu à temps. Une fenêtre "
                "d'autorisation est peut-être ouverte dans TWS : il faut "
                "accepter la connexion entrante.")
    if "client id" in t.lower() or "326" in t:
        return ("Ce numéro de client est déjà pris par un autre programme "
                "branché sur TWS. Changez-le (n'importe quel nombre libre).")
    return t


# Une classe de remplacement pour les tests, qui imite l'API d'IBKR sans
# TWS. Meme principe que `data.load_yf` : le module de test remplace la
# source, le code qui s'en sert ne change pas d'une ligne.
FABRIQUE = None

# Ce que l'application veut faire de chaque execution nouvellement
# consignee (relever l'etat du programme a la veille de l'ordre). Pose
# par `app.main()` ; ce module n'a pas a connaitre l'application.
APRES_EXECUTION = None


class Liaison:
    """La session IBKR, tenue par un fil a part."""

    def __init__(self):
        self._verrou = threading.Lock()
        self._fil = None
        self._arret = threading.Event()
        self._photo = {"etat": "deconnecte", "message": "",
                       "lignes": [], "compte": {}, "pnl": {},
                       "numero": "", "simulation": None, "quand": None}

    # --- lecture, depuis n'importe quel fil -------------------------
    def photo(self) -> dict:
        with self._verrou:
            return json.loads(json.dumps(self._photo, default=str))

    def _pose(self, **kw):
        with self._verrou:
            self._photo.update(kw)

    # --- commande ------------------------------------------------------
    def demarre(self, hote: str, port: int, client: int) -> None:
        self.arrete()
        self._arret = threading.Event()
        # L'adresse de la session EN COURS voyage avec la photo. La page
        # affichait le reglage enregistre a cote de l'etat de la session :
        # un selecteur sur « 7497 — simulation » a cote de « CONNECTE —
        # COMPTE REEL », c'est exactement la confusion a rendre impossible.
        self._pose(etat="connexion", message=f"Connexion à {hote}:{port}…",
                   lignes=[], compte={}, pnl={}, hote=hote, port=int(port),
                   libelle_port=libelle_port(port))
        self._fil = threading.Thread(
            target=self._tourne, args=(hote, int(port), int(client),
                                       self._arret),
            name="carruos-ibkr", daemon=True)
        self._fil.start()

    def arrete(self) -> None:
        if self._fil and self._fil.is_alive():
            self._arret.set()
            self._fil.join(timeout=5)
        self._fil = None
        self._pose(etat="deconnecte", message="Déconnecté.")

    def actif(self) -> bool:
        return bool(self._fil and self._fil.is_alive())

    # --- le fil ---------------------------------------------------------
    def _tourne(self, hote, port, client, arret):
        asyncio.set_event_loop(asyncio.new_event_loop())
        IB = FABRIQUE
        if IB is None:
            try:
                from ib_async import IB
            except ImportError:
                try:
                    from ib_insync import IB       # ancien nom du meme outil
                except ImportError:
                    self._pose(etat="erreur", message=(
                        "La bibliothèque IBKR n'est pas installée. Dans une "
                        "invite de commandes : py -m pip install ib_async"))
                    return

        essai = 0
        while not arret.is_set():
            ib = IB()
            try:
                # Premier verrou : la session elle-meme ne peut pas
                # transmettre d'ordre.
                ib.connect(hote, port, clientId=client, readonly=True,
                           timeout=8)
            except Exception as exc:
                attente = REPRISE[min(essai, len(REPRISE) - 1)]
                self._pose(etat="erreur",
                           message=_diagnostic(exc, port)
                           + f" Nouvel essai dans {attente} s.")
                essai += 1
                if arret.wait(attente):
                    break
                continue
            essai = 0
            try:
                self._suit(ib, arret, hote, port)
            except Exception as exc:
                self._pose(etat="erreur",
                           message=f"Session interrompue : {_diagnostic(exc, port)}")
            finally:
                try:
                    ib.disconnect()
                except Exception:
                    pass
            if not arret.is_set():
                self._pose(etat="connexion",
                           message="Session perdue — TWS s'est peut-être "
                                   "relancé. Reconnexion…")
                arret.wait(REPRISE[0])

    def _suit(self, ib, arret, hote="", port=0):
        """La boucle de lecture, tant que la session tient."""
        comptes = ib.managedAccounts() or []
        numero = comptes[0] if comptes else ""
        # Les comptes de simulation IBKR commencent par « DU » (ou « DF »
        # pour un conseiller). Le dire en gros evite de lire un compte en
        # croyant lire l'autre.
        simulation = numero.upper().startswith(("DU", "DF"))
        # Type 3 : le meilleur disponible. Temps reel si l'abonnement
        # existe, differe sinon — et le type recu est lu tick par tick.
        ib.reqMarketDataType(3)
        pnl_compte = ib.reqPnL(numero) if numero else None
        cours, pnl_ligne = {}, {}
        vus_ex = None           # identifiants deja consignes, lus une fois
        self._pose(etat="connecte", numero=numero, simulation=simulation,
                   message=f"Session ouverte en lecture seule sur "
                           f"{hote}:{port}.")

        while not arret.is_set() and ib.isConnected():
            items = ib.portfolio(numero) if numero else ib.portfolio()
            # Une ligne achetee sur IBKR pendant la session apparait ici :
            # on l'abonne a son cours et a son P&L au passage.
            for it in items:
                cid = it.contract.conId
                if cid not in cours:
                    try:
                        cours[cid] = ib.reqMktData(it.contract)
                    except Exception:
                        cours[cid] = None
                if cid not in pnl_ligne and numero:
                    try:
                        pnl_ligne[cid] = ib.reqPnLSingle(numero, "", cid)
                    except Exception:
                        pnl_ligne[cid] = None
            lignes = [self._ligne(it, cours.get(it.contract.conId),
                                  pnl_ligne.get(it.contract.conId))
                      for it in items]
            compte = {}
            for v in ib.accountValues(numero) if numero else ib.accountValues():
                if v.tag in dict(CHAMPS_COMPTE) and v.currency not in ("", None):
                    if v.currency == "BASE" or v.tag not in compte:
                        compte[v.tag] = {"valeur": _num(v.value),
                                         "devise": v.currency}
            pnl = {}
            if pnl_compte is not None:
                pnl = {"jour": _num(pnl_compte.dailyPnL),
                       "latent": _num(pnl_compte.unrealizedPnL),
                       "realise": _num(pnl_compte.realizedPnL)}
            # Vos executions, pour la memoire. Une erreur ici ne doit
            # jamais couper la lecture du compte.
            try:
                if vus_ex is None:
                    from . import memoire as me
                    vus_ex = {r.get("id") for r in me.lit_executions()}
                fl = ib.fills() if hasattr(ib, "fills") else []
                consigne(fl, vus=vus_ex, apres=APRES_EXECUTION)
            except Exception:
                pass
            self._pose(lignes=lignes, compte=compte, pnl=pnl,
                       quand=time.strftime("%H:%M:%S"))
            ib.sleep(1.0)

    @staticmethod
    def _ligne(it, tk, pnl) -> dict:
        c = it.contract
        genre = getattr(c, "secType", "STK")
        place = getattr(c, "primaryExchange", "") or getattr(c, "exchange", "")
        ticker = vers_ticker(c.symbol, place, c.currency, genre)
        prix, t_cle, t_lib = None, "compte", "FLUX DU COMPTE (≈ 3 MIN)"
        if tk is not None:
            try:
                p = _num(tk.marketPrice())
            except Exception:
                p = None
            if p is not None and p > 0:
                prix = p
                t_cle, t_lib = TYPES_COURS.get(
                    int(getattr(tk, "marketDataType", 0) or 0),
                    ("inconnu", "TYPE INCONNU"))
        if prix is None:
            prix = _num(it.marketPrice)
        return {
            "ticker": ticker,
            "libelle": f"{c.symbol} ({place or '?'}, {c.currency})",
            "symbole": c.symbol, "place": place, "devise": c.currency,
            "genre": genre, "conid": c.conId,
            "quantite": _num(it.position),
            "prix_revient": _num(it.averageCost),
            "cours": prix,
            "type_cours": t_cle, "type_cours_libelle": t_lib,
            "valeur": _num(it.marketValue),
            "latent": _num(it.unrealizedPNL),
            "pnl_jour": _num(getattr(pnl, "dailyPnL", None)) if pnl else None,
        }


# La liaison du programme : une seule, partagee par toutes les pages.
LIAISON = Liaison()


def demarre_auto() -> None:
    """Au lancement du programme : se rebrancher si c'etait voulu."""
    c = config()
    if c.get("auto"):
        LIAISON.demarre(c["hote"], c["port"], c["client"])


def etat(registre: list[dict] | None = None) -> dict:
    """Tout ce que la page affiche, en une photo."""
    p = LIAISON.photo()
    c = config()
    p["config"] = {**c, "libelle_port": libelle_port(c["port"])}
    p["ports"] = [{"port": n, "libelle": l} for n, l in PORTS]
    p["champs"] = [{"cle": k, "libelle": l} for k, l in CHAMPS_COMPTE]
    reg = registre or []
    p["rapprochement"] = rapproche(p.get("lignes", []), reg)
    p["franchissements"] = franchissements(p.get("lignes", []), reg)
    p["sans_fraicheur"] = sans_fraicheur(p.get("lignes", []))
    p["stops"] = {(r.get("ticker") or "").upper(): r.get("stop")
                  for r in reg if r.get("stop")}
    p["rappel"] = RAPPEL
    return p


RAPPEL = (
    "CARRUOS lit votre compte ; il ne peut pas y passer d'ordre. La "
    "session est ouverte en lecture seule, aucune fonction d'ordre "
    "n'existe dans le code, et un test le vérifie à chaque version. "
    "Pour acheter ou vendre : IBKR.")
