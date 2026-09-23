"""Bruce — application de bureau.

    py -m equity_scanner.app

Ouvre une VRAIE fenetre Windows (pas un onglet de navigateur) grace a
pywebview, qui s'appuie sur le moteur Edge WebView2 present d'origine sur
Windows 10 et 11.

    py -m pip install pywebview

Si pywebview n'est pas installe, l'appli bascule sur le navigateur par
defaut plutot que de refuser de demarrer.

Architecture : un petit serveur HTTP sur 127.0.0.1, port libre choisi
automatiquement, consomme par la fenetre. Rien n'est expose a l'exterieur.
"""

from __future__ import annotations

import datetime as _dt
import html
import http.server
import json
import socket
import threading
import traceback
import urllib.parse
import webbrowser
from pathlib import Path

from . import chart as gr
from . import data as dl
from . import find as fd
from . import hud as hd
from . import news as nw
from . import positions as ps
from . import reglages as rg
from .indicators import enrich
from .rules import (evaluate, evaluate_exit, market_regime_ok, position_size,
                    rank)

NOM = "CARRUOS"
TITRE = NOM + " - scanner actions"
import os

FICHIER_CLE = Path(".bruce_cache") / "cle-alphavantage.txt"
FICHIER_RADAR = Path(".bruce_cache") / "radar.json"


def _cle_durable() -> Path:
    """Copie de la cle dans le profil utilisateur, HORS du dossier du
    programme.

    `.bruce_cache` est cree a cote de l'executable et ne fait pas partie
    de l'archive livree. Installer une nouvelle version dans un dossier
    neuf faisait donc disparaitre la cle sans un mot, et les actualites
    tombaient en panne sans explication. Celle-ci survit aux mises a
    jour.

    Fichier en clair, comme l'autre : c'est une cle de lecture gratuite,
    sans acces a un compte ni a de l'argent. Si elle fuit, on en demande
    une autre en trente secondes.
    """
    return Path.home() / ".carruos" / "cle-alphavantage.txt"


def _lit(f: Path) -> str:
    try:
        return f.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def cle_av() -> str:
    """La cle Alpha Vantage, dans l'ordre : fichier local, copie durable
    du profil, puis variables d'environnement.

    Le fichier local gagne : c'est celui que remplit le champ de
    l'accueil. La copie durable le rattrape apres une mise a jour.
    """
    v = _lit(FICHIER_CLE)
    if v:
        return v
    v = _lit(_cle_durable())
    if v:
        # Recuperation apres une mise a jour : on repose la cle a cote du
        # programme pour que le reste du code n'ait rien a savoir de tout
        # ca. Silencieux si le dossier n'est pas accessible en ecriture.
        try:
            FICHIER_CLE.parent.mkdir(exist_ok=True)
            FICHIER_CLE.write_text(v, encoding="utf-8")
        except Exception:
            pass
        return v
    v = (os.environ.get("CARRUOS_AV_KEY")
         or os.environ.get("ALPHAVANTAGE_KEY") or "").strip()
    if v:
        return v
    # Dernier recours : aller la chercher dans une ancienne installation.
    return retrouve_cle()


# Une seule fouille par lancement. Sans ce verrou, chaque requete de la
# page relancerait la recherche et le disque serait sollicite en boucle.
_FOUILLE = {"faite": False, "trouvee": "", "ou": ""}

# Noms de dossiers ou une copie precedente de CARRUOS a des chances de
# se trouver. On ne balaie PAS le disque : on regarde une poignee
# d'endroits, a deux niveaux de profondeur, et on s'arrete.
_LIEUX = ("Desktop", "Bureau", "Downloads", "Telechargements",
          "Téléchargements", "Documents", "OneDrive", "OneDrive/Bureau",
          "OneDrive/Documents")
_PLAFOND = 400          # dossiers examines au maximum


def _candidats() -> list:
    """Les dossiers ou chercher une ancienne cle, du plus probable au
    moins probable."""
    out = []
    try:
        # UN SEUL niveau au-dessus : les dossiers freres de
        # l'installation. Remonter de deux revenait a fouiller tout
        # C:\Users — beaucoup trop large, et lent.
        out.append(Path.cwd().resolve().parent)
    except OSError:
        pass
    try:
        maison = Path.home()
        out.append(maison)
        out += [maison / n for n in _LIEUX]
    except (OSError, RuntimeError):
        pass
    vus, propres = set(), []
    for d in out:
        try:
            r = d.resolve()
        except OSError:
            continue
        if r in vus:
            continue
        vus.add(r)
        propres.append(r)
    return propres


def retrouve_cle() -> str:
    """Cherche une cle laissee par une installation precedente.

    POURQUOI CETTE FONCTION EXISTE. La cle vit dans `.bruce_cache`, cree
    a cote du programme et absent de l'archive. Installer une nouvelle
    version dans un dossier neuf la laissait derriere, et les actualites
    tombaient en panne sans explication. La copie durable dans le profil
    regle le cas a partir du moment ou la cle a ete saisie une fois dans
    une version qui la connait — mais pas pour les cles plus anciennes.

    On regarde donc, une seule fois par lancement, dans une poignee de
    dossiers probables. Ce n'est PAS un balayage du disque : deux
    niveaux de profondeur, un plafond de dossiers examines, et un seul
    nom de fichier recherche. Rien d'autre n'est lu.
    """
    if _FOUILLE["faite"]:
        return _FOUILLE["trouvee"]
    _FOUILLE["faite"] = True
    # Le dossier personnel existe des qu'une cle a ete saisie OU effacee
    # ici. Sa presence signifie donc : « ce programme a deja ete regle
    # sur cette machine ». On ne devine plus rien apres ca — sinon
    # effacer volontairement la cle la ferait ressusciter au lancement
    # suivant, ce qui ressemblerait a un bug.
    try:
        if _cle_durable().parent.exists():
            return ""
    except OSError:
        return ""
    ici = None
    try:
        ici = Path.cwd().resolve()
    except OSError:
        pass
    examines = 0
    for base in _candidats():
        for motif in ("*/.bruce_cache/cle-alphavantage.txt",
                      "*/*/.bruce_cache/cle-alphavantage.txt"):
            try:
                trouves = base.glob(motif)
            except OSError:
                continue
            for f in trouves:
                examines += 1
                if examines > _PLAFOND:
                    return ""
                # Ne pas se retrouver soi-meme. Comparer le dossier
                # grand-parent ne suffisait pas : selon l'endroit d'ou
                # part le glob, le fichier courant remontait sous une
                # autre forme. On ecarte TOUT ce qui se trouve dans le
                # dossier d'execution, a n'importe quelle profondeur.
                try:
                    r = f.resolve()
                    if ici is not None and (r.parent.parent == ici
                                            or ici in r.parents):
                        continue
                except OSError:
                    continue
                v = _lit(f)
                if v:
                    _FOUILLE["trouvee"] = v
                    _FOUILLE["ou"] = str(f)
                    # On la recopie aux deux endroits : la prochaine fois,
                    # aucune fouille ne sera necessaire.
                    pose_cle(v)
                    print(f"  cle Alpha Vantage recuperee depuis {f}")
                    return v
    return ""


def pose_cle(v: str) -> bool:
    """Enregistre la cle AUX DEUX ENDROITS, ou l'efface des deux.

    Ecrire un seul des deux rendrait le comportement dependant de l'ordre
    de lecture : effacer la cle localement la verrait revenir au prochain
    lancement, ce qui ressemblerait a un bug.
    """
    v = (v or "").strip()
    for f in (FICHIER_CLE, _cle_durable()):
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            if v:
                f.write_text(v, encoding="utf-8")
            else:
                f.unlink(missing_ok=True)
        except Exception:
            pass
    return bool(v)


REGLAGES = {"sleeve": 8000.0, "fx": 1.08, "av_key": cle_av()}
INDICES = {"us": ("SPY", "S&P 500", "USD"), "europe": ("^STOXX", "Stoxx 600", "EUR"),
           "france": ("^FCHI", "CAC 40", "EUR"), "allemagne": ("^GDAXI", "DAX", "EUR")}
# Le logo ne joue qu'au lancement : les retours a l'accueil sont instantanes.
_LANCE = {"fait": False}
SUF_EU = (".PA", ".DE", ".AS", ".MI", ".MC", ".BR", ".LS", ".VI")

# Cerf vectorise depuis le visuel fourni par l'utilisateur.
# Un seul chemin, fill-rule evenodd : l'oeil et l'interieur de l'oreille
# sont des decoupes du contour principal, pas des formes separees.
TRACE_D = "M185.7 375.9C185.0 376.3 184.7 376.1 184.2 375.9C183.7 375.7 183.2 375.8 182.5 374.7C181.9 373.6 180.8 372.6 180.1 369.4C179.5 366.2 180.1 361.7 178.7 355.5C177.2 349.2 174.2 338.1 171.5 331.9C168.7 325.6 164.4 321.4 162.3 317.9C160.2 314.4 159.7 312.9 158.9 310.7C158.1 308.4 157.7 306.3 157.5 304.4C157.3 302.5 157.2 300.8 157.5 299.1C157.8 297.4 158.8 294.9 159.2 294.1C159.6 293.3 159.7 293.1 159.9 294.3C160.1 295.5 160.1 299.8 160.4 301.0C160.7 302.3 161.5 301.5 161.8 302.0C162.2 302.5 162.2 303.8 162.6 304.2C162.9 304.5 163.5 303.9 164.0 304.2C164.5 304.5 166.1 307.1 165.7 305.9C165.2 304.6 162.0 298.5 161.3 296.7C160.7 295.0 161.5 295.6 161.8 295.3C162.1 294.9 162.5 294.5 163.0 294.5C163.6 294.5 164.4 294.2 165.2 295.3C166.0 296.4 167.0 299.2 168.1 301.0C169.2 302.9 170.7 305.6 171.7 306.1C172.7 306.6 173.5 305.0 173.9 303.9C174.2 302.9 174.0 300.7 173.9 299.6C173.7 298.5 173.9 298.7 172.9 297.2C171.9 295.7 169.6 293.2 168.1 290.5C166.6 287.7 164.8 283.9 163.8 280.8C162.7 277.8 162.1 274.2 161.8 272.2C161.5 270.1 161.5 268.0 162.1 268.5C162.6 269.1 164.4 273.5 165.2 275.5C166.0 277.6 166.3 280.3 166.6 280.8C167.0 281.4 166.8 279.3 167.1 278.9C167.4 278.5 167.8 277.9 168.3 278.2C168.8 278.4 169.4 279.0 170.0 280.3C170.6 281.7 171.1 285.0 171.9 286.1C172.8 287.3 174.9 287.9 175.1 287.3C175.2 286.8 173.3 283.8 172.9 282.8C172.5 281.7 172.6 281.8 172.9 281.3C173.2 280.8 174.0 279.8 174.6 279.6C175.2 279.4 175.0 277.8 176.5 280.1C178.1 282.4 182.5 291.2 184.0 293.3C185.5 295.5 185.7 294.1 185.4 292.9C185.1 291.6 182.5 287.4 182.1 285.6C181.6 283.9 182.0 283.3 182.5 282.3C183.1 281.2 186.0 281.1 185.4 279.4C184.9 277.6 180.1 273.6 179.2 271.7C178.2 269.7 179.3 268.7 179.6 267.8C180.0 266.9 180.4 266.5 181.3 266.1C182.2 265.8 185.3 266.9 184.9 265.9C184.6 264.9 180.1 261.4 179.2 260.1C178.2 258.8 179.8 259.6 179.2 258.2C178.5 256.8 175.7 252.3 175.1 251.7C174.4 251.1 175.4 254.2 175.3 254.8C175.2 255.5 175.0 255.4 174.6 255.5C174.2 255.7 173.4 255.7 173.1 255.5C172.9 255.3 173.2 254.7 172.9 254.3C172.6 253.9 171.7 253.2 171.2 253.1C170.8 253.1 170.7 253.9 170.3 254.1C169.8 254.3 168.9 254.3 168.3 254.1C167.8 253.9 167.6 254.6 167.1 252.9C166.6 251.2 165.6 245.5 165.2 243.7C164.8 242.0 164.8 242.7 164.5 242.5C164.1 242.3 163.6 242.9 163.0 242.5C162.4 242.2 161.1 244.1 160.9 240.4C160.6 236.6 161.2 224.2 161.3 220.2C161.5 216.1 161.5 217.0 161.8 215.8C162.2 214.6 163.0 216.1 163.3 212.9C163.5 209.8 163.0 198.4 163.3 197.0C163.6 195.7 164.5 202.8 165.2 204.7C165.9 206.7 167.0 207.4 167.6 208.6C168.2 209.8 168.2 208.9 168.6 212.0C169.0 215.0 169.6 224.0 170.0 226.9C170.5 229.8 170.9 229.2 171.2 229.5C171.6 229.9 171.6 228.7 172.2 229.1C172.7 229.5 173.9 231.5 174.6 231.9C175.2 232.4 174.8 230.8 176.0 231.9C177.2 233.1 180.8 237.8 181.8 238.7C182.8 239.6 182.2 238.0 182.1 237.5C181.9 237.0 181.1 236.1 181.1 235.6C181.1 235.0 181.3 234.0 181.8 234.4C182.3 234.7 183.8 237.5 184.2 237.7C184.7 237.9 184.1 236.1 184.5 235.6C184.8 235.0 185.6 234.4 186.1 234.4C186.7 234.4 187.4 235.0 187.8 235.6C188.3 236.1 188.0 237.0 189.0 237.7C190.0 238.4 192.6 239.5 193.9 239.7C195.1 239.8 195.7 239.3 196.7 238.7C197.8 238.1 199.3 236.6 200.1 236.3C200.9 236.0 201.1 236.3 201.6 236.8C202.0 237.2 202.2 238.9 203.0 239.2C203.8 239.5 205.4 239.1 206.4 238.7C207.3 238.3 207.9 238.0 208.5 237.0C209.2 236.0 209.9 233.6 210.5 232.7C211.0 231.7 211.7 231.6 211.9 231.2C212.1 230.9 212.1 230.6 211.7 230.5C211.2 230.4 210.0 230.7 209.3 230.5C208.5 230.3 208.2 229.5 207.3 229.5C206.5 229.5 205.1 230.3 204.0 230.5C202.8 230.7 201.5 230.7 200.6 230.5C199.7 230.3 200.8 229.6 198.7 229.5C196.5 229.5 189.9 230.1 187.6 230.0C185.3 229.9 185.4 229.5 184.7 229.1C184.0 228.6 183.6 227.8 183.5 227.4C183.4 227.0 182.6 226.7 184.2 226.7C185.9 226.6 191.4 227.2 193.4 227.1C195.3 227.1 196.4 227.3 196.0 226.4C195.7 225.6 192.2 223.1 191.2 222.1C190.2 221.0 190.5 221.1 190.2 220.2C190.0 219.2 189.6 217.2 189.8 216.3C190.0 215.4 190.2 214.7 191.4 214.6C192.7 214.5 195.7 214.9 197.2 215.6C198.7 216.2 199.7 218.1 200.6 218.5C201.5 218.9 201.8 218.4 202.5 218.0C203.2 217.6 204.0 216.4 204.9 216.1C205.8 215.7 207.1 215.9 207.8 216.1C208.5 216.3 208.8 216.7 209.0 217.3C209.2 217.9 209.2 218.8 209.0 219.7C208.9 220.6 208.6 221.5 208.1 222.6C207.5 223.6 205.7 225.2 205.7 225.9C205.6 226.6 206.7 226.5 207.8 226.7C209.0 226.8 211.5 226.9 212.6 226.7C213.8 226.5 214.4 227.3 214.8 225.4C215.2 223.6 216.4 219.3 215.3 215.3C214.2 211.3 208.2 207.0 208.1 201.4C207.9 195.8 212.7 185.5 214.3 181.6C215.9 177.8 217.1 179.1 217.7 178.3C218.3 177.5 217.9 177.3 217.7 176.8C217.5 176.4 217.4 176.0 216.5 175.6C215.6 175.2 213.3 174.3 212.2 174.6C211.0 175.0 210.6 176.8 209.7 177.5C208.9 178.3 208.3 178.7 206.9 179.0C205.4 179.2 203.6 179.3 201.1 179.0C198.6 178.7 194.7 177.4 191.9 177.1C189.2 176.7 187.1 178.0 184.7 177.1C182.3 176.1 179.4 172.5 177.5 171.3C175.6 170.1 174.2 170.3 173.1 169.8C172.1 169.3 172.1 167.4 171.2 168.4C170.3 169.4 169.1 174.1 167.6 175.8C166.1 177.6 163.1 178.0 162.3 178.7C161.5 179.5 162.5 179.9 162.8 180.2C163.1 180.5 164.0 180.0 164.2 180.7C164.5 181.3 164.4 183.3 164.2 184.0C164.1 184.8 164.0 185.0 163.5 185.2C163.0 185.5 162.7 186.6 161.1 185.7C159.5 184.8 156.4 181.1 153.9 179.9C151.4 178.7 148.6 179.2 146.2 178.5C143.8 177.8 141.7 177.3 139.4 175.6C137.2 173.9 134.7 171.3 132.5 168.1C130.2 165.0 127.1 160.1 125.7 156.6C124.3 153.1 124.1 149.1 124.3 147.0C124.4 144.8 125.5 144.3 126.4 143.8C127.4 143.4 128.2 143.5 129.8 144.3C131.4 145.1 134.9 147.4 135.8 148.4C136.8 149.4 136.4 149.7 135.6 150.1C134.7 150.4 131.9 150.3 130.8 150.6C129.6 150.8 129.1 151.1 128.6 151.8C128.1 152.5 127.6 153.7 127.6 154.7C127.6 155.6 127.5 156.4 128.6 157.6C129.7 158.7 132.6 159.6 134.4 161.4C136.1 163.2 137.6 166.7 139.2 168.6C140.8 170.6 141.9 172.1 143.8 173.2C145.7 174.3 148.3 174.1 150.5 175.1C152.7 176.2 155.4 178.9 156.8 179.5C158.2 180.0 158.4 179.0 158.9 178.3C159.5 177.5 159.5 175.7 159.9 174.9C160.3 174.0 160.9 173.4 161.6 173.2C162.3 173.0 163.0 174.3 164.0 173.7C165.0 173.1 166.7 170.9 167.6 169.6C168.5 168.3 169.2 166.8 169.5 165.7C169.9 164.7 169.7 163.9 169.5 163.3C169.3 162.8 169.0 162.7 168.3 162.6C167.6 162.5 166.2 162.4 165.4 162.6C164.6 162.8 164.0 163.2 163.5 163.6C163.1 163.9 162.9 163.6 162.8 164.8C162.7 165.9 163.0 169.5 162.8 170.6C162.6 171.6 162.4 171.2 161.6 171.3C160.8 171.4 159.1 171.6 158.2 171.3C157.3 170.9 156.4 171.2 156.1 169.1C155.7 167.1 156.5 161.0 156.1 159.0C155.6 156.9 155.9 158.1 153.4 156.8C151.0 155.6 143.8 152.8 141.4 151.5C138.9 150.3 139.0 149.8 138.7 149.4C138.5 149.0 137.7 148.5 139.9 149.1C142.1 149.7 147.4 151.0 152.0 153.0C156.5 154.9 164.6 159.4 167.4 160.7C170.2 162.0 168.4 161.1 168.8 160.7C169.3 160.2 170.2 158.8 170.0 158.0C169.9 157.2 169.1 156.3 167.8 155.9C166.6 155.4 164.4 156.4 162.6 155.4C160.7 154.3 160.4 151.9 156.8 149.6C153.2 147.3 146.0 143.6 140.9 141.4C135.7 139.3 132.7 138.4 126.0 136.6C119.2 134.8 107.3 132.3 100.4 130.3C93.6 128.3 89.7 126.7 85.0 124.6C80.4 122.5 76.6 120.8 72.5 117.8C68.5 114.9 63.2 109.4 60.7 107.0C58.3 104.5 58.8 104.7 57.8 103.1C56.9 101.5 55.5 99.2 54.9 97.4C54.4 95.5 54.4 93.1 54.4 92.1C54.5 91.1 54.7 91.3 55.2 91.3C55.7 91.4 56.4 91.1 57.3 92.5C58.3 93.9 59.0 97.2 60.7 99.8C62.4 102.4 65.9 106.6 67.7 108.2C69.5 109.8 70.6 109.3 71.5 109.2C72.5 109.0 72.8 108.1 73.2 107.5C73.7 106.9 74.0 106.5 74.2 105.5C74.3 104.6 74.7 103.2 74.2 101.7C73.7 100.2 73.5 98.9 71.3 96.4C69.1 93.9 64.2 90.1 61.2 86.8C58.1 83.5 55.4 80.0 53.0 76.7C50.6 73.3 48.5 69.7 46.7 66.5C45.0 63.3 43.5 60.6 42.4 57.4C41.3 54.2 40.4 50.1 40.0 47.3C39.6 44.5 39.5 43.4 40.0 40.5C40.5 37.6 42.0 32.4 42.9 29.9C43.8 27.5 44.6 26.5 45.3 25.6C46.0 24.7 46.7 24.2 47.0 24.4C47.3 24.6 47.5 25.2 47.2 26.6C46.9 27.9 45.8 30.2 45.3 32.3C44.8 34.5 44.3 37.0 44.3 39.6C44.4 42.1 44.8 45.0 45.8 47.8C46.7 50.6 48.2 53.1 50.1 56.4C52.0 59.7 55.5 65.1 57.3 67.5C59.1 70.0 59.7 70.4 60.9 71.1C62.2 71.9 64.0 72.0 64.8 72.1C65.6 72.1 65.6 74.0 65.5 71.4C65.5 68.7 64.6 62.2 64.6 56.4C64.6 50.6 65.0 41.9 65.5 36.7C66.0 31.5 66.9 27.7 67.4 25.1C68.0 22.6 68.5 22.1 68.9 21.3C69.3 20.4 69.8 20.2 70.1 20.1C70.4 20.0 70.8 17.3 70.8 20.8C70.9 24.3 70.3 35.6 70.3 41.0C70.4 46.5 70.7 48.6 71.3 53.5C71.9 58.4 72.8 65.7 73.7 70.4C74.6 75.1 75.7 79.0 76.6 81.9C77.5 84.9 77.8 85.8 79.0 88.2C80.2 90.6 80.9 92.9 83.8 96.4C86.7 99.9 92.8 105.9 96.6 109.2C100.3 112.4 102.5 113.7 106.2 115.9C109.9 118.1 117.6 122.5 118.7 122.6C119.9 122.8 114.6 118.7 113.2 116.6C111.8 114.6 110.9 112.4 110.3 110.4C109.7 108.4 109.5 106.7 109.3 104.6C109.2 102.4 109.1 98.7 109.3 97.4C109.5 96.0 110.1 96.4 110.5 96.6C110.9 96.9 111.1 96.7 111.7 98.8C112.4 100.9 113.2 106.7 114.2 109.4C115.1 112.0 116.4 113.3 117.5 114.7C118.6 116.1 117.4 115.1 120.7 117.8C123.9 120.6 133.2 128.6 137.0 131.3C140.9 134.0 139.5 131.9 143.8 134.2C148.0 136.4 159.3 143.3 162.6 144.8C165.8 146.3 164.3 145.0 163.3 143.1C162.3 141.2 158.1 135.9 156.5 133.5C155.0 131.1 154.8 130.3 154.1 128.7C153.5 127.0 153.0 127.9 152.7 123.4C152.4 118.8 152.1 105.3 152.2 101.2C152.3 97.2 153.0 99.4 153.4 99.0C153.8 98.7 154.4 98.4 154.8 99.0C155.3 99.7 155.8 100.8 156.1 103.1C156.3 105.4 156.1 109.2 156.5 112.8C157.0 116.4 157.7 121.3 158.9 124.8C160.2 128.3 161.9 130.5 164.2 134.0C166.6 137.4 171.3 143.5 172.9 145.5C174.5 147.6 172.3 146.1 173.6 146.2C175.0 146.4 178.8 145.8 180.9 146.2C182.9 146.7 182.5 148.6 185.7 149.1C188.9 149.7 196.8 149.9 200.1 149.6C203.4 149.3 203.1 150.0 205.7 147.4C208.2 144.9 212.8 138.0 215.3 134.4C217.8 130.8 219.4 128.4 220.6 125.8C221.8 123.1 221.9 122.5 222.5 118.5C223.1 114.6 223.5 105.4 223.9 102.2C224.4 98.9 224.8 99.6 225.2 99.0C225.5 98.5 225.7 98.6 226.1 99.0C226.6 99.5 227.6 97.8 227.8 101.7C228.0 105.6 227.9 117.4 227.3 122.4C226.8 127.4 226.2 128.1 224.4 131.5C222.7 135.0 217.9 140.9 216.7 143.1C215.6 145.3 214.7 146.0 217.4 144.8C220.2 143.5 229.1 137.9 233.3 135.6C237.6 133.4 239.0 134.0 243.0 131.3C246.9 128.7 253.4 123.0 256.9 119.7C260.5 116.5 262.8 114.0 264.4 111.8C266.0 109.6 266.2 108.8 266.8 106.5C267.4 104.3 267.8 100.0 268.3 98.3C268.7 96.7 269.1 96.8 269.5 96.6C269.9 96.5 270.6 95.2 270.7 97.4C270.7 99.6 270.4 106.6 269.7 109.9C269.0 113.2 267.8 115.0 266.3 117.1C264.8 119.2 258.9 123.2 260.8 122.6C262.7 122.0 273.4 116.1 277.6 113.5C281.9 110.8 283.3 109.5 286.3 106.7C289.3 104.0 293.7 99.2 295.7 96.9C297.7 94.5 297.3 95.1 298.6 92.5C299.9 90.0 302.1 85.3 303.4 81.5C304.7 77.6 305.4 74.2 306.3 69.4C307.2 64.6 308.1 57.8 308.7 52.6C309.3 47.4 309.5 42.9 309.7 38.1C309.8 33.4 309.8 27.0 309.7 24.2C309.5 21.4 308.8 21.9 308.7 21.3C308.6 20.6 308.9 20.4 309.2 20.3C309.5 20.2 310.1 19.9 310.6 20.8C311.2 21.7 311.9 22.8 312.6 25.6C313.2 28.4 314.1 31.2 314.5 37.6C314.9 44.1 315.0 58.8 315.0 64.1C314.9 69.5 314.0 68.6 314.0 69.9C314.0 71.2 314.5 71.8 315.2 72.1C315.9 72.4 316.9 72.3 318.1 71.6C319.3 70.9 320.6 69.9 322.2 68.0C323.7 66.1 325.6 63.5 327.5 60.3C329.4 57.1 332.5 51.4 333.7 48.7C335.0 46.1 334.9 45.9 335.2 44.4C335.5 42.9 335.7 41.5 335.7 39.6C335.6 37.6 335.3 35.2 334.7 32.8C334.1 30.5 332.7 27.0 332.3 25.6C331.9 24.2 332.1 24.8 332.3 24.6C332.5 24.4 332.6 23.3 333.5 24.4C334.4 25.5 336.6 29.1 337.6 31.4C338.6 33.7 339.1 35.7 339.5 38.1C339.9 40.5 340.3 42.7 340.0 45.8C339.7 49.0 339.6 52.0 337.6 56.9C335.6 61.8 331.3 70.0 328.0 75.2C324.6 80.4 320.7 84.5 317.4 88.2C314.0 91.9 309.6 95.4 307.7 97.4C305.9 99.3 306.7 98.7 306.3 99.8C305.9 100.8 305.3 102.4 305.3 103.6C305.3 104.8 305.8 106.1 306.3 107.0C306.8 107.9 307.6 108.9 308.5 109.2C309.3 109.4 309.9 109.7 311.3 108.7C312.8 107.7 315.5 104.8 316.9 103.1C318.3 101.5 318.9 100.5 319.8 98.8C320.7 97.1 321.5 94.3 322.2 93.0C322.9 91.8 323.4 91.6 323.9 91.3C324.3 91.1 324.6 91.2 324.8 91.3C325.1 91.5 325.4 91.4 325.6 92.1C325.7 92.7 325.7 94.4 325.6 95.4C325.4 96.5 325.7 96.3 324.6 98.3C323.5 100.3 321.6 104.3 318.8 107.5C316.0 110.6 311.8 114.6 308.0 117.3C304.2 120.1 301.0 121.8 295.9 124.1C290.9 126.3 284.6 128.7 277.6 130.8C270.7 132.9 260.7 134.8 254.0 136.6C247.4 138.4 242.7 139.8 237.7 141.9C232.6 144.0 226.9 147.1 223.7 149.1C220.5 151.2 219.2 152.7 218.7 154.2C218.1 155.7 219.4 157.5 220.3 158.3C221.3 159.0 222.6 159.2 224.2 158.8C225.8 158.3 226.7 156.7 230.0 155.4C233.3 154.0 239.4 152.6 243.9 150.6C248.5 148.6 254.8 144.5 257.4 143.3C260.1 142.1 259.1 143.0 259.8 143.3C260.6 143.7 261.8 143.5 262.0 145.5C262.2 147.5 261.7 152.9 261.0 155.1C260.4 157.4 259.2 157.0 258.1 159.0C257.1 161.0 255.9 165.0 254.8 167.2C253.6 169.3 252.7 170.5 251.4 172.0C250.1 173.5 248.5 174.9 246.8 176.1C245.1 177.3 243.0 178.3 241.0 179.0C239.1 179.7 237.4 180.2 235.3 180.4C233.1 180.7 229.4 179.6 228.0 180.4C226.7 181.3 227.8 184.0 227.3 185.5C226.8 187.0 225.2 187.9 224.9 189.3C224.7 190.8 225.9 192.4 225.9 194.1C225.9 195.9 224.9 198.6 224.9 199.9C224.9 201.2 225.7 200.2 225.9 201.9C226.0 203.5 226.1 207.6 225.9 209.6C225.6 211.6 224.8 211.6 224.4 213.9C224.1 216.1 223.9 218.4 223.9 223.0C223.9 227.7 223.1 234.7 224.4 241.8C225.7 249.0 230.1 261.4 231.7 265.9C233.2 270.4 233.1 267.7 233.6 268.8C234.1 269.9 234.1 271.5 234.5 272.6C235.0 273.8 236.1 274.7 236.5 275.5C236.8 276.3 236.0 276.3 236.5 277.5C237.0 278.7 238.9 281.5 239.4 282.8C239.8 284.0 239.5 284.4 239.4 285.2C239.2 285.9 238.9 286.6 238.4 287.1C237.9 287.6 236.6 287.4 236.5 288.0C236.3 288.7 237.6 290.1 237.4 290.9C237.3 291.8 235.6 292.3 235.5 293.3C235.4 294.4 236.7 295.5 237.0 297.2C237.2 298.9 237.3 302.0 237.0 303.5C236.6 304.9 235.7 305.5 234.8 306.1C233.8 306.7 231.1 306.3 231.2 307.3C231.3 308.3 234.7 310.7 235.5 312.1C236.3 313.6 236.3 314.9 236.0 316.0C235.6 317.1 234.3 318.2 233.3 318.6C232.3 319.1 230.9 318.8 230.0 318.6C229.1 318.5 228.4 317.5 228.0 317.7C227.7 317.8 228.0 318.9 227.8 319.3C227.6 319.8 227.2 320.3 226.6 320.6C226.0 320.8 224.5 320.0 224.4 320.8C224.4 321.6 226.0 323.7 226.4 325.1C226.7 326.6 226.6 328.5 226.4 329.5C226.2 330.5 225.7 330.7 225.2 331.1C224.6 331.6 223.9 332.0 223.2 332.1C222.6 332.2 221.9 332.0 221.3 331.6C220.7 331.2 220.2 329.6 219.4 329.7C218.6 329.8 217.6 331.9 216.5 332.1C215.4 332.3 213.3 330.3 212.9 330.9C212.4 331.5 213.8 334.0 213.8 335.7C213.8 337.4 213.5 339.8 212.9 341.0C212.3 342.3 211.1 342.8 210.2 343.2C209.3 343.5 208.3 343.4 207.3 343.2C206.4 342.9 205.0 341.9 204.4 341.7C203.8 341.6 204.0 341.1 203.7 342.5C203.4 343.8 203.3 348.0 202.8 349.7C202.2 351.4 201.6 352.2 200.6 352.8C199.6 353.4 197.9 353.5 196.7 353.3C195.6 353.1 194.3 350.6 193.6 351.6C192.9 352.6 193.3 357.1 192.6 359.3C192.0 361.6 190.2 363.2 189.8 365.1C189.3 366.9 190.0 368.9 189.8 370.4C189.5 371.8 189.0 372.8 188.3 373.8C187.6 374.7 186.3 375.6 185.7 375.9ZM127.4 248.3C125.9 249.5 126.0 248.6 125.5 248.3C125.0 248.0 124.1 247.3 124.3 246.6C124.4 246.0 125.9 244.8 126.2 244.2C126.5 243.6 127.0 242.6 126.0 243.0C125.0 243.5 122.3 246.2 120.2 246.9C118.1 247.6 114.8 247.7 113.4 247.4C112.1 247.0 112.9 245.4 112.0 245.0C111.1 244.5 108.9 244.8 108.1 244.5C107.3 244.1 108.0 243.4 107.2 243.0C106.4 242.6 104.5 242.6 103.3 242.1C102.2 241.5 99.3 240.1 100.2 239.9C101.1 239.7 105.7 241.0 108.6 241.1C111.5 241.2 114.8 241.0 117.8 240.6C120.7 240.2 122.9 239.8 126.4 238.7C130.0 237.6 136.5 234.8 139.0 233.9C141.4 232.9 140.0 233.8 140.9 232.9C141.8 232.1 143.0 231.5 144.5 228.8C145.9 226.2 148.7 217.6 149.6 217.0C150.4 216.5 149.7 221.7 149.3 225.4C148.9 229.2 148.1 237.0 147.4 239.4C146.7 241.9 145.7 240.3 145.2 240.1C144.7 239.9 144.7 238.2 144.3 238.2C143.8 238.2 142.8 239.5 142.6 239.9C142.3 240.3 142.8 240.5 142.6 240.9C142.4 241.2 141.8 241.9 141.4 242.1C140.9 242.3 140.6 241.5 139.9 242.1C139.2 242.6 137.8 245.0 137.0 245.4C136.3 245.9 135.6 245.4 135.3 244.7C135.1 244.0 135.5 241.9 135.3 241.3C135.2 240.7 135.9 239.9 134.6 241.1C133.3 242.3 128.9 247.1 127.4 248.3ZM176.0 193.4C174.6 193.4 172.5 192.7 171.2 192.0C170.0 191.3 169.4 190.6 168.6 189.3C167.7 188.1 166.5 185.5 166.2 184.5C165.8 183.5 164.8 183.4 166.4 183.3C168.0 183.3 173.5 183.8 175.6 184.3C177.6 184.8 177.9 185.6 178.7 186.4C179.4 187.3 179.9 188.4 180.1 189.3C180.4 190.3 180.8 191.5 180.1 192.2C179.4 192.9 177.5 193.5 176.0 193.4Z"
PERIM = 4185

