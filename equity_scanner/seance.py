"""Horaires des places européennes et américaines, en heure de Paris.

CE QUE CE MODULE DIT, ET CE QU'IL NE DIT PAS

Il dit des FAITS : quand chaque place ouvre, quand elle ferme, quand se
tiennent ses fixings d'ouverture et de clôture, si elle est fermée
aujourd'hui pour un jour férié, et combien de temps avant le prochain
événement. Tout est calculé dans le fuseau de la place, donc l'heure
d'été suit toute seule des deux côtés de l'Atlantique — et les deux ne
changent pas d'heure le même week-end, ce qui décale la séance
américaine d'une heure pendant une quinzaine de jours par an.

Il ne dit PAS à quelle heure il vaut mieux acheter. Voir `pourquoi_pas_
de_meilleure_heure()` : ce n'est pas une omission, c'est une réponse.

LE FIXING DE CLOTURE

C'est le seul moment de la journée dont on peut affirmer quelque chose
sans mesure intraday : c'est mécaniquement là que le plus gros volume
d'une séance s'échange, parce que les indices, les ETF et les fonds
indiciels y sont contraints de se caler sur le cours de clôture. Ce
n'est pas un signal — c'est une information de liquidité.

    py -m equity_scanner.seance
    py -m equity_scanner.seance --place paris
"""

from __future__ import annotations

import argparse
import datetime as dt
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")

# La locale de la machine n'est pas garantie francaise : strftime("%A")
# rendait « Tuesday ». On formate a la main.
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi",
         "dimanche")
MOIS = ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "aout", "septembre", "octobre", "novembre", "decembre")


def date_fr(d: dt.datetime) -> str:
    return (f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}, "
            f"{d:%H:%M}")

# ---------------------------------------------------------------------
# Les places
#
# `continu` = début et fin de la cotation en continu, dans le fuseau de
# la place. `fixing_ouv` et `fixing_clo` sont les fixings ; le fixing de
# clôture se dénoue APRES la fin du continu, d'où une heure plus tardive.
# ---------------------------------------------------------------------
PLACES = {
    "paris": {
        "nom": "EURONEXT PARIS", "tz": "Europe/Paris", "pays": "FR",
        "continu": ((9, 0), (17, 30)),
        "fixing_ouv": (9, 0), "fixing_clo": (17, 35),
        "indice": "CAC 40", "feries": "euronext",
    },
    "amsterdam": {
        "nom": "EURONEXT AMSTERDAM", "tz": "Europe/Amsterdam", "pays": "NL",
        "continu": ((9, 0), (17, 30)),
        "fixing_ouv": (9, 0), "fixing_clo": (17, 35),
        "indice": "AEX", "feries": "euronext",
    },
    "bruxelles": {
        "nom": "EURONEXT BRUXELLES", "tz": "Europe/Brussels", "pays": "BE",
        "continu": ((9, 0), (17, 30)),
        "fixing_ouv": (9, 0), "fixing_clo": (17, 35),
        "indice": "BEL 20", "feries": "euronext",
    },
    "francfort": {
        "nom": "XETRA FRANCFORT", "tz": "Europe/Berlin", "pays": "DE",
        "continu": ((9, 0), (17, 30)),
        "fixing_ouv": (9, 0), "fixing_clo": (17, 35),
        "indice": "DAX", "feries": "xetra",
    },
    "milan": {
        "nom": "BORSA ITALIANA", "tz": "Europe/Rome", "pays": "IT",
        "continu": ((9, 0), (17, 30)),
        "fixing_ouv": (9, 0), "fixing_clo": (17, 35),
        "indice": "FTSE MIB", "feries": "euronext",
    },
    "madrid": {
        "nom": "BME MADRID", "tz": "Europe/Madrid", "pays": "ES",
        "continu": ((9, 0), (17, 30)),
        "fixing_ouv": (9, 0), "fixing_clo": (17, 35),
        "indice": "IBEX 35", "feries": "euronext",
    },
    "zurich": {
        "nom": "SIX SUISSE", "tz": "Europe/Zurich", "pays": "CH",
        "continu": ((9, 0), (17, 20)),
        "fixing_ouv": (9, 0), "fixing_clo": (17, 30),
        "indice": "SMI", "feries": "six",
    },
    "londres": {
        "nom": "LONDON STOCK EXCHANGE", "tz": "Europe/London", "pays": "GB",
        "continu": ((8, 0), (16, 30)),
        "fixing_ouv": (8, 0), "fixing_clo": (16, 35),
        "indice": "FTSE 100", "feries": "lse",
    },
    "newyork": {
        "nom": "NYSE / NASDAQ", "tz": "America/New_York", "pays": "US",
        "continu": ((9, 30), (16, 0)),
        "fixing_ouv": (9, 30), "fixing_clo": (16, 0),
        "avant": (4, 0), "apres": (20, 0),
        "indice": "S&P 500", "feries": "us",
    },
}

