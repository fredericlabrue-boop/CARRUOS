"""CARRUOS BRAIN 2.0 — le titre ET le portefeuille, sous le contrat du majordome.

Ce que la version 29 apportait, et qui est garde : une page qui prend un
titre et une question, et qui met le portefeuille IBKR sous les yeux du
modele, pour qu'on puisse lui parler de ses lignes et pas seulement d'un
titre isole.

Ce qui a ete corrige, mesure a l'appui
--------------------------------------
- Le contexte envoye faisait 70 502 caracteres pour un plafond de 24 000.
  Coupe au caractere pres, il perdait sa FIN — le portefeuille, pose en
  dernier. Le modele ne l'a jamais vu. Le contexte est maintenant construit
  par priorite : la question et le portefeuille d'abord, le dossier du
  titre ensuite, reduit sans etre coupe (`cerveau.compacte`).
- Le numero de compte IBKR partait chez le fournisseur du modele. Il n'est
  plus envoye, ni l'hote, ni le port, ni le numero de client.
- Les faits calcules n'etaient pas affiches : sans cle, la page ne
  montrait que sept amplitudes. Les faits passent d'abord, comme au
  majordome, et restent a l'ecran quoi qu'il arrive au modele.
- Concentration, poids, stops franchis etaient laisses au modele, qui les
  aurait calcules lui-meme — donc invérifiables. Ils sont comptes ICI, et
  le modele n'a plus qu'a les citer.
- Les amplitudes etaient recalculees sur un second telechargement alors
  que le dossier les porte deja, puis classees « du plus grand mouvement ».
  Un classement qui invite a choisir un horizon : la duree de detention
  est une consequence des regles de sortie, le dossier la donne mesuree.
"""

from __future__ import annotations

from . import cerveau as cv
from . import dossier as ds
from .rules import MAX_WEIGHT

# Au-dela, on ne releve pas les conditions de sortie de chaque ligne : il
# faut charger les cours de chacune, et une page ne doit pas attendre.
LIGNES_MAX = 15

# Ce qui ne part JAMAIS chez le fournisseur du modele.
SECRETS = ("numero", "hote", "port", "client", "config", "conid")

RAPPEL_PORTEFEUILLE = (
    "Les poids sont des parts de vos POSITIONS, hors liquidités, calculées à "
    "l'intérieur de chaque devise : sans taux de change, additionner des "
    "euros et des dollars donnerait un chiffre faux. CARRUOS lit le compte, "
    "il n'y passe aucun ordre.")