# Demarrage : le cerf emerge par le bas derriere un masque a bord degrade.
# L'ordre d'apparition n'est pas arbitraire — poitrail, cou, tete, et les
# bois en dernier : on termine sur l'element le plus fort du logo.
CERF = (
    '<svg viewBox="0 0 380 400" width="{0}" height="{1}">'
    '<defs><linearGradient id="gr" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#000"/><stop offset="0.2" stop-color="#fff"/>'
    '<stop offset="1" stop-color="#fff"/></linearGradient>'
    '<mask id="mk"><rect class="mkr" x="0" y="-400" width="380" height="800" '
    'fill="url(#gr)"/></mask></defs>'
    '<path class="rm" d="' + TRACE_D + '"/></svg>'
)

# --- Panneau de detail de l'accueil -----------------------------------
#
# Cliquer un titre surveille ouvrait le graphique et rien d'autre. On
# voyait la courbe sans savoir POURQUOI le titre etait la. Ce panneau
# repond a la question avant d'ouvrir quoi que ce soit.
# --- Style de la fiche, partage par les deux pages --------------------
#
# La fiche s'affiche sur l'accueil ET sur la page STRATEGIE. Son style
# doit donc voyager avec elle : laisse dans le CSS d'une seule page,
# elle s'affichait ailleurs sans mise en forme, libelles et valeurs
# colles les uns aux autres.
CSS_FICHE = """
.lig{border:1px solid var(--bord);padding:11px 13px;margin-bottom:9px;
 clip-path:polygon(11px 0,100% 0,100% calc(100% - 11px),
 calc(100% - 11px) 100%,0 100%,0 11px)}
.lig h3{font:500 13px ui-monospace,monospace;letter-spacing:.1em;
 color:var(--txt-fort);margin-bottom:8px}
.lig h3 span{font-size:10.5px;color:var(--txt-faible);letter-spacing:.06em}
.kv2{display:grid;grid-template-columns:1fr auto;gap:2px 10px;
 font:400 11.5px ui-monospace,monospace;color:var(--txt-mi)}
.kv2 b{color:var(--txt-fort);text-align:right}
.trajet{margin:9px 0;padding:8px 10px;background:rgba(8,20,26,.5);
 border-left:2px solid var(--acc)}
.sortie{display:flex;justify-content:space-between;font-size:11px;
 padding:3px 0;color:var(--txt-mi)}
.sortie.on{color:var(--neg)}
.sortie .et{font:500 9px ui-monospace,monospace;letter-spacing:.14em}
.pos{color:var(--pos)}.neg{color:var(--neg)}

/* --- L'ETAT, EN GRAND -------------------------------------------------
   Le reproche etait juste : tout etait en 11 px et se ressemblait. Ce
   qui decide se lit maintenant de loin, le detail reste sous les yeux
   pour qui veut verifier. Aucune de ces classes ne porte d'animation de
   mise en page : uniquement des couleurs et des bordures. */
.etat{margin:10px 0 12px;padding:13px 15px;border:1px solid #123c47;
 background:rgba(8,20,26,.55)}
.etat.chaud{border-color:#7d2530;background:rgba(40,10,14,.42)}
.etat.tiede{border-color:#7a5b1e;background:rgba(38,28,8,.38)}
.etat .gros{font:600 25px ui-monospace,monospace;letter-spacing:.04em;
 color:var(--txt-fort);line-height:1.25}
.etat.chaud .gros{color:var(--neg)}
.etat .sous{margin-top:7px;font-size:12px;line-height:1.7;color:var(--txt-doux)}
.etat .sous b{color:var(--txt-fort)}
.chiffres{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));
 gap:9px;margin:11px 0}
.chiffres .c{padding:8px 10px;border:1px solid var(--bord);
 background:rgba(8,20,26,.42)}
.chiffres .c .e{font:500 8.5px ui-monospace,monospace;letter-spacing:.15em;
 color:var(--txt-faible);display:block;margin-bottom:4px}
.chiffres .c .v{font:600 17px ui-monospace,monospace;color:var(--txt-fort);white-space:nowrap;overflow-wrap:normal}
.chiffres .c .v.pos{color:var(--pos)}
.chiffres .c .v.neg{color:var(--neg)}
.sortie.gr{font-size:12.5px;padding:6px 9px;margin-bottom:3px;
 border:1px solid var(--bord);background:rgba(8,20,26,.35)}
.sortie.gr.on{border-color:#7d2530;background:rgba(40,10,14,.4)}
.sortie.gr .et{font-size:10px;letter-spacing:.16em}
/* Les etiquettes des blocs manquants et des vetos. Sans cette regle, les
   `span` restent en ligne, sans ecart, et se lisent comme un seul mot. */
.manque{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
.manque span{font:400 10px ui-monospace,monospace;padding:3px 7px;
 border:1px solid #7d2530;color:#f87171;white-space:nowrap}
.manque span.ok{border-color:#10705a;color:var(--pos)}
/* Les blocs manquants, nommes ET chiffres. Une etiquette « 4a_rvol »
   ne dit ni ce qui manque ni de combien on est loin ; deux lignes si. */
.mqf{margin-top:9px}
.mqf div{margin-bottom:8px;line-height:1.45}
.mqf b{display:block;color:#fca5a5;font-weight:500;font-size:13px}
.mqf i{font-style:normal;color:#64748b;font-size:12px;
 font-variant-numeric:tabular-nums}
.thz{width:100%;border-collapse:collapse;margin-top:8px;
 font:400 11px ui-monospace,monospace}
.thz th{text-align:right;padding:4px 5px;font-weight:500;font-size:8.5px;
 letter-spacing:.13em;color:var(--txt-faible);border-bottom:1px solid var(--bord)}
.thz th:first-child,.thz td:first-child{text-align:left}
.thz td{text-align:right;padding:3px 5px;border-bottom:1px solid #0b2028;
 color:var(--txt-doux)}
.thz td:first-child{color:var(--txt-fort)}
.repli{margin-top:11px}
.repli>summary{cursor:pointer;font:500 9px ui-monospace,monospace;
 letter-spacing:.17em;color:var(--txt-faible);padding:5px 0;list-style:none}
.repli>summary::-webkit-details-marker{display:none}
.repli>summary:before{content:"[ + ]  "}
.repli[open]>summary:before{content:"[ - ]  "}
.repli>summary:hover{color:var(--acc)}
"""


CSS_DETAIL = """
#voile{position:fixed;inset:0;z-index:80;background:rgba(2,5,9,.82);
 display:none;align-items:center;justify-content:center;padding:26px}
#voile.ouvert{display:flex}
#detail{width:min(760px,94vw);max-height:88vh;overflow-y:auto;
 background:rgba(4,10,14,.98);border:1px solid #123c47;padding:19px 22px;
 clip-path:polygon(15px 0,100% 0,100% calc(100% - 15px),
 calc(100% - 15px) 100%,0 100%,0 15px)}
#detail .tete{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}
#detail .tete h2{flex:1;font:500 15px ui-monospace,monospace;
 letter-spacing:.14em;color:var(--acc)}
#detail .fx{cursor:pointer;font-size:17px;color:#5d8a97;padding:0 5px;
 user-select:none}
#detail .fx:hover{color:var(--neg)}
#detail .pourquoi{margin:10px 0 13px;padding:10px 12px;
 background:rgba(8,20,26,.55);border-left:2px solid var(--acc);
 font-size:12px;line-height:1.7;color:var(--txt-doux)}
#detail .pourquoi b{color:var(--txt-fort)}
#detail .manque{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
#detail .manque span{font:400 10px ui-monospace,monospace;padding:3px 7px;
 border:1px solid #7d2530;color:#f87171}
#detail .manque span.ok{border-color:#10705a;color:var(--pos)}
#detail .actions{display:flex;gap:7px;margin-top:14px}
.rap{border:1px solid var(--bord);padding:10px 12px;margin-bottom:8px}
.rap .n{font:500 12px ui-monospace,monospace;color:var(--txt-fort)}
.rap .d{font-size:11px;color:var(--txt-mi);margin-top:3px;line-height:1.6}
"""

CSS = hd.CSS + hd.FOND_CSS + rg.CSS_OPTIONS + rg.CSS_THEMES \
    + rg.TIROIR_CSS + CSS_FICHE + CSS_DETAIL + """
*{box-sizing:border-box;margin:0}
body{background:var(--fond);color:var(--txt);
 font:14px var(--corps-police,ui-sans-serif,Segoe UI,system-ui);
 min-height:100vh;overflow-x:hidden}
#splash{position:fixed;inset:0;background:#080b10;display:flex;flex-direction:column;
 align-items:center;justify-content:center;gap:17px;z-index:99;
 animation:out .8s ease 2.9s forwards}
@keyframes out{to{opacity:0;visibility:hidden}}
.rm{fill:#c9b28a;fill-rule:evenodd;mask:url(#mk)}
.fx{fill:#c9b28a;fill-rule:evenodd}
.mkr{animation:up 1.9s cubic-bezier(.33,0,.15,1) forwards}
@keyframes up{from{transform:translateY(800px)}to{transform:translateY(0)}}
#splash .rule{width:120px;height:1px;background:#c9b28a;opacity:.4;
 animation:fade .9s ease 1.5s backwards}
/* LE SAUT DE LA PREMIERE PAGE VENAIT D'ICI.
   L'ouverture animait `letter-spacing` et `text-indent` de 1,1em a
   0,52em. Ce sont deux proprietes de MISE EN PAGE : le navigateur
   recalcule la largeur du mot a chaque image, et comme le titre est
   centre, toute la ligne se deplace. En 1280 de large le mouvement
   passait inapercu ; en plein ecran il fait plusieurs dizaines de
   pixels, d'un coup, a l'ouverture — c'est le « visuel qui saute ».
   Le meme effet, lettre par lettre, en `transform` : chaque lettre
   part ecartee du centre et revient. La largeur du mot ne change
   jamais, donc plus rien ne se recalcule. */
#splash h1{font-size:23px;font-weight:300;color:#c9b28a;letter-spacing:.52em;
 text-indent:.52em}
#splash h1 i{display:inline-block;font-style:normal;opacity:0;
 will-change:transform,opacity;
 animation:lettre 1.05s cubic-bezier(.25,0,.15,1) forwards;
 animation-delay:calc(1.5s + var(--i,0) * .045s)}
@keyframes lettre{from{opacity:0;transform:translateX(calc(var(--d,0) * 1em))}
 to{opacity:1;transform:translateX(0)}}
#splash p{font-size:10px;letter-spacing:.34em;color:#6d675f;text-indent:.34em;
 animation:fade .9s ease 1.9s backwards}
.load{width:120px;height:1px;background:#1a1d22;margin-top:5px;border-radius:2px;overflow:hidden}
.load i{display:block;height:100%;background:#c9b28a;opacity:.55;animation:go 2.6s ease;transform-origin:left}
@keyframes go{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.mark svg{flex:none}

/* --- Mise en page : un seul ecran, aucun defilement global --------
   La hauteur est figee a 100vh. Seuls les corps de panneaux defilent,
   ce qui garde la console toujours visible : l'hologramme, les cadrans
   et le verdict ne sortent jamais du champ. */
html{height:100%}
body{overflow:hidden}
.fond{transform:translateZ(0);backface-visibility:hidden}
.app{position:relative;z-index:1;height:100vh;display:grid;
 grid-template-rows:auto auto minmax(0,1fr);
 gap:var(--gap);padding:9px 13px 11px}

/* .bar et .raf vivent dans hud.py : une barre, une definition. */
/* --- Majordome. Disque flottant, panneau au clic. --- */
.maj{position:fixed;right:18px;bottom:18px;z-index:70;width:54px;height:54px;
 border-radius:50%;background:rgba(6,18,26,.9);border:1px solid var(--bord-fort);
 color:var(--acc);display:grid;place-items:center;cursor:pointer;
 box-shadow:0 0 22px rgba(34,211,238,.18);
 transition:box-shadow .18s,color .18s,border-color .18s}
.maj:hover{box-shadow:0 0 34px rgba(34,211,238,.4)}
.maj svg{width:30px;height:30px}
.maj .mo{transform-origin:22px 22px;animation:tour 22s linear infinite}
.maj.ecoute{color:#34d399;border-color:#34d399;
 animation:battement 1.4s ease-in-out infinite}
.maj.parle{color:#f59e0b;border-color:#f59e0b}
@keyframes battement{0%,100%{box-shadow:0 0 14px rgba(52,211,153,.3)}
 50%{box-shadow:0 0 34px rgba(52,211,153,.75)}}
.majp{position:fixed;right:18px;bottom:82px;z-index:70;width:330px;
 background:rgba(4,10,14,.96);border:1px solid #0d2a33;padding:13px 15px;
 display:none;
 clip-path:polygon(13px 0,100% 0,100% calc(100% - 13px),
 calc(100% - 13px) 100%,0 100%,0 13px)}
.majp.ouvert{display:block}
/* Entete : titre a gauche, croix de fermeture a droite. Sans elle, le
   panneau une fois ouvert ne se refermait plus et masquait l'ecran. */
.majh{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.majt{font:500 8px ui-monospace,monospace;letter-spacing:.26em;color:var(--txt-faible);
 flex:1}
.majx{flex:none;width:22px;height:22px;line-height:19px;text-align:center;
 cursor:pointer;font-size:15px;color:#5d8a97;background:rgba(8,34,42,.9);
 border:1px solid #123c47;user-select:none;
 clip-path:polygon(5px 0,100% 0,100% calc(100% - 5px),
 calc(100% - 5px) 100%,0 100%,0 5px)}
.majx:hover{color:#f87171;border-color:#7d2530;background:#2a1114}
.majmic.ko{color:#6b4a4f;border-color:#3a1c20}
.majr{font-size:12px;line-height:1.55;color:var(--txt-fort);min-height:42px;
 margin-bottom:9px}
.maje{font-size:9.5px;line-height:1.6;color:#2f5462;margin-top:8px}
.raf.occupe{color:var(--txt-faible);border-color:#123c47}
.raf.occupe span{display:inline-block;animation:tour 1s linear infinite}
#roue{top:8px;right:13px;width:34px;height:34px;line-height:32px;font-size:15px;
 border-radius:0;clip-path:polygon(7px 0,100% 0,100% calc(100% - 7px),
 calc(100% - 7px) 100%,0 100%,0 7px);background:rgba(8,34,42,.9)}
#roue:hover{background:#0e3b48}

/* --- Le panneau : meme traitement que le HUD ----------------------
   Coins biseautes, equerres dans les angles, bordure cyan sombre.
   Un seul et meme cadre pour toute l'application. */
.grille{display:grid;grid-template-columns:.92fr 1.08fr 1.1fr .9fr;
 gap:var(--gap);min-height:0}
/* La geometrie passe par des variables : c'est ce qui permet a un theme
   de changer la FORME du panneau — biseau, arrondi, densite, matiere —
   et pas seulement sa couleur. Les valeurs par defaut sont exactement
   l'apparence d'origine, donc un theme qui n'en redefinit aucune ne
   change rien. */
.pan{background:var(--pan-fond);border:1px solid var(--bord);
 position:relative;padding:var(--pad);display:flex;flex-direction:column;
 min-height:0;box-shadow:var(--pan-ombre);border-radius:var(--rayon);
 clip-path:polygon(var(--coin) 0,100% 0,100% calc(100% - var(--coin)),
 calc(100% - var(--coin)) 100%,0 100%,0 var(--coin));
 animation:monte .75s cubic-bezier(.22,1,.36,1) backwards}
.grille .pan:nth-child(1){animation-delay:.06s}
.grille .pan:nth-child(2){animation-delay:.16s}
.grille .pan:nth-child(3){animation-delay:.26s}
@keyframes monte{from{opacity:0;transform:translateY(22px)}}
/* equerres : elles respirent au lieu d'etre figees */
.pan::before,.pan::after{content:"";position:absolute;width:24px;height:24px;
 border:1px solid var(--bord-fort);pointer-events:none;
 opacity:var(--equerre);
 animation:equerre 4.6s ease-in-out infinite}
/* La variable doit entrer DANS les etapes : une animation l'emporte
   toujours sur une declaration normale, donc `opacity:var(--equerre)`
   seul etait rallume a chaque cycle. Avec --equerre a 0, les deux
   etapes valent zero et les equerres disparaissent vraiment. */
@keyframes equerre{0%,100%{opacity:calc(var(--equerre,1) * .45)}
 50%{opacity:calc(var(--equerre,1) * .95)}}
.pan::before{top:5px;right:5px;border-left:0;border-bottom:0}
.pan::after{bottom:5px;left:5px;border-right:0;border-top:0;
 animation-delay:2.3s}
/* trait lumineux qui parcourt le haut du panneau */
.trait{position:absolute;top:0;left:15px;right:0;height:1px;overflow:hidden;
 pointer-events:none}
.trait i{position:absolute;top:0;left:0;height:1px;width:34%;
 background:linear-gradient(90deg,transparent,var(--acc),transparent);
 will-change:transform;animation:court 5.2s linear infinite}
@keyframes court{0%{transform:translateX(-100%)}
 100%{transform:translateX(294%)}}
.grille .pan:nth-child(2) .trait i{animation-delay:1.7s}
.grille .pan:nth-child(3) .trait i{animation-delay:3.4s}
.pan h2{font:500 9.5px var(--titre-police,ui-monospace,Consolas,monospace);
 letter-spacing:var(--titre-espace,.24em);
 text-transform:var(--titre-casse,none);
 color:var(--txt-faible);margin-bottom:11px;flex:none;display:flex;
 align-items:center;gap:9px}
.pan h2::after{content:"";flex:1;height:1px;
 background:linear-gradient(90deg,#123c47,transparent)}
.corps{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;
 padding-right:4px}
.corps::-webkit-scrollbar{width:6px}
.corps::-webkit-scrollbar-track{background:#07131a}
.corps::-webkit-scrollbar-thumb{background:#13323c}
.corps::-webkit-scrollbar-thumb:hover{background:var(--bord-fort)}

/* --- Le HUD resserre pour tenir dans le budget vertical ---------- */
/* Le HUD passe en verre pour laisser voir la projection derriere.
   La hauteur est FIGEE : sans ca, quand /api/etat remplace les cadrans,
   le contenu change de taille et toute la page saute a chaque
   rafraichissement. */
.hud{margin-bottom:0;padding:13px 16px 9px;flex:none;
 background:rgba(5,8,13,.62);min-height:170px;contain:layout style}
.hud-g{grid-template-columns:300px auto 300px!important;align-items:center}
#hud-cad,#hud-rails{min-height:112px;contain:layout}
#hud-band{min-height:44px;contain:layout}
#hud-verdict{min-height:13px;display:block}
.hud-c{display:flex;flex-direction:column;align-items:center;
 justify-content:center;min-width:250px}
.cad svg{width:92px;height:92px}
.hud-id{margin-top:2px}
.hud-id .tk{font-size:30px;letter-spacing:.36em;text-indent:.36em;
 text-shadow:0 0 24px rgba(34,211,238,.42)}
.hud-id .st{font-size:9.5px;margin-top:6px;letter-spacing:.3em}
.bandeau{margin-top:9px;padding-top:8px}
.bandeau .v{font-size:12.5px}

/* --- Saisie et boutons, au meme dessin que les cadres ------------ */
.row{display:flex;gap:7px}
input{flex:1;min-width:0;background:var(--champ-fond);
 border:1px solid var(--bord);
 padding:10px 12px;color:var(--txt-fort);font:15px ui-monospace,Consolas,monospace;
 letter-spacing:.07em;outline:none;
 transition:border-color .14s,background-color .14s}
input:focus{border-color:var(--acc);background:#081b23}
input::placeholder{color:#2f5462;letter-spacing:.03em}
button{background:#08222a;border:1px solid var(--bord-fort);color:var(--acc);
 padding:10px 17px;font:500 12.5px ui-monospace,Consolas,monospace;
 letter-spacing:.12em;cursor:pointer;white-space:nowrap;
 transition:background-color .14s,border-color .14s,color .14s;
 clip-path:polygon(7px 0,100% 0,100% calc(100% - 7px),
 calc(100% - 7px) 100%,0 100%,0 7px)}
button:hover{background:#0e3b48;border-color:var(--acc)}
button:active{transform:translateY(1px)}
.sec{background:#0a1620;border-color:#123c47;color:var(--txt-mi)}
.sec:hover{background:#0e2530;color:var(--txt-fort)}

/* formulaire des positions : quatre champs qui tiennent toujours */
.posf{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;
 margin-bottom:9px}
.posf input{font-size:13px;padding:9px 10px}
.posf button{grid-column:1/-1;padding:9px}

/* scans : une colonne de quatre lignes compactes */
.gh{display:flex;flex-direction:column;gap:7px}
.gh button{text-align:left;padding:10px 13px;background:#0a1620;
 border-color:#123c47;color:var(--txt-doux)}
.gh button:hover{border-color:var(--acc);color:var(--txt-fort)}
.gh b{display:block;color:var(--txt-fort);font-weight:500;font-size:12.5px;
 letter-spacing:.1em;margin-bottom:2px}
.gh i{font-style:normal;font-size:10px;color:var(--txt-faible);letter-spacing:.1em}

.msg{font-size:12px;line-height:1.7;color:#5b7b8a;min-height:18px;margin-top:10px;
 white-space:pre-wrap;font-family:ui-monospace,Consolas,monospace}
.err{color:#fb7185}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
th{text-align:left;color:var(--txt-faible);font-weight:400;font-size:9px;letter-spacing:.16em;
 padding:6px 7px;font-family:ui-monospace,Consolas,monospace}
td{padding:7px;border-top:1px solid var(--bord);color:var(--txt-doux)}
tr:hover td{background:#08181f}
td b{color:#e8f6fa;font-weight:500}
.go{color:var(--acc);cursor:pointer}
.go:hover{text-shadow:0 0 7px var(--acc)}
.clebloc{margin:8px 0 10px;padding:9px 11px;background:var(--pan-fond);
 border:1px solid #123c47}
.clebloc .ch{font-size:7.5px;letter-spacing:.2em;color:var(--txt-faible);display:block;
 margin-bottom:6px}
.clebloc input{font-size:12px}
.clebloc button{padding:8px 12px;font-size:10.5px}
.act{padding:7px 0;border-bottom:1px solid #0b2028}
.act:last-child{border:0}
.ah{display:flex;gap:9px;font:400 8.5px ui-monospace,monospace;
 letter-spacing:.14em;color:#2f5462;margin-bottom:3px}
.ah b{font-weight:400;margin-left:auto}
.at{font-size:11.5px;line-height:1.5;color:var(--txt-doux)}
.sep2{height:1px;background:#0b2028;margin:11px 0 9px}
select{background:#07131a;border:1px solid #123c47;color:var(--txt-fort);
 padding:9px 8px;font:12px ui-monospace,monospace;flex:1;min-width:0;
 outline:none}
select:focus{border-color:var(--acc)}
.p0b{display:flex;align-items:center;gap:9px;padding:9px 11px;
 border:1px solid;margin-bottom:8px;
 clip-path:polygon(9px 0,100% 0,100% calc(100% - 9px),
 calc(100% - 9px) 100%,0 100%,0 9px)}
.p0b b{font:500 19px ui-monospace,monospace;letter-spacing:.14em}
.p0b span{font-size:10px;color:var(--txt-mi);line-height:1.4}
.p0c{font-size:10px;line-height:1.7;color:var(--txt-mi);font-family:ui-monospace,
 monospace;white-space:pre-wrap;max-height:120px;overflow-y:auto;
 border-top:1px solid #0b2028;padding-top:7px;margin-top:7px}
.avert{margin-top:11px;font:400 10px ui-monospace,Consolas,monospace;
 line-height:1.75;color:#2f5462;border-top:1px solid var(--bord);padding-top:9px}

/* --- Ecrans etroits : on rend le defilement, sinon rien ne tient - */
@media(max-width:1500px){
 .grille{grid-template-columns:1fr 1fr}}
@media(max-width:1150px){
 body{overflow:auto}
 .app{height:auto;grid-template-rows:none}
 .grille{grid-template-columns:1fr}
 .corps{overflow:visible}
}
"""

