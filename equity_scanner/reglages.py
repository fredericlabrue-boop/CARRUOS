"""Reglages de l'interface : couleurs, indicateurs, modules, effets.

Persistance cote serveur dans .bruce_cache/reglages.json. Pas de
localStorage : le port du serveur change a chaque lancement, donc un
stockage lie a l'origine serait perdu a chaque demarrage.

Tout s'applique en direct par variables CSS et classes sur <body> — aucun
rechargement de page.
"""

from __future__ import annotations

import json
from pathlib import Path

FICHIER = Path(".bruce_cache") / "reglages.json"

# =====================================================================
# THEMES
#
# Un theme n'est pas qu'une couleur d'accent : c'est le fond, la teinte
# de l'hologramme, la matiere des panneaux et le contraste du texte.
# Les trois se distinguent au premier coup d'oeil, sans quoi changer de
# theme ne sert a rien.
#
# `holo` est un triplet RVB, pas un code hexadecimal : il sert dans des
# rgba() de degrades, ou l'hexadecimal ne passe pas.
# =====================================================================
THEMES = {
    "carruos": {
        "nom": "CARRUOS",
        "resume": "cyan et or, sobre",
        "accent": "#22d3ee", "marque": "#c9b28a", "fond": "#080b10",
        "pos": "#34d399", "neg": "#f87171", "holo": "34,211,238",
    },
    "jarvis": {
        "nom": "JARVIS",
        "resume": "hologramme bleu clair et or, lumineux",
        "accent": "#6cd8ff", "marque": "#ffc46b", "fond": "#030a14",
        "pos": "#5eead4", "neg": "#ff8a5b", "holo": "125,211,252",
    },
    "ultron": {
        "nom": "ULTRON",
        "resume": "tres sombre, neons violet et rouge",
        "accent": "#b06cff", "marque": "#ff2d55", "fond": "#05030a",
        "pos": "#00e5a0", "neg": "#ff2d55", "holo": "176,108,255",
    },
    # Le tableau de bord dense : bleu electrique franc sur noir, traits
    # fins et lumineux, panneaux instrumentes. Plus dur et plus contraste
    # que JARVIS, qui reste la version douce et doree.
    "reacteur": {
        "nom": "REACTEUR",
        "resume": "bleu electrique dense, tableau de bord",
        "accent": "#00b4ff", "marque": "#dff3ff", "fond": "#02060c",
        "pos": "#00e08a", "neg": "#ff4d5e", "holo": "0,180,255",
    },

    # ------------------------------------------------------------------
    # Les themes qui suivent changent la FORME, pas seulement la couleur.
    # Chacun redefinit sa geometrie, sa densite et sa typographie : mis
    # cote a cote en noir et blanc, ils resteraient reconnaissables.
    # ------------------------------------------------------------------

    # Angles droits, pas une seule diagonale, pas d'equerre, beaucoup de
    # vide. Le contraire exact de l'apparence d'origine.
    "monolithe": {
        "nom": "MONOLITHE",
        "resume": "angles droits, aucun ornement, tres aere",
        "accent": "#d8d2c4", "marque": "#8a8578", "fond": "#0c0c0d",
        "pos": "#9fbfa4", "neg": "#c98b86", "holo": "216,210,196",
        "forme": {
            "coin": "0px", "rayon": "0px", "equerre": "0",
            "pad": "22px 24px 19px", "gap": "14px",
            "bord": "#232322", "bord_fort": "#3a3937",
            "pan_fond": "rgba(17,17,18,.82)",
            "pan_ombre": "none",
            "txt": "#9b968c", "txt_fort": "#ece7dc",
            "txt_doux": "#b8b2a6", "txt_mi": "#8a8578",
            "txt_faible": "#5e5b54",
            "titre_espace": ".34em", "titre_casse": "uppercase",
            "champ_fond": "#151516",
        },
    },

    # Arrondi franc, traits circulaires, lettres tres espacees. Tout ce
    # qui etait anguleux devient courbe.
    "orbite": {
        "nom": "ORBITE",
        "resume": "tout en courbes, bleu profond, lettres espacees",
        "accent": "#7fe3ff", "marque": "#cfe9f5", "fond": "#040911",
        "pos": "#57e3b8", "neg": "#ff7a92", "holo": "127,227,255",
        "forme": {
            "coin": "0px", "rayon": "19px", "equerre": "0",
            "pad": "18px 20px 15px", "gap": "12px",
            "bord": "#13344a", "bord_fort": "#2b6f93",
            "pan_fond": "rgba(6,15,26,.7)",
            "pan_ombre": ("inset 0 1px 0 rgba(127,227,255,.12),"
                          "0 8px 30px rgba(0,0,0,.55)"),
            "txt": "#8aa7bb", "txt_fort": "#e4f4fd",
            "txt_doux": "#a9c8da", "txt_mi": "#7d9cb0",
            "txt_faible": "#4d7a96",
            "titre_espace": ".42em", "titre_casse": "uppercase",
            "champ_fond": "#081726",
        },
    },

    # Chaleur : or sur brun tres sombre, coins doucement arrondis,
    # titres en serif. La seule fonte a empattements de la maison.
    "nocturne": {
        "nom": "NOCTURNE",
        "resume": "or sur brun sombre, titres en serif, feutre",
        "accent": "#d9b166", "marque": "#e8d5ad", "fond": "#0c0906",
        "pos": "#8fbf87", "neg": "#d4756b", "holo": "217,177,102",
        "forme": {
            "coin": "0px", "rayon": "8px", "equerre": "0",
            "pad": "19px 21px 16px", "gap": "12px",
            "bord": "#2b2115", "bord_fort": "#4e3c22",
            "pan_fond": "rgba(20,15,9,.8)",
            "pan_ombre": "0 6px 26px rgba(0,0,0,.6)",
            "txt": "#a8987c", "txt_fort": "#f2e6cd",
            "txt_doux": "#cbb894", "txt_mi": "#9c8a6d",
            "txt_faible": "#6d5f47",
            "titre_police": "Georgia,'Times New Roman',serif",
            "titre_espace": ".16em", "titre_casse": "none",
            "corps_police": "Georgia,'Times New Roman',serif",
            "champ_fond": "#171109",
        },
    },

    # Biseau sur les QUATRE angles, contraste dur, glace et violet.
    "cristal": {
        "nom": "CRISTAL",
        "resume": "biseaute aux quatre angles, glace et violet",
        "accent": "#a9b4ff", "marque": "#e6e9ff", "fond": "#06060d",
        "pos": "#6ee7d0", "neg": "#ff6b9d", "holo": "169,180,255",
        "forme": {
            "coin": "22px", "rayon": "0px", "equerre": "0",
            "pad": "20px 22px 17px", "gap": "11px",
            "bord": "#1e2044", "bord_fort": "#4a4f96",
            "pan_fond": "rgba(11,11,22,.78)",
            "pan_ombre": ("inset 0 0 60px rgba(169,180,255,.06),"
                          "0 0 30px rgba(0,0,0,.6)"),
            "txt": "#9497c4", "txt_fort": "#e8eaff",
            "txt_doux": "#b5b8e0", "txt_mi": "#8386b5",
            "txt_faible": "#565a8c",
            "titre_espace": ".3em", "titre_casse": "uppercase",
            "champ_fond": "#0e0e1c",
        },
    },

    # Densite maximale : rien de decoratif, tout est information. Le
    # theme a choisir quand on veut voir le plus de choses a la fois.
    "terminal": {
        "nom": "TERMINAL",
        "resume": "dense, sans ornement, tout en chasse fixe",
        "accent": "#4ade80", "marque": "#bbf7d0", "fond": "#010402",
        "pos": "#4ade80", "neg": "#fb7185", "holo": "74,222,128",
        "forme": {
            "coin": "0px", "rayon": "0px", "equerre": "0",
            "pad": "8px 9px 7px", "gap": "5px",
            "bord": "#12301e", "bord_fort": "#1f6b3d",
            "pan_fond": "rgba(2,8,4,.9)",
            "pan_ombre": "none",
            "txt": "#78a98c", "txt_fort": "#d6ffe4",
            "txt_doux": "#9ec9ae", "txt_mi": "#6c9a7e",
            "txt_faible": "#4a6f59",
            "titre_espace": ".18em", "titre_casse": "uppercase",
            "corps_police": "ui-monospace,Consolas,monospace",
            "champ_fond": "#04160a",
        },
    },

    # Le seul theme CLAIR. Fond ivoire, texte sombre, filets fins : pour
    # travailler en plein jour sans se bruler les yeux. C'est le test le
    # plus severe du systeme de variables — si celui-ci tient, tous
    # tiennent.
    "papier": {
        "nom": "PAPIER",
        "resume": "clair, ivoire et encre, pour le plein jour",
        "accent": "#0f6e7a", "marque": "#8a6a3c", "fond": "#f4f1ea",
        "pos": "#1c7a4f", "neg": "#b03a3a", "holo": "15,110,122",
        "forme": {
            "coin": "0px", "rayon": "3px", "equerre": "0",
            "pad": "18px 20px 15px", "gap": "12px",
            "bord": "#d6d0c4", "bord_fort": "#b3aa99",
            "pan_fond": "rgba(255,253,248,.92)",
            "pan_ombre": "0 1px 3px rgba(60,50,35,.1)",
            "txt": "#4a453d", "txt_fort": "#171512",
            "txt_doux": "#3a3630", "txt_mi": "#6a6459",
            "txt_faible": "#8a8376",
            "titre_espace": ".26em", "titre_casse": "uppercase",
            "champ_fond": "#fffdf8",
        },
    },
}