def _num(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _conditions(tickers: list[str]) -> dict:
    """Les quatre conditions de sortie et le dernier cours, par titre."""
    from . import cache as ch
    from . import memoire as me
    from .indicators import enrich
    from .rules import evaluate_exit, market_regime_ok
    reperes, out = {}, {}
    for tk in tickers[:LIGNES_MAX]:
        try:
            b = me.bench_de(tk)
            if b not in reperes:
                bb = ch.charge(b, annees=3)
                reperes[b] = (bb, bool(market_regime_ok(enrich(bb))))
            bb, ok = reperes[b]
            d = enrich(ch.charge(tk, annees=3), bench_close=bb["close"])
            if len(d) < 220:
                out[tk] = {"erreur": f"historique trop court ({len(d)} séances)"}
                continue
            cond = evaluate_exit(d, ok)
            out[tk] = {"conditions": cond,
                       "actives": [k for k, v in cond.items() if v],
                       "cloture": round(float(d["close"].iloc[-1]), 4),
                       "date": str(d.index[-1].date())}
        except Exception as exc:
            out[tk] = {"erreur": f"{type(exc).__name__}: {exc}"}
    return out


def faits_portefeuille(photo: dict | None = None,
                       registre: list[dict] | None = None,
                       conditions: bool = True) -> dict:
    """Le portefeuille, COMPTE par le programme.

    Le compte IBKR s'il est branche ; sinon le registre local des
    positions, en le disant. Aucun avis : des poids, des ecarts, des
    conditions actives.
    """
    from . import ibkr
    from . import positions as ps
    reg = ps.charge() if registre is None else registre
    p = ibkr.etat(reg) if photo is None else photo
    branche = p.get("etat") == "connecte"
    if branche:
        brutes = [dict(l) for l in p.get("lignes") or []]
        source = "compte IBKR"
    else:
        brutes = [{"ticker": (r.get("ticker") or "").upper(),
                   "quantite": r.get("quantite"),
                   "prix_revient": r.get("entree"),
                   "devise": None, "cours": None,
                   "type_cours_libelle": "CLÔTURE"}
                  for r in reg if r.get("ticker")]
        source = "registre local (IBKR non branché)"
    stops = {(r.get("ticker") or "").upper(): _num(r.get("stop"))
             for r in reg if r.get("stop")}
    franchis = {f.get("ticker") for f in p.get("franchissements") or []}

    cond = _conditions([l["ticker"] for l in brutes if l.get("ticker")]) \
        if conditions and brutes else {}
    for l in brutes:
        c = cond.get(l.get("ticker") or "", {})
        if l.get("cours") is None and c.get("cloture") is not None:
            l["cours"] = c["cloture"]
        if not l.get("devise") and l.get("ticker"):
            from . import strategie as sg
            l["devise"] = sg.devise_du_titre(l["ticker"])
        if l.get("valeur") is None and l.get("cours") is not None:
            q = _num(l.get("quantite"))
            l["valeur"] = q * l["cours"] if q is not None else None
        if l.get("latent") is None and l.get("valeur") is not None:
            q, pru = _num(l.get("quantite")), _num(l.get("prix_revient"))
            if q is not None and pru is not None:
                l["latent"] = l["valeur"] - q * pru

    totaux: dict = {}
    for l in brutes:
        v = _num(l.get("valeur"))
        if v is not None:
            totaux[l.get("devise") or "?"] = totaux.get(l.get("devise") or "?",
                                                        0.0) + abs(v)
    lignes = []
    for l in brutes:
        tk = l.get("ticker") or ""
        nom = tk or l.get("libelle") or "?"
        dev = l.get("devise") or "?"
        v, lat = _num(l.get("valeur")), _num(l.get("latent"))
        cours, stop = _num(l.get("cours")), stops.get(tk.upper())
        base = (v - lat) if v is not None and lat is not None else None
        c = cond.get(tk, {})
        lignes.append({
            "titre": nom, "devise": dev,
            "quantite": _num(l.get("quantite")),
            "prix_revient": _num(l.get("prix_revient")),
            "cours": cours, "type_cours": l.get("type_cours_libelle"),
            "valeur": None if v is None else round(v, 2),
            "latent": None if lat is None else round(lat, 2),
            "latent_pc": round(lat / abs(base) * 100, 2) if base else None,
            "pnl_jour": _num(l.get("pnl_jour")),
            "poids_pc": (round(abs(v) / totaux[dev] * 100, 1)
                         if v is not None and totaux.get(dev) else None),
            "stop_inscrit": stop,
            "ecart_au_stop_pc": (round((cours / stop - 1) * 100, 2)
                                 if stop and cours else None),
            "sous_le_stop": tk in franchis,
            "conditions_sortie": (f"{len(c['actives'])} sur "
                                  f"{len(c['conditions'])} actives"
                                  if c.get("conditions") else None),
            "conditions_actives": c.get("actives") or [],
            "conditions_erreur": c.get("erreur"),
        })
    lignes.sort(key=lambda x: -(x["poids_pc"] or 0))

    par_devise = {}
    for dev, tot in totaux.items():
        ls = [x for x in lignes if x["devise"] == dev and x["poids_pc"]]
        par_devise[dev] = {
            "lignes": len(ls), "valeur": round(tot, 2),
            "plus_grosse": ls[0]["titre"] if ls else None,
            "poids_plus_grosse_pc": ls[0]["poids_pc"] if ls else None,
            "trois_premieres_pc": round(sum(x["poids_pc"] for x in ls[:3]), 1),
        }
    plafond = MAX_WEIGHT * 100
    # Le plafond de la specification porte sur le capital entier. On ne
    # peut le verifier que si toutes les lignes sont dans UNE devise : avec
    # deux lignes en dollars et deux en euros, chacune depasse 25 % « de sa
    # devise » sans rien dire du portefeuille. La premiere version de ce
    # module les signalait toutes les quatre.
    verifiable = len(par_devise) == 1
    return {
        "ok": True, "source": source, "branche": branche,
        "compte": ("simulation" if p.get("simulation") else "réel")
                  if branche else None,
        "quand": p.get("quand"),
        "message": None if branche else p.get("message"),
        "n_lignes": len(lignes), "lignes": lignes, "par_devise": par_devise,
        "plafond_ligne_pc": plafond,
        "plafond_verifiable": verifiable,
        "au_dessus_du_plafond": [x["titre"] for x in lignes
                                 if verifiable and (x["poids_pc"] or 0) > plafond],
        "sans_stop_inscrit": [x["titre"] for x in lignes
                              if not x["stop_inscrit"]],
        "stops_franchis": [x["titre"] for x in lignes if x["sous_le_stop"]],
        "cours_non_temps_reel": list(p.get("sans_fraicheur") or []),
        "rappel": RAPPEL_PORTEFEUILLE,
    }


def _nf(x, dec=1, suffixe=""):
    if x is None:
        return "—"
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",") + suffixe