JS = """
const $=i=>document.getElementById(i);
const clean=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
$('tk').addEventListener('keydown',e=>{if(e.key==='Enter')go();});

async function go(){
 const t=$('tk').value.trim(); if(!t)return;
 $('m').textContent='Chargement de '+t.toUpperCase()+' (20 ans d\\'historique)...';
 $('m').className='msg'; $('res').innerHTML='';
 try{
  const j=await (await fetch('/api/analyse?ticker='+encodeURIComponent(t))).json();
  if(j.ok){location.href='/graphique?ticker='+encodeURIComponent(j.ticker);}
  else{$('m').textContent=j.erreur; $('m').className='msg err';}
 }catch(e){$('m').textContent='Erreur : '+e; $('m').className='msg err';}
}

async function cherche(){
 const t=$('tk').value.trim(); if(!t)return;
 $('m').textContent='Recherche...'; $('m').className='msg'; $('res').innerHTML='';
 const j=await (await fetch('/api/find?q='+encodeURIComponent(t))).json();
 if(!j.res.length){$('m').textContent=
   "Aucun resultat. Si la societe n'est pas cotee, il n'existe pas de ticker.";
   $('m').className='msg err'; return;}
 $('m').textContent="Clique sur un ticker pour l'analyser.";
 let h='<table><tr><th>TICKER</th><th>PLACE</th><th>DEVISE</th><th>NOM</th></tr>';
 j.res.forEach(x=>{h+='<tr><td class="go" onclick="pick(\\''+clean(x.ticker)+
  '\\')"><b>'+clean(x.ticker)+'</b></td><td>'+clean(x.place)+'</td><td>'+
  clean(x.devise)+'</td><td>'+clean(x.nom)+'</td></tr>';});
 $('res').innerHTML=h+'</table>';
}
function pick(t){$('tk').value=t; go();}

async function scan(u,m){
 $('ms').textContent='Scan '+u+' en cours, ne ferme pas la fenetre...';
 $('ms').className='msg'; $('rs').innerHTML='';
 try{
  const j=await (await fetch('/api/scan?universe='+u+'&marche='+m)).json();
  if(!j.ok){$('ms').textContent=j.erreur; $('ms').className='msg err'; return;}
  // Un titre ecarte par le controle qualite doit se VOIR. Sans cette
  // ligne, "0 candidat sur 60 titres" ne dit pas que 40 series ont ete
  // refusees : elles disparaissent en silence, ce qui est exactement le
  // defaut que le controle qualite est cense corriger.
  var ec=(j.ecartes&&j.ecartes.length)?
   '   '+j.ecartes.length+' ecarte(s) : donnees refusees':'';
  $('ms').textContent=j.regime+'   '+j.fired.length+' candidat(s) sur '+
   j.n+' titres'+ec;
  $('ms').title=ec?j.ecartes.join('  |  '):'';
  if(!j.fired.length){
   let h='<table><tr><th>LES PLUS PROCHES</th><th>BLOCS MANQUANTS</th></tr>';
   j.proches.forEach(x=>{h+='<tr><td class="go" onclick="fiche(\\''+clean(x.ticker)+
    '\\',\\''+clean(x.manque)+'\\')"><b>'+clean(x.ticker)+'</b></td><td>'+clean(x.manque)+'</td></tr>';});
   $('rs').innerHTML=h+'</table>'; radar(); return;}
  let h='<table><tr><th>TITRE</th><th>ENTREE</th><th>STOP</th><th>TITRES</th><th>RS 6M</th></tr>';
  j.fired.forEach(x=>{h+='<tr><td class="go" onclick="fiche(\\''+clean(x.ticker)+
   '\\',\\'\\')"><b>'+clean(x.ticker)+'</b></td><td>'+x.entree+'</td><td>'+x.stop+
   '</td><td>'+x.titres+'</td><td>'+x.rs+'</td></tr>';});
  $('rs').innerHTML=h+'</table>'; radar();
 }catch(e){$('ms').textContent='Erreur : '+e; $('ms').className='msg err';}
}
"""

# Chaine BRUTE (r""") : en chaine normale, Python transforme \' en
# apostrophe nue et casse la syntaxe JS de toute la page. Ne pas retirer le r.
JS_POS = r"""
function coul(v){return v>=0?'#34d399':'#f87171';}

async function pos(){
 var mp=$('mp'), rp=$('rp');
 if(!mp||!rp)return;
 mp.className='msg'; mp.textContent='Releve des positions...';
 try{
  var r=await fetch('/api/positions');
  var j=await r.json();
  if(!j || !j.lignes){throw new Error(j&&j.erreur?j.erreur:'reponse invalide');}
  if(!j.lignes.length){
   rp.innerHTML='';
   mp.textContent="Aucune position. Ajoute ici les lignes que tu detiens sur IBKR.";
   return;}
  mp.textContent='';
  var h='<table><tr><th>TITRE</th><th>QTE</th><th>ENTREE</th><th>COURS</th>'
   +'<th>P&amp;L</th><th>STOP</th><th>VERDICT</th><th></th></tr>';
  j.lignes.forEach(function(l){
   var vc=(l.verdict==='CONSERVER')?'var(--txt)'
        :((l.verdict==='SURVEILLER')?'#fbbf24'
        :((l.verdict==='INDISPONIBLE')?'#64748b':'#f87171'));
   var act=Object.keys(l.sorties||{}).filter(function(k){return l.sorties[k];});
   var pnl=(l.pnl_pct==null)?'<td>&ndash;</td>'
        :'<td style="color:'+coul(l.pnl_pct)+'">'+l.pnl_pct+'%</td>';
   var stp=(l.marge_stop==null)?'<td>&ndash;</td>'
        :'<td style="color:'+coul(l.marge_stop)+'">'+l.marge_stop+'%</td>';
   var det=act.length?'<br><span style="font-size:11px;color:#64748b">'
        +clean(act.join(', '))+'</span>':'';
   if(l.erreur){det='<br><span style="font-size:11px;color:#64748b">'
        +clean(l.erreur)+'</span>';}
   h+='<tr><td class="go" onclick="pick(\'' +clean(l.ticker)+ '\')"><b>'
    +clean(l.ticker)+'</b></td><td>'+l.quantite+'</td><td>'+l.entree+'</td>'
    +'<td>'+(l.cours==null?'&ndash;':l.cours)+'</td>'+pnl+stp
    +'<td style="color:'+vc+'">'+clean(l.verdict)+det+'</td>'
    +'<td class="go" onclick="delpos(\'' +clean(l.ticker)+ '\')">retirer</td></tr>';
  });
  rp.innerHTML=h+'</table>';
 }catch(e){
  rp.innerHTML='';
  mp.className='msg err';
  mp.textContent='Releve impossible : '+e.message;
 }
}

async function addpos(){
 var mp=$('mp');
 var t=$('ptk').value.trim(), q=parseFloat($('pq').value),
     e=parseFloat($('pe').value), s=parseFloat($('pst').value);
 if(!t||!q||!e){
  mp.className='msg err';
  mp.textContent="Ticker, quantite et prix d\'entree sont obligatoires.";
  return;}
 mp.className='msg'; mp.textContent='Enregistrement...';
 try{
  var r=await fetch('/api/positions',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({ticker:t,quantite:q,entree:e,stop:isNaN(s)?null:s})});
  var j=await r.json();
  if(!j.ok){throw new Error(j.erreur||'refus du serveur');}
  $('ptk').value=''; $('pq').value=''; $('pe').value=''; $('pst').value='';
  pos();
 }catch(err){mp.className='msg err'; mp.textContent='Echec : '+err.message;}
}

async function delpos(t){
 try{
  await fetch('/api/positions',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({action:'retire',ticker:t})});
 }catch(e){}
 pos();
}

['ptk','pq','pe','pst'].forEach(function(id){
 var el=$(id);
 if(el)el.addEventListener('keydown',function(ev){
  if(ev.key==='Enter')addpos();});
});
pos();
"""