DEFAUTS = {
    "theme": "carruos",
    "accent": "#22d3ee",
    "marque": "#c9b28a",
    "fond": "#080b10",
    "pos": "#34d399",
    "neg": "#f87171",
    "effets": {"scan": True, "bloom": True, "chroma": True,
               "rotation": True, "vacille": True, "halo": True, "cone": True,
               "fond": True, "sol": True, "rayon": True, "trait": True,
               "entree": True, "verre": True},
    "indics": {"ema20": True, "sma50": True, "sma200": True, "bb": True,
               "rsi": True, "macd": True, "volume": True, "signaux": True},
    "modules": {"momentum": True, "ecarts": True, "perfrel": True,
                "signal": True, "horloge": True, "resultats": True,
                "actus": True, "cadrans": True, "rails": True,
                "hologramme": True, "bandeau": True},
    "densite": "normale",
    "grille": True,
}

PALETTES = [
    ("Cyan", "#22d3ee"), ("Ambre", "#f59e0b"), ("Emeraude", "#10b981"),
    ("Violet", "#a78bfa"), ("Rose", "#fb7185"), ("Or", "#c9b28a"),
    ("Bleu", "#60a5fa"), ("Blanc", "#e2e8f0"),
]

LIB_EFFETS = [("scan", "Lignes de balayage"), ("bloom", "Halo lumineux"),
              ("chroma", "Aberration chromatique"), ("rotation", "Anneaux rotatifs"),
              ("vacille", "Vacillement"), ("halo", "Pulsation du noyau"),
              ("cone", "Cone de projection"),
              ("fond", "Cerf geant en fond"), ("sol", "Sol en perspective"),
              ("rayon", "Faisceau descendant"), ("trait", "Trait lumineux"),
              ("entree", "Apparition des panneaux"),
              ("verre", "Panneaux en verre")]

LIB_INDICS = [("ema20", "EMA 20"), ("sma50", "SMA 50"), ("sma200", "SMA 200"),
              ("bb", "Bollinger 20/2"), ("rsi", "RSI 14"),
              ("macd", "MACD 12-26-9"), ("volume", "Volume"),
              ("signaux", "Fleches de signal")]

LIB_MODULES = [("cadrans", "Cadrans radiaux"), ("hologramme", "Hologramme du cerf"),
               ("rails", "Rails de mesure"), ("bandeau", "Bandeau de chiffres"),
               ("momentum", "Momentum"), ("ecarts", "Ecart aux reperes"),
               ("perfrel", "Performance relative"), ("signal", "Signal sur ce titre"),
               ("horloge", "Seance et execution"), ("resultats", "Resultats"),
               ("actus", "Actualites")]