def lignes_portefeuille(f: dict) -> list[str]:
    """Les faits du portefeuille en phrases — des gabarits, aucun avis."""
    if not f.get("n_lignes"):
        return [f"Aucune ligne ({f.get('source')})."]
    out = [f"{f['n_lignes']} ligne(s), lues sur le {f['source']}"
           + (f", compte {f['compte']}" if f.get("compte") else "") + "."]
    for dev, g in f["par_devise"].items():
        out.append(f"En {dev} : {g['lignes']} ligne(s). La plus grosse, "
                   f"{g['plus_grosse']}, pèse {_nf(g['poids_plus_grosse_pc'])} % ; "
                   f"les trois premières, {_nf(g['trois_premieres_pc'])} %.")
    if f["au_dessus_du_plafond"]:
        out.append(f"Au-dessus du plafond de {_nf(f['plafond_ligne_pc'], 0)} % "
                   f"par ligne (en part des positions) : "
                   f"{', '.join(f['au_dessus_du_plafond'])}.")
    elif not f.get("plafond_verifiable") and len(f["par_devise"]) > 1:
        out.append(f"{len(f['par_devise'])} devises : sans taux de change, le "
                   f"plafond de {_nf(f['plafond_ligne_pc'], 0)} % par ligne ne "
                   f"se vérifie pas ici.")
    if f["stops_franchis"]:
        out.append("Sous le stop que vous avez inscrit : "
                   + ", ".join(f["stops_franchis"]) + ".")
    if f["sans_stop_inscrit"]:
        out.append("Sans stop inscrit dans le registre : "
                   + ", ".join(f["sans_stop_inscrit"]) + ".")
    if f["cours_non_temps_reel"]:
        out.append("Cours qui ne sont pas en temps réel : "
                   + ", ".join(f["cours_non_temps_reel"]) + ".")
    for x in f["lignes"]:
        if x["conditions_sortie"]:
            act = (" — " + ", ".join(x["conditions_actives"])
                   if x["conditions_actives"] else "")
            out.append(f"{x['titre']} : conditions de sortie "
                       f"{x['conditions_sortie']}{act}.")
    out.append("La spécification ferme une ligne à la PREMIÈRE condition "
               "atteinte.")
    return out


def _sans_secrets(photo_faits: dict) -> dict:
    return {k: v for k, v in photo_faits.items() if k not in SECRETS}


def contexte(question: str, faits_titre: dict | None,
             portefeuille: dict | None) -> dict:
    """Ce que le modele recoit, par ordre de priorite.

    La question et le portefeuille sont proteges : ils ne sont jamais
    retires. Le dossier du titre est reduit s'il le faut, en le disant.
    """
    ctx = {"question": question}
    proteges = ["question"]
    if portefeuille:
        ctx["portefeuille"] = _sans_secrets(portefeuille)
        proteges.append("portefeuille")
    if faits_titre and faits_titre.get("ok"):
        for k, v in faits_titre.items():
            if k not in ctx:
                ctx[k] = v
        proteges += ["ticker", "cours", "date", "devise", "interet",
                     "revue", "position", "rappel"]
    ctx["_proteges"] = proteges
    return ctx


def analyse(ticker: str = "", question: str = "",
            historique=None, avec_modele: bool = True) -> dict:
    """BRAIN 2.0 : les faits d'abord, calcules ici ; le modele ensuite."""
    question = (question or "Analyse complète").strip()
    tk = (ticker or "").strip().upper()
    faits, deterministe = None, None
    if tk:
        try:
            faits = ds.constitue(tk)
            deterministe = ds.repond(question, faits)
        except Exception as exc:
            deterministe = {"ok": False, "ticker": tk,
                            "erreur": f"{type(exc).__name__} : {exc}"}
    try:
        portef = faits_portefeuille()
    except Exception as exc:
        portef = {"ok": False, "erreur": f"{type(exc).__name__} : {exc}",
                  "n_lignes": 0}
    out = {"ok": True, "ticker": tk, "question": question,
           "faits": deterministe,
           "portefeuille": portef,
           "portefeuille_lignes": (lignes_portefeuille(portef)
                                   if portef.get("ok") else []),
           "horizons": (faits or {}).get("horizons") or [],
           "duree": ((faits or {}).get("profil") or {}).get("duree"),
           "rappel": ds.RAPPEL}
    if not avec_modele or not cv.disponible():
        out["modele"] = {"ok": False, "configure": cv.disponible(),
                         "erreur": "cerveau non configuré"}
        return out
    ctx = contexte(question, faits, portef if portef.get("ok") else None)
    out["modele"] = cv.demande(question, dossier=ctx,
                               historique=historique or [])
    return out