# Chaine BRUTE : voir l'avertissement sur JS_POS.
JS_HUD = r"""
async function etat(){
 var v=$('hud-verdict');
 if(!v)return;
 try{
  var j=await (await fetch('/api/etat')).json();
  if(!j.ok)throw new Error(j.erreur||'indisponible');
  $('hud-rails').innerHTML=j.rails;
  $('hud-band').innerHTML=j.bandeau;
  v.textContent=j.verdict;
 }catch(e){ v.textContent='MARCHE INDISPONIBLE'; }
}
async function p0Lance(){
 const m=$('p0m');
 m.className='msg'; m.textContent='Demarrage...';
 try{
  const j=await (await fetch('/api/phase0',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({univers:$('p0u').value})})).json();
  if(!j.ok) throw new Error(j.erreur||'refus');
  p0Suivi();
 }catch(e){ m.className='msg err'; m.textContent='Echec : '+e.message; }
}

async function p0Suivi(){
 try{
  const j=await (await fetch('/api/phase0')).json();
  const v=$('p0v'), m=$('p0m');
  if(j.verdict){
   const go=j.verdict==='GO';
   const c=go?'#34d399':'#f87171';
   v.innerHTML='<div class="p0b" style="border-color:'+c+'">'
    +'<b style="color:'+c+'">'+j.verdict+'</b>'
    +'<span>'+clean(j.univers)+'<br>'+clean(j.duree)+'</span></div>'
    +(j.criteres.length?'<div class="p0c">'
      +j.criteres.map(clean).join('\n')+'</div>':'');
   m.textContent = go
    ? 'Les cinq criteres passent. Reste la barre economique contre SMH.'
    : "NO-GO : l'hypothese est morte, elle ne se retouche pas.";
   m.className = 'msg';
  } else if(j.encours){
   v.innerHTML='<div class="p0b" style="border-color:#f59e0b">'
    +'<b style="color:#f59e0b">CALCUL</b><span>'+clean(j.univers)
    +'<br>'+clean(j.duree)+' &middot; '+j.n+' lignes</span></div>'
    +'<div class="p0c">'+j.lignes.map(clean).join('\n')+'</div>';
   m.className='msg'; m.textContent='Tu peux fermer la fenetre, le calcul '
    +'continue. Reviens plus tard.';
  }
  if(j.encours) setTimeout(p0Suivi, 4000);
 }catch(e){}
}
p0Suivi();

async function radar(){
 const g=document.getElementById('echos'), lab=$('rad-lab');
 if(!g)return;
 try{
  const j=await (await fetch('/api/radar')).json();
  if(j.vide){ g.innerHTML=''; lab.textContent='AUCUN SCAN'; return; }
  lab.textContent=clean(j.univers.toUpperCase())+' '+clean(j.quand);
  g.innerHTML=j.echos.map(function(e,i){
   const a=e.a*Math.PI/180;
   const x=(66+e.r*Math.cos(a)).toFixed(1), y=(66+e.r*Math.sin(a)).toFixed(1);
   const c = e.manque===0 ? '#34d399'
           : (e.manque<=2 ? '#f59e0b' : '#22d3ee');
   const rr = e.manque===0 ? 3.6 : 2.6;
   return '<g class="ec" style="cursor:pointer" onclick="pick(\''
    +clean(e.t)+'\')">'
    +'<title>'+clean(e.t)+' \u2014 '
    +(e.manque?e.manque+' bloc(s) manquant(s)':'signal complet')+'</title>'
    +'<circle cx="'+x+'" cy="'+y+'" r="'+rr+'" fill="'+c+'">'
    +'<animate attributeName="opacity" values="0;1;1;0" dur="4.2s" '
    +'begin="'+(i*0.28).toFixed(2)+'s" repeatCount="indefinite"/></circle>'
    +(e.manque===0?'<circle cx="'+x+'" cy="'+y+'" r="7" fill="none" '
      +'stroke="'+c+'" stroke-width=".8"><animate attributeName="r" '
      +'values="3;11" dur="2s" repeatCount="indefinite"/>'
      +'<animate attributeName="opacity" values=".9;0" dur="2s" '
      +'repeatCount="indefinite"/></circle>':'')
    +'</g>';
  }).join('');
 }catch(e){ lab.textContent='RADAR INDISPONIBLE'; }
}
radar();

async function actus(){
 const m=$('man'), r=$('ran');
 if(!m)return;
 try{
  const j=await (await fetch('/api/actus')).json();
  if(j.items && j.items.length && j.items[0].sans_cle){
   $('clebloc').style.display='block';
   m.className='msg';
   m.textContent="Aucune cle enregistree. Sans elle, pas d'actualites.";
   $('ran').innerHTML=''; return;
  }
  if(j.items && j.items.length && j.items[0].erreur){
   $('clebloc').style.display='block';
   m.className='msg err';
   m.textContent=j.items[0].titre;
   $('ran').innerHTML=''; return;
  }
  // Alpha Vantage repond 200 meme quand le quota est epuise : le
  // message est dans l'item, pas dans le code HTTP.
  if(j.items && j.items.length && j.items[0].erreur){
   $('ran').innerHTML='';
   m.className='msg err';
   m.textContent=j.items[0].titre
    +(j.quota!=null?'  ('+j.quota+' appels restants aujourd\'hui)':'');
   return;
  }
  if(!j.items || !j.items.length) throw new Error('rien a afficher');
  $('clebloc').style.display='none';
  m.className='msg';
  m.textContent = (j.quota!=null && j.quota<=8)
   ? j.quota+' appels Alpha Vantage restants aujourd\'hui.' : '';
  r.innerHTML=j.items.map(function(a){
   var c = a.score==null ? 'var(--txt-mi)'
         : (a.score>0.15?'#34d399':(a.score<-0.15?'#f87171':'var(--txt)'));
   var s = a.score==null ? '' : (a.score>0.15?'positif'
         : (a.score<-0.15?'negatif':'neutre'));
   return '<div class="act">'
    +'<div class="ah"><span>'+clean(a.quand||'')+'</span>'
    +'<span>'+clean(a.source||'')+'</span>'
    +(s?'<b style="color:'+c+'">'+s+'</b>':'')+'</div>'
    +'<div class="at">'+clean(a.titre||'')+'</div></div>';
  }).join('');
 }catch(e){
  $('clebloc').style.display='block';
  m.className='msg err';
  m.textContent='Actualites indisponibles ('+e.message+'). '
   +'Colle ta cle ci-dessous, ou verifie que news.py est bien a jour.';
 }
}
actus();
setInterval(actus, 1800000);

// Ctrl+V est parfois avale par la fenetre : on lit le presse-papiers
// directement, et on enregistre dans la foulee.
async function collerCle(){
 const m=$('man');
 try{
  const v=(await navigator.clipboard.readText()).trim();
  if(!v) throw new Error('presse-papiers vide');
  $('cle').value=v;
  await poseCle();
 }catch(e){
  m.className='msg err';
  m.textContent="Lecture du presse-papiers refusee. Tape la cle a la main "
   +"dans le champ, ou ecris-la dans "
   +".bruce_cache\\cle-alphavantage.txt";
 }
}

// Ctrl+V n'est pas toujours transmis a la page dans la fenetre Windows.
// On lit le presse-papier directement.
async function collerCle(){
 const m=$('man');
 try{
  const v=await navigator.clipboard.readText();
  if(!v || !v.trim()) throw new Error('presse-papier vide');
  $('cle').value=v.trim();
  m.className='msg'; m.textContent='Cle collee. Clique ENREGISTRER.';
 }catch(e){
  m.className='msg err';
  m.textContent='Impossible de lire le presse-papier ('+e.message+'). '
   +'Tape la cle a la main, ou colle-la avec le clic droit.';
 }
}

async function poseCle(){
 const m=$('man'), v=$('cle').value.trim();
 if(!v){ m.className='msg err'; m.textContent='Colle la cle avant.'; return; }
 m.className='msg'; m.textContent='Enregistrement...';
 try{
  await fetch('/api/cle',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({cle:v})});
  $('cle').value=''; actus();
 }catch(e){ m.className='msg err'; m.textContent='Echec : '+e.message; }
}

// Un seul bouton relance tout : etat du marche, actualites, radar,
// positions. Les actualites forcent le contournement du cache.
// =====================================================================
// MAJORDOME
//
// Voix posee, phrases courtes, aucune flatterie et aucune incitation.
// Il rapporte ce que l'ecran affiche. Il ne conseille jamais d'acheter :
// la Phase 0 a rendu NO-GO, et un majordome qui pousse a l'ordre serait
// exactement le defaut qu'on evite depuis le debut.
// =====================================================================
const MAJ = {ecoute:false, reco:null, micKo:false, recu:false};
if(window.speechSynthesis){
 speechSynthesis.getVoices();
 speechSynthesis.onvoiceschanged=function(){ speechSynthesis.getVoices(); };
}

function majDit(txt, ecrire){
 // Une legere ponctuation fait respirer la synthese : sans elle, le
 // debit est plat et robotique.
 txt = String(txt).replace(/\. /g, '.  ');
 if(ecrire!==false) $('majr').textContent = txt;
 if(!window.speechSynthesis) return;
 try{
  speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(txt);
  u.lang='fr-FR'; u.rate=0.88; u.pitch=0.7; u.volume=1.0;
  // Ordre de preference : voix masculines francaises connues, puis toute
  // voix masculine, puis n'importe quelle voix francaise. Les voix
  // "Natural" de Windows 11 sont nettement meilleures que les anciennes.
  const v=speechSynthesis.getVoices().filter(function(x){
   return x.lang && x.lang.toLowerCase().indexOf('fr')===0;});
  const ordre=[/Henri.*Natural/i,/Paul.*Natural/i,/Remy.*Natural/i,
   /Claude.*Natural/i,/Natural/i,/Henri|Paul|Remy|Thierry|Guillaume|Claude/i,
   /Male|Homme/i];
  let choix=null;
  for(let i=0;i<ordre.length && !choix;i++)
   choix=v.find(function(x){return ordre[i].test(x.name);});
  if(choix||v[0]) u.voice=choix||v[0];
  const d=$('maj');
  u.onstart=function(){d.classList.add('parle');};
  u.onend=function(){d.classList.remove('parle');};
  speechSynthesis.speak(u);
 }catch(e){}
}

const UNIV={'cac':'cac40','cac 40':'cac40','dax':'dax','europe':'europe_total',
 'stoxx':'stoxx600','nasdaq':'nasdaq100','sp 500':'sp500','s&p 500':'sp500',
 'etats-unis':'us_total','amerique':'us_total','us':'us'};

async function majExec(txt){
 const q=(txt||'').toLowerCase().trim();
 if(!q){ majDit('Je vous ecoute.'); return; }
 $('majc').value='';

 if(/actualise|rafraich|met a jour/.test(q)){
  majDit('Je rafraichis les donnees.');
  await toutRafraichir();
  majDit('Donnees a jour.'); return;
 }
 if(/position/.test(q)){
  try{
   const j=await (await fetch('/api/positions')).json();
   const n=(j.lignes||[]).length;
   if(!n) return majDit('Aucune position enregistree.');
   const a=j.lignes.filter(function(l){
    return l.verdict!=='CONSERVER';}).length;
   majDit(n+(n>1?' lignes ouvertes. ':' ligne ouverte. ')
    +(a? a+(a>1?' demandent':' demande')+' une decision aujourd\'hui.'
       : 'Aucune ne demande de decision.'));
  }catch(e){ majDit('Je n\'arrive pas a lire vos positions.'); }
  return;
 }
 if(/etat|marche|regime/.test(q)){
  try{
   const j=await (await fetch('/api/etat')).json();
   majDit(j.verdict ? j.verdict.toLowerCase().replace(/_/g,' ')
    : 'Etat du marche indisponible.');
  }catch(e){ majDit('Etat du marche indisponible.'); }
  return;
 }
 if(/actualit|nouvelle|news/.test(q)){
  try{
   const j=await (await fetch('/api/actus')).json();
   const it=(j.items||[])[0];
   majDit(it && it.titre ? 'Derniere depeche. '+it.titre
    : 'Aucune actualite disponible.');
  }catch(e){ majDit('Actualites indisponibles.'); }
  return;
 }
 const ms=q.match(/scan(?:ne|ner)?\s+(.+)/);
 if(ms){
  const cle=Object.keys(UNIV).find(function(k){
   return ms[1].indexOf(k)>=0;});
  if(!cle) return majDit('Quel univers ? Cac 40, Dax, Europe, '
   +'Nasdaq, S et P 500, ou toute la cote americaine.');
  majDit('Je lance le scan. Cela peut prendre plusieurs minutes.');
  scan(UNIV[cle], 'us');
  return;
 }
 const ma=q.match(/(?:analyse|regarde|ouvre|affiche)\s+(.+)/);
 if(ma){
  const t=ma[1].replace(/[.?!]/g,'').trim();
  majDit('J\'ouvre '+t+'.');
  $('tk').value=t; go();
  return;
 }
 // Avant d'abandonner : la question porte peut-etre sur un TITRE.
 // C'est le serveur qui tranche quel mot est un ticker — il a les
 // donnees, le navigateur non.
 if(await majDossier(q)) return;

 majDit('Je n\'ai pas compris. Essayez : je sors quand sur TLX, '
  +'combien je peux perdre sur Coin, que penses-tu de Nvidia, '
  +'analyse Sanofi, scan Cac 40, etat du marche, ou mes positions.');
}

// --- Le dossier d'un titre -------------------------------------------
//
// Rien n'est genere ici. Le serveur rend des LIGNES deja ecrites a
// partir des chiffres des modules ; le majordome les affiche et en lit
// les premieres a voix haute. Si un chiffre n'est pas dans le dossier,
// aucune phrase ne peut le sortir.
async function majDossier(q){
 var dflt = '';
 try{ dflt = ($('tk') && $('tk').value ? $('tk').value.trim() : ''); }catch(e){}
 try{
  majDit('Je regarde.', false);
  var j = await (await fetch('/api/dossier?q=' + encodeURIComponent(q)
    + '&ticker=' + encodeURIComponent(dflt))).json();
  if(!j.ok){
   if(j.intention){ majDit(j.erreur || 'Titre non reconnu.'); return true; }
   return false;
  }
  var h = '<b>' + j.ticker + '</b> &mdash; ' + j.titre
    + (j.cours ? ' &middot; ' + j.cours + ' ' + (j.devise||'') : '')
    + '<br><br>';
  j.lignes.forEach(function(l){
   if(!l){ h += '<br>'; return; }
   // Les lignes d'etat des sorties portent leur puce : on les garde
   // telles quelles, elles se lisent comme une liste.
   h += l.replace(/</g,'&lt;') + '<br>';
  });
  h += '<br><span style="color:var(--txt-faible)">' + j.rappel + '</span>';
  $('majr').innerHTML = h;
  majDit(j.voix || j.titre, false);
  return true;
 }catch(e){ return false; }
}

async function ouvrirWeb(){
 // window.open() est bloque ou detourne dans la fenetre Windows : on
 // demande au serveur d'ouvrir le navigateur par defaut. C'est le seul
 // chemin qui fonctionne a tous les coups.
 try{
  const j=await (await fetch('/api/navigateur')).json();
  if(j.ok){
   majDit('Page ouverte dans le navigateur. Le micro y fonctionne.', false);
   $('majr').innerHTML='Carruos est ouvert dans votre navigateur. '
    +'Le micro y fonctionne.<br><span style="color:var(--txt-faible)">'+j.url+'</span>';
   return;
  }
 }catch(e){}
 try{ window.open(location.href, '_blank'); }catch(e){}
 $('majr').innerHTML='Ouvrez cette adresse dans Edge ou Chrome :<br>'
  +'<span style="color:#f59e0b">'+location.href+'</span>';
}

// --- Ouverture et fermeture du panneau -------------------------------
//
// Ces deux gestes etaient confondus : cliquer le disque AJOUTAIT la
// classe "ouvert" sans jamais la retirer, et relancait l'ecoute dans la
// foulee. Une fois ouvert, le panneau ne se refermait plus, et chaque
// clic pour s'en debarrasser redemandait le micro. D'ou la fenetre
// bloquante apres un echec d'ecoute.
//
// Desormais : le disque OUVRE ou FERME, la croix ferme, Echap ferme.
// L'ecoute ne part QUE si on clique le bouton MICRO.

function majFerme(){
 const p=$('majp');
 if(p) p.classList.remove('ouvert');
 majStop();
 try{ if(window.speechSynthesis) speechSynthesis.cancel(); }catch(e){}
 const d=$('maj');
 if(d) d.classList.remove('parle');
}

function majOuvre(){
 const p=$('majp');
 if(!p) return;
 p.classList.add('ouvert');
 const c=$('majc');
 if(c) c.focus();
}

function majStop(){
 if(MAJ.reco){ try{ MAJ.reco.abort(); }catch(e){
   try{ MAJ.reco.stop(); }catch(e2){} } }
 MAJ.ecoute=false;
 const d=$('maj');
 if(d) d.classList.remove('ecoute');
}

// --- Micro ------------------------------------------------------------
//
// La reconnaissance vocale du navigateur n'existe pas dans la fenetre
// Windows : le moteur WebView2 qui l'affiche n'embarque pas le service
// de transcription de Chrome. Ce n'est pas un reglage a trouver, c'est
// une brique absente. Dans Edge ou Chrome, la meme page l'a.
//
// On le dit une fois, clairement, et on n'y revient plus : le champ
// texte fait exactement le meme travail et repond a voix haute.

const MICRO_DIT = {
 'no-speech': 'Je n\'ai rien entendu. Le micro fonctionne, mais aucune '
  +'parole n\'est arrivee. Reessayez en parlant plus pres.',
 'audio-capture': 'Aucun micro detecte. Verifiez qu\'il est branche et '
  +'choisi dans les reglages de son de Windows.',
 'not-allowed': 'Le micro est refuse dans cette fenetre. C\'est une '
  +'limite du cadre Windows, pas un reglage a corriger.',
 'service-not-allowed': 'Le service de transcription n\'est pas '
  +'disponible dans cette fenetre.',
 'network': 'Le service de transcription n\'est pas joignable depuis '
  +'cette fenetre. C\'est le cas normal du cadre Windows.',
 'aborted': 'Ecoute interrompue.'
};

function majMicroIndispo(txt){
 // Le bouton se marque comme inutilisable : inutile de laisser esperer.
 const b=$('majmic');
 if(b){ b.classList.add('ko'); b.textContent='MICRO INDISPO'; }
 MAJ.micKo=true;
 $('majr').innerHTML = txt
  +'<br><span style="color:#f59e0b">Ecrivez ci-dessous</span> : je '
  +'reponds a voix haute, exactement comme a l\'oral. '
  +'Le bouton EDGE ouvre la meme page dans le navigateur, '
  +'ou le micro fonctionne.';
 const c=$('majc');
 if(c) c.focus();
}

// --- Autorisation du micro -------------------------------------------
//
// « J'appuie sur micro et rien ne se passe. » C'est le symptome d'une
// autorisation jamais DEMANDEE. La reconnaissance vocale peut echouer
// sans bruit : ni resultat, ni erreur, ni fin. getUserMedia, lui, pose
// franchement la question au navigateur et repond toujours — accorde,
// refuse, ou aucun micro branche. On passe donc par lui d'abord.

async function majPermission(){
 if(!window.isSecureContext && location.protocol!=='http:')
  return {ok:false, motif:'contexte'};
 if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia)
  return {ok:false, motif:'absent'};
 try{
  const flux=await navigator.mediaDevices.getUserMedia({audio:true});
  // On relache le micro aussitot : le seul but etait d'obtenir l'accord.
  try{ flux.getTracks().forEach(function(t){t.stop();}); }catch(e){}
  return {ok:true};
 }catch(e){
  return {ok:false, motif:(e&&e.name)||'refus'};
 }
}

const PERM_DIT = {
 'NotAllowedError': 'Le micro est REFUSE pour cette page. Cliquez le '
  +'cadenas a gauche de l\'adresse, puis Micro, puis Autoriser. '
  +'Si le reglage est grise, c\'est Windows qui bloque : Parametres, '
  +'Confidentialite, Microphone, et activez l\'acces pour les '
  +'applications de bureau.',
 'NotFoundError': 'Aucun micro n\'est branche, ou aucun n\'est choisi '
  +'comme peripherique d\'entree dans les reglages de son de Windows.',
 'NotReadableError': 'Le micro est occupe par une autre application. '
  +'Fermez Teams, Discord ou Zoom, puis reessayez.',
 'SecurityError': 'Le navigateur refuse le micro sur cette adresse.',
 'absent': 'Ce navigateur n\'expose pas le micro. Utilisez Edge ou '
  +'Chrome.',
 'contexte': 'Le micro exige une adresse locale ou securisee.',
 'refus': 'Le micro a ete refuse.'
};

// --- Diagnostic -------------------------------------------------------
// Un bouton qui repond a la seule question utile : qu'est-ce qui bloque,
// exactement ? Chaque ligne est un fait verifiable, pas une hypothese.

async function majDiag(){
 majOuvre();
 $('majr').textContent='Diagnostic du micro en cours...';
 const L=[];
 const R=window.SpeechRecognition||window.webkitSpeechRecognition;
 L.push((window.isSecureContext?'OK':'NON')
  +' &nbsp; adresse consideree comme sure');
 L.push(((navigator.mediaDevices&&navigator.mediaDevices.getUserMedia)
  ?'OK':'NON')+' &nbsp; le navigateur expose le micro');
 L.push((R?'OK':'NON')+' &nbsp; moteur de reconnaissance vocale present');

 let etat='inconnu';
 try{
  if(navigator.permissions&&navigator.permissions.query){
   const p=await navigator.permissions.query({name:'microphone'});
   etat=p.state;
  }
 }catch(e){}
 L.push((etat==='granted'?'OK':(etat==='denied'?'NON':'?  '))
  +' &nbsp; autorisation : '+etat);

 let micros=0;
 try{
  const d=await navigator.mediaDevices.enumerateDevices();
  micros=d.filter(function(x){return x.kind==='audioinput';}).length;
 }catch(e){}
 L.push((micros?'OK':'NON')+' &nbsp; '+micros+' micro(s) detecte(s)');

 const p=await majPermission();
 L.push((p.ok?'OK':'NON')+' &nbsp; acces effectif au micro'
  +(p.ok?'':' ('+p.motif+')'));

 let conseil='';
 if(!R) conseil='Le moteur de reconnaissance manque : ouvrez cette page '
  +'dans Edge ou Chrome.';
 else if(!p.ok) conseil=PERM_DIT[p.motif]||PERM_DIT['refus'];
 else conseil='Tout est en place. Cliquez MICRO et parlez.';

 $('majr').innerHTML='<div style="font:11px ui-monospace,monospace;'
  +'line-height:1.85">'+L.join('<br>')+'</div>'
  +'<div style="margin-top:9px;color:#f59e0b">'+conseil+'</div>';
}

function majEcoute(){
 majOuvre();
 if(MAJ.ecoute){ majStop(); $('majr').textContent='Ecoute arretee.'; return; }
 const R=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!R){
  majMicroIndispo('Le micro n\'existe pas dans cette fenetre.');
  majDit('Le micro n\'est pas disponible ici. Ecrivez votre '
   +'instruction.', false);
  return;
 }
 $('majr').textContent='Autorisation du micro...';
 majPermission().then(function(p){
  if(!p.ok){
   const dit=PERM_DIT[p.motif]||PERM_DIT['refus'];
   $('majr').innerHTML=dit
    +'<br><span style="color:var(--txt-faible)">Le bouton DIAGNOSTIC dit '
    +'precisement ce qui bloque.</span>';
   majDit('Le micro est refuse. Voyez le diagnostic.', false);
   const c=$('majc');
   if(c) c.focus();
   return;
  }
  majDemarre(R);
 });
}

function majDemarre(R){
 let r;
 try{ r=new R(); }catch(e){
  majMicroIndispo('Le micro n\'a pas pu demarrer.');
  return;
 }
 r.lang='fr-FR'; r.interimResults=false; r.maxAlternatives=1;
 MAJ.reco=r; MAJ.ecoute=true; MAJ.recu=false;
 $('maj').classList.add('ecoute');
 const b=$('majmic');
 if(b) b.textContent='J\'ECOUTE...';
 $('majr').textContent='Je vous ecoute. Cliquez MICRO pour arreter.';
 r.onresult=function(e){
  MAJ.recu=true;
  const txt=e.results[0][0].transcript;
  $('majr').textContent='« '+txt+' »';
  majExec(txt);
 };
 r.onerror=function(e){
  const code=(e&&e.error)||'inconnu';
  const dit=MICRO_DIT[code]||('Le micro a rendu une erreur ('+code+').');
  // Une panne de service ne se repare pas en reessayant : on ferme la
  // porte proprement au lieu de reproposer un bouton qui echouera.
  if(code==='not-allowed'||code==='service-not-allowed'
     ||code==='network'||code==='audio-capture'){
   majMicroIndispo(dit);
  }else{
   $('majr').textContent=dit;
   const c=$('majc');
   if(c) c.focus();
  }
  majDit(dit, false);
 };
 r.onend=function(){
  MAJ.ecoute=false;
  $('maj').classList.remove('ecoute');
  const bb=$('majmic');
  if(bb && !MAJ.micKo) bb.textContent='MICRO';
  if(!MAJ.recu && $('majr').textContent.indexOf('ecoute')>=0){
   $('majr').textContent='Rien n\'est arrive. Ecrivez ci-dessous.';
   const c=$('majc');
   if(c) c.focus();
  }
 };
 // Un demarrage refuse ne leve pas toujours : le filet ci-dessous
 // garantit qu'il se passe TOUJOURS quelque chose a l'ecran.
 try{ r.start(); }catch(e){ majStop();
  majMicroIndispo('Le micro n\'a pas pu demarrer ('+(e.name||'erreur')+').');
  return; }
 setTimeout(function(){
  if(MAJ.ecoute && !MAJ.recu
     && $('majr').textContent.indexOf('ecoute')>=0){
   $('majr').innerHTML='Le micro ne repond pas. Cliquez '
    +'<b>DIAGNOSTIC</b> pour savoir pourquoi, ou ecrivez ci-dessous.';
  }
 }, 9000);
}

(function(){
 const d=$('maj');
 if(!d) return;
 d.onclick=function(){
  const p=$('majp');
  if(p.classList.contains('ouvert')){ majFerme(); return; }
  majOuvre();
  majDit('A votre service.');
 };
 const c=$('majc');
 if(c) c.addEventListener('keydown',function(e){
  if(e.key==='Enter') majExec(c.value);
  if(e.key==='Escape') majFerme(); });
 // Echap ferme le panneau depuis n'importe ou : c'est le reflexe, et
 // c'est le filet quand la souris ne trouve plus de bouton.
 document.addEventListener('keydown',function(e){
  if(e.key==='Escape') majFerme(); });
})();

async document.addEventListener('click', function(ev){
 var b=ev.target.closest ? ev.target.closest('[data-raf]') : null;
 if(b) toutRafraichir();
});
function toutRafraichir(){
 const b=$('raf');
 if(!b || b.classList.contains('occupe')) return;
 b.classList.add('occupe');
 b.innerHTML='<span>\u21bb</span> EN COURS';
 try{
  await fetch('/api/actus?force=1').catch(function(){});
  await Promise.allSettled([etat(), actus(), radar(), pos()]);
 }finally{
  b.classList.remove('occupe');
  b.innerHTML='\u21bb ACTUALISER';
 }
}

etat();
setInterval(etat, 300000);
"""

JS_DETAIL = r"""
function fermeDetail(){ $('voile').classList.remove('ouvert'); }

// Cliquer LE VOILE ferme ; cliquer le panneau ne ferme pas.
function voileClic(e){ if(e.target === $('voile')) fermeDetail(); }

function ouvreDetail(titre, corps){
 $('dtitre').textContent = titre;
 $('dcorps').innerHTML = corps;
 $('voile').classList.add('ouvert');
}

// Cliquer un titre surveille : on dit POURQUOI il est la, puis tous les
// faits mesures. Aucun avis d'achat : les blocs manquants et les
// conditions de sortie sont ceux de la specification.
async function fiche(tk, manque){
 ouvreDetail(tk, '<div class="msg">Releve de ' + tk + '...</div>');
 var h = '';
 if(manque){
  h += '<div class="pourquoi"><b>Pourquoi ce titre est surveille</b><br>'
     + "Il remplit une partie des treize blocs d'entree, pas tous. "
     + 'Ce qui manque :<div class="manque">';
  manque.split(',').forEach(function(m){
   m = m.trim();
   if(m) h += '<span>' + m + '</span>';
  });
  h += '</div></div>';
 }
 try{
  var j = await (await fetch('/api/revue?ticker=' + encodeURIComponent(tk))).json();
  h += j.ok ? carte(j.revue)
            : '<div class="msg err">' + (j.erreur||'') + '</div>';
 }catch(e){
  h += '<div class="msg err">Erreur : ' + e + '</div>';
 }
 h += '<div class="actions">'
    + '<button onclick="voirGraphique(&#39;' + tk + '&#39;)">GRAPHIQUE '
    + 'COMPLET</button>'
    + '<button class="sec" onclick="location.href=&#39;/strategie&#39;">'
    + 'PAGE STRATEGIE</button>'
    + '<button class="sec" onclick="fermeDetail()">FERMER</button></div>';
 ouvreDetail(tk, h);
}

function voirGraphique(tk){ $('tk').value = tk; fermeDetail(); go(); }

// Ce que contiennent les rapports poses a cote du programme. Un chiffre
// qu'on ne peut pas ouvrir n'apprend rien.
async function rapports(){
 ouvreDetail('RAPPORTS', '<div class="msg">Lecture...</div>');
 try{
  var j = await (await fetch('/api/rapports')).json();
  var h = '<div class="pourquoi">' + j.explication + '</div>';
  if(!j.rapports.length){
   h += '<div class="msg">Aucun rapport pour le moment. Lancez une '
      + 'Phase 0 depuis le panneau de validation : elle deposera un '
      + 'fichier CSV a cote du programme.</div>';
  }else{
   j.rapports.forEach(function(r){
    h += '<div class="rap"><div class="n">' + r.genre + ' &mdash; '
       + r.univers + '</div><div class="d">'
       + (r.trades||0) + ' trades sur ' + (r.titres||0) + ' titres';
    if(r.periode) h += ' &middot; ' + r.periode;
    h += '<br>' + r.fichier + ' &middot; ' + r.quand;
    if(r.ev_R !== undefined && r.ev_R !== null)
      h += '<br>esperance ' + (r.ev_R>0?'+':'') + r.ev_R + ' R par trade'
         + (r.pf ? ' &middot; profit factor ' + r.pf : '')
         + ' &middot; ' + (r.gagnants||0) + ' gagnants';
    h += '</div></div>';
   });
  }
  if(j.audit && j.audit.lignes)
   h += "<div class=\"rap\"><div class=\"n\">Journal d'audit</div>"
      + '<div class="d">' + j.audit.lignes + ' signal(aux) evalue(s), '
      + j.audit.declenches + ' declenche(s)<br>empreinte des parametres '
      + j.audit.empreinte + '\u2026'
      + (j.audit.parametres_changes
         ? "<br><span style=\"color:#f59e0b\">Les parametres ont change en "
           + "cours de journal : les lignes d'avant et d'apres ne se "
           + "comparent pas.</span>" : "")
      + '</div></div>';
  h += '<div class="pourquoi" style="border-color:var(--neg)">'
     + j.verdict_connu + '</div>';
  h += '<div class="actions"><button class="sec" onclick="fermeDetail()">'
     + 'FERMER</button></div>';
  ouvreDetail('RAPPORTS', h);
 }catch(e){
  ouvreDetail('RAPPORTS', '<div class="msg err">Erreur : ' + e + '</div>');
 }
}

// L'ancien libelle de ce rail se lisait comme une liste de titres a
// acheter. Ce sont VOS lignes dont au moins une condition de sortie est
// active, ou dont le stop est depasse. On les nomme, et on dit laquelle.
async function lignesATraiter(){
 ouvreDetail('MES LIGNES A TRAITER', '<div class="msg">Releve...</div>');
 try{
  var j = await (await fetch('/api/positions')).json();
  var l = (j.lignes||[]).filter(function(x){
   return x.verdict !== 'CONSERVER'; });
  var h = '<div class="pourquoi"><b>Ce que compte ce chiffre</b><br>'
        + "Ce ne sont pas des titres a acheter : ce sont VOS positions "
        + "dont au moins une condition de sortie de votre specification "
        + "est active, ou dont le stop note est depasse.</div>";
  if(!(j.lignes||[]).length){
   h += '<div class="msg">Aucune position enregistree.</div>';
  }else if(!l.length){
   h += '<div class="msg">Vos ' + j.lignes.length + ' ligne(s) sont '
      + 'toutes a CONSERVER : aucune condition de sortie active.</div>';
  }else{
   l.forEach(function(x){
    var actives = Object.keys(x.sorties||{}).filter(function(k){
     return x.sorties[k]; });
    h += '<div class="rap"><div class="n">' + x.ticker + ' &mdash; '
       + x.verdict + '</div><div class="d">'
       + 'cours ' + (x.cours||'?') + ' &middot; P&amp;L '
       + (x.pnl_pct>0?'+':'') + (x.pnl_pct||0) + ' %'
       + (x.marge_stop_pct!==undefined && x.marge_stop_pct!==null
          ? ' &middot; marge stop ' + (x.marge_stop_pct>0?'+':'')
            + x.marge_stop_pct + ' %' : '')
       + (actives.length ? '<br>conditions actives : ' + actives.join(', ')
                         : '')
       + (x.erreur ? '<br><span style="color:#f87171">' + x.erreur
                     + '</span>' : '')
       + '</div></div>';
   });
  }
  h += '<div class="actions">'
     + '<button class="sec" onclick="location.href=&#39;/strategie&#39;">'
     + 'VOIR LE DETAIL COMPLET</button>'
     + '<button class="sec" onclick="fermeDetail()">FERMER</button></div>';
  ouvreDetail('MES LIGNES A TRAITER', h);
 }catch(e){
  ouvreDetail('MES LIGNES A TRAITER',
              '<div class="msg err">Erreur : ' + e + '</div>');
 }
}

// Les horaires sont des FAITS. « La meilleure heure pour acheter » n'en
// est pas un : le panneau dit les uns et explique pourquoi il se tait
// sur l'autre.
async function lesPlaces(){
 ouvreDetail('LES PLACES', '<div class="msg">Releve...</div>');
 try{
  var j = await (await fetch('/api/places')).json();
  var h = '<div class="pourquoi">Toutes les heures sont donnees a '
        + '<b>PARIS</b>. Chaque place suit son propre fuseau : l\'Europe '
        + 'et les Etats-Unis ne changent pas d\'heure le meme week-end, '
        + 'donc la seance americaine se decale d\'une heure deux fois '
        + 'par an, pendant une quinzaine de jours.<br>' + j.heure + '</div>';
  h += '<table class="thz"><tr><th>place</th><th>etat</th>'
     + '<th>ouverture</th><th>fin continu</th><th>fixing clot.</th>'
     + '<th>prochain</th></tr>';
  j.places.forEach(function(p){
   var cl = p.ouverte ? 'pos' : (p.ferie || p.weekend ? '' : 'neg');
   var pr = p.prochain;
   var q = pr.jour === "aujourd'hui"
         ? pr.quoi + ' a ' + pr.quand_paris
         : 'ouverture le ' + pr.jour;
   h += '<tr><td>' + p.nom + '</td>'
      + '<td class="' + cl + '">' + p.code + '</td>'
      + '<td>' + p.ouv_paris + '</td><td>' + p.clo_paris + '</td>'
      + '<td>' + (p.fixing_a_la_cloture ? 'a la cloture' : p.fix_paris)
      + '</td><td>' + q + '</td></tr>';
   if(p.avant_paris){
    h += '<tr><td></td><td colspan="5" style="color:var(--txt-faible)">'
       + 'pre-marche ' + p.avant_paris + ', seance prolongee jusqu\'a '
       + p.apres_paris + " — liquidite faible, ecarts larges</td></tr>";
   }
  });
  h += '</table>';
  var q = j.horaire;
  h += '<div class="titre-sec">A QUELLE HEURE ACHETER OU VENDRE ?</div>';
  [['Ce que dit votre specification','ce_que_dit_la_specification'],
   ['Ce qui est structurel, sans mesure','ce_qui_est_structurel'],
   ['Ce qui ne peut PAS etre mesure avec vos donnees',
    'ce_qui_ne_peut_pas_etre_mesure_ici'],
   ['En pratique','ce_qu_il_faut_en_faire']].forEach(function(x){
   h += '<div class="rap"><div class="n">' + x[0] + '</div>'
      + '<div class="d">' + q[x[1]] + '</div></div>';
  });
  h += '<div class="actions">'
     + '<button class="sec" onclick="fermeDetail()">FERMER</button></div>';
  ouvreDetail('LES PLACES', h);
 }catch(e){
  ouvreDetail('LES PLACES',
              '<div class="msg err">Erreur : ' + e + '</div>');
 }
}

document.addEventListener('keydown', function(e){
 if(e.key === 'Escape') fermeDetail();
});
"""