def _fusion(base: dict, autre: dict) -> dict:
    out = dict(base)
    for k, v in (autre or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _fusion(out[k], v)
        elif k in out:
            out[k] = v
    return out


def charge() -> dict:
    """Les defauts sont toujours la base : un reglage absent du fichier
    reprend sa valeur d'origine au lieu de faire planter la page."""
    try:
        return _fusion(DEFAUTS, json.loads(FICHIER.read_text(encoding="utf-8")))
    except Exception:
        return json.loads(json.dumps(DEFAUTS))


def applique_theme(r: dict, cle: str) -> dict:
    """Pose les cinq couleurs du theme. Choisir un theme repeint tout ;
    la palette d'accent, ensuite, ne change que l'accent."""
    t = THEMES.get(cle)
    if not t:
        return r
    out = dict(r, theme=cle)
    for k in ("accent", "marque", "fond", "pos", "neg"):
        out[k] = t[k]
    return out


def sauve(r: dict) -> dict:
    actuel = charge()
    # Un changement de theme repeint les couleurs AVANT la fusion, sinon
    # l'ancien accent survivrait au nouveau theme.
    if r.get("theme") and r["theme"] != actuel.get("theme"):
        actuel = applique_theme(actuel, r["theme"])
    fusionne = _fusion(actuel, r)
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(fusionne, indent=1), encoding="utf-8")
    return fusionne


# Valeurs de FORME par defaut. Un theme qui n'en redefinit aucune retombe
# exactement sur l'apparence d'origine — c'est la regle du projet, et elle
# est ici tenue par construction : ces valeurs SONT l'apparence d'origine.
#
# Elles ne sont pas decoratives. `coin` change la geometrie des panneaux,
# `equerre` fait disparaitre les marques d'angle, `pad` et `gap` changent
# la densite, `titre_espace` et `titre_police` changent la typographie.
# C'est ce qui permet a un theme de changer la FORME, pas seulement la
# couleur.
FORME = {
    "coin": "15px",          # taille du biseau d'angle des panneaux
    "rayon": "0px",          # arrondi (exclusif du biseau, en pratique)
    "equerre": "1",          # opacite des equerres d'angle ; 0 les enleve
    "pad": "14px 15px 11px",
    "gap": "9px",
    "bord": "#0e2b34",
    "bord_fort": "#1b6b7d",
    "pan_fond": "rgba(5,9,14,.66)",
    "pan_ombre": "inset 0 0 38px rgba(34,211,238,.05),0 0 22px rgba(0,0,0,.45)",
    "txt": "#94a3b8",
    "txt_fort": "#cbe9f2",
    "txt_doux": "#8fb3c1",
    "txt_mi": "#6f93a3",
    "txt_faible": "#3f6b78",
    "titre_police": "ui-monospace,Consolas,monospace",
    "titre_espace": ".22em",
    "titre_casse": "none",
    "corps_police": "ui-sans-serif,Segoe UI,system-ui",
    "champ_fond": "#0a1620",
}


def forme(cle: str) -> dict:
    """La forme d'un theme : ses valeurs par-dessus les valeurs de base."""
    t = THEMES.get(cle) or {}
    return {**FORME, **(t.get("forme") or {})}


def variables(r: dict) -> str:
    """Les variables CSS : changer une valeur ici la propage partout.

    Couleurs ET geometrie. Les huit teintes de texte et de bordure qui
    etaient ecrites en dur a 93 endroits passent par ici : sans cela, un
    theme clair restait impossible, et chaque theme sombre devait
    reecrire les memes regles.
    """
    d = {"normale": ("1", "14px"), "compacte": (".82", "13px"),
         "large": ("1.18", "15px")}
    ech, police = d.get(r.get("densite", "normale"), d["normale"])
    cle = r.get("theme", "carruos")
    theme = THEMES.get(cle, THEMES["carruos"])
    f = forme(cle)
    return (f":root{{--acc:{r['accent']};--marque:{r['marque']};"
            f"--fond:{r['fond']};--pos:{r['pos']};--neg:{r['neg']};"
            f"--holo:{theme['holo']};"
            f"--ech:{ech};--police:{police};"
            f"--coin:{f['coin']};--rayon:{f['rayon']};"
            f"--equerre:{f['equerre']};--pad:{f['pad']};--gap:{f['gap']};"
            f"--bord:{f['bord']};--bord-fort:{f['bord_fort']};"
            f"--pan-fond:{f['pan_fond']};--pan-ombre:{f['pan_ombre']};"
            f"--txt:{f['txt']};--txt-fort:{f['txt_fort']};"
            f"--txt-doux:{f['txt_doux']};--txt-mi:{f['txt_mi']};"
            f"--txt-faible:{f['txt_faible']};"
            f"--titre-police:{f['titre_police']};"
            f"--titre-espace:{f['titre_espace']};"
            f"--titre-casse:{f['titre_casse']};"
            f"--corps-police:{f['corps_police']};"
            f"--champ-fond:{f['champ_fond']}}}")


def classes(r: dict) -> str:
    """Classes posees sur <body> : chaque option desactivee devient une
    regle CSS qui masque ou neutralise l'element concerne."""
    cl = []
    for k, v in r.get("effets", {}).items():
        if not v:
            cl.append(f"sans-{k}")
    for k, v in r.get("modules", {}).items():
        if not v:
            cl.append(f"off-{k}")
    for k, v in r.get("indics", {}).items():
        if not v:
            cl.append(f"noind-{k}")
    if not r.get("grille", True):
        cl.append("sans-grille")
    cl.append("theme-" + r.get("theme", "carruos"))
    return " ".join(cl)