ORDRE = ["paris", "amsterdam", "bruxelles", "francfort", "milan",
         "madrid", "zurich", "londres", "newyork"]


# ---------------------------------------------------------------------
# Jours feries — CALCULES, jamais recopies d'une table qui perime
# ---------------------------------------------------------------------
def paques(an: int) -> dt.date:
    """Dimanche de Pâques, algorithme de Gauss-Butcher. Sert à placer le
    Vendredi saint et le lundi de Pâques, qui ferment toutes ces places
    et qui bougent chaque année."""
    a, b, c = an % 19, an // 100, an % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(an, mois, jour)


def _nieme(an: int, mois: int, jsem: int, n: int) -> dt.date:
    """Le n-ième `jsem` du mois (lundi = 0). n = -1 pour le dernier."""
    if n > 0:
        d = dt.date(an, mois, 1)
        d += dt.timedelta(days=(jsem - d.weekday()) % 7)
        return d + dt.timedelta(weeks=n - 1)
    fin = dt.date(an + (mois == 12), (mois % 12) + 1, 1) - dt.timedelta(days=1)
    return fin - dt.timedelta(days=(fin.weekday() - jsem) % 7)


def _decale_us(d: dt.date) -> dt.date:
    """Un férié américain tombant un samedi est chômé le vendredi, un
    dimanche le lundi. Sans cette règle, la séance serait annoncée
    ouverte un jour où elle ne l'est pas."""
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


def feries(calendrier: str, an: int) -> set:
    """Les jours de fermeture d'un calendrier, pour une année donnée.

    Ce sont les fermetures ANNUELLES et prévisibles. Les fermetures
    exceptionnelles — deuil national, panne technique — n'y sont pas, et
    ne peuvent pas y être : elles ne s'annoncent pas à l'avance.
    """
    p = paques(an)
    vendredi_saint = p - dt.timedelta(days=2)
    lundi_paques = p + dt.timedelta(days=1)

    if calendrier == "us":
        j = {
            dt.date(an, 1, 1),                        # Jour de l'an
            _nieme(an, 1, 0, 3),                      # Martin Luther King
            _nieme(an, 2, 0, 3),                      # Presidents' Day
            vendredi_saint,
            _nieme(an, 5, 0, -1),                     # Memorial Day
            dt.date(an, 6, 19),                       # Juneteenth
            dt.date(an, 7, 4),                        # Independence Day
            _nieme(an, 9, 0, 1),                      # Labor Day
            _nieme(an, 11, 3, 4),                     # Thanksgiving
            dt.date(an, 12, 25),                      # Noël
        }
        # Le Vendredi saint n'est pas décalé : il tombe toujours un
        # vendredi. Les autres dates fixes, si.
        return {d if d == vendredi_saint else _decale_us(d) for d in j}

    base = {
        dt.date(an, 1, 1),
        vendredi_saint,
        lundi_paques,
        dt.date(an, 5, 1),                            # Fête du travail
        dt.date(an, 12, 25),
        dt.date(an, 12, 26),
    }
    if calendrier == "lse":
        # Le Royaume-Uni ne chôme pas le 1er mai ni le 26 décembre sous
        # ce nom : ce sont des « bank holidays » qui se décalent.
        base.discard(dt.date(an, 5, 1))
        base |= {_nieme(an, 5, 0, 1), _nieme(an, 5, 0, -1),
                 _nieme(an, 8, 0, -1)}
        base = {_decale_us(d) if d.month == 12 else d for d in base}
    if calendrier == "six":
        base |= {dt.date(an, 8, 1),                   # Fête nationale
                 p + dt.timedelta(days=39),           # Ascension
                 p + dt.timedelta(days=50)}           # lundi de Pentecôte
    if calendrier == "xetra":
        base |= {p + dt.timedelta(days=39), p + dt.timedelta(days=50)}
    return base


def ferie(cle: str, jour: dt.date) -> bool:
    cal = PLACES[cle]["feries"]
    return jour in feries(cal, jour.year)


# ---------------------------------------------------------------------
# Etat d'une place
# ---------------------------------------------------------------------
def _h(jour: dt.date, hm: tuple, tz: ZoneInfo) -> dt.datetime:
    return dt.datetime(jour.year, jour.month, jour.day, hm[0], hm[1],
                       tzinfo=tz)