# --- Fiche d'un titre, partagee par les deux pages ---------------------
#
# L'accueil et la page STRATEGIE affichent la meme fiche. Elle est ecrite
# une fois : deux copies finiraient par diverger, et c'est toujours celle
# qu'on ne regarde pas qui garde le bug.
JS_FICHE = r"""
// Le symbole euro etait colle a TOUS les montants, y compris ceux d'un
// titre cote en dollars ou en pence. Un montant dans la mauvaise devise
// n'est pas une approximation : c'est un chiffre faux.
var SYMBOLE = {EUR:'€', USD:'$', GBP:'£', GBp:'p', CHF:'CHF',
               SEK:'kr', NOK:'kr', DKK:'kr', CAD:'C$', JPY:'¥', AUD:'A$'};

function mt(v, dev){
 var d = dev || 'EUR';
 var sym = SYMBOLE[d] || d;
 return (v<0?'-':'') + Math.abs(Math.round(v)).toLocaleString('fr-FR')
        + ' ' + sym;
}

function eur(v){ return mt(v, 'EUR'); }

function sgn(v, suff){
 var c = v > 0 ? 'pos' : (v < 0 ? 'neg' : '');
 return '<b class="' + c + '">' + (v>0?'+':'') + v.toFixed(2)
        + (suff||' %') + '</b>';
}

// Le rendu d'une carte, commun au releve des positions et a l'examen
// d'un titre quelconque. Les mesures qui dependent d'un prix d'entree
// sont absentes quand il n'y en a pas : on ne les invente pas.
function carte(r){
 if(!r.ok){
  return '<div class="lig"><h3>' + (r.ticker||'') + '</h3>'
       + '<div class="msg err">' + (r.erreur||'') + '</div></div>';
 }
 var tenu = r.detenu;
 var h = '<div class="lig"><h3>' + r.ticker + ' <span>'
   + (tenu ? (r.quantite + ' titres a ' + r.entree.toFixed(2)
              + ' ' + (r.devise||'') + ' · depuis le ' + r.depuis)
           : ('non detenu · observe sur ' + (r.fenetre_mois||12)
              + ' mois'))
   + '</span></h3>';

 h += alerteCoherence(r) + etatSortie(r) + chiffresCles(r, tenu)
    + blocsSortie(r);
 h += blocEntree(r.entree_regle, r.ticker, r.devise);
 h += blocHorizons(r.horizons);
 h += blocObjectifs(r.objectifs);
 h += detailTechnique(r, tenu);

 if(r.point_mort)
   h += "<div class=\"bilan\">Vendre aujourd'hui : impot de <b>"
      + mt(r.point_mort.impot, r.devise) + '</b>, il resterait <b>'
      + mt(r.point_mort.net_si_vendu, r.devise) + '</b> a replacer. Le nouveau '
      + 'placement partirait avec <b>'
      + r.point_mort.handicap_pct.toFixed(2) + ' %</b> de retard.</div>';
 else if(!tenu)
   h += '<div class="bilan">Aucune position sur ce titre : ni gain '
      + 'latent, ni cout fiscal ne sont calcules. Donnez un prix '
      + "d'entree pour obtenir le trajet complet.</div>";
 return h + '</div>';
}

// Un gain latent tres negatif vient presque toujours d'un prix d'entree
// qui n'appartient pas a cette serie — pas d'un desastre boursier. On le
// dit AVANT tout le reste, sinon on lit un chiffre faux sans le savoir.
function alerteCoherence(r){
 var c = r.coherence_entree;
 if(!c || c.ok) return '';
 return '<div class="etat chaud"><div class="gros">PRIX D\'ENTREE HORS '
      + 'BORNES</div><div class="sous">'
      + 'Vous avez saisi <b>' + c.entree.toFixed(2) + '</b>, mais depuis le '
      + c.depuis + " ce titre n'est jamais sorti de l'intervalle <b>"
      + c.bas.toFixed(2) + ' &ndash; ' + c.haut.toFixed(2) + '</b> '
      + (r.devise||'') + '.'
      + '<br>Le gain latent affiche plus bas est donc <b>faux</b>.'
      + '<br>Piste : ' + (c.piste||'') + '</div></div>';
}

// Ce que dit VOTRE specification, lu tel quel. Elle ferme a la PREMIERE
// condition atteinte : ce n'est pas une opinion sur le titre, c'est la
// regle que vous avez ecrite, relue a voix haute.
function etatSortie(r){
 var n = r.n_sorties, tot = Object.keys(r.sorties||{}).length || 4;
 var cls = n >= 1 ? ' chaud' : '';
 var gros, sous;
 if(n === 0){
  gros = 'AUCUNE CONDITION DE SORTIE ACTIVE';
  sous = 'Votre specification ferme la position a la <b>premiere</b> '
       + 'condition atteinte. Aucune ne l\'est. Elle ne demande rien '
       + 'aujourd\'hui.';
 }else{
  gros = n + ' CONDITION' + (n>1?'S':'') + ' SUR ' + tot + ' ACTIVE'
       + (n>1?'S':'');
  sous = 'Votre specification ferme la position a la <b>premiere</b> '
       + 'condition atteinte. Il y en a <b>' + n + '</b>. '
       + 'Ce que vous en faites reste votre decision : le programme ne '
       + 'la prend pas a votre place.';
 }
 if(r.marge_stop_pct !== null && r.marge_stop_pct !== undefined
    && r.marge_stop_pct <= 0){
  gros = 'STOP DEPASSE';
  sous = 'Le cours est <b>' + Math.abs(r.marge_stop_pct).toFixed(2)
       + ' %</b> sous le stop que vous avez note. ' + sous;
 }
 return '<div class="etat' + cls + '"><div class="gros">' + gros
      + '</div><div class="sous">' + sous + '</div></div>';
}

function chiffresCles(r, tenu){
 var h = '<div class="chiffres">';
 h += cel('COURS', r.cours.toFixed(2), 0);
 if(tenu){
  h += cel('GAIN LATENT', sgnTxt(r.pnl_pct), r.pnl_pct);
  h += cel('AU MIEUX', sgnTxt(r.mfe_pct), r.mfe_pct);
  h += cel('RENDU DEPUIS', r.gain_rendu_pct.toFixed(1) + ' pts',
           -Math.abs(r.gain_rendu_pct));
 }
 h += cel('DEPUIS LE SOMMET', sgnTxt(r.recul_depuis_haut_pct),
          r.recul_depuis_haut_pct);
 if(r.marge_stop_pct !== null && r.marge_stop_pct !== undefined)
   h += cel('MARGE AU STOP', sgnTxt(r.marge_stop_pct), r.marge_stop_pct);
 if(tenu && r.valeur !== null && r.valeur !== undefined)
   h += cel('VALEUR', mt(r.valeur, r.devise), 0);
 return h + '</div>';
}

function cel(etiquette, valeur, signe){
 var c = signe > 0 ? ' pos' : (signe < 0 ? ' neg' : '');
 return '<div class="c"><span class="e">' + etiquette + '</span>'
      + '<span class="v' + c + '">' + valeur + '</span></div>';
}

function sgnTxt(v){
 if(v === null || v === undefined) return '—';
 return (v > 0 ? '+' : '') + v.toFixed(2) + ' %';
}

function blocsSortie(r){
 var h = '<div class="titre-sec" style="margin-top:12px">'
       + 'LES CONDITIONS DE SORTIE, UNE PAR UNE</div>';
 Object.keys(r.sorties||{}).forEach(function(k){
  var on = r.sorties[k];
  h += '<div class="sortie gr' + (on?' on':'') + '"><span>' + k
     + '</span><span class="et">' + (on?'ACTIVE':'dormante')
     + '</span></div>';
 });
 if(r.resultats && r.resultats.jours !== undefined
    && r.resultats.jours !== null)
   h += '<div class="sortie gr on"><span>resultats dans '
      + r.resultats.jours + ' seances</span><span class="et">'
      + (r.resultats.date||'') + '</span></div>';
 return h;
}

// « Est-ce que je renforce ? » a une reponse ecrite : les treize blocs
// d'entree. Soit ils declenchent, soit ils disent lesquels manquent.
// Le titre de ce bloc evite deliberement le verbe qui en ferait un
// conseil : il annonce une REGLE consultee, pas une action suggeree.
function blocEntree(e, tk, dev){
 if(!e || e.erreur) return '';
 var h = '<div class="titre-sec">RENFORCER LA LIGNE ? CE QUE DIT VOTRE '
       + 'SPECIFICATION D\'ENTREE</div>';
 if(e.declenche){
  h += '<div class="etat"><div class="gros">LES ' + e.n_blocs
     + ' BLOCS SONT REMPLIS</div><div class="sous">'
     + 'Votre specification declencherait une entree. Elle est pourtant '
     + '<b>NO-GO en Phase 0</b> : elle n\'a pas demontre d\'avantage '
     + 'sur le hasard. Un declenchement ne vaut donc pas '
     + 'demonstration.</div></div>';
 }else{
  h += '<div class="etat tiede"><div class="gros">' + e.n_remplis
     + ' BLOCS SUR ' + e.n_blocs + '</div><div class="sous">'
     + 'Votre specification <b>ne declencherait pas</b> d\'entree sur '
     + tk + ' aujourd\'hui.</div></div>';
  if(e.detail && e.detail.length){
   h += '<div class="mqf">';
   e.detail.forEach(function(m){
    h += '<div><b>' + m.nom + '</b>'
       + (m.texte ? '<i>' + m.texte + '</i>' : '') + '</div>';
   });
   h += '</div>';
  }else if(e.manquants && e.manquants.length){
   h += '<div class="manque">';
   e.manquants.forEach(function(m){ h += '<span>' + m + '</span>'; });
   h += '</div>';
  }
 }
 if(e.vetos && e.vetos.length){
  h += '<div class="manque" style="margin-top:6px">';
  e.vetos.forEach(function(v){ h += '<span>' + v + '</span>'; });
  h += '</div>';
 }
 if(e.titres > 0){
  h += '<div class="bilan" style="margin-top:10px">'
     + 'Si vous preniez la ligne quand meme, au prix et au stop de la '
     + 'regle : <b>' + e.titres + (e.titres > 1 ? ' titres' : ' titre')
     + '</b> pour <b>'
     + mt(e.montant, dev) + '</b>, soit <b>'
     + mt(e.risque_eur, dev)
     + '</b> de perte si le stop saute'
     + (e.plafonne ? ' (taille reduite par le plafond de poids)' : '')
     + '. Arithmetique, pas un conseil.</div>';
 }
 if(e.vigilance && e.vigilance.length){
  h += '<div class="manque" style="margin-top:6px">';
  e.vigilance.forEach(function(v){ h += '<span>' + v + '</span>'; });
  h += '</div>';
 }
 if(e.pas_un_avis){
  h += '<p class="ex" style="margin-top:8px">' + e.pas_un_avis + '</p>';
 }
 return h;
}

function blocHorizons(hz){
 if(!hz || !hz.length) return '';
 var h = '<details class="repli"><summary>AMPLITUDE PAR HORIZON &mdash; '
       + 'CE QUE CE TITRE BOUGE, SANS DIRECTION</summary>'
       + '<table class="thz"><tr><th>horizon</th><th>typique</th>'
       + '<th>2 sur 3 entre</th><th>fenetres indep.</th></tr>';
 hz.forEach(function(x){
  h += '<tr><td>' + x.nom + '</td><td>' + x.typique.toFixed(1)
     + ' %</td><td>' + x.bas68.toFixed(1) + ' %  a  +'
     + x.haut68.toFixed(1) + ' %</td><td>' + x.independantes
     + '</td></tr>';
 });
 h += '</table><div class="bilan" style="margin-top:8px">'
    + '<b>Aucune direction ici.</b> « typique » est la variation '
    + 'absolue mediane des fenetres passees. « fenetres indep. » est la '
    + 'vraie taille de l\'echantillon : des fenetres qui se recouvrent '
    + 'ne sont pas des observations independantes.</div></details>';
 return h;
}

function blocObjectifs(o){
 if(!o || o.erreur || !o.cibles || !o.cibles.length) return '';
 var h = '<details class="repli"><summary>QUEL TAKE-PROFIT SERAIT '
       + 'ENVISAGEABLE SUR CE TITRE</summary>';
 ['1 semaine','1 mois','3 mois'].forEach(function(per){
  var l = o[per];
  if(!l || !l.length) return;
  h += '<div class="titre-sec" style="margin:10px 0 4px;border:0;'
     + 'padding:0">HORIZON ' + per.toUpperCase() + '</div>'
     + '<table class="thz"><tr><th>objectif</th><th>touche</th>'
     + '<th>en (median)</th><th>puis rendu</th></tr>';
  l.forEach(function(x){
   var part = x.seances_medianes === null ? 'jamais'
            : (x.part < 0.005 ? '&lt;1 %'
                              : (x.part*100).toFixed(0) + ' %');
   var q = x.seances_medianes === null ? '—'
         : x.seances_medianes.toFixed(0) + ' j';
   var rd = x.part_rendue === null ? '—'
          : (x.part_rendue*100).toFixed(0) + ' %';
   h += '<tr><td>+' + x.cible.toFixed(1) + ' %</td><td>' + part
      + '</td><td>' + q + '</td><td>' + rd + '</td></tr>';
  });
  h += '</table>';
 });
 h += '<div class="bilan" style="margin-top:9px">'
    + '<b>« puis rendu »</b> est le chiffre qui repond a la question : '
    + 'parmi les fenetres qui ont touche l\'objectif, la part qui a fini '
    + '<b>sous</b> lui. C\'est ce qu\'un take-profit evite &mdash; et '
    + 'c\'est aussi la hausse qu\'il coupe quand elle continue.<br><br>'
    + 'Ces chiffres partent de <b>n\'importe quelle seance</b>, pas d\'un '
    + 'signal : c\'est une propriete du titre, pas d\'une strategie. Et '
    + 'une frequence passee n\'est pas une probabilite future. '
    + 'Les objectifs sont deduits de l\'ATR du titre, pour qu\'ils '
    + 'veuillent dire la meme chose sur un titre calme et sur un nerveux.'
    + '</div></details>';
 return h;
}

function detailTechnique(r, tenu){
 var h = '<details class="repli"><summary>LE DETAIL, POUR VERIFIER'
       + '</summary><div class="trajet"><div class="kv2">'
   + '<span>plus haut de la periode (' + r.date_plus_haut + ')</span><b>'
   + r.plus_haut.toFixed(2) + '</b>'
   + '<span>plus bas de la periode</span><b>' + r.plus_bas.toFixed(2)
   + '</b>';
 if(tenu) h += '<span>pire moment du trajet</span>' + sgn(r.mae_pct);
 h += '<span>recul depuis le haut 52 semaines</span>'
    + sgn(r.recul_52s_pct) + '</div></div><div class="kv2">';
 [['EMA 20','ema20'],['SMA 50','sma50'],['SMA 200','sma200']]
  .forEach(function(p){
   var e = r[p[1]];
   if(!e) return;
   h += '<span>ecart a la ' + p[0] + '</span>' + sgn(e.pct);
  });
 if(r.rsi!==null && r.rsi!==undefined)
   h += '<span>RSI 14</span><b>' + r.rsi + '</b>';
 if(r.rvol!==null && r.rvol!==undefined)
   h += '<span>volume relatif</span><b>' + r.rvol + '</b>';
 if(r.atr_pct!==null && r.atr_pct!==undefined)
   h += '<span>ATR 14 (bruit quotidien)</span><b>' + r.atr_pct
      + ' %</b>';
 if(r.stop!==null && r.stop!==undefined)
   h += '<span>stop note</span><b>' + r.stop.toFixed(2) + '</b>';
 return h + '</div></details>';
}

"""


# --- Page STRATEGIE ---------------------------------------------------
# Deux colonnes : a gauche de l'arithmetique, a droite des faits mesures.
# Aucune animation de mise en page : uniquement transform et opacity.
CSS_CARNET = """
.crn{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr);
 gap:var(--gap);min-height:0;overflow:hidden}
@media(max-width:900px){.crn{grid-template-columns:minmax(0,1fr)}}
.crn>section{min-width:0;min-height:0;display:flex;flex-direction:column}
.crn .corps{overflow:auto;min-height:0}
.crn textarea{width:100%;min-height:190px;resize:vertical;background:#070d13;
 border:1px solid var(--bord);color:var(--txt-fort);padding:10px 11px;
 font:400 13px/1.62 inherit}
.crn input,.crn select{background:#070d13;border:1px solid var(--bord);
 color:var(--txt-fort);padding:8px 10px;font:400 12px inherit;min-width:0}
.crn .lg{display:flex;gap:8px;margin-bottom:9px;flex-wrap:wrap}
.crn .lg>*{flex:1 1 130px;min-width:0}
.crn .lg button{flex:0 0 auto}
.cse{border:1px solid var(--bord);border-left:2px solid var(--bord-fort);
 padding:10px 12px;margin-bottom:9px;background:rgba(6,12,18,.5)}
.cse.g-releve{border-left-color:var(--acc)}
.cse.g-ordre{border-left-color:#c9b28a}
.cse .t{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap;
 margin-bottom:5px}
.cse .d{font:400 9px ui-monospace,monospace;letter-spacing:.14em;
 color:var(--txt-faible);font-variant-numeric:tabular-nums}
.cse .g{font:500 8px ui-monospace,monospace;letter-spacing:.2em;
 color:var(--txt-faible);border:1px solid var(--bord);padding:1px 6px}
.cse.g-releve .g{color:var(--acc);border-color:var(--bord-fort)}
.cse .tk{font:500 11px ui-monospace,monospace;letter-spacing:.1em;
 color:var(--acc);cursor:pointer}
.cse .ti{color:var(--txt-fort);font-weight:500;flex:1;min-width:0}
.cse .x{cursor:pointer;color:#5d8a97;font-size:14px;line-height:1}
.cse .x:hover{color:#f87171}
.cse pre{white-space:pre-wrap;word-break:break-word;margin:0;
 font:400 12.5px/1.62 inherit;color:var(--txt-doux)}
.cse .dn{margin-top:7px;font:400 11px/1.55 ui-monospace,monospace;
 color:var(--txt-faible);white-space:pre-wrap;word-break:break-word;
 max-height:190px;overflow:auto;border-top:1px solid var(--bord);
 padding-top:6px}
.crn .cpt{font:400 9px ui-monospace,monospace;letter-spacing:.16em;
 color:var(--txt-faible);margin-bottom:9px}
"""

CSS_PALM = """
.palm{max-width:1180px;margin:0 auto;padding:0 4px 40px}
.palm .saisie{display:grid;gap:11px;align-items:end;margin-bottom:14px;
 grid-template-columns:minmax(min(100%,240px),1fr) minmax(118px,150px)
 minmax(118px,150px)}
.palm .saisie>div{min-width:0}
.palm textarea{width:100%;min-height:74px;resize:vertical;
 background:var(--champ-fond,#0a1620);border:1px solid #22303f;
 color:var(--txt);border-radius:9px;padding:11px 13px;
 font:400 13px ui-monospace,Consolas,monospace;line-height:1.6}
.palm textarea:focus{outline:0;border-color:var(--acc)}
.palm label{display:block;font-size:10px;letter-spacing:.16em;
 color:#475a72;margin-bottom:5px}
.palm select,.palm input[type=number]{width:100%;
 background:var(--champ-fond,#0a1620);border:1px solid #22303f;
 color:var(--txt);border-radius:9px;padding:9px 11px;font:400 13px inherit}
.palm .go{width:100%;background:#0e2b34;border:1px solid var(--acc);
 color:var(--txt-fort);border-radius:9px;padding:10px;cursor:pointer;
 font:500 13px inherit;letter-spacing:.1em}
.palm .go:hover{background:#123a46}
/* Un groupe = une marche de l'echelle d'interet. Le titre du groupe dit
   POURQUOI les titres y sont, pas s'ils sont bons. */
.palm .grp{margin-top:20px}
.palm .grp>h3{font:500 10px ui-monospace,Consolas,monospace;
 letter-spacing:.2em;color:#475a72;margin:0 0 9px;padding-bottom:6px;
 border-bottom:1px solid #1a2330}
.palm .li{background:#0d1219;border:1px solid #1a2330;border-radius:11px;
 padding:12px 15px;margin-bottom:9px}
.palm .li .tete{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.palm .li .tk{font:500 17px ui-monospace,Consolas,monospace;
 color:var(--txt-fort);letter-spacing:.06em;cursor:pointer}
.palm .li .tk:hover{color:var(--acc)}
.palm .li .cpt{font:500 13px ui-monospace,monospace;
 font-variant-numeric:tabular-nums}
.palm .li .px{margin-left:auto;font:400 13px ui-monospace,monospace;
 color:#94a3b8;font-variant-numeric:tabular-nums}
/* Colonnes FIXES : un libelle plus long ne doit pas decaler la grille. */
.palm .faits{display:grid;gap:5px 16px;margin-top:9px;
 grid-template-columns:repeat(auto-fit,minmax(min(100%,168px),1fr))}
.palm .faits div{font-size:11.5px;color:#64748b;min-width:0}
.palm .faits b{color:#cbd5e1;font-weight:500;
 font-variant-numeric:tabular-nums}
.palm .mq{margin-top:9px;font-size:11.5px;line-height:1.5}
.palm .mq b{display:block;color:#fca5a5;font-weight:500}
.palm .mq i{font-style:normal;color:#64748b;
 font-variant-numeric:tabular-nums}
.palm .veto{margin-top:8px;font-size:11px;color:#c4a5e4;
 border-left:2px solid #4a3a63;padding-left:9px;line-height:1.55}
.palm .refus{border-left-color:#7d2530;color:#fca5a5}
.palm .av{margin-top:18px;font-size:11.5px;color:#475a72;line-height:1.75;
 border-top:1px solid #1a2330;padding-top:13px}
.palm .av b{color:#94a3b8;font-weight:500}
.g-complet{color:var(--pos)}.g-proche{color:#fbbf24}.g-loin{color:#7c8ba1}
.g-sortie{color:var(--neg)}.g-hors{color:#c4a5e4}.g-na{color:#a78bfa}
.g-refus{color:var(--neg)}.g-erreur{color:#7c8ba1}
"""


CSS_STRAT = """
/* .app attend TROIS rangees (barre, console, grille). Cette page n'en a
   que deux : sans gabarit propre, les panneaux tombaient dans la rangee
   « auto » et s'arretaient au milieu de l'ecran. */
.app.strat-page{grid-template-rows:auto minmax(0,1fr)}
.strat{display:grid;grid-template-columns:1fr 1.15fr;
 grid-template-rows:minmax(0,1fr);gap:9px;min-height:0}
.strat .corps{overflow-y:auto;min-height:0}
@media(max-width:1150px){.strat{grid-template-columns:1fr;
 grid-template-rows:auto auto}}
.champs{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.champs label{display:flex;flex-direction:column;gap:4px;
 font:400 10px ui-monospace,monospace;letter-spacing:.14em;color:var(--txt-faible)}
.champs input{width:100%}
.ex{font-size:11.5px;line-height:1.6;color:var(--txt-mi);margin-bottom:11px}
.tproj{width:100%;border-collapse:collapse;margin-top:12px;
 font:400 11.5px ui-monospace,monospace}
.tproj th{text-align:right;padding:5px 6px;font-weight:500;font-size:9.5px;
 letter-spacing:.14em;color:var(--txt-faible);border-bottom:1px solid var(--bord)}
.tproj th:first-child,.tproj td:first-child{text-align:left}
.tproj td{text-align:right;padding:4px 6px;border-bottom:1px solid #0b2028}
.tproj tr.fort td{color:var(--txt-fort);font-weight:600}
.bilan{margin-top:13px;padding-top:11px;border-top:1px solid var(--bord);
 font-size:12px;line-height:1.75;color:var(--txt-doux)}
.bilan b{color:var(--acc)}
.titre-sec{font:500 9px ui-monospace,monospace;letter-spacing:.2em;
 color:var(--txt-faible);margin:16px 0 9px;padding-top:11px;
 border-top:1px solid var(--bord)}
"""