# --- CSS des options -------------------------------------------------
# Chaque classe posee sur <body> neutralise un element. Tout est en CSS :
# basculer une option n'exige aucun rechargement.
CSS_OPTIONS = """
.sans-scan .holo::after{display:none}
.sans-halo .holo::before{display:none}
.sans-bloom [filter]{filter:none!important}
.sans-bloom .f-halo{display:none}
.sans-chroma .spectre{display:none}
.sans-rotation .rot1,.sans-rotation .rot2,.sans-rotation .rot3{animation:none}
.sans-vacille .cerf-fil{animation:none;opacity:1}
.sans-cone .cone,.sans-cone .socle{display:none}
.off-cadrans .cadrans,.off-rails .rails,.off-bandeau .bandeau,
.off-hologramme .noyau{display:none}
.off-momentum [data-mod=momentum],.off-ecarts [data-mod=ecarts],
.off-perfrel [data-mod=perfrel],.off-signal [data-mod=signal],
.off-horloge [data-mod=horloge],.off-resultats [data-mod=resultats],
.off-actus [data-mod=actus]{display:none}
/* --- fond de page et animations des panneaux --- */
.sans-fond .fond-cerf{display:none}
.sans-sol .fond-sol{display:none}
.sans-rayon .fond-ray{display:none}
.sans-halo .fond-lueur{display:none}
.sans-scan .fond-scan{display:none}
.sans-trait .trait{display:none}
.sans-entree .pan{animation:none}
.sans-verre .pan{background:#05080d;box-shadow:none}
.sans-verre .hud{background:#05080d}
.sans-vacille .f-m{animation:none}
.sans-rotation .fond-anneaux{display:none}
.sans-cone .fond-cone,.sans-cone .fond-socle{display:none}
.sans-chroma .f-c1,.sans-chroma .f-c2{display:none}
"""

