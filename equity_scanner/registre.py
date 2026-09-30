"""Le registre des tests — etape 10 du protocole.

« Un fichier unique ou chaque test lance est inscrit AVANT son resultat.
On y inscrit les echecs. Surtout les echecs. »

Deux fichiers, ranges dans ~/.carruos pour qu'une mise a jour du
programme ne les efface jamais :

- `registre-tests.md`, pour etre lu. On n'y reecrit jamais une ligne :
  l'ouverture d'un test y ajoute une ligne « en cours », sa fin en
  ajoute une seconde avec le resultat. L'historique reste lisible tel
  qu'il s'est deroule, interruptions comprises.
- `registre-tests.json`, pour que le programme sache qu'une periode de
  validation a deja ete regardee. C'est lui qui refuse un second
  passage : la periode de validation est un consommable.

Une entree ouverte et jamais fermee veut dire que le calcul s'est
interrompu AVANT que le moindre resultat ne s'affiche — la fermeture est
ecrite avant l'affichage, jamais apres. Une telle entree n'est donc pas
un regard, et le passage peut reprendre ; la reprise est inscrite.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

DOSSIER = Path.home() / ".carruos"
MD = DOSSIER / "registre-tests.md"
ETAT = DOSSIER / "registre-tests.json"

ENTETE = (
    "# Registre des tests\n\n"
    "Chaque test est inscrit avant son résultat. Les lignes ne sont "
    "jamais réécrites : un test ouvert puis fermé occupe deux lignes.\n\n"
    "| date | hypothèse | empreinte SHA256 | univers | période | résultat | z |\n"
    "|---|---|---|---|---|---|---|\n")


# ---------------------------------------------------------------------
# Le lancement d'un passage unique
#
# Apres une repetition generale NO-GO, un simple OUI ne suffit plus : il
# faut taper LANCER QUAND MEME. Le verdict de la repetition reste
# indicatif — seul le passage unique juge — mais lancer malgre lui
# consomme la periode de validation pour une hypothese que ses propres
# donnees de conception n'ont pas soutenue. Cela doit etre un geste
# delibere, pas un reflexe. Un verdict ABSENT compte comme un NO-GO : la
# regle ne peut que durcir le lancement, jamais l'assouplir.
# ---------------------------------------------------------------------
PHRASE_SIMPLE = "OUI"
PHRASE_FORCEE = "LANCER QUAND MEME"


def phrase_de_lancement(verdict_repetition: str | None) -> str:
    """La phrase exacte a taper pour lancer le passage unique."""
    if verdict_repetition and verdict_repetition != "NO-GO":
        return PHRASE_SIMPLE
    return PHRASE_FORCEE


def lancement_accepte(reponse: str | None,
                      verdict_repetition: str | None) -> bool:
    """La reponse tapee lance-t-elle le passage ? Exactement la phrase
    (l'accent de MÊME est admis), rien d'approchant."""
    phrase = phrase_de_lancement(verdict_repetition)
    r = (reponse or "").strip()
    return r in {phrase, phrase.replace("MEME", "MÊME")}


def _maintenant() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def lit(etat: Path | None = None) -> list[dict]:
    f = etat or ETAT
    try:
        v = json.loads(f.read_text(encoding="utf-8"))
        return v if isinstance(v, list) else []
    except (FileNotFoundError, ValueError):
        return []


def _ecrit(entrees: list[dict], etat: Path | None = None) -> None:
    """Ecriture atomique : un registre a moitie ecrit serait pire que pas
    de registre, il dirait qu'aucune periode n'a ete regardee."""
    f = etat or ETAT
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(entrees, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, f)


def _ligne_md(date: str, e: dict, resultat: str, z: str,
              md: Path | None = None) -> None:
    f = md or MD
    f.parent.mkdir(parents=True, exist_ok=True)
    neuf = not f.exists()
    with f.open("a", encoding="utf-8") as fp:
        if neuf:
            fp.write(ENTETE)
        fp.write(f"| {date} | {e['hypothese']} | {e['empreinte']} | "
                 f"{e['univers']} | {e['periode']} | {resultat} | {z} |\n")


def regards(hypothese: str, periode: str,
            etat: Path | None = None) -> list[dict]:
    """Les passages de CETTE hypothese sur CETTE periode."""
    return [e for e in lit(etat)
            if e.get("hypothese") == hypothese and e.get("periode") == periode]


def deja_regardee(hypothese: str, periode: str,
                  etat: Path | None = None) -> dict | None:
    """Le premier passage TERMINE, s'il existe. C'est lui qui compte."""
    for e in regards(hypothese, periode, etat):
        if e.get("fin"):
            return e
    return None


def autres_regards(hypothese: str, periode: str,
                   etat: Path | None = None) -> list[dict]:
    """Les passages TERMINES d'AUTRES hypotheses sur cette meme periode.

    Le protocole consomme une periode par hypothese. Qu'une autre l'ait
    deja regardee ne la brule pas pour celle-ci — mais cela doit etre
    dit, amende et inscrit, jamais decouvert apres coup."""
    return [e for e in lit(etat)
            if e.get("periode") == periode and e.get("fin")
            and e.get("hypothese") != hypothese]


def ouvre(hypothese: str, periode: str, univers: str, empreinte: str,
          details: dict | None = None, motif: str = "",
          etat: Path | None = None, md: Path | None = None) -> str:
    """Inscrit un test AVANT son resultat. Rend son identifiant."""
    entrees = lit(etat)
    date = _maintenant()
    precedents = [e for e in entrees if e.get("hypothese") == hypothese
                  and e.get("periode") == periode]
    e = {"id": f"{hypothese}|{periode}|{date}", "debut": date, "fin": None,
         "hypothese": hypothese, "periode": periode, "univers": univers,
         "empreinte": empreinte, "details": details or {},
         "rang": len(precedents) + 1, "motif": motif, "resultat": None}
    entrees.append(e)
    _ecrit(entrees, etat)
    lib = "en cours"
    if any(p.get("fin") for p in precedents):
        lib = f"en cours — SECOND REGARD : {motif}"
    elif precedents:
        lib = "en cours — reprise après interruption"
    _ligne_md(date, e, lib, "—", md)
    return e["id"]


def ferme(ident: str, resultat: str, z: float | None,
          details: dict | None = None,
          etat: Path | None = None, md: Path | None = None) -> None:
    """Inscrit le resultat. A appeler AVANT d'afficher quoi que ce soit."""
    entrees = lit(etat)
    for e in entrees:
        if e.get("id") == ident:
            e["fin"] = _maintenant()
            e["resultat"] = resultat
            e["z"] = None if z is None else round(float(z), 2)
            e["details"] = {**e.get("details", {}), **(details or {})}
            _ecrit(entrees, etat)
            zs = "—" if z is None else f"{z:+.2f}".replace(".", ",")
            _ligne_md(e["fin"], e, resultat, zs, md)
            return
    raise KeyError(f"aucun test ouvert sous l'identifiant {ident!r}")


# ---------------------------------------------------------------------
# L'abandon AVANT le passage unique
#
# Une hypothese peut mourir sur sa periode de conception : la repetition
# generale la rejette si nettement que depenser la periode de validation
# n'apprendrait rien. « On y inscrit les echecs. Surtout les echecs » :
# un abandon s'inscrit donc comme un echec, avec ce qui l'a motive.
#
# Il ne porte sur AUCUNE periode de validation — rien n'y a ete regarde,
# et `autres_regards()` ne le compte pas comme un regard sur 2024-2026.
# Il FERME l'hypothese : un passage ulterieur serait une resurrection
# choisie apres coup, et le programme le refuse.
# ---------------------------------------------------------------------
PERIODE_ABANDON = "aucune (abandon avant le passage unique)"


def abandonnee(hypothese: str, etat: Path | None = None) -> dict | None:
    """L'inscription de l'abandon de cette hypothese, s'il existe."""
    for e in lit(etat):
        if (e.get("hypothese") == hypothese
                and e.get("periode") == PERIODE_ABANDON and e.get("fin")):
            return e
    return None


def abandonne(hypothese: str, univers: str, empreinte: str, motif: str,
              details: dict | None = None, etat: Path | None = None,
              md: Path | None = None) -> dict:
    """Inscrit l'abandon, une fois. Une seule ligne : il n'y a pas de
    calcul entre l'ouverture et la fermeture, donc rien a interrompre."""
    deja = abandonnee(hypothese, etat)
    if deja:
        return deja
    entrees = lit(etat)
    date = _maintenant()
    e = {"id": f"{hypothese}|{PERIODE_ABANDON}|{date}", "debut": date,
         "fin": date, "hypothese": hypothese, "periode": PERIODE_ABANDON,
         "univers": univers, "empreinte": empreinte,
         "details": details or {}, "rang": 1, "motif": motif,
         "resultat": f"ABANDONNÉE — {motif}", "z": None}
    entrees.append(e)
    _ecrit(entrees, etat)
    _ligne_md(date, e, e["resultat"], "—", md)
    return e