JS_STRAT = r"""
async function proj(){
 var q = 'capital=' + ($('pcap').value||0)
       + '&mensuel=' + ($('pmens').value||0)
       + '&taux=' + ($('ptaux').value||0)
       + '&ans=' + ($('pans').value||10)
       + (PEA ? '&pea=1' : '');
 $('pres').innerHTML = '<div class="msg">Calcul...</div>';
 try{
  var j = await (await fetch('/api/projection?' + q)).json();
  if(!j.ok){
   $('pres').innerHTML = '<div class="msg err">' + (j.raison||'') + '</div>';
   return;
  }
  var h = j.hypothese, jal = [1,3,5,10,15,20];
  // Ce que VOUS versez et ce que le fonds produit TOUT SEUL, en deux
  // colonnes separees : le capital final tout nu melange l'effort
  // d'epargne et le rendement, et on ne voit pas la capitalisation
  // prendre le relais.
  var t = '<div class="etat"><div class="gros">'
        + eur(j.genere_total) + '</div><div class="sous">'
        + 'C\'est ce que le fonds capitalise <b>tout seul</b> en '
        + h.annees + ' ans, en plus des <b>' + eur(j.verse_total)
        + '</b> sortis de votre poche. Soit <b>'
        + j.part_generee.toFixed(0) + ' %</b> du capital final.'
        + (j.an_bascule
           ? '<br>A partir de l\'annee <b>' + j.an_bascule + '</b>, le '
             + 'fonds a genere plus que ce que vous y avez mis.'
           : '<br>Sur cet horizon, vos versements restent superieurs a '
             + 'ce que le fonds genere.')
        + '</div></div>';
  t += '<table class="tproj"><tr><th>AN</th><th>VERSE</th>'
     + '<th>GENERE SEUL</th><th>CAPITALISANT</th><th>ROTATION</th>'
     + '<th>GAINS RETIRES</th></tr>';
  j.lignes.forEach(function(x){
   if(jal.indexOf(x.an) < 0 && x.an !== h.annees) return;
   t += '<tr' + (x.an===h.annees ? ' class="fort"' : '') + '><td>' + x.an
      + '</td><td>' + eur(x.verse) + '</td><td class="pos">'
      + eur(x.genere) + ' <span style="opacity:.55">('
      + x.part_generee.toFixed(0) + ' %)</span></td><td>'
      + eur(x.capitalisant_net)
      + '</td><td>' + eur(x.rotation_net) + '</td><td>'
      + eur(x.retire_total) + '</td></tr>';
  });
  t += '</table>';
  t += '<div class="bilan">Vous aurez verse <b>' + eur(j.verse_total)
     + '</b> en ' + h.annees + ' ans.<br>'
     + 'La friction fiscale de la rotation coute <b>'
     + eur(j.ecart_capitalisant_rotation) + '</b>, soit '
     + j.part_perdue_en_friction.toFixed(1) + ' % du capitalisant.<br>'
     + 'Pour seulement <b>egaler</b> le capitalisant, une rotation doit '
     + 'produire <b>' + (j.barre_brute*100).toFixed(2) + ' %</b> brut par '
     + 'an au lieu de ' + (h.taux*100).toFixed(2) + ' %.'
     + "<br><span style=\"color:var(--txt-faible)\">Ce tableau n'est pas une "
     + "prevision : il deroule l'hypothese que vous avez saisie.</span>"
     + '</div>';
  $('pres').innerHTML = t;
 }catch(e){
  $('pres').innerHTML = '<div class="msg err">Erreur : ' + e + '</div>';
 }
}

function $(i){return document.getElementById(i);}
var PEA = false;

function basculePea(){
 PEA = !PEA;
 $('benv').textContent = PEA ? 'PEA +5 ANS (17,2 %)'
                             : 'COMPTE-TITRES (30 %)';
 proj();
}

async function revue(){
 var tk = ($('rtk').value||'').trim();
 if(!tk){ $('rres').innerHTML = '<div class="msg err">Donnez un ticker.</div>';
          return; }
 var q = 'ticker=' + encodeURIComponent(tk);
 var e = ($('rent').value||'').trim();
 if(e) q += '&entree=' + encodeURIComponent(e);
 $('rres').innerHTML = '<div class="msg">Releve de ' + tk + '...</div>';
 try{
  var j = await (await fetch('/api/revue?' + q)).json();
  if(!j.ok){
   $('rres').innerHTML = '<div class="msg err">' + (j.erreur||'') + '</div>';
   return;
  }
  $('rres').innerHTML = carte(j.revue);
 }catch(err){
  $('rres').innerHTML = '<div class="msg err">Erreur : ' + err + '</div>';
 }
}

async function lignes(){
 try{
  var j = await (await fetch('/api/lignes')).json();
  if(!j.ok){
   $('lres').className = 'msg err';
   $('lres').textContent = j.erreur || 'indisponible';
   return;
  }
  if(!j.lignes.length){
   $('lres').className = 'msg';
   $('lres').textContent = "Aucune position enregistree. "
     + "Ajoutez-les depuis la page d'accueil, ou examinez "
     + "n'importe quel titre ci-dessus.";
   return;
  }
  var h = '';
  j.lignes.forEach(function(r){ h += carte(r); });
  h += "<p class=\"ex\" style=\"margin-top:10px\">Les actualites et le "
     + "contexte geopolitique n'entrent dans <b>aucune</b> regle et ne "
     + "sont pas chiffres ici : une information publique est deja dans "
     + "les cours. Servez-vous en pour votre verification avant de passer "
     + "l'ordre, pas comme d'un signal.</p>";
  $('lres').className = '';
  $('lres').innerHTML = h;
 }catch(e){
  $('lres').className = 'msg err';
  $('lres').textContent = 'Erreur : ' + e;
 }
}

proj(); lignes();
"""




def _lettres(mot: str) -> str:
    """Le mot, une balise par lettre, chacune avec son decalage de depart.

    `--i` cadence l'entree, `--d` dit de combien la lettre part ecartee
    du centre : negatif a gauche, positif a droite. Tout est anime en
    `transform`, donc la largeur du mot ne bouge jamais.
    """
    n = len(mot)
    return "".join(
        f'<i style="--i:{i};--d:{round((i - (n - 1) / 2) * 0.62, 3)}">'
        f"{html.escape(c)}</i>"
        for i, c in enumerate(mot))


def _accueil(splash: bool = True) -> str:
    reg = rg.charge()
    ouverture = (
        f'<div id="splash">{CERF.format(300, 316)}<div class="rule"></div>'
        f"<h1>{_lettres(NOM)}</h1>"
        '<p>REPLI EN TENDANCE</p><div class="load"><i></i></div></div>'
    ) if splash else ""

    return ('<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<link rel="icon" type="image/svg+xml" href="/carruos.svg"><link rel="alternate icon" href="/favicon.ico">'
            f"<title>{TITRE}</title>"
            f"<style>{rg.variables(reg)}{CSS}</style></head>"
            f'<body class="{rg.classes(reg)}"{rg.corps_attrs(reg)}>'
            + rg.tiroir_html(reg)
            + ouverture
            + hd.fond(TRACE_D)
            + '<div class="maj" id="maj" title="Majordome">'
              '<svg viewBox="0 0 44 44"><circle class="mo" cx="22" cy="22" '
              'r="19" fill="none" stroke="currentColor" stroke-width="1" '
              'stroke-dasharray="4 7"/>'
              '<path d="M22 12v11M22 27.5v1" stroke="currentColor" '
              'stroke-width="2.2" stroke-linecap="round"/>'
              '<path d="M15 21a7 7 0 0 0 14 0" fill="none" '
              'stroke="currentColor" stroke-width="1.6" '
              'stroke-linecap="round"/></svg></div>'
              '<div class="majp" id="majp">'
              '<div class="majh"><div class="majt">MAJORDOME</div>'
              '<div class="majx" id="majx" onclick="majFerme()" '
              'title="Fermer (Echap)">&times;</div></div>'
              '<div class="majr" id="majr">Ecris ton instruction. '
              'Je reponds a voix haute.</div>'
              '<div class="row"><input id="majc" '
              'placeholder="ton instruction ici">'
              '<button onclick="majExec($(\'majc\').value)">ENVOYER</button>'
              '</div>'
              '<div class="row" style="margin-top:7px">'
              '<button class="sec" id="majmic" onclick="majEcoute()">'
              'MICRO</button>'
              '<button class="sec" onclick="majDiag()">DIAGNOSTIC</button>'
              '<button class="sec" onclick="ouvrirWeb()">EDGE</button>'
              '</div>'
              '<div class="maje">je sors quand sur TLX &middot; '
              'combien je peux perdre sur Coin &middot; '
              'que penses-tu de Nvidia &middot; une figure sur Hood ? '
              '&middot; analyse sanofi &middot; scan cac 40 &middot; '
              'etat du marche &middot; mes positions</div>'
              '</div>'
            + '<div id="voile" onclick="voileClic(event)">'
              '<div id="detail"><div class="tete"><h2 id="dtitre"></h2>'
              '<div class="fx" onclick="fermeDetail()" title="Fermer (Echap)">'
              '&times;</div></div><div id="dcorps"></div></div></div>'
            + '<div class="app">'
            + hd.barre(
                TRACE_D, NOM, actif="accueil", soustitre="REPLI EN TENDANCE",
                avant='<button class="raf" id="raf" data-raf="1">'
                      '&#8635; ACTUALISER</button>')
            + hd.console(TRACE_D, hologramme=False)
            + '<div class="grille">'

            '<section class="pan"><div class="trait"><i></i></div><h2>ANALYSER UN TITRE</h2><div class="corps">'
            '<div class="row">'
            '<input id="tk" placeholder="MC.PA, NVDA, FR0000121014..." autofocus>'
            '<button onclick="go()">ANALYSER</button>'
            '<button class="sec" onclick="cherche()">CHERCHER</button></div>'
            '<div class="msg" id="m"></div><div id="res"></div>'
            '</div></section>'

            '<section class="pan"><div class="trait"><i></i></div><h2>MES POSITIONS</h2><div class="corps">'
            '<div class="posf">'
            '<input id="ptk" placeholder="Ticker">'
            '<input id="pq" placeholder="Qte" inputmode="decimal">'
            '<input id="pe" placeholder="Entree" inputmode="decimal">'
            '<input id="pst" placeholder="Stop" inputmode="decimal">'
            '<button onclick="addpos()">AJOUTER LA LIGNE</button></div>'
            '<div class="msg" id="mp"></div><div id="rp"></div>'
            '</div></section>'

            '<section class="pan"><div class="trait"><i></i></div>'
            '<h2>ACTUALITES MARCHE &amp; GEOPOLITIQUE</h2><div class="corps">'
            '<div class="msg" id="man">Chargement...</div>'
            '<div class="clebloc" id="clebloc" style="display:none">'
            '<span class="ch">CLE ALPHA VANTAGE</span>'
            '<div class="row"><input id="cle" placeholder="colle ta cle ici" '
            'autocomplete="off" spellcheck="false">'
            '<button class="sec" onclick="collerCle()">COLLER</button>'
            '<button onclick="poseCle()">ENREGISTRER</button></div>'
            '<div class="note" style="margin-top:6px;border:0;padding:0">'
            'Gratuite sur alphavantage.co/support/#api-key. '
            'Enregistree a deux endroits : a cote du programme, et '
            'dans ton dossier personnel. La deuxieme copie est celle '
            'qui te la rend apres une mise a jour.</div></div>'
            '<div id="ran"></div>'
            '<div class="avert">Aucune de ces actualites n\'entre dans une '
            "regle. Une information publique est deja dans les cours. "
            "C'est du contexte avant de passer un ordre, pas un signal."
            '</div></div></section>'
            '<section class="pan"><div class="trait"><i></i></div><h2>SCANS COMPLETS</h2><div class="corps">'
            '<div class="gh">'
            '<button onclick="scan(\'us_total\',\'us\')"><b>TOUTE LA COTE US</b>'
            "<i>~900 titres &middot; 25-40 min</i></button>"
            '<button onclick="scan(\'europe_total\',\'europe\')">'
            "<b>TOUTE L'EUROPE</b>"
            "<i>STOXX 600 + CAC + DAX &middot; 20-30 min</i></button>"
            '<button onclick="scan(\'us\',\'us\')">'
            "<b>US LARGE</b><i>S&amp;P 500 + Nasdaq 100 &middot; 12-20 min</i></button>"
            '<button onclick="scan(\'stoxx600\',\'europe\')"><b>STOXX 600</b>'
            "<i>~600 titres &middot; 15-25 min</i></button>"
            '<button onclick="scan(\'sp500\',\'us\')"><b>S&amp;P 500</b>'
            "<i>~500 titres &middot; 10-20 min</i></button>"
            '<button onclick="scan(\'nasdaq100\',\'us\')"><b>NASDAQ 100</b>'
            "<i>100 titres &middot; 3 min</i></button>"
            '<button onclick="scan(\'cac40\',\'france\')"><b>CAC 40</b>'
            "<i>38 titres &middot; 2 min</i></button>"
            '<button onclick="scan(\'dax\',\'allemagne\')"><b>DAX</b>'
            "<i>37 titres &middot; 2 min</i></button>"
            '</div><div class="msg" id="ms"></div><div id="rs"></div>'
            '<div class="sep2"></div>'
            '<div class="ch">VALIDATION GO / NO-GO</div>'
            '<div class="row" style="margin-bottom:7px">'
            '<select id="p0u">'
            '<option value="sp500">S&amp;P 500 &middot; 10-20 min</option>'
            '<option value="us">US large &middot; 12-20 min</option>'
            '<option value="us_total">Toute la cote US &middot; 25-40 min</option>'
            '<option value="stoxx600">STOXX 600 &middot; 15-25 min</option>'
            '<option value="cac40">CAC 40 &middot; 2 min</option>'
            '</select>'
            '<button onclick="p0Lance()">LANCER</button></div>'
            '<div id="p0v"></div>'
            '<div class="msg" id="p0m">Le verdict decide si Carruos produit '
            "une liste d'ordres ou une liste de surveillance.</div>"
            '<div class="avert">Regles evaluees sur cloture. '
            "Tant que la Phase 0 n'a pas rendu un GO, toute sortie de "
            "Carruos est une liste de surveillance, pas une liste "
            "d'ordres.</div>"
            '</div></section>'

            '</div></div>'
            f"<script>{hd.BARRE_JS}{JS}{JS_POS}{JS_HUD}{JS_FICHE}{JS_DETAIL}"
            f"{rg.tiroir_js()}</script></body></html>")