# --- CSS des themes ---------------------------------------------------
#
# Chaque theme se pose par une classe sur <body> et ne fait qu'OUTREPASSER
# les regles de base : rien n'est retire, donc un theme inconnu retombe
# proprement sur l'apparence d'origine.
#
# Contraintes respectees : aucune animation de mise en page (transform et
# opacity seulement), aucun backdrop-filter, aucun mode de fusion sur le
# fond. Ce sont les trois choses qui font sauter la page.
CSS_THEMES = """
/* ===================================================================
   LES SIX THEMES DE FORME
   Leur geometrie, leur densite et leur typographie viennent des
   variables (voir FORME). Il ne reste ici que ce qu'une variable ne
   peut pas porter : le fond de page et les elements de l'hologramme.
   =================================================================== */

/* --------- MONOLITHE : pas une diagonale, pas un ornement --------- */
body.theme-monolithe{background:
 radial-gradient(ellipse 140% 90% at 50% 120%,rgba(216,210,196,.05),
 transparent 66%),var(--fond)}
body.theme-monolithe .hud{background:rgba(17,17,18,.8);
 border-color:var(--bord);clip-path:none;border-radius:0}
body.theme-monolithe .bar{border-color:var(--bord)}
body.theme-monolithe .pan h2::after{background:var(--bord)}
body.theme-monolithe .majp,body.theme-monolithe #tiroir{
 background:rgba(12,12,13,.99);border-color:var(--bord)}
body.theme-monolithe .maj{border-radius:0;box-shadow:none}
body.theme-monolithe .raf{clip-path:none;background:#1a1a1b;
 border-color:#3a3937}
body.theme-monolithe button{clip-path:none;background:#1a1a1b;
 border-color:#3a3937;border-radius:0}
body.theme-monolithe .lig{clip-path:none;border-radius:0}
body.theme-monolithe .fond-cone,body.theme-monolithe .fond-socle,
body.theme-monolithe .fond-scan,body.theme-monolithe .fond-rayon{display:none}
body.theme-monolithe .fond-cerf{opacity:.1}
body.theme-monolithe .fond-lueur{background:radial-gradient(circle,
 rgba(216,210,196,.05) 0%,transparent 60%)}

/* --------- ORBITE : tout devient courbe --------------------------- */
body.theme-orbite{background:
 radial-gradient(ellipse 120% 85% at 50% 118%,rgba(127,227,255,.12),
 transparent 64%),var(--fond)}
body.theme-orbite .hud{background:rgba(6,15,26,.72);border-color:var(--bord);
 clip-path:none;border-radius:19px}
body.theme-orbite .bar{border-color:var(--bord)}
body.theme-orbite .pan h2::after{background:linear-gradient(90deg,
 rgba(127,227,255,.45),transparent)}
body.theme-orbite .majp,body.theme-orbite #tiroir{
 background:rgba(4,11,20,.98);border-color:var(--bord);border-radius:19px}
body.theme-orbite .raf,body.theme-orbite button{clip-path:none;
 border-radius:999px;background:#0a2033;border-color:#2b6f93;
 padding-left:16px;padding-right:16px}
body.theme-orbite input{border-radius:999px;padding-left:15px}
body.theme-orbite .lig{clip-path:none;border-radius:15px}
body.theme-orbite .rail{background:#081726;border-radius:999px}
body.theme-orbite .fond-cone{background:linear-gradient(0deg,
 rgba(127,227,255,.2),rgba(127,227,255,0) 82%)}
body.theme-orbite .fond-socle{background:radial-gradient(ellipse at center,
 rgba(210,245,255,.8) 0%,rgba(127,227,255,.3) 38%,transparent 70%)}
body.theme-orbite .fond-scan{display:none}
body.theme-orbite .f-c1,body.theme-orbite .f-c2{opacity:.75}

/* --------- NOCTURNE : or, serif, feutre --------------------------- */
body.theme-nocturne{background:
 radial-gradient(ellipse 130% 88% at 50% 120%,rgba(217,177,102,.1),
 transparent 62%),var(--fond)}
body.theme-nocturne .hud{background:rgba(20,15,9,.82);
 border-color:var(--bord);clip-path:none;border-radius:8px}
body.theme-nocturne .bar{border-color:var(--bord)}
body.theme-nocturne .bar h1{font-family:Georgia,'Times New Roman',serif;
 letter-spacing:.3em}
body.theme-nocturne .pan h2::after{background:linear-gradient(90deg,
 rgba(217,177,102,.4),transparent)}
body.theme-nocturne .majp,body.theme-nocturne #tiroir{
 background:rgba(14,10,6,.99);border-color:var(--bord);border-radius:8px}
body.theme-nocturne .raf,body.theme-nocturne button{clip-path:none;
 border-radius:5px;background:#241a0f;border-color:#4e3c22}
body.theme-nocturne input{border-radius:5px}
body.theme-nocturne .lig{clip-path:none;border-radius:6px}
body.theme-nocturne .rail{background:#171109;border-radius:3px}
body.theme-nocturne .fond-cone{background:linear-gradient(0deg,
 rgba(217,177,102,.18),rgba(217,177,102,0) 80%)}
body.theme-nocturne .fond-socle{background:radial-gradient(ellipse at center,
 rgba(245,225,180,.7) 0%,rgba(217,177,102,.25) 38%,transparent 70%)}
body.theme-nocturne .fond-scan{display:none}
body.theme-nocturne .fond-cerf{opacity:.6}

/* --------- CRISTAL : biseau sur les quatre angles ----------------- */
body.theme-cristal{background:
 radial-gradient(ellipse 125% 85% at 50% 120%,rgba(169,180,255,.13),
 transparent 62%),var(--fond)}
/* Le biseau des quatre coins ne peut pas venir d'une variable : la
   variable donne la TAILLE, le polygone donne la FORME. */
body.theme-cristal .pan,body.theme-cristal .hud,body.theme-cristal .lig{
 clip-path:polygon(var(--coin) 0,calc(100% - var(--coin)) 0,
 100% var(--coin),100% calc(100% - var(--coin)),
 calc(100% - var(--coin)) 100%,var(--coin) 100%,
 0 calc(100% - var(--coin)),0 var(--coin))}
body.theme-cristal .hud{background:rgba(11,11,22,.8);border-color:var(--bord)}
body.theme-cristal .bar{border-color:var(--bord)}
body.theme-cristal .pan h2::after{background:linear-gradient(90deg,
 rgba(169,180,255,.5),transparent)}
body.theme-cristal .majp,body.theme-cristal #tiroir{
 background:rgba(8,8,16,.98);border-color:var(--bord)}
body.theme-cristal .raf,body.theme-cristal button{background:#15152b;
 border-color:#4a4f96;
 clip-path:polygon(8px 0,calc(100% - 8px) 0,100% 8px,
 100% calc(100% - 8px),calc(100% - 8px) 100%,8px 100%,
 0 calc(100% - 8px),0 8px)}
body.theme-cristal .rail{background:#0e0e1c}
body.theme-cristal .fond-cone{background:linear-gradient(0deg,
 rgba(169,180,255,.24),rgba(169,180,255,0) 82%)}
body.theme-cristal .fond-socle{background:radial-gradient(ellipse at center,
 rgba(230,233,255,.85) 0%,rgba(169,180,255,.3) 38%,transparent 70%)}
body.theme-cristal .fond-scan{background:repeating-linear-gradient(180deg,
 transparent 0 3px,rgba(169,180,255,.05) 3px 4px)}

/* --------- TERMINAL : densite maximale, zero decor ---------------- */
body.theme-terminal{background:var(--fond)}
body.theme-terminal .hud{background:rgba(2,8,4,.92);border-color:var(--bord);
 clip-path:none;border-radius:0}
body.theme-terminal .bar{border-color:var(--bord)}
body.theme-terminal .bar h1{letter-spacing:.22em;font-weight:500}
body.theme-terminal .pan h2{margin-bottom:6px}
body.theme-terminal .pan h2::after{background:var(--bord)}
body.theme-terminal .majp,body.theme-terminal #tiroir{
 background:rgba(1,5,2,.99);border-color:var(--bord)}
body.theme-terminal .maj{border-radius:0;box-shadow:none}
body.theme-terminal .raf,body.theme-terminal button{clip-path:none;
 border-radius:0;background:#04160a;border-color:#1f6b3d;padding:4px 9px}
body.theme-terminal .lig{clip-path:none;border-radius:0;padding:7px 9px;
 margin-bottom:5px}
body.theme-terminal .rail{background:#04160a}
/* Aucun hologramme : ce theme montre des chiffres, pas un decor. */
body.theme-terminal .fond-cone,body.theme-terminal .fond-socle,
body.theme-terminal .fond-cerf,body.theme-terminal .fond-lueur,
body.theme-terminal .fond-rayon,body.theme-terminal .fond-sol{display:none}
body.theme-terminal .fond-scan{background:repeating-linear-gradient(180deg,
 transparent 0 2px,rgba(74,222,128,.035) 2px 3px)}

/* --------- PAPIER : le seul theme clair -------------------------- */
body.theme-papier{background:
 radial-gradient(ellipse 140% 90% at 50% 120%,rgba(15,110,122,.05),
 transparent 66%),var(--fond)}
body.theme-papier #splash{background:var(--fond)}
body.theme-papier .hud{background:rgba(255,253,248,.9);
 border-color:var(--bord);clip-path:none;border-radius:3px}
body.theme-papier .bar{border-color:var(--bord)}
body.theme-papier .bar h1{color:#3d2f18}
body.theme-papier .pan h2::after{background:var(--bord)}
body.theme-papier .majp,body.theme-papier #tiroir{
 background:rgba(255,253,248,.99);border-color:var(--bord)}
body.theme-papier .majr{color:#171512}
body.theme-papier .maj{background:rgba(255,253,248,.95);
 border-color:var(--bord-fort);box-shadow:0 2px 8px rgba(60,50,35,.18)}
body.theme-papier .raf,body.theme-papier button{clip-path:none;
 border-radius:3px;background:#eae5da;border-color:#b3aa99;color:#1f4d54}
body.theme-papier button:hover,body.theme-papier .raf:hover{
 background:#ded8ca}
body.theme-papier input{background:var(--champ-fond);
 border-color:var(--bord-fort);color:#171512}
body.theme-papier th{color:#6a6459}
body.theme-papier td{border-color:var(--bord);color:#2b2822}
body.theme-papier .lig{clip-path:none;border-radius:3px;
 background:rgba(255,253,248,.7)}
body.theme-papier .rail{background:#e7e2d6}
body.theme-papier .rail .t{background:#cdc6b6}
body.theme-papier .trajet{background:rgba(15,110,122,.05)}
body.theme-papier .etat{background:rgba(15,110,122,.05)}
body.theme-papier .chiffres .c{background:rgba(15,110,122,.04)}
body.theme-papier .sortie.gr{background:rgba(15,110,122,.04)}
/* Sur fond clair, un hologramme lumineux ne se voit pas : on l'eteint
   plutot que de laisser des taches pales sans signification. */
body.theme-papier .fond-cone,body.theme-papier .fond-socle,
body.theme-papier .fond-lueur,body.theme-papier .fond-scan,
body.theme-papier .fond-rayon,body.theme-papier .fond-sol{display:none}
body.theme-papier .fond-cerf{opacity:.07;filter:invert(1)}

/* ================= JARVIS =========================================
   Projection bleu clair et or. Panneaux plus translucides, traits fins,
   beaucoup de lumiere : on est dans un atelier eclaire, pas dans une
   cave. ============================================================ */
body.theme-jarvis{background:
 radial-gradient(ellipse 120% 80% at 50% 118%,rgba(125,211,252,.13),
 transparent 62%),
 radial-gradient(ellipse 90% 60% at 50% -10%,rgba(255,196,107,.06),
 transparent 60%),var(--fond)}
body.theme-jarvis .pan{background:rgba(6,17,30,.52);border-color:#14405c;
 box-shadow:inset 0 0 46px rgba(125,211,252,.09),0 0 26px rgba(0,0,0,.5)}
body.theme-jarvis .pan::before,body.theme-jarvis .pan::after{
 border-color:rgba(125,211,252,.55)}
body.theme-jarvis .hud{background:rgba(5,15,27,.55);border-color:#14405c}
body.theme-jarvis .bar{border-color:#14405c}
body.theme-jarvis .pan h2{color:#8fd4f0}
body.theme-jarvis .pan h2::after{background:linear-gradient(90deg,
 rgba(125,211,252,.5),transparent)}
body.theme-jarvis .majp,body.theme-jarvis #tiroir{
 background:rgba(4,13,24,.97);border-color:#14405c}
body.theme-jarvis .majr{color:#dff1ff}
body.theme-jarvis input{background:#07172a;border-color:#14405c;color:#dff1ff}
body.theme-jarvis button{background:#0a2338;border-color:#2b7fa8}
body.theme-jarvis th{color:#5f9dbb}
body.theme-jarvis td{border-color:#0f2f45}
body.theme-jarvis .rail{background:#07172a}
body.theme-jarvis .fond-cone{background:linear-gradient(0deg,
 rgba(125,211,252,.24),rgba(125,211,252,0) 84%)}
body.theme-jarvis .fond-socle{background:radial-gradient(ellipse at center,
 rgba(205,240,255,.82) 0%,rgba(125,211,252,.3) 40%,transparent 70%)}
body.theme-jarvis .fond-lueur{background:radial-gradient(circle,
 rgba(125,211,252,.14) 0%,rgba(255,196,107,.05) 42%,transparent 68%)}
body.theme-jarvis .fond-scan{background:repeating-linear-gradient(180deg,
 transparent 0 3px,rgba(125,211,252,.045) 3px 4px)}
body.theme-jarvis .fond-cerf{opacity:.96}
body.theme-jarvis .f-c1,body.theme-jarvis .f-c2{opacity:.5}

/* ================= ULTRON =========================================
   Presque noir, neons violet et rouge, contraste dur. Les panneaux sont
   opaques : la projection ne les traverse plus, elle les cerne. ==== */
body.theme-ultron{background:
 radial-gradient(ellipse 130% 85% at 50% 122%,rgba(176,108,255,.14),
 transparent 60%),
 radial-gradient(ellipse 70% 50% at 50% 8%,rgba(255,45,85,.07),
 transparent 62%),var(--fond)}
body.theme-ultron .pan{background:rgba(9,5,16,.88);border-color:#3a1b5c;
 box-shadow:inset 0 0 40px rgba(176,108,255,.1),
 0 0 24px rgba(0,0,0,.72),0 0 1px rgba(176,108,255,.5)}
body.theme-ultron .pan::before,body.theme-ultron .pan::after{
 border-color:rgba(255,45,85,.7)}
body.theme-ultron .hud{background:rgba(8,4,14,.9);border-color:#3a1b5c}
body.theme-ultron .bar{border-color:#3a1b5c}
body.theme-ultron .bar h1{color:#ff2d55}
body.theme-ultron .pan h2{color:#c79bff}
body.theme-ultron .pan h2::after{background:linear-gradient(90deg,
 rgba(255,45,85,.6),transparent)}
body.theme-ultron .majp,body.theme-ultron #tiroir{
 background:rgba(7,3,12,.98);border-color:#3a1b5c}
body.theme-ultron .majr{color:#e7d7ff}
body.theme-ultron input{background:#140a22;border-color:#3a1b5c;color:#e7d7ff}
body.theme-ultron button{background:#1b0d2e;border-color:#7b3fd4}
body.theme-ultron th{color:#9a6fc4}
body.theme-ultron td{border-color:#2a1440}
body.theme-ultron .rail{background:#140a22}
body.theme-ultron .fond-cone{background:linear-gradient(0deg,
 rgba(176,108,255,.26),rgba(255,45,85,.05) 40%,rgba(176,108,255,0) 84%)}
body.theme-ultron .fond-socle{background:radial-gradient(ellipse at center,
 rgba(255,45,85,.6) 0%,rgba(176,108,255,.3) 38%,transparent 70%)}
body.theme-ultron .fond-lueur{background:radial-gradient(circle,
 rgba(176,108,255,.13) 0%,rgba(255,45,85,.05) 40%,transparent 68%)}
body.theme-ultron .fond-scan{background:repeating-linear-gradient(180deg,
 transparent 0 3px,rgba(176,108,255,.05) 3px 4px)}
body.theme-ultron .fond-cerf{opacity:.88}
body.theme-ultron .f-c1{opacity:.7}
body.theme-ultron .f-c2{opacity:.34}
body.theme-ultron .fond-sol{opacity:.55}

/* ================= REACTEUR =======================================
   Tableau de bord d'instruments. Bleu electrique franc sur noir, traits
   fins et lumineux, texte presque blanc. La densite vient d'une trame
   de graduation posee sur les panneaux : une image de fond STATIQUE,
   donc gratuite au repeint, jamais une animation. ================== */
body.theme-reacteur{background:
 radial-gradient(ellipse 130% 78% at 50% 120%,rgba(0,180,255,.16),
 transparent 58%),
 radial-gradient(ellipse 60% 40% at 50% 0%,rgba(0,180,255,.07),
 transparent 62%),var(--fond)}
body.theme-reacteur .pan{background:rgba(2,10,20,.78);border-color:#0e6d9e;
 background-image:repeating-linear-gradient(90deg,
  rgba(0,180,255,.17) 0 1px,transparent 1px 17px),
 repeating-linear-gradient(0deg,
  rgba(0,180,255,.13) 0 1px,transparent 1px 17px);
 box-shadow:inset 0 0 0 1px rgba(0,180,255,.09),
 inset 0 0 34px rgba(0,180,255,.07),0 0 20px rgba(0,0,0,.6)}
body.theme-reacteur .pan::before,body.theme-reacteur .pan::after{
 border-color:rgba(0,180,255,.9)}
body.theme-reacteur .hud{background:rgba(2,9,17,.78);border-color:#0e6d9e;
 box-shadow:inset 0 0 0 1px rgba(0,180,255,.1)}
body.theme-reacteur .bar{border-color:#0e6d9e}
body.theme-reacteur .bar h1{color:#dff3ff}
body.theme-reacteur .pan h2{color:#7fd8ff;letter-spacing:.3em}
body.theme-reacteur .pan h2::after{background:linear-gradient(90deg,
 rgba(0,180,255,.85),transparent)}
body.theme-reacteur .majp,body.theme-reacteur #tiroir{
 background:rgba(1,7,14,.98);border-color:#0a4f77}
body.theme-reacteur .majr{color:#e8f7ff}
body.theme-reacteur input{background:#031320;border-color:#0a4f77;
 color:#e8f7ff}
body.theme-reacteur button{background:#04283d;border-color:#0d7fb8}
body.theme-reacteur th{color:#4aa8d6}
body.theme-reacteur td{border-color:#083247;color:#d5eeff}
body.theme-reacteur .rail{background:#031320}
body.theme-reacteur .rail .t{background:#062436}
/* Hologramme : anneaux et cone plus francs, halo plus serre. */
body.theme-reacteur .fond-cone{background:linear-gradient(0deg,
 rgba(0,180,255,.3),rgba(0,180,255,0) 80%)}
body.theme-reacteur .fond-socle{background:radial-gradient(ellipse at center,
 rgba(190,240,255,.95) 0%,rgba(0,180,255,.4) 34%,transparent 68%)}
body.theme-reacteur .fond-lueur{background:radial-gradient(circle,
 rgba(0,180,255,.18) 0%,rgba(0,180,255,.05) 38%,transparent 64%)}
body.theme-reacteur .fond-scan{background:repeating-linear-gradient(180deg,
 transparent 0 3px,rgba(0,180,255,.06) 3px 4px)}
/* Les anneaux passent au premier plan : c'est la signature du style.
   Traits plus epais, opacite pleine, et un second jeu de graduations
   dessine par une simple trame conique — statique, donc gratuite. */
/* Les anneaux entrent ENTIEREMENT dans l'ecran : c'est le reacteur du
   modele, un disque complet au centre, et non plus un arc qui sort du
   cadre par le haut et par le bas. On change une taille, pas une
   animation : rien ne se recalcule pendant la rotation. */
body.theme-reacteur .fond-anneaux{opacity:1;
 width:min(94vh,94vw);height:min(94vh,94vw)}
body.theme-reacteur .fond-anneaux circle{stroke-width:2.1}
body.theme-reacteur .fond-cerf{opacity:.78}
body.theme-reacteur .f-c1,body.theme-reacteur .f-c2{opacity:.3}
/* Titre et intitules francs, comme sur un vrai tableau de bord. */
body.theme-reacteur #splash h1,body.theme-reacteur .hud-c h1,
body.theme-reacteur .hud-id .tk{color:#dff3ff}
body.theme-reacteur .rail .n{color:#4aa8d6}
body.theme-reacteur .rail .v{color:#eaf8ff}
body.theme-reacteur .bandeau{border-color:#0a4f77}

/* Selecteur de theme dans le tiroir */
.themes{display:flex;flex-direction:column;gap:6px}
.themes button{text-align:left;padding:9px 11px;background:#121a24;
 border:1px solid #223044;color:var(--txt);border-radius:7px;cursor:pointer;
 font-size:12px;line-height:1.45}
.themes button .n{display:block;font:500 11px ui-monospace,monospace;
 letter-spacing:.16em;color:#cbd5e1}
.themes button .r{display:block;font-size:10.5px;color:var(--txt-mi);margin-top:2px}
.themes button.sel{border-color:var(--acc)}
.themes button.sel .n{color:var(--acc)}
.themes button i{display:inline-block;width:9px;height:9px;border-radius:50%;
 margin-right:7px;vertical-align:baseline}
"""