def etat(cle: str, maintenant: dt.datetime | None = None) -> dict:
    """Où en est cette place, à cet instant précis.

    `maintenant` sert aux tests : sans lui, c'est l'heure courante.
    """
    p = PLACES[cle]
    tz = ZoneInfo(p["tz"])
    now = (maintenant or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
    jour = now.date()
    (oh, om), (fh, fm) = p["continu"]
    ouv = _h(jour, (oh, om), tz)
    clo = _h(jour, (fh, fm), tz)
    fix = _h(jour, p["fixing_clo"], tz)

    weekend = jour.weekday() >= 5
    jf = ferie(cle, jour)
    if weekend or jf:
        code = "WEEK-END" if weekend else "FERIE"
    elif now < ouv:
        code = "AVANT OUVERTURE"
    elif now < clo:
        code = "OUVERTE"
    elif now < fix:
        code = "FIXING DE CLOTURE"
    else:
        code = "FERMEE"

    return {
        "cle": cle, "nom": p["nom"], "indice": p["indice"],
        "code": code,
        "ouverte": code == "OUVERTE",
        "ferie": jf, "weekend": weekend,
        "locale": now.strftime("%H:%M"),
        "paris": now.astimezone(PARIS).strftime("%H:%M"),
        "ouv_paris": ouv.astimezone(PARIS).strftime("%H:%M"),
        "clo_paris": clo.astimezone(PARIS).strftime("%H:%M"),
        "fix_paris": fix.astimezone(PARIS).strftime("%H:%M"),
        # Le fixing de cloture americain se denoue A la cloture : afficher
        # deux heures identiques laisserait croire a une erreur.
        "fixing_a_la_cloture": p["fixing_clo"] == (fh, fm),
        # Pre-marche et seance prolongee : ils existent aux Etats-Unis et
        # nulle part ailleurs dans cette table.
        "avant_paris": (_h(jour, p["avant"], tz).astimezone(PARIS)
                        .strftime("%H:%M") if "avant" in p else None),
        "apres_paris": (_h(jour, p["apres"], tz).astimezone(PARIS)
                        .strftime("%H:%M") if "apres" in p else None),
        "prochain": prochain(cle, now),
    }


def prochaine_seance(cle: str, depuis: dt.date) -> dt.date:
    """Le prochain jour de bourse, week-ends et fériés sautés."""
    j = depuis
    for _ in range(14):
        j += dt.timedelta(days=1)
        if j.weekday() < 5 and not ferie(cle, j):
            return j
    return j


def prochain(cle: str, now: dt.datetime) -> dict:
    """Le prochain événement de cette place, et dans combien de temps."""
    p = PLACES[cle]
    tz = ZoneInfo(p["tz"])
    jour = now.date()
    (oh, om), (fh, fm) = p["continu"]
    ouvrable = jour.weekday() < 5 and not ferie(cle, jour)
    jalons = []
    if ouvrable:
        jalons = [("ouverture", _h(jour, (oh, om), tz)),
                  ("fin du continu", _h(jour, (fh, fm), tz)),
                  ("fixing de cloture", _h(jour, p["fixing_clo"], tz))]
    for nom, quand in jalons:
        if now < quand:
            reste = quand - now
            return {"quoi": nom,
                    "quand_paris": quand.astimezone(PARIS).strftime("%H:%M"),
                    "dans_minutes": int(reste.total_seconds() // 60),
                    "jour": "aujourd'hui"}
    suivant = prochaine_seance(cle, jour)
    quand = _h(suivant, (oh, om), tz)
    reste = quand - now
    return {"quoi": "ouverture",
            "quand_paris": quand.astimezone(PARIS).strftime("%H:%M"),
            "dans_minutes": int(reste.total_seconds() // 60),
            "jour": suivant.isoformat()}


def toutes(maintenant: dt.datetime | None = None) -> list:
    return [etat(c, maintenant) for c in ORDRE]


# ---------------------------------------------------------------------
# La question de l'heure
# ---------------------------------------------------------------------
def pourquoi_pas_de_meilleure_heure() -> dict:
    """Pourquoi ce programme n'affiche aucune « meilleure heure ».

    Ce n'est pas une prudence de façade : c'est ce que les données
    disponibles permettent de dire, et rien de plus.
    """
    return {
        "ce_que_dit_la_specification": (
            "Vos règles exécutent à l'OUVERTURE de la séance suivante, "
            "pas à un moment choisi dans la journée. Le backtest mesure "
            "exactement ça, spread et slippage compris. Exécuter à une "
            "autre heure, c'est exécuter une autre stratégie que celle "
            "qui a été testée."),
        "ce_qui_est_structurel": (
            "Deux faits ne demandent aucune mesure. À l'ouverture, les "
            "écarts entre achat et vente sont les plus larges de la "
            "journée : le carnet se reconstitue. Au fixing de clôture, "
            "le plus gros volume de la séance s'échange, parce que les "
            "indices et les fonds indiciels doivent s'y caler. C'est de "
            "la liquidité, pas une direction."),
        "ce_qui_ne_peut_pas_etre_mesure_ici": (
            "Tout le reste. Vos données sont des bougies JOURNALIÈRES : "
            "une barre par séance, ouverture, plus haut, plus bas, "
            "clôture. Aucune heure intermédiaire n'y figure. Affirmer "
            "que 15h30 vaut mieux que 11h demanderait des données "
            "intraday que le programme n'a pas — c'est le chantier 7, et "
            "il est bloqué sur une question plus dure que les données."),
        "ce_qu_il_faut_en_faire": (
            "Passer l'ordre quand votre règle le dit, à l'ouverture, et "
            "éviter les toutes premières minutes si le titre est peu "
            "liquide. Rien de plus fin ne serait vérifiable."),
    }


# ---------------------------------------------------------------------
def texte(maintenant: dt.datetime | None = None) -> str:
    now = (maintenant or dt.datetime.now(dt.timezone.utc)).astimezone(PARIS)
    L = [f"\n  LES PLACES — {date_fr(now)} à Paris",
         "",
         f"    {'place':<24}{'etat':<19}{'ouverture':>11}"
         f"{'fin continu':>13}{'fixing clot.':>15}   prochain"]
    for e in toutes(maintenant):
        pr = e["prochain"]
        quand = (f"{pr['quoi']} a {pr['quand_paris']}"
                 if pr["jour"] == "aujourd'hui"
                 else f"ouverture le {pr['jour']}")
        fx = "a la cloture" if e["fixing_a_la_cloture"] else e["fix_paris"]
        L.append(f"    {e['nom']:<24}{e['code']:<19}{e['ouv_paris']:>11}"
                 f"{e['clo_paris']:>13}{fx:>15}   {quand}")
        if e["avant_paris"]:
            L.append(f"    {'':<24}pre-marche {e['avant_paris']}, "
                     f"seance prolongee jusqu'a {e['apres_paris']} "
                     "— liquidite faible, ecarts larges")
    L.append("")
    L.append("    Toutes les heures sont données à PARIS. Les fuseaux des")
    L.append("    places suivent leur propre heure d'été : l'Europe et les")
    L.append("    Etats-Unis n'en changent pas le meme week-end, donc la")
    L.append("    seance americaine se decale d'une heure deux fois par an,")
    L.append("    pendant une quinzaine de jours.")

    q = pourquoi_pas_de_meilleure_heure()
    L.append("")
    L.append("  A QUELLE HEURE ACHETER OU VENDRE ?")
    for titre, cle in (("Ce que dit votre specification",
                        "ce_que_dit_la_specification"),
                       ("Ce qui est structurel, sans mesure",
                        "ce_qui_est_structurel"),
                       ("Ce qui ne peut PAS etre mesure avec vos donnees",
                        "ce_qui_ne_peut_pas_etre_mesure_ici"),
                       ("En pratique", "ce_qu_il_faut_en_faire")):
        L.append("")
        L.append(f"    {titre.upper()}")
        for ligne in _plie(q[cle], 66):
            L.append(f"    {ligne}")
    L.append("")
    return "\n".join(L)


def _plie(t: str, largeur: int) -> list:
    mots, ligne, out = t.split(), "", []
    for m in mots:
        if len(ligne) + len(m) + 1 > largeur:
            out.append(ligne)
            ligne = m
        else:
            ligne = f"{ligne} {m}".strip()
    if ligne:
        out.append(ligne)
    return out


def main() -> None:
    a = argparse.ArgumentParser(description="Horaires des places")
    a.add_argument("--place", default="", help="une seule place")
    o = a.parse_args()
    if o.place:
        cle = o.place.lower()
        if cle not in PLACES:
            print(f"\n  Place inconnue. Au choix : {', '.join(ORDRE)}\n")
            return
        e = etat(cle)
        print(f"\n  {e['nom']} — {e['code']}")
        print(f"    heure locale      {e['locale']}  "
              f"(Paris {e['paris']})")
        print(f"    ouverture         {e['ouv_paris']} Paris")
        print(f"    fin du continu    {e['clo_paris']} Paris")
        print(f"    fixing de cloture {e['fix_paris']} Paris")
        pr = e["prochain"]
        print(f"    prochain          {pr['quoi']} a {pr['quand_paris']} "
              f"({pr['jour']})\n")
        return
    print(texte())


if __name__ == "__main__":
    main()