class Bruce(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _envoie(self, corps, ctype="text/html; charset=utf-8", code=200):
        b = corps.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _json(self, obj, code=200):
        self._envoie(json.dumps(obj), "application/json; charset=utf-8", code)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path not in ("/api/reglages", "/api/positions",
                          "/api/cle", "/api/validation", "/api/phase0",
                          "/api/carnet"):
            return self._envoie("<h1>404</h1>", code=404)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            corps = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/validation":
                return self._json(_val_lance(corps.get("quoi", "phase0")))
            if u.path == "/api/carnet":
                return self._json(_carnet_ecrit(corps))
            if u.path == "/api/cle":
                ok = pose_cle(corps.get("cle", ""))
                return self._json({"ok": True, "pose": ok})
            if u.path == "/api/phase0":
                if _P0["encours"]:
                    return self._json({"ok": False,
                                       "erreur": "calcul deja en cours"})
                uni = corps.get("univers", "sp500")
                if uni not in dl.UNIVERS:
                    return self._json({"ok": False, "erreur": "univers inconnu"})
                _p0_lance(uni)
                return self._json({"ok": True})
            if u.path == "/api/positions":
                if corps.get("action") == "retire":
                    ps.retire(corps["ticker"])
                else:
                    ps.ajoute(corps["ticker"], corps["quantite"],
                              corps["entree"], corps.get("stop"))
                return self._json({"ok": True})
            if "raz=1" in (u.query or ""):
                rg.FICHIER.unlink(missing_ok=True)
                return self._json(rg.charge())
            return self._json(rg.sauve(corps))
        except Exception as exc:
            return self._json({"ok": False, "erreur": str(exc)}, 500)

    # Fichiers servis depuis le dossier du programme. La liste est FERMEE :
    # un nom construit a partir de l'URL permettrait de remonter l'arbre
    # des dossiers et de lire n'importe quel fichier de la machine.
    STATIQUES = {"lightweight-charts.js": "application/javascript"}

    def _favicon(self):
        """carruos.ico, s'il est la. Le navigateur demande /favicon.ico
        tout seul ; pywebview aussi pour l'icone de la fenetre."""
        f = Path(__file__).resolve().parent.parent / "carruos.ico"
        try:
            brut = f.read_bytes()
        except OSError:
            # Pas d'icone binaire : le SVG de l'onglet suffit, on ne
            # renvoie surtout pas une page HTML a la place d'une image.
            return self._envoie("", code=404)
        self.send_response(200)
        self.send_header("Content-Type", "image/vnd.microsoft.icon")
        self.send_header("Content-Length", str(len(brut)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(brut)

    def _statique(self, nom: str):
        genre = self.STATIQUES.get(nom)
        if genre is None:
            return self._envoie("<h1>404</h1>", code=404)
        f = Path(__file__).resolve().parent / "statique" / nom
        try:
            brut = f.read_bytes()
        except OSError:
            return self._envoie("<h1>404</h1>", code=404)
        self.send_response(200)
        self.send_header("Content-Type", genre)
        self.send_header("Content-Length", str(len(brut)))
        # Le fichier ne change jamais : inutile de le redemander.
        self.send_header("Cache-Control", "public, max-age=31536000")
        self.end_headers()
        self.wfile.write(brut)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path == "/":
                premier = not _LANCE["fait"]
                _LANCE["fait"] = True
                return self._envoie(_accueil(splash=premier))
            if u.path == "/api/find":
                return self._json({"res": _find(q.get("q", ""))})
            if u.path == "/api/analyse":
                return self._json(_verifie(q.get("ticker", "")))
            if u.path == "/carruos.svg":
                return self._envoie(hd.icone(TRACE_D),
                                    "image/svg+xml")
            if u.path == "/favicon.ico":
                return self._favicon()
            if u.path.startswith("/statique/"):
                return self._statique(u.path[len("/statique/"):])
            if u.path == "/graphique":
                return self._envoie(_page_graphique(q.get("ticker", "")))
            if u.path == "/palmares":
                return self._envoie(_page_palmares())
            if u.path == "/carnet":
                return self._envoie(_page_carnet())
            if u.path == "/api/carnet":
                return self._json(_carnet(q))
            if u.path == "/api/dossier":
                return self._json(_dossier(q))
            if u.path == "/api/palmares":
                return self._json(_palmares(q))
            if u.path == "/strategie":
                return self._envoie(_page_strategie())
            if u.path == "/api/projection":
                return self._json(_projection(q))
            if u.path == "/api/lignes":
                return self._json(_revue_lignes())
            if u.path == "/api/revue":
                return self._json(_revue_titre(q))
            if u.path == "/api/places":
                from . import seance as sn
                return self._json({
                    "ok": True, "places": sn.toutes(),
                    "heure": sn.date_fr(_dt.datetime.now(sn.PARIS)),
                    "horaire": sn.pourquoi_pas_de_meilleure_heure()})
            if u.path == "/api/rapports":
                return self._json(_rapports())
            if u.path == "/api/reglages":
                return self._json(rg.charge())
            if u.path == "/api/positions":
                from . import cache as ch
                return self._json({"lignes": ps.controle(
                    lambda tk: ch.charge(tk, annees=3))})
            if u.path == "/api/validation":
                return self._json({"ok": True, "actif": _VAL["actif"],
                                   "quoi": _VAL["quoi"], "fini": _VAL["fini"],
                                   "verdict": _VAL["verdict"],
                                   "lignes": _VAL["lignes"][-120:]})
            if u.path == "/api/phase0":
                return self._json(_p0_etat())
            if u.path == "/api/radar":
                return self._json(_radar())
            if u.path == "/api/navigateur":
                # window.open() est bloque ou detourne dans le cadre
                # Windows : c'est le serveur qui ouvre le navigateur par
                # defaut, ce qui marche a tous les coups.
                port = self.server.server_address[1]
                adresse = f"http://127.0.0.1:{port}/"
                try:
                    webbrowser.open(adresse)
                    return self._json({"ok": True, "url": adresse})
                except Exception as exc:
                    return self._json({"ok": False, "url": adresse,
                                       "erreur": f"{type(exc).__name__}"})
            if u.path == "/api/cle":
                return self._json({"ok": True, "pose": bool(cle_av())})
            if u.path == "/api/actus":
                force = "force=1" in (u.query or "")
                it = _actus(force=force)
                try:
                    from . import news as nw
                    reste = nw.reste_quota()
                except Exception:
                    reste = None
                return self._json({"ok": True, "items": it,
                                   "quota": reste})
            if u.path == "/api/etat":
                return self._json(_etat())
            if u.path == "/api/scan":
                return self._json(_scan(q.get("universe", ""), q.get("marche", "us")))
            return self._envoie("<h1>404</h1>", code=404)
        except Exception as exc:
            traceback.print_exc()
            self._json({"ok": False, "erreur": f"{type(exc).__name__}: {exc}"}, 500)


# =====================================================================
# VALIDATION LANCEE DEPUIS L'INTERFACE
#
# Les tests tournent dans un fil separe et ecrivent leur sortie au fur
# et a mesure. L'interface la relit : on voit le test avancer au lieu
# d'attendre devant une fenetre figee.
# =====================================================================
_VAL = {"actif": False, "quoi": "", "lignes": [], "debut": None,
        "fini": False, "verdict": ""}


def tables_univers() -> dict:
    """{cle: fonction qui rend la liste de tickers}. Un seul endroit ou
    cette table se construit : elle etait recopiee a quatre endroits."""
    return {k: f for k, (_, f) in dl.UNIVERS.items()}


def _val_journal(txt=""):
    _VAL["lignes"].append(str(txt))
    if len(_VAL["lignes"]) > 400:
        del _VAL["lignes"][:100]
    s = str(txt)
    if "GO —" in s or "GO -" in s:
        _VAL["verdict"] = "NO-GO" if "NO-GO" in s else "GO"


def _val_lance(quoi: str) -> dict:
    if _VAL["actif"]:
        return {"ok": False, "erreur": "un test tourne deja"}
    _VAL.update({"actif": True, "quoi": quoi, "lignes": [], "fini": False,
                 "verdict": "", "debut": _dt.datetime.now().isoformat()})

    def travail():
        try:
            if quoi == "pead":
                from . import pead
                _val_journal("Univers US large. Collecte des dates "
                             "d'annonces, puis rejeu.")
                pead.lance(tables_univers()["us"](), csv="pead-us.csv",
                           journal=_val_journal)
            else:
                from . import phase0
                _val_journal("Phase 0 sur le S&P 500. Hors echantillon "
                             "2022-2026, un seul passage.")
                # phase0.lance attend une LISTE de tickers. On lui passait
                # la chaine "sp500" : len() valait 5 et le moteur rejouait
                # les regles sur cinq « titres » nommes s, p, 5, 0 et 0.
                # Le bouton VALIDATION rendait donc toujours NO-GO, sans
                # avoir teste quoi que ce soit.
                phase0.lance(tables_univers()["sp500"](),
                             csv="phase0-sp500.csv", journal=_val_journal,
                             univers="sp500")
        except Exception as exc:
            import traceback
            _val_journal(f"ECHEC : {type(exc).__name__}: {exc}")
            traceback.print_exc()
        finally:
            _VAL["actif"] = False
            _VAL["fini"] = True
            _val_journal("")
            _val_journal("Test termine.")

    threading.Thread(target=travail, daemon=True).start()
    return {"ok": True}


# Etat de la validation, partage entre le fil de calcul et les requetes.
_P0 = {"encours": False, "univers": "", "lignes": [], "fini": False,
       "debut": None}


def _p0_lance(univers: str) -> None:
    """Lance la Phase 0 dans un fil separe et collecte sa sortie.

    Elle dure 30 a 90 minutes : la faire tourner dans la requete HTTP
    bloquerait toute l'interface. Les lignes sont accumulees au fur et a
    mesure pour que la page puisse les afficher pendant le calcul.
    """
    import threading

    def bosse():
        _P0.update(encours=True, univers=univers, lignes=[], fini=False,
                   debut=_dt.datetime.now())
        def note(*a):
            txt = " ".join(str(x) for x in a)
            _P0["lignes"].append(txt)
            print(txt)
        try:
            from . import phase0
            note(f"  Univers : {dl.UNIVERS[univers][0]}")
            phase0.lance(tables_univers()[univers](), journal=note,
                         univers=univers)
        except Exception as exc:
            note(f"  ECHEC : {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()
        finally:
            _P0.update(encours=False, fini=True)

    threading.Thread(target=bosse, daemon=True).start()


def _p0_etat() -> dict:
    """Ce que la page affiche : progression, verdict, criteres."""
    lg = _P0["lignes"]
    verdict = ""
    for x in lg:
        if "GO —" in x or "GO -" in x:
            verdict = "NO-GO" if "NO-GO" in x else "GO"
    crit = [x.strip() for x in lg if "PASSE" in x or "ECHOUE" in x]
    duree = ""
    if _P0["debut"]:
        s = int((_dt.datetime.now() - _P0["debut"]).total_seconds())
        duree = f"{s // 60} min {s % 60:02d} s"
    return {"ok": True, "encours": _P0["encours"], "fini": _P0["fini"],
            "univers": _P0["univers"], "duree": duree,
            "n": len(lg), "verdict": verdict, "criteres": crit,
            "lignes": lg[-14:]}


def _radar():
    """Echos du radar : les titres du dernier scan, places selon leur
    distance au declenchement.

    Le rayon vient du nombre de blocs manquants : au centre, un titre
    complet ; au bord, un titre qui en manque cinq ou plus. L'angle est
    derive du nom, donc stable d'un scan a l'autre.
    """
    try:
        d = json.loads(FICHIER_RADAR.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": True, "vide": True, "echos": []}
    echos = []
    for e in d.get("echos", []):
        m = int(e.get("manque", 0))
        # 0 bloc manquant -> rayon 14 ; 5 et plus -> rayon 58
        r = 14 + min(m, 5) / 5 * 44
        ang = (abs(hash(e["t"])) % 360)
        echos.append({"t": e["t"], "manque": m, "r": round(r, 1), "a": ang})
    echos.sort(key=lambda x: x["manque"])
    return {"ok": True, "vide": not echos, "echos": echos,
            "univers": d.get("univers", ""), "quand": d.get("horodatage", ""),
            "n": d.get("n", 0)}


def _actus(force: bool = False):
    """Actualites de marche. Cache de 2 h, contourne par le bouton
    ACTUALISER : le quota gratuit est de 25 appels par jour, un
    rafraichissement manuel de temps en temps reste largement dedans."""
    cle = cle_av()
    try:
        from . import news as nw
        if not hasattr(nw, "monde"):
            raise AttributeError("news.py n'est pas a jour "
                                 "(fonction 'monde' absente)")
    except Exception as exc:
        return [{"titre": f"{exc}", "url": "", "source": "MODULE",
                 "quand": "", "score": None, "sujets": "",
                 "sans_cle": not cle}]
    if not cle:
        return [{"titre": "", "url": "", "source": "", "quand": "",
                 "score": None, "sujets": "", "sans_cle": True}]
    try:
        return nw.monde(cle, limit=12, force=force)
    except Exception as exc:
        return [{"titre": f"indisponible ({type(exc).__name__})", "url": "",
                 "source": "", "quand": "", "score": None, "sujets": ""}]


def _etat():
    """Etat du marche pour la console d'accueil.

    Deux indices seulement : l'ecart a la MM200 dit tout ce qu'il faut ici,
    et deux telechargements suffisent a garder l'accueil rapide.
    """
    import datetime as _dt
    from zoneinfo import ZoneInfo

    from .indicators import enrich

    def ecart(tk):
        try:
            from . import cache as ch
            # Trois ans comme partout ailleurs : une seule entree de cache
            # par titre, partagee avec le scan et les positions.
            d = enrich(ch.charge(tk, annees=3))
            c = float(d["close"].iloc[-1])
            s = float(d["sma200"].iloc[-1])
            return round((c / s - 1) * 100, 1) if s == s and s else None
        except Exception:
            return None

    us, eu = ecart("SPY"), ecart("^STOXX50E")

    lignes = ps.charge()
    n = len(lignes)
    surv = 0
    if n:
        try:
            from . import cache as ch
            ctrl = ps.controle(lambda tk: ch.charge(tk, annees=3))
            surv = sum(1 for x in ctrl
                       if x["verdict"] in ("SORTIE", "STOP TOUCHE", "SURVEILLER"))
        except Exception:
            surv = 0

    # L'etat des neuf places, europeennes comprises. L'ancien calcul ne
    # regardait que New York, avec des horaires ecrits en dur — donc faux
    # pendant les quinze jours ou l'Europe et les Etats-Unis ne sont pas
    # encore passes a l'heure d'ete ensemble.
    from . import seance as sn
    places = sn.toutes()
    ouvertes = [x for x in places if x["ouverte"]]
    ouvert = any(x["cle"] == "newyork" and x["ouverte"] for x in places)
    seance = next((x["code"] for x in places if x["cle"] == "newyork"), "--")
    if ouvertes:
        places_resume = f"{len(ouvertes)} OUVERTE(S)"
    else:
        pr = min(places, key=lambda x: x["prochain"]["dans_minutes"])
        places_resume = f"TOUTES FERMEES"
    # La fenetre d'execution suit la place, elle n'est plus ecrite en dur.
    ny_etat = next(x for x in places if x["cle"] == "newyork")
    execution = f"NY {ny_etat['ouv_paris']} - {ny_etat['clo_paris']}"

    csv = sorted(Path(".").glob("phase0-*.csv"))
    phase0 = "NON LANCEE" if not csv else f"{len(csv)} RAPPORT(S)"

    if us is None and eu is None:
        verdict = "MARCHE INDISPONIBLE"
    elif (us or 0) >= 0 and (eu or 0) >= 0:
        verdict = "REGIME PORTEUR"
    elif (us or 0) < 0 and (eu or 0) < 0:
        verdict = "REGIME DEFENSIF - AUCUN ACHAT"
    else:
        verdict = "REGIME PARTAGE"
    if surv:
        verdict = f"{surv} LIGNE(S) A TRAITER"

    return {"ok": True, **hd.console_etat({
        "us": us, "eu": eu, "n_lignes": n, "max_lignes": 5,
        "n_surveiller": surv, "seance": seance, "ouvert": ouvert,
        "places_resume": places_resume, "execution": execution,
        "places_ouvertes": bool(ouvertes),
        "phase0": phase0, "phase0_ok": bool(csv), "verdict": verdict})}


def _find(terme):
    from .resolve import par_alias
    vrai = par_alias(terme)
    if vrai:
        terme = vrai
    if not terme.strip():
        return []
    try:
        res = fd.chercher_yahoo(terme)
    except Exception:
        return []
    return [{"ticker": r["ticker"], "nom": r["nom"][:40], "place": r["place"],
             "devise": fd.devise(r["ticker"])}
            for r in res if r["type"] in ("EQUITY", "ETF")]


def _verifie(saisie):
    from . import resolve as rs
    if not saisie.strip():
        return {"ok": False, "erreur": "Saisis un ticker."}
    from . import cache as ch
    tk, _ = rs.resoudre(saisie, lambda t: ch.charge(t, annees=3),
                        journal=lambda m: None)
    if tk is None:
        return {"ok": False,
                "erreur": f"{saisie.upper()} introuvable. Utilise Chercher "
                          f"pour trouver le bon ticker."}
    return {"ok": True, "ticker": tk}


def _page_graphique(tk):
    marche = "europe" if tk.endswith(SUF_EU) else "us"
    bench_tk, _nom, ccy = INDICES[marche]
    fx = 1.0 if ccy == "EUR" else REGLAGES["fx"]

    # Resultats et actualites : uniquement si une cle Alpha Vantage existe.
    # Sans cle, les modules correspondants ne s'affichent simplement pas.
    earn, actus, cle = None, None, REGLAGES.get("av_key")
    if cle:
        try:
            cal = nw.earnings_map(cle)
            if tk in cal:
                earn = {"date": cal[tk].isoformat(),
                        "jours": nw.seances_avant(cal[tk])}
        except Exception:
            pass
        try:
            actus = nw.news(cle, tk, limit=5)
        except Exception:
            pass
    if earn is None:
        j = dl.days_to_earnings_yf(tk) if marche == "us" else None
        earn = {"date": "date inconnue", "jours": j}

    from . import cache as ch
    return gr.build_html(ch.charge(tk, annees=20), tk,
                         ch.charge(bench_tk, annees=20),
                         REGLAGES["sleeve"] * fx, ccy, barre=hd.barre(TRACE_D, NOM, fenetre=f"carruos-{tk}",
                                        soustitre="GRAPHIQUE"),
                         marche=marche, earn=earn, actus=actus)


def _scan(univers, marche):
    """Scan d'un univers depuis l'interface.

    TROIS CORRECTIONS.

    1. `days_to_earnings=None` etait passe en dur pour TOUS les titres.
       La regle traite « inconnu » comme un veto — a juste titre — donc
       chaque signal en portait un, `fired` etait toujours faux, et
       `rank()` rendait invariablement une liste vide. Le bouton SCANNER
       ne pouvait structurellement afficher aucun candidat. Le calendrier
       Alpha Vantage est desormais consulte quand une cle existe, et le
       veto ne subsiste que pour les titres reellement inconnus.

    2. Telechargements en parallele et mis en cache : un univers de 500
       titres ne bloque plus l'interface pendant une demi-heure.

    3. Controle qualite avant evaluation, et journal d'audit apres.
    """
    from . import audit as ad
    from . import cache as ch
    from . import qualite as ql
    from .dashboard import LABELS

    tables = tables_univers()
    if univers not in tables:
        return {"ok": False, "erreur": "univers inconnu"}
    if marche not in INDICES:
        return {"ok": False, "erreur": "marche inconnu"}
    bench_tk, nom, ccy = INDICES[marche]
    fx = 1.0 if ccy == "EUR" else REGLAGES["fx"]
    sleeve = REGLAGES["sleeve"] * fx

    detenus = ps.tickers()      # veto "deja en portefeuille", automatique
    bench_raw = ch.charge(bench_tk, annees=3)
    rap_bench = ql.controle(bench_raw, ticker=bench_tk)
    if not rap_bench.utilisable:
        return {"ok": False,
                "erreur": f"donnees de l'indice refusees : {rap_bench.resume()}"}
    bench = enrich(bench_raw)
    regime_ok = market_regime_ok(bench)
    b = bench.iloc[-1]
    regime = (f"{nom} {b['close']:.2f} / MM200 {b['sma200']:.2f} - "
              f"{'RISK-ON' if regime_ok else 'RISK-OFF'}")
    if not regime_ok:
        return {"ok": True, "regime": regime + " - aucune entree autorisee",
                "n": 0, "fired": [], "proches": [], "ecartes": []}

    # Calendrier des resultats : un seul appel pour tout le marche US.
    cal = {}
    cle = cle_av()
    if cle:
        try:
            cal = nw.earnings_map(cle)
        except Exception:
            cal = {}

    liste = tables[univers]()
    brutes, echecs = ch.charge_lot(liste, annees=3)
    sigs, enrichies, rapports = [], {}, {}
    ecartes = [f"{tk} : {m}" for tk, m in echecs[:10]]
    for tk, brut in sorted(brutes.items()):
        try:
            rap = ql.controle(brut, bench_raw, ticker=tk)
            if not rap.utilisable:
                if len(ecartes) < 10:
                    ecartes.append(f"{tk} : {rap.resume()}")
                continue
            d = enrich(brut, bench_close=bench_raw["close"])
            if len(d) < 220:
                continue
            jours = nw.seances_avant(cal.get(tk)) if cal else None
            sigs.append(evaluate(d, tk, regime_ok, open_tickers=detenus,
                                 n_open=len(detenus), days_to_earnings=jours))
            enrichies[tk] = d
            rapports[tk] = rap
        except Exception:
            continue

    # Sans calendrier Alpha Vantage, `jours` vaut None pour tout le monde
    # et la regle pose — a juste titre — un veto « resultats inconnus ».
    # Sans la levee ci-dessous, ce veto frappait les 500 titres et aucun
    # candidat ne pouvait jamais s'afficher : le meme bouton mort que
    # celui corrige plus haut, sous une autre forme. On ne va chercher la
    # date que pour les titres dont c'est le DERNIER obstacle.
    from .scan import resout_resultats
    sigs = resout_resultats(sigs, enrichies, regime_ok, detenus, "yf")
    for sig in sigs:
        ad.enregistre(sig, enrichies.get(sig.ticker), source="interface",
                      univers=univers,
                      qualite={"alertes": rapports[sig.ticker].alertes
                               if sig.ticker in rapports else []})

    out = []
    for s in rank(sigs)[:5]:
        taille = position_size(s, sleeve)
        out.append({"ticker": s.ticker, "entree": round(s.entry, 2),
                    "stop": round(s.stop, 2), "titres": taille["shares"],
                    "rs": round(s.rs_6m, 3)})
    proches = sorted((x for x in sigs if not x.fired),
                     key=lambda x: len(x.failed_blocks))[:12]
    res = {"ok": True, "regime": regime, "n": len(sigs), "fired": out,
           "ecartes": ecartes,
           "calendrier": len(cal),
           "proches": [{"ticker": x.ticker,
                        "manque": ", ".join(LABELS.get(k.split("_")[0], k)
                                            for k in x.failed_blocks[:3])
                                  or "; ".join(x.vetos[:2])}
                       for x in proches]}
    # Trace pour le radar : ce qui manque a chaque titre, en nombre de
    # blocs. C'est cette distance qui donne le rayon de l'echo.
    try:
        FICHIER_RADAR.parent.mkdir(exist_ok=True)
        FICHIER_RADAR.write_text(json.dumps({
            "univers": univers,
            "horodatage": _dt.datetime.now().strftime("%d/%m %H:%M"),
            "n": len(sigs),
            "echos": ([{"t": s.ticker, "manque": 0} for s in rank(sigs)[:5]]
                      + [{"t": x.ticker, "manque": len(x.failed_blocks)}
                         for x in proches])[:14],
        }, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"  radar : ecriture impossible ({type(exc).__name__}: {exc})")
    return res


def _projection(q: dict) -> dict:
    """Projection de reinvestissement. Tout vient de la requete : le taux
    est une hypothese de l'utilisateur, jamais une valeur devinee ici."""
    from . import strategie as sg

    def nombre(cle, defaut, mini=0.0, maxi=1e9):
        try:
            return max(mini, min(maxi, float(q.get(cle, defaut))))
        except (TypeError, ValueError):
            return defaut

    capital = nombre("capital", REGLAGES["sleeve"])
    taux = nombre("taux", 8.0, -50.0, 60.0) / 100.0
    ans = int(nombre("ans", 15, 1, 40))
    mensuel = nombre("mensuel", 0.0)
    impot = sg.PEA_5ANS if q.get("pea") in ("1", "true", "oui") else sg.PFU
    p = sg.projette(capital, taux, ans, mensuel, impot)
    if p.get("ok"):
        p["friction"] = sg.table_friction(taux, impot)
    return p


def _revue_lignes() -> dict:
    """Les faits sur chaque ligne detenue. Aucun verdict n'est calcule :
    les conditions de sortie affichees sont celles de la specification."""
    from . import cache as ch
    from . import qualite as ql
    from . import strategie as sg

    lignes = ps.charge()
    if not lignes:
        return {"ok": True, "lignes": [], "vide": True}
    try:
        bench_brut = ch.charge("SPY", annees=3)
        marche = market_regime_ok(enrich(bench_brut))
    except Exception as exc:
        return {"ok": False, "erreur": f"indice indisponible ({exc})"}

    cal = {}
    cle = cle_av()
    if cle:
        try:
            cal = nw.earnings_map(cle)
        except Exception:
            cal = {}

    out = []
    for l in lignes:
        tk = l["ticker"]
        try:
            brut = ch.charge(tk, annees=3)
            rap = ql.controle(brut, bench_brut, ticker=tk)
            if not rap.utilisable:
                out.append({"ticker": tk, "ok": False,
                            "erreur": rap.resume()})
                continue
            d = enrich(brut, bench_close=bench_brut["close"])
            earn = {}
            if tk in cal:
                earn = {"date": cal[tk].isoformat(),
                        "jours": nw.seances_avant(cal[tk])}
            r = sg.revue_ligne(l, d, marche, earn=earn)
            r["point_mort"] = sg.point_mort_fiscal(r)
            r["alertes"] = rap.alertes
            out.append(r)
        except Exception as exc:
            out.append({"ticker": tk, "ok": False,
                        "erreur": f"{type(exc).__name__}: {exc}"})
    return {"ok": True, "lignes": out, "marche_ok": marche}


def _rapports() -> dict:
    """Ce que contiennent les rapports poses a cote du programme.

    La case PHASE 0 de l'accueil affichait « 2 RAPPORT(S) » sans dire
    lesquels ni ce qu'ils valaient. Un chiffre qu'on ne peut pas ouvrir
    n'apprend rien.
    """
    import csv as _csv

    out = []
    for f in sorted(Path(".").glob("*.csv")):
        nom = f.name
        if not (nom.startswith("phase0-") or nom.startswith("pead-")):
            continue
        genre = "Phase 0" if nom.startswith("phase0-") else "Derive post-annonce"
        info = {"fichier": nom, "genre": genre,
                "univers": nom.split("-", 1)[1].rsplit(".", 1)[0],
                "quand": _dt.datetime.fromtimestamp(
                    f.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                "octets": f.stat().st_size}
        try:
            with f.open(encoding="utf-8") as fp:
                lignes = list(_csv.DictReader(fp))
            info["trades"] = len(lignes)
            rs = [float(x["R"]) for x in lignes if x.get("R")]
            if rs:
                gains = sum(r for r in rs if r > 0)
                pertes = -sum(r for r in rs if r < 0)
                info["gagnants"] = sum(1 for r in rs if r > 0)
                info["ev_R"] = round(sum(rs) / len(rs), 3)
                info["pf"] = (round(gains / pertes, 2) if pertes > 0
                              else None)
            tickers = {x.get("ticker", "") for x in lignes}
            info["titres"] = len(tickers - {""})
            dates = sorted(x.get("entree", "") for x in lignes
                           if x.get("entree"))
            if dates:
                info["periode"] = f"{dates[0]} → {dates[-1]}"
        except Exception as exc:
            info["erreur"] = f"{type(exc).__name__}"
        out.append(info)

    # Le journal d'audit n'est pas un rapport de validation, mais c'est
    # la meme question : qu'est-ce que le programme a garde comme trace ?
    audit = {}
    try:
        from . import audit as ad
        v = ad.verifie()
        audit = {"lignes": v["lignes"],
                 "declenches": v["signaux_declenches"],
                 "parametres_changes": v["parametres_changes"],
                 "empreinte": v["empreinte_actuelle"][:16]}
    except Exception:
        audit = {}

    return {
        "ok": True, "rapports": out, "audit": audit,
        "explication": (
            "Un rapport de Phase 0 est le resultat d'un REJEU des regles "
            "sur l'historique. Il contient chaque trade qu'aurait pris le "
            "systeme : date d'entree, de sortie, prix, stop, resultat en "
            "multiples de risque, et motif de sortie. Il sert a repondre a "
            "une seule question : le signal fait-il mieux que le hasard ? "
            "Ce n'est pas une liste d'actions a acheter."),
        "verdict_connu": (
            "Strategie 1, repli en tendance : NO-GO. Les cinq criteres "
            "n'ont pas ete franchis sur donnees hors echantillon. Les "
            "candidats affiches par le scan restent donc une watchlist, "
            "pas des ordres."),
    }


def _fini(v) -> float | None:
    """Un NaN traverse le JSON en `NaN`, que JSON.parse refuse. On rend
    None : la page sait afficher une valeur absente, pas une erreur de
    parsing."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, 4) if x == x and x not in (float("inf"),
                                               float("-inf")) else None


def _revue_titre(q: dict) -> dict:
    """Revue de N'IMPORTE QUEL titre, detenu ou non.

    Si le titre figure au registre des positions, ses vraies valeurs
    d'entree servent et le trajet complet s'affiche. Sinon, on rend ce
    qui ne depend pas d'une position — sans fabriquer un prix d'entree.
    """
    from . import cache as ch
    from . import qualite as ql
    from . import resolve as rs
    from . import strategie as sg

    saisie = (q.get("ticker") or "").strip()
    if not saisie:
        return {"ok": False, "erreur": "Donnez un ticker."}
    try:
        tk, _ = rs.resoudre(saisie, lambda t: ch.charge(t, annees=3),
                            journal=lambda m: None)
    except Exception as exc:
        return {"ok": False, "erreur": f"{type(exc).__name__}: {exc}"}
    if tk is None:
        return {"ok": False,
                "erreur": f"{saisie.upper()} introuvable. Cherchez le bon "
                          f"ticker depuis l'accueil."}

    try:
        bench_brut = ch.charge("SPY", annees=3)
        marche = market_regime_ok(enrich(bench_brut))
        brut = ch.charge(tk, annees=3)
    except Exception as exc:
        return {"ok": False, "erreur": f"donnees indisponibles ({exc})"}

    rap = ql.controle(brut, bench_brut, ticker=tk)
    if not rap.utilisable:
        return {"ok": False, "ticker": tk,
                "erreur": f"donnees refusees : {rap.resume()}"}
    d = enrich(brut, bench_close=bench_brut["close"])

    # Le registre gagne : si la ligne est detenue, ce sont ses vrais
    # chiffres qui comptent, pas ceux qu'on retaperait a la main.
    detenue = next((l for l in ps.charge()
                    if l["ticker"].upper() == tk.upper()), None)
    entree = detenue["entree"] if detenue else None
    qte = detenue["quantite"] if detenue else 0.0
    depuis = detenue.get("date", "") if detenue else ""
    if not detenue:
        try:
            v = float(q.get("entree") or 0)
            if v > 0:
                entree = v
                qte = float(q.get("qte") or 0)
        except (TypeError, ValueError):
            pass

    earn = {}
    cle = cle_av()
    if cle:
        try:
            cal = nw.earnings_map(cle)
            if tk in cal:
                earn = {"date": cal[tk].isoformat(),
                        "jours": nw.seances_avant(cal[tk])}
        except Exception:
            earn = {}

    r = sg.revue_titre(tk, d, marche, entree, qte, depuis, earn=earn)
    r["point_mort"] = sg.point_mort_fiscal(r)
    r["alertes"] = rap.alertes
    r["au_registre"] = bool(detenue)

    # « Dois-je en racheter ? » se lit dans la specification d'entree,
    # pas dans une opinion. Les treize blocs sont evalues sur la derniere
    # barre : soit ils declenchent, soit ils disent lesquels manquent.
    try:
        from . import rules as R
        jours = earn.get("jours") if earn else None
        sig = R.evaluate(d, tk, marche, days_to_earnings=jours)
        taille = R.position_size(sig, float(REGLAGES.get("sleeve") or 0))
        r["entree_regle"] = {
            "declenche": bool(sig.fired),
            "blocs": {k: bool(v) for k, v in sig.blocks.items()},
            "manquants": list(sig.failed_blocks),
            "vetos": list(sig.vetos),
            "n_blocs": len(sig.blocks),
            "n_remplis": sum(1 for v in sig.blocks.values() if v),
            "prix": _fini(sig.entry),
            "stop": _fini(sig.stop),
            "titres": taille.get("shares", 0),
            "montant": taille.get("notional", 0.0),
            "risque_eur": taille.get("risk_eur", 0.0),
            "plafonne": bool(taille.get("capped")),
            "sleeve": float(REGLAGES.get("sleeve") or 0),
        }
        # « 4a_rvol » ne dit rien a personne, et surtout pas de combien
        # on est loin. Le meme bloc, nomme et chiffre : « volume
        # confirme — volume relatif 0,81 (il faut au moins 1,20) ».
        from . import chart as _gr
        from . import interet as _it
        _u = _it.lire_unite(d, enrich(bench_brut), sig,
                            evaluate_exit(d, marche),
                            _gr._bloc_etats(d, sig),
                            refuse=not rap.utilisable,
                            motifs=rap.bloquants)
        r["entree_regle"]["detail"] = _u["manquants"]
        r["entree_regle"]["niveau"] = _u["titre"]
        r["entree_regle"]["compte"] = _u["compte"]
        r["entree_regle"]["vigilance"] = _u["vigilance"]
        # Sans ca, « RÉSULTATS INCONNUS » s'affichait DEUX fois : une
        # fois en veto, une fois en vigilance. C'est un calendrier qui
        # manque, pas un defaut du titre : il n'appartient qu'a la
        # seconde liste.
        r["entree_regle"]["vetos"] = _u["vetos"]
        r["entree_regle"]["pas_un_avis"] = _it.PAS_UN_AVIS
    except Exception as exc:
        r["entree_regle"] = {"erreur": f"{type(exc).__name__}: {exc}"}

    # Amplitude par horizon et objectifs atteignables : des proprietes du
    # TITRE, mesurees, sans direction et sans rapport avec une strategie.
    try:
        from . import horizon as hz
        dl_ = enrich(ch.charge(tk, annees=10))
        r["horizons"] = hz.amplitude(dl_)
        cib = hz.cibles_du_titre(dl_)
        r["objectifs"] = {
            "cibles": list(cib),
            "1 semaine": hz.atteinte(dl_, cib, 5),
            "1 mois": hz.atteinte(dl_, cib, 21),
            "3 mois": hz.atteinte(dl_, cib, 63),
        }
    except Exception as exc:
        r["horizons"], r["objectifs"] = [], {"erreur": str(exc)}

    return {"ok": True, "revue": r}


JS_PALM = r"""
function $p(i){return document.getElementById(i);}

function echappe(t){
 return String(t==null?'':t).replace(/[&<>"]/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});
}

function ligne(t){
 if(t.groupe==='erreur'){
  return '<div class="li"><div class="tete"><span class="tk">'
   + echappe(t.ticker) + '</span><span class="px">'
   + echappe(t.motif||'illisible') + '</span></div></div>';
 }
 var n = t.niveaux || {}, h = t.histo || {};
 var g = '<div class="li"><div class="tete">'
  + '<span class="tk" data-tk="' + echappe(t.ticker) + '">'
  + echappe(t.ticker) + '</span>'
  + '<span class="cpt g-' + t.groupe + '">' + echappe(t.compte) + '</span>'
  + '<span class="px">' + t.cours + '</span></div>';

 var f = [];
 if(n.risque != null)
  f.push('<div>risque <b>' + n.risque.toFixed(2) + ' %</b></div>');
 if(n.titres)
  f.push('<div><b>' + n.titres + '</b> titre(s) pour <b>' + n.montant
         + '</b></div>',
         '<div>perte si le stop saute <b>' + n.risque_eur + '</b></div>',
         '<div>entrée <b>' + n.entree + '</b> · stop <b>'
         + n.stop + '</b></div>');
 if(t.rs_6m != null)
  f.push('<div>force relative 6 mois <b>'
         + (t.rs_6m>0?'+':'') + t.rs_6m.toFixed(2) + '</b></div>');
 if(f.length) g += '<div class="faits">' + f.join('') + '</div>';

 // Ce que ce signal a REELLEMENT rendu sur ce titre. Jamais un taux nu.
 if(h.n){
  g += '<div class="faits"><div style="grid-column:1/-1">'
    + 'ce signal sur ce titre : <b>' + h.gagnants + ' / ' + h.n
    + '</b> gagnants (intervalle <b>' + h.bas + '–' + h.haut
    + ' %</b>), R moyen <b>' + (h.evR>0?'+':'') + h.evR.toFixed(2)
    + '</b>' + (h.pf==null?'':', profit factor <b>' + h.pf + '</b>')
    + '</div></div>';
 }else if(t.histo){
  g += '<div class="faits"><div style="grid-column:1/-1">ce signal n’a '
    + 'jamais été pris sur ce titre : aucune référence '
    + 'propre</div></div>';
 }

 (t.vetos||[]).forEach(function(v){
  g += '<div class="veto">VETO : ' + echappe(v) + '</div>';});
 (t.refus_motifs||[]).forEach(function(v){
  g += '<div class="veto refus">DONNÉES REFUSÉES : '
       + echappe(v) + '</div>';});
 if((t.groupe==='proche'||t.groupe==='loin') && (t.manquants||[]).length){
  t.manquants.slice(0,4).forEach(function(m){
   g += '<div class="mq"><b>' + echappe(m.nom) + '</b><i>'
        + echappe(m.texte) + '</i></div>';});
 }
 return g + '</div>';
}

// Un seul ecouteur, delegue. L'ancienne version posait un `onclick` en
// ligne avec le ticker entre apostrophes : c'est le piege documente du
// projet — une apostrophe echappee dans une chaine Python NON brute
// devient une apostrophe nue et tue tout le script de la page. Ici il
// n'y a plus une seule apostrophe a echapper.
document.addEventListener('click', function(ev){
 var el = ev.target.closest ? ev.target.closest('.tk[data-tk]') : null;
 if(!el) return;
 location.href = '/graphique?ticker=' + encodeURIComponent(el.dataset.tk);
});

async function classe(){
 var t = $p('ptitres').value.trim();
 if(!t){ $p('pres').innerHTML = '<div class="msg">Collez vos tickers.</div>';
         return; }
 $p('pres').innerHTML = '<div class="msg">Chargement de dix ans de cours '
   + 'par titre… la première fois est la plus longue.</div>';
 var q = 'titres=' + encodeURIComponent(t)
   + '&tri=' + encodeURIComponent($p('ptri').value)
   + '&marche=' + encodeURIComponent($p('pmarche').value)
   + '&sleeve=' + encodeURIComponent($p('psleeve').value);
 try{
  var j = await (await fetch('/api/palmares?' + q)).json();
  if(!j.ok){ $p('pres').innerHTML = '<div class="msg err">'
             + echappe(j.erreur||'') + '</div>'; return; }
  var h = '';
  j.groupes.forEach(function(g){
   h += '<div class="grp"><h3 class="g-' + g.cle + '">' + echappe(g.titre)
     + '</h3>';
   g.lignes.forEach(function(t){ h += ligne(t); });
   h += '</div>';
  });
  if(j.inconnus && j.inconnus.length)
   h += '<div class="av">Introuvables : ' + echappe(j.inconnus.join(', '))
      + '</div>';
  h += '<div class="av"><b>' + echappe(j.avertissement_ratio) + '</b></div>'
    + '<div class="av">' + echappe(j.avertissement_tri) + '</div>';
  $p('pres').innerHTML = h;
 }catch(e){
  $p('pres').innerHTML = '<div class="msg err">Erreur : ' + e + '</div>';
 }
}
"""


# ---------------------------------------------------------------------
# LE CARNET
# ---------------------------------------------------------------------

JS_CARNET = r"""
var CRN_TK='', CRN_G='';
function e(s){ return (s==null?'':String(s))
 .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function crnCharge(){
 var u='/api/carnet?ticker='+encodeURIComponent(CRN_TK)
      +'&genre='+encodeURIComponent(CRN_G)
      +'&q='+encodeURIComponent(($('cq').value||'').trim());
 var j=await (await fetch(u)).json();
 var c=j.compte||{};
 $('ccpt').textContent=(c.total||0)+' ENTREES  ·  '+(c.note||0)+' NOTES  ·  '
   +(c.releve||0)+' RELEVES  ·  '+(c.ordre||0)+' ORDRES';
 var h='';
 (j.entrees||[]).forEach(function(x){
  h+='<div class="cse g-'+e(x.genre)+'"><div class="t">'
   +'<span class="d">'+e((x.date||'').slice(0,16).replace('T',' '))+'</span>'
   +'<span class="g">'+e((x.genre||'note').toUpperCase())+'</span>'
   +(x.ticker?'<span class="tk" data-vers="/graphique?ticker='
     +encodeURIComponent(x.ticker)+'" data-fen="carruos-'+e(x.ticker)+'">'
     +e(x.ticker)+'</span>':'')
   +'<span class="ti">'+e(x.titre)+'</span>'
   +'<span class="x" data-sup="'+e(x.id)+'" title="Supprimer">&times;</span>'
   +'</div>';
  if(x.texte) h+='<pre>'+e(x.texte)+'</pre>';
  if(x.donnees) h+='<div class="dn">'+e(JSON.stringify(x.donnees,null,1))+'</div>';
  h+='</div>';
 });
 $('cl').innerHTML=h||'<p class="ex">Rien encore. La premiere note se '
  +'prend au moment ou vous decidez, pas apres.</p>';
 var o='<option value="">TOUS LES TITRES</option>';
 (j.tickers||[]).forEach(function(t){
  o+='<option value="'+e(t)+'"'+(t===CRN_TK?' selected':'')+'>'+e(t)+'</option>';});
 $('cft').innerHTML=o;
}

async function crnEcrit(){
 var titre=($('ctitre').value||'').trim(), texte=$('ctexte').value||'';
 if(!titre && !texte.trim()){ $('cm').textContent='Rien a enregistrer.'; return; }
 $('cm').textContent='Enregistrement...';
 var r=await fetch('/api/carnet',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({action:'ajoute',titre:titre,texte:texte,
     ticker:($('ctk').value||'').trim(),genre:$('cg').value})});
 var j=await r.json();
 if(!j.ok){ $('cm').textContent=j.erreur||'Echec.'; return; }
 $('ctitre').value=''; $('ctexte').value='';
 $('cm').textContent='Enregistre.';
 crnCharge();
}

async function crnReleve(){
 var tk=($('ctk').value||'').trim();
 if(!tk){ $('cm').textContent='Un releve demande un ticker.'; return; }
 $('cm').textContent='Mesure en cours...';
 var r=await fetch('/api/carnet',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({action:'releve',ticker:tk})});
 var j=await r.json();
 $('cm').textContent=j.ok?('Releve de '+tk+' fige.'):(j.erreur||'Echec.');
 if(j.ok) crnCharge();
}

document.addEventListener('click',async function(ev){
 var x=ev.target.closest && ev.target.closest('[data-sup]');
 if(!x) return;
 await fetch('/api/carnet',{method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({action:'supprime',id:x.getAttribute('data-sup')})});
 crnCharge();
});
// Brouillon garde dans le navigateur : fermer la fenetre par megarde ne
// doit pas effacer ce qu'on etait en train d'ecrire.
['ctitre','ctexte','ctk'].forEach(function(k){
 var el=$(k); if(!el) return;
 try{ var v=localStorage.getItem('crn-'+k); if(v) el.value=v; }catch(e){}
 el.addEventListener('input',function(){
  try{ localStorage.setItem('crn-'+k, el.value); }catch(e){} });
});
document.addEventListener('DOMContentLoaded', function(){
 $('cft').addEventListener('change', function(){ CRN_TK=this.value; crnCharge(); });
 $('cfg').addEventListener('change', function(){ CRN_G=this.value; crnCharge(); });
 $('cq').addEventListener('input', function(){ crnCharge(); });
 crnCharge();
});
"""


def _page_carnet() -> str:
    """Le CARNET : vos notes, et les releves dates de ce qui etait mesure.

    La page ne calcule rien elle-meme. Le bouton FIGER LE RELEVE demande
    au serveur l'etat du titre tel que le moteur le voit a cet instant,
    et l'ecrit tel quel. Un releve reconstruit apres coup ne repondrait
    pas a la question qu'on lui pose.
    """
    reg = rg.charge()
    from . import carnet as cn
    genres = "".join(f'<option value="{k}">{v}</option>'
                     for k, v in cn.GENRES.items())
    return (
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="icon" type="image/svg+xml" href="/carruos.svg">'
        '<link rel="alternate icon" href="/favicon.ico">'
        f"<title>{NOM} - carnet</title>"
        f"<style>{rg.variables(reg)}{CSS}{CSS_CARNET}</style></head>"
        f'<body class="{rg.classes(reg)}"{rg.corps_attrs(reg)}>'
        + rg.tiroir_html(reg)
        + hd.fond(TRACE_D)
        + '<div class="app">'
        + hd.barre(TRACE_D, NOM, actif="carnet", soustitre="CARNET")
        + '<div class="crn">'

          '<section class="pan"><div class="trait"><i></i></div>'
          '<h2>ECRIRE</h2><div class="corps">'
          '<p class="ex">Ce que vous ecrivez ici n\'est <b>ni lu ni '
          'interprete</b> par le programme. Un <b>releve</b>, lui, fige '
          'ce que le moteur mesure <b>a cet instant</b> : c\'est la '
          'seule facon de savoir plus tard ce que vous voyiez le jour '
          'ou vous avez decide.</p>'
          '<div class="lg">'
          '<input id="ctk" placeholder="Titre concerne (optionnel)">'
          f'<select id="cg">{genres}</select></div>'
          '<div class="lg"><input id="ctitre" placeholder="Titre de la note">'
          '</div>'
          '<textarea id="ctexte" placeholder="Pourquoi cette ligne. Ce que '
          'vous attendez. Ce qui vous ferait changer d\'avis."></textarea>'
          '<div class="lg" style="margin-top:9px">'
          '<button onclick="crnEcrit()">ENREGISTRER</button>'
          '<button class="sec" onclick="crnReleve()">FIGER LE RELEVE</button>'
          '</div><div class="msg" id="cm"></div>'
          '</div></section>'

          '<section class="pan"><div class="trait"><i></i></div>'
          '<h2>LE CARNET</h2><div class="corps">'
          '<div class="cpt" id="ccpt">&mdash;</div>'
          '<div class="lg">'
          '<select id="cft"><option value="">TOUS LES TITRES</option></select>'
          '<select id="cfg"><option value="">TOUS LES GENRES</option>'
          '<option value="note">NOTES</option>'
          '<option value="releve">RELEVES</option>'
          '<option value="ordre">ORDRES</option></select>'
          '<input id="cq" placeholder="Chercher un mot"></div>'
          '<div id="cl"></div>'
          '</div></section>'

          '</div></div>'
        + f"<script>{hd.BARRE_JS}{JS_CARNET}{rg.tiroir_js()}</script>"
          "</body></html>")


def _carnet(q: dict) -> dict:
    """Lecture du carnet, filtree."""
    from . import carnet as cn
    return {"ok": True,
            "entrees": cn.entrees(ticker=q.get("ticker", ""),
                                  genre=q.get("genre", ""),
                                  q=q.get("q", "")),
            "tickers": cn.tickers(),
            "compte": cn.compte()}


def _carnet_ecrit(c: dict) -> dict:
    """Ecriture. Un releve passe par le moteur, jamais par le navigateur.

    Le navigateur pourrait poster n'importe quel chiffre dans `donnees`.
    Le releve serait alors une photo de ce que la page AFFICHAIT, pas de
    ce que le moteur a MESURE — et c'est exactement la confusion que le
    carnet est cense empecher. Le serveur recalcule donc lui-meme.
    """
    from . import carnet as cn
    action = (c.get("action") or "ajoute").strip()
    if action == "supprime":
        return {"ok": cn.supprime(c.get("id", ""))}
    if action == "modifie":
        e = cn.modifie(c.get("id", ""), titre=c.get("titre"),
                       texte=c.get("texte"), ticker=c.get("ticker"))
        return {"ok": e is not None, "entree": e}
    if action == "releve":
        tk = (c.get("ticker") or "").strip().upper()
        if not tk:
            return {"ok": False, "erreur": "Un releve demande un ticker."}
        faits = _faits_releve(tk)
        if not faits.get("ok"):
            return {"ok": False, "erreur": faits.get("erreur", "mesure impossible")}
        return {"ok": True, "entree": cn.releve(tk, faits)}
    if action == "ajoute":
        return {"ok": True,
                "entree": cn.ajoute(titre=c.get("titre", ""),
                                    texte=c.get("texte", ""),
                                    ticker=c.get("ticker", ""),
                                    genre=c.get("genre", "note"))}
    return {"ok": False, "erreur": "action inconnue"}


def _faits_releve(tk: str) -> dict:
    """Ce que le moteur mesure sur un titre, a cet instant.

    On reutilise le dossier du majordome : c'est deja le point unique
    ou les faits d'un titre sont rassembles, et en ajouter un second
    garantirait qu'un jour les deux divergent.
    """
    from . import dossier as ds
    try:
        d = ds.constitue(tk)
    except Exception as exc:
        return {"ok": False, "erreur": f"{type(exc).__name__}: {exc}"}
    if not d or d.get("erreur"):
        return {"ok": False, "erreur": (d or {}).get("erreur", "titre introuvable")}
    d["ok"] = True
    return d


def _page_palmares() -> str:
    """MA LISTE : des titres colles a la main, passes aux 13 blocs.

    Le tri par defaut est celui de la SPECIFICATION — force relative a
    6 mois — et la page affiche l'avertissement que ce tri porte dans
    son propre code. Les autres tris portent chacun sur UN fait. Aucun
    score composite : c'est ce que le projet refuse depuis le debut.
    """
    from . import palmares as pm

    reg = rg.charge()
    tris = "".join(
        f'<option value="{k}"'
        + (" selected" if k == pm.TRI_DEFAUT else "")
        + f">{html.escape(v)}</option>"
        for k, v in {k: v[0] for k, v in pm.TRIS.items()}.items())
    sleeve = int(REGLAGES.get("sleeve") or 8000)
    return (
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="icon" type="image/svg+xml" href="/carruos.svg">'
        '<link rel="alternate icon" href="/favicon.ico">'
        f"<title>{NOM} - ma liste</title>"
        f"<style>{rg.variables(reg)}{CSS}{CSS_FICHE}{CSS_PALM}</style></head>"
        f'<body class="{rg.classes(reg)}"{rg.corps_attrs(reg)}>'
        + rg.tiroir_html(reg)
        + hd.fond(TRACE_D)
        + '<div class="app">'
          + hd.barre(TRACE_D, NOM, actif="palmares",
                     soustitre="MA LISTE")
          + '<div class="palm">'
          '<p class="ex">Collez vos tickers &mdash; <b>COIN HOOD TLX.DE '
          'MC.PA</b> &mdash; séparés par des espaces ou des '
          'virgules. Chacun passe les <b>13 blocs</b> de la '
          'spécification et ses <b>vetos</b>, puis se range dans son '
          'groupe. Cliquez un ticker pour ouvrir son graphique.</p>'
          '<div class="saisie">'
          '<div><label>TITRES</label>'
          '<textarea id="ptitres" placeholder="COIN HOOD TLX.DE MC.PA">'
          '</textarea></div>'
          f'<div><label>TRI</label><select id="ptri">{tris}</select></div>'
          '<div><label>INDICE DE RÉFÉRENCE</label>'
          '<select id="pmarche"><option value="us">S&amp;P 500 (US)</option>'
          '<option value="europe">STOXX 600 (Europe)</option></select></div>'
          '</div>'
          '<div class="saisie" style="grid-template-columns:1fr 150px 150px">'
          '<div></div>'
          '<div><label>SLEEVE</label>'
          f'<input id="psleeve" type="number" value="{sleeve}"></div>'
          '<div><button class="go" onclick="classe()">CLASSER</button></div>'
          '</div>'
          '<div id="pres"></div>'
          '</div></div>'
        + f"<script>{hd.BARRE_JS}{JS_PALM}{rg.tiroir_js()}</script></body></html>")


def _dossier(q: dict) -> dict:
    """Une question en francais -> la section du dossier qui y repond.

    La reconnaissance se fait ICI, cote serveur, parce que trancher
    quel mot est un ticker demande d'interroger les donnees : « QUE
    PENSE TU DE TLX » ne contient aucun autre indice.
    """
    from . import cache as ch
    from . import dossier as ds

    question = (q.get("q") or "").strip()
    defaut = (q.get("ticker") or "").strip().upper() or None
    if not question and not defaut:
        return {"ok": False, "erreur": "Posez une question : « je sors "
                                       "quand sur TLX », « combien je peux "
                                       "perdre sur COIN »."}

    def existe(t):
        try:
            ch.charge(t, annees=1)
            return True
        except Exception:
            return False

    try:
        inten, tk = ds.comprend(question, existe, defaut)
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "erreur": f"{type(exc).__name__}: {exc}"}
    if not tk:
        return {"ok": False, "intention": inten,
                "erreur": "Je n'ai pas reconnu de titre dans la question. "
                          "Nommez-le : « je sors quand sur TLX.DE »."}

    # Si la ligne est au registre, ses VRAIS chiffres comptent — pas un
    # prix d'entree fabrique pour combler le trou.
    pos = next((l for l in ps.charge()
                if l.get("ticker", "").upper() == tk), None)
    try:
        d = ds.constitue(tk, av_key=cle_av(),
                         sleeve=float(REGLAGES.get("sleeve") or 8000),
                         position=pos)
        rep = ds.repond(question, d)
        rep["voix"] = ds.phrase(rep)
        rep["cours"] = d.get("cours")
        rep["devise"] = d.get("devise", "")
        rep["date"] = d.get("date", "")
        return rep
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "erreur": f"{type(exc).__name__}: {exc}"}


def _palmares(q: dict) -> dict:
    """Une liste de titres passee aux 13 blocs, groupee et triee."""
    from . import palmares as pm

    saisie = (q.get("titres") or "").strip()
    if not saisie:
        return {"ok": False, "erreur": "Collez vos tickers : COIN HOOD "
                                       "TLX.DE, separes par des espaces "
                                       "ou des virgules."}
    jetons = pm.decoupe(saisie)
    if not jetons:
        return {"ok": False, "erreur": "Aucun ticker lisible dans la saisie."}
    if len(jetons) > 40:
        return {"ok": False,
                "erreur": f"{len(jetons)} titres d'un coup, c'est trop : "
                          f"chacun demande dix ans de cours. Quarante au "
                          f"maximum."}
    try:
        sleeve = float(q.get("sleeve") or REGLAGES.get("sleeve") or 8000)
    except (TypeError, ValueError):
        sleeve = float(REGLAGES.get("sleeve") or 8000)
    marche = "europe" if (q.get("marche") == "europe") else "us"
    tri = q.get("tri") or pm.TRI_DEFAUT
    try:
        return pm.evalue(jetons, sleeve, marche, tri, av_key=cle_av(),
                         journal=lambda _m: None)
    except Exception as exc:
        traceback.print_exc()
        return {"ok": False, "erreur": f"{type(exc).__name__}: {exc}"}


def _page_strategie() -> str:
    """La page STRATEGIE. Deux moities de nature differente, et le texte
    le dit : a gauche de l'arithmetique, a droite des faits mesures."""
    reg = rg.charge()
    return (
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="icon" type="image/svg+xml" href="/carruos.svg"><link rel="alternate icon" href="/favicon.ico">'
        f"<title>{NOM} - strategie</title>"
        f"<style>{rg.variables(reg)}{CSS}{CSS_FICHE}{CSS_STRAT}</style></head>"
        f'<body class="{rg.classes(reg)}"{rg.corps_attrs(reg)}>'
        + rg.tiroir_html(reg)
        + hd.fond(TRACE_D)
        + '<div class="app strat-page">'
          + hd.barre(TRACE_D, NOM, actif="strategie",
                     soustitre="STRATEGIE")

          + '<div class="strat">'
          '<section class="pan"><h2>SI JE REINVESTIS</h2>'
          '<div class="corps">'
          '<p class="ex">Le meme rendement, trois traitements fiscaux. '
          'Le taux ci-dessous est <b>votre hypothese</b> : ce tableau en '
          'tire les consequences, il ne les devine pas.</p>'
          '<div class="champs">'
          '<label>Capital<input id="pcap" type="number" value="8000"></label>'
          '<label>Versement / mois<input id="pmens" type="number" value="0">'
          '</label>'
          '<label>Rendement brut %/an<input id="ptaux" type="number" '
          'value="8" step="0.5"></label>'
          '<label>Horizon (ans)<input id="pans" type="number" value="15">'
          '</label>'
          '</div>'
          '<div class="row" style="margin-top:9px">'
          '<button onclick="proj()">CALCULER</button>'
          '<button class="sec" id="benv" onclick="basculePea()">'
          'COMPTE-TITRES (30 %)</button></div>'
          '<div id="pres"></div>'
          '</div></section>'

          '<section class="pan"><h2>MES LIGNES</h2>'
          '<div class="corps">'
          '<p class="ex">Les faits mesurables sur chaque position, et '
          'l\'etat des <b>quatre conditions de sortie de votre '
          'specification</b>. Aucun verdict n\'est calcule ici.</p>'
          '<div class="row">'
          '<input id="rtk" placeholder="n\'importe quel titre : NVDA, MC.PA, '
          'TLX...">'
          '<input id="rent" type="number" step="0.01" '
          'title="facultatif : donne le trajet complet de la position" '
          'placeholder="prix d\'entree" style="max-width:150px">'
          '<button onclick="revue()">EXAMINER</button></div>'
          '<div id="rres"></div>'
          '<div class="titre-sec">MES POSITIONS</div>'
          '<div id="lres" class="msg">Releve en cours...</div>'
          '</div></section>'
          '</div></div>'
        + f"<script>{hd.BARRE_JS}{JS_FICHE}{JS_STRAT}{rg.tiroir_js()}</script>"
          "</body></html>")


def _icone() -> str:
    """carruos.ico vit a cote de Carruos.vbs, donc au-dessus du paquet."""
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / "carruos.ico"
    return str(f) if f.exists() else ""


def _pose_icone(titre: str, chemin: str) -> None:
    """Windows tire l'icone d'une fenetre du processus qui la cree : sans ca,
    la barre des taches affiche celle de Python. On attend que la fenetre
    existe, puis on lui envoie WM_SETICON."""
    import ctypes
    import time
    try:
        u = ctypes.windll.user32
    except AttributeError:
        return
    IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
    WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
    for _ in range(80):
        h = u.FindWindowW(None, titre)
        if h:
            for taille, quel in ((64, ICON_BIG), (16, ICON_SMALL)):
                ico = u.LoadImageW(None, chemin, IMAGE_ICON, taille, taille,
                                   LR_LOADFROMFILE)
                if ico:
                    u.SendMessageW(h, WM_SETICON, quel, ico)
            return
        time.sleep(.25)


def _port_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    port = _port_libre()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Bruce)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    ico = _icone()
    try:
        # Identite d'application distincte : la barre des taches regroupe
        # Carruos sous sa propre icone au lieu de la fondre dans Python.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Carruos.Scanner.1")
    except Exception:
        pass

    try:
        import webview

        # « je veux que la premiere reste et quand j'ouvre un onglet ca
        # m'ouvre une autre fenetre ». Dans un navigateur, `window.open`
        # suffit. Sous pywebview, le moteur n'ouvre pas de fenetre tout
        # seul : c'est Python qui doit la creer. La page appelle donc
        # `pywebview.api.fenetre()` quand elle existe, et retombe sur
        # `window.open` sinon — le meme code sert les deux mondes.
        class Fenetres:
            """Ouvre, ou rappelle, une fenetre nommee."""

            def __init__(self):
                self._ouvertes = {}

            def fenetre(self, adresse: str, nom: str = ""):
                adresse = str(adresse or "/")
                if not adresse.startswith("/"):
                    return {"ok": False}
                nom = str(nom or adresse)
                f = self._ouvertes.get(nom)
                if f is not None:
                    # Une fenetre fermee reste dans le dictionnaire : on
                    # ne le sait qu'en essayant de s'en servir.
                    try:
                        f.load_url(url.rstrip("/") + adresse)
                        return {"ok": True, "rappelee": True}
                    except Exception:
                        self._ouvertes.pop(nom, None)
                self._ouvertes[nom] = webview.create_window(
                    TITRE, url.rstrip("/") + adresse, width=1280, height=880,
                    min_size=(900, 620), background_color="#080b10")
                return {"ok": True, "rappelee": False}

        webview.create_window(TITRE, url, width=1420, height=940,
                              min_size=(980, 680), background_color="#080b10",
                              js_api=Fenetres())
        if ico:
            threading.Thread(target=_pose_icone, args=(TITRE, ico),
                             daemon=True).start()
        webview.start()
    except ImportError:
        print("pywebview absent : ouverture dans le navigateur.")
        print("Pour une vraie fenetre :  py -m pip install pywebview")
        print(f"Bruce tourne sur {url}   (Ctrl+C pour arreter)")
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