TIROIR_CSS = """
#roue{position:fixed;top:12px;right:12px;z-index:60;width:38px;height:38px;
 border-radius:50%;background:#0d1219;border:1px solid var(--acc);color:var(--acc);
 cursor:pointer;font-size:17px;line-height:36px;text-align:center;padding:0}
#roue:hover{background:#132a2f}
#tiroir{position:fixed;top:0;right:0;bottom:0;width:330px;z-index:59;
 background:#080b10;border-left:1px solid #1a2330;padding:18px;overflow-y:auto;
 transform:translateX(102%);transition:transform .28s cubic-bezier(.3,0,.2,1)}
#tiroir.ouvert{transform:none}
#tiroir h3{font:500 10px ui-monospace,monospace;letter-spacing:.2em;color:#475a72;
 margin:20px 0 10px}
#tiroir h3:first-child{margin-top:34px}
.pal{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}
.pal button{height:30px;border-radius:7px;border:1px solid #223044;cursor:pointer;padding:0}
.pal button.sel{border-color:#fff;border-width:2px}
.opt{display:flex;justify-content:space-between;align-items:center;
 font-size:12.5px;color:var(--txt);padding:5px 0;cursor:pointer}
.sw{width:34px;height:18px;border-radius:10px;background:#1c2635;position:relative;
 flex:none;transition:.18s}
.sw::after{content:"";position:absolute;top:2px;left:2px;width:14px;height:14px;
 border-radius:50%;background:#5b6d85;transition:.18s}
.opt.on .sw{background:var(--acc)}
.opt.on .sw::after{left:18px;background:#05080d}
.dens{display:flex;gap:6px}
.dens button{flex:1;background:#121a24;border:1px solid #223044;color:var(--txt);
 border-radius:7px;padding:7px;font-size:11.5px;cursor:pointer}
.dens button.sel{border-color:var(--acc);color:var(--acc)}
#tiroir .pied{margin-top:22px;padding-top:12px;border-top:1px solid #1a2330;
 font-size:11px;color:#3f5168;line-height:1.8}
#tiroir .raz{width:100%;margin-top:10px;background:#121a24;border:1px solid #223044;
 color:var(--txt);border-radius:7px;padding:9px;font-size:12px;cursor:pointer}
"""


def tiroir_html(r: dict) -> str:
    """Le panneau lateral. Chaque interrupteur agit en direct puis persiste."""
    def sect(titre, items, groupe):
        etat = r.get(groupe, {})
        li = "".join(
            f'<div class="opt {"on" if etat.get(k) else ""}" data-g="{groupe}" '
            f'data-k="{k}"><span>{lab}</span><span class="sw"></span></div>'
            for k, lab in items)
        return f"<h3>{titre}</h3>{li}"

    pal = "".join(
        f'<button data-col="{c}" style="background:{c}" title="{n}"'
        + (' class="sel"' if c == r["accent"] else '')
        + '></button>'
        for n, c in PALETTES)
    dens = "".join(
        f'<button data-dens="{d}"'
        + (' class="sel"' if r.get("densite") == d else '')
        + f'>{lab}</button>'
        for d, lab in
        (("compacte", "Compacte"), ("normale", "Normale"), ("large", "Large")))

    themes = "".join(
        f'<button data-theme="{k}"'
        + (' class="sel"' if r.get("theme", "carruos") == k else '')
        + f'><span class="n"><i style="background:{t["accent"]}"></i>'
          f'{t["nom"]}</span><span class="r">{t["resume"]}</span></button>'
        for k, t in THEMES.items())

    return (
        '<button id="roue" title="Reglages">&#9881;</button>'
        '<div id="tiroir">'
        '<h3>THEME</h3>'
        f'<div class="themes">{themes}</div>'
        '<h3>COULEUR D\'ACCENT</h3>'
        f'<div class="pal">{pal}</div>'
        '<h3>DENSITE</h3>'
        f'<div class="dens">{dens}</div>'
        + sect("EFFETS VISUELS", LIB_EFFETS, "effets")
        + sect("INDICATEURS", LIB_INDICS, "indics")
        + sect("MODULES", LIB_MODULES, "modules")
        + '<div class="pied">Les reglages sont enregistres et repris au '
          'prochain lancement.<button class="raz" id="raz">Tout remettre '
          'par defaut</button></div></div>')


def tiroir_js() -> str:
    """Le script du tiroir, avec la table des themes injectee.

    Elle doit exister cote navigateur pour appliquer un theme sans
    rechargement ; la recopier a la main serait la garantie qu'un jour
    les deux divergent.
    """
    return TIROIR_JS.replace("__THEMES__", json.dumps(
        {k: {c: t[c] for c in ("accent", "marque", "fond", "pos", "neg",
                               "holo")}
         for k, t in THEMES.items()}))


TIROIR_JS = """
(function(){
 var roue=document.getElementById('roue'), tir=document.getElementById('tiroir');
 if(!roue)return;
 roue.onclick=function(){tir.classList.toggle('ouvert');};
 function envoie(o){
  fetch('/api/reglages',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify(o)}).catch(function(){});
 }
 // Couleur : application immediate par variable CSS, puis persistance.
 document.querySelectorAll('.pal button').forEach(function(b){
  b.onclick=function(){
   document.querySelectorAll('.pal button').forEach(function(x){
    x.classList.remove('sel');});
   b.classList.add('sel');
   document.documentElement.style.setProperty('--acc',b.dataset.col);
   envoie({accent:b.dataset.col});
  };});
 document.querySelectorAll('.dens button').forEach(function(b){
  b.onclick=function(){
   document.querySelectorAll('.dens button').forEach(function(x){
    x.classList.remove('sel');});
   b.classList.add('sel');
   var m={compacte:['.82','13px'],normale:['1','14px'],large:['1.18','15px']};
   var v=m[b.dataset.dens];
   document.documentElement.style.setProperty('--ech',v[0]);
   document.documentElement.style.setProperty('--police',v[1]);
   envoie({densite:b.dataset.dens});
  };});
 // Theme : les couleurs s'appliquent en direct par variables CSS, et la
 // classe sur <body> bascule les regles propres au theme. Aucun
 // rechargement ; le serveur enregistre pour le prochain lancement.
 var THEMES_JS = __THEMES__;
 document.querySelectorAll('.themes button').forEach(function(b){
  b.onclick=function(){
   var cle=b.dataset.theme, t=THEMES_JS[cle];
   if(!t) return;
   document.querySelectorAll('.themes button').forEach(function(x){
    x.classList.remove('sel');});
   b.classList.add('sel');
   Object.keys(THEMES_JS).forEach(function(k){
    document.body.classList.remove('theme-'+k);});
   document.body.classList.add('theme-'+cle);
   var st=document.documentElement.style;
   st.setProperty('--acc',t.accent); st.setProperty('--marque',t.marque);
   st.setProperty('--fond',t.fond);  st.setProperty('--pos',t.pos);
   st.setProperty('--neg',t.neg);    st.setProperty('--holo',t.holo);
   // La pastille de la palette d'accent suit le nouveau theme.
   document.querySelectorAll('.pal button').forEach(function(x){
    x.classList.toggle('sel', x.dataset.col===t.accent);});
   envoie({theme:cle});
  };});
 var prefixe={effets:'sans-',modules:'off-',indics:'noind-'};
 document.querySelectorAll('.opt').forEach(function(o){
  o.onclick=function(){
   var actif=!o.classList.contains('on');
   o.classList.toggle('on',actif);
   document.body.classList.toggle(prefixe[o.dataset.g]+o.dataset.k,!actif);
   if(o.dataset.g==='indics'&&window.CARRUOS_IND)
     window.CARRUOS_IND(o.dataset.k,actif);
   var p={}; p[o.dataset.g]={}; p[o.dataset.g][o.dataset.k]=actif;
   envoie(p);
  };});
 document.getElementById('raz').onclick=function(){
  fetch('/api/reglages?raz=1',{method:'POST',headers:{'Content-Type':'application/json'},
   body:'{}'}).then(function(){location.reload();});
 };
})();
"""
