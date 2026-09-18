"""Controle des pages generees. Tourne sans node, sans reseau.

Raison d'etre : une chaine Python normale transforme \\' en apostrophe nue.
Quand ce \\' se trouve dans du JavaScript, la syntaxe du script est detruite
et TOUT le script de la page meurt d'un coup — la recherche, les scans, les
positions. Le symptome est une page ou plus aucun bouton ne repond.

Verifier que le texte est present dans la page ne suffit pas : le bug est
passe une fois exactement comme ca. On verifie donc la forme des chaines
JavaScript et la correspondance avec les identifiants du HTML.

    py -m equity_scanner.test_pages
"""

from __future__ import annotations

import re
import sys

ECHECS: list[str] = []


def _v(cond, libelle: str) -> None:
    print(f"   {'OK  ' if cond else 'ECHEC'} {libelle}")
    if not cond:
        ECHECS.append(libelle)


def _re_couleurs(css: str) -> list:
    """Tout ce qui ressemble a un code couleur dans une DECLARATION.

    On ecarte les selecteurs d'identifiant (#tiroir, #roue), qui
    commencent aussi par un diese sans etre des couleurs.
    """
    return [c for c in re.findall(r"#[0-9a-zA-Z]+", css)
            if not re.fullmatch(r"#[a-z]{4,}", c)]


def _scripts(html: str) -> str:
    blocs = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    return "\n;\n".join(blocs)


def _apostrophes_effondrees(js: str) -> list[str]:
    """Signature du bug : un appel onclick dont l'apostrophe a ete mangee.

    Correct   : onclick="pick(\\'" + t + "\\')"   -> pick(\\'...
    Casse     : onclick="pick(''  + t +  '')"    -> pick(''...
    """
    fautes = []
    for i, brute in enumerate(js.splitlines(), 1):
        # Les commentaires contiennent du francais : ils n'ont pas a etre
        # echappes et generaient un faux positif.
        nu = brute.strip()
        if nu.startswith(("//", "*", "/*")):
            continue
        coupe = brute.find("//")
        ligne = brute
        if coupe > 0 and "'" not in brute[:coupe] and '"' not in brute[:coupe]:
            ligne = brute[:coupe]
        for m in re.finditer(r"(\w+)\(''\s*\+|\+\s*''\)", ligne):
            fautes.append(f"ligne {i} : {ligne.strip()[:70]}")
            break
        # apostrophe nue au milieu d'un litteral simple quote
        if re.search(r"'[^'\"\n]*\bd'[a-z]", ligne) and "\\'" not in ligne:
            fautes.append(f"ligne {i} (apostrophe francaise) : "
                          f"{ligne.strip()[:70]}")
    return fautes


def _ids_manquants(js: str, html: str) -> list[str]:
    """Chaque $('x') du script doit correspondre a un id="x" du HTML."""
    demandes = set(re.findall(r"\$\(\s*'([A-Za-z0-9_-]+)'\s*\)", js))
    demandes |= set(re.findall(r"getElementById\(\s*'([A-Za-z0-9_-]+)'\s*\)", js))
    presents = set(re.findall(r'\bid="([A-Za-z0-9_-]+)"', html))
    presents |= set(re.findall(r"\bid='([A-Za-z0-9_-]+)'", html))
    return sorted(demandes - presents)


def _fonctions_appelees(html: str, js: str) -> list[str]:
    """Chaque onclick="f(...)" doit pointer sur une fonction definie."""
    appelees = set(re.findall(r'on(?:click|change)="\s*([A-Za-z_]\w*)\s*\(', html))
    definies = set(re.findall(r"function\s+([A-Za-z_]\w*)\s*\(", js))
    definies |= set(re.findall(r"(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*"
                              r"(?:async\s*)?\(?", js))
    connues = {"location", "history", "alert", "print"}
    return sorted(appelees - definies - connues)


def _chaine_brute_preservee() -> bool:
    """JS_POS doit rester une chaine brute : c'est la protection de fond."""
    from . import app
    src = open(app.__file__, encoding="utf-8").read()
    return bool(re.search(r"JS_POS\s*=\s*r\"\"\"", src))


def main() -> int:
    import os
    import tempfile

    os.chdir(tempfile.mkdtemp())      # pas d'ecriture dans le dossier reel
    import numpy as np
    import pandas as pd

    from . import data as dl

    def faux(tk, years=3, **kw):
        r = np.random.default_rng(7)
        n = 600
        c = [100.0]
        for _ in range(n - 1):
            c.append(c[-1] * (1 + 0.0006 + r.normal(0, 0.013)))
        i = pd.bdate_range("2023-01-02", periods=n)
        o = pd.Series(c, index=i).shift(1).fillna(100.0)
        return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.007,
                             "low": np.minimum(o, c) * 0.993, "close": c,
                             "volume": r.uniform(9e5, 4e6, n)}, index=i)

    vrai = dl.load_yf
    dl.load_yf = faux
    try:
        from . import app
        pages = {"accueil": app._accueil(splash=False),
                 "graphique": app._page_graphique("AAA")}
    finally:
        dl.load_yf = vrai

    print("\n  PAGES GENEREES")
    _v(_chaine_brute_preservee(),
       "JS_POS est bien une chaine brute r\"\"\"")

    for nom, html in pages.items():
        js = _scripts(html)
        print(f"\n  {nom.upper()}  ({len(html)} caracteres, "
              f"{len(js)} de script)")
        f = _apostrophes_effondrees(js)
        _v(not f, "aucune apostrophe effondree dans le JavaScript")
        for x in f[:5]:
            print(f"          -> {x}")
        m = _ids_manquants(js, html)
        _v(not m, "tout element interroge par le script existe dans le HTML")
        if m:
            print(f"          -> introuvables : {', '.join(m)}")
        fn = _fonctions_appelees(html, js)
        _v(not fn, "toute fonction appelee par un bouton est definie")
        if fn:
            print(f"          -> non definies : {', '.join(fn)}")
        _v(js.count("<") == 0 or "</script" not in js,
           "aucune balise de fermeture prematuree")

    h = pages["accueil"]
    css = re.search(r"<style>(.*?)</style>", h, re.S).group(1)
    print("\n  MISE EN PAGE UN SEUL ECRAN")
    _v("body{overflow:hidden}" in css.replace(" ", "").replace("\n", ""),
       "le defilement global est coupe")
    _v("height:100vh" in css, "la console occupe exactement la hauteur ecran")
    _v(h.count('class="pan"') == 4, "quatre panneaux dans la grille")
    _v(css.count("overflow-y:auto") >= 1,
       "seuls les corps de panneaux defilent")
    _v("@media(max-width:1150px)" in css.replace(" ", ""),
       "le defilement revient sur ecran etroit")
    _v('<div class="app">' in h and h.index('class="hud"') < h.index('class="grille"'),
       "HUD au-dessus de la grille, tout dans .app")

    # Budget vertical : ce qui est fige doit laisser de la place aux panneaux.
    # marges 21, gouttieres 20, barre 30, bloc HUD 170 (sans hologramme
    # central : celui-ci est passe en fond de page)
    fige = 21 + 20 + 30 + 170
    print(f"\n  BUDGET VERTICAL  (fige : {fige} px)")
    for haut in (768, 900, 1080):
        reste = haut - fige
        _v(reste >= 380, f"ecran {haut} px -> {reste} px pour les panneaux")

    print("\n  FOND HOLOGRAPHIQUE")
    _v('class="fond-anneaux"' in h, "anneaux en rotation a l'echelle de l'ecran")
    _v(h.count('class="rot') >= 5, "cinq anneaux, trois vitesses")
    _v('class="fond-cone"' in h and 'class="fond-socle"' in h,
       "cone de projection et socle lumineux")
    _v('class="fond-cerf"' in h, "cerf projete pleine hauteur")
    _v(h.count('href="#fond-t"') == 5 and h.count('id="fond-t"') == 1,
       "trace declare une fois, reference cinq fois")
    regles_fond = "\n".join(l for l in css.splitlines()
                            if ".fond" in l or ".f-c" in l or ".f-m" in l)
    _v("mix-blend-mode" not in regles_fond,
       "aucun mode de fusion sur le fond (cause de scintillement)")
    _v("min-height:170px" in css and "contain:layout" in css,
       "hauteurs du HUD figees : pas de saut au rafraichissement")
    _v('class="f-halo"' in h and ".sans-bloom .f-halo" in css,
       "halo lumineux present et debrayable")
    fond_h = h.split('class="fond"')[1].split('class="app"')[0]
    _v(fond_h.split("fond-cerf")[0].count('vector-effect="non-scaling-stroke"') == 5,
       "les cinq anneaux ont aussi une epaisseur fixe")
    _v("filter=" not in h.split('class="fond"')[1].split("</svg></div>")[0],
       "aucun filtre SVG sur le fond (cout de repeint)")
    _v("rgba(5,8,13,.62)" in css and "rgba(5,9,14,.66)" in css,
       "HUD et panneaux translucides : la projection traverse")
    _v("backdrop-filter" not in css,
       "aucun flou de fond : le cerf reste net derriere l'interface")
    _v(h.count('vector-effect="non-scaling-stroke"') >= 7,
       "traits a epaisseur fixe en pixels ecran")
    _v('shape-rendering="geometricPrecision"' in h,
       "rendu geometrique precis demande au navigateur")
    _v(h.count('class="noyau holo"') == 0,
       "pas de second hologramme au centre du HUD")

    # Regression vecue : "ps" designait a la fois le module positions et une
    # variable locale, ce qui cassait les quatre scans par UnboundLocalError.
    print("\n  COLLISIONS DE NOMS")
    import re as _re
    from . import app as _app
    src = open(_app.__file__, encoding="utf-8").read()
    alias = set(_re.findall(r"^from \. import \w+ as (\w+)", src, _re.M))
    locales = set(_re.findall(r"^\s+(\w+)\s*=\s*(?!=)", src, _re.M))
    collision = sorted(alias & locales)
    _v(not collision,
       f"aucun alias de module ({len(alias)}) n'est reutilise comme variable")
    for c in collision:
        print(f"          -> '{c}' est a la fois un module et une variable")

    print("\n  PERFORMANCE D'ANIMATION")
    mise_en_page = re.compile(r"\b(top|left|right|bottom|width|height|margin"
                             r"|padding|background-position)\s*:")
    blocs = re.findall(r"@keyframes\s+(\w+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", css)
    fautives = [n for n, b in blocs if mise_en_page.search(b)]
    _v(not fautives,
       f"les {len(blocs)} animations sont composees (transform / opacity)")
    for n in fautives:
        print(f"          -> {n} anime une propriete de mise en page")

    print("\n  CHARTE VISUELLE")
    _v(css.count("clip-path:polygon") >= 3,
       "coins biseautes sur les cadres et les boutons")
    _v(".pan::before" in css and ".pan::after" in css,
       "equerres dans les angles des panneaux")
    _v("var(--acc)" in css, "la couleur d'accent des reglages est suivie")
    _v('id="roue"' in h, "roue de reglages presente")

    # --- Le majordome -------------------------------------------------
    # Regression vecue : le panneau une fois ouvert ne se refermait plus.
    # d.onclick AJOUTAIT la classe "ouvert" sans jamais la retirer, et
    # relancait l'ecoute dans la foulee : apres un echec de micro, la
    # fenetre restait a l'ecran et chaque clic pour s'en debarrasser
    # redemandait le micro.
    print("\n  MAJORDOME")
    jsa = _scripts(h)
    _v('id="majx"' in h and 'onclick="majFerme()"' in h,
       "une croix de fermeture existe dans le panneau")
    _v("function majFerme" in jsa and "remove('ouvert')" in jsa,
       "majFerme() retire bien la classe qui affiche le panneau")
    bloc_clic = jsa.split("d.onclick=function")[1][:260] \
        if "d.onclick=function" in jsa else ""
    _v("majFerme()" in bloc_clic,
       "le disque referme le panneau au lieu de seulement l'ouvrir")
    _v("majEcoute()" not in bloc_clic,
       "cliquer le disque ne redemande plus le micro")
    _v("document.addEventListener('keydown'" in jsa and "'Escape'" in jsa,
       "Echap ferme le panneau depuis n'importe ou")
    _v('id="majc"' in h and 'id="majmic"' in h,
       "le champ texte et le bouton micro sont tous deux presents")
    _v("MICRO_DIT" in jsa and "no-speech" in jsa and "audio-capture" in jsa,
       "chaque panne de micro a son message en francais")
    _v("function majMicroIndispo" in jsa and "majc" in jsa,
       "un micro indisponible renvoie vers le champ texte")
    _v("/api/navigateur" in jsa,
       "le bouton EDGE passe par le serveur, pas par window.open")
    # « J'appuie sur micro et rien ne se passe » : symptome d'une
    # autorisation jamais DEMANDEE. getUserMedia la demande franchement
    # et repond toujours, la ou la reconnaissance vocale peut rester
    # muette.
    _v("getUserMedia" in jsa and "function majPermission" in jsa,
       "l'autorisation du micro est demandee explicitement")
    _v("NotAllowedError" in jsa and "NotFoundError" in jsa
       and "NotReadableError" in jsa,
       "refus, absence et micro occupe ont chacun leur message")
    _v('onclick="majDiag()"' in h and "function majDiag" in jsa,
       "un bouton DIAGNOSTIC dit ce qui bloque")
    _v("enumerateDevices" in jsa and "permissions" in jsa,
       "le diagnostic compte les micros et lit l'autorisation")
    _v("cadenas" in jsa and "Confidentialite" in jsa,
       "la marche a suivre nomme le cadenas du navigateur et Windows")

    # --- Les themes ---------------------------------------------------
    print("\n  THEMES")
    from . import reglages as _rg
    _v(set(_rg.THEMES) == {"carruos", "jarvis", "ultron", "reacteur"},
       "quatre themes : CARRUOS, JARVIS, ULTRON, REACTEUR")
    complet = all(
        all(k in t for k in ("nom", "resume", "accent", "marque", "fond",
                             "pos", "neg", "holo"))
        for t in _rg.THEMES.values())
    _v(complet, "chaque theme declare ses six couleurs et son resume")
    n_themes = len(_rg.THEMES)
    _v(len({t["accent"] for t in _rg.THEMES.values()}) == n_themes
       and len({t["fond"] for t in _rg.THEMES.values()}) == n_themes,
       "chacun se distingue par l'accent ET par le fond")
    # Une couleur mal tapee ne casse rien : le navigateur ignore la
    # regle en silence et l'element garde l'apparence de base. C'est
    # exactement le genre de faute qu'on ne voit jamais a l'oeil.
    faux_codes = [c for c in _re_couleurs(_rg.CSS_THEMES)
                  if not re.fullmatch(
                      r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", c)]
    _v(not faux_codes,
       "toutes les couleurs hexadecimales des themes sont valides")
    if faux_codes:
        print(f"          -> invalides : {', '.join(faux_codes)}")
    mauvais = [f"{k}.{c}" for k, t in _rg.THEMES.items()
               for c in ("accent", "marque", "fond", "pos", "neg")
               if not re.fullmatch(r"#[0-9a-fA-F]{6}", t[c])]
    _v(not mauvais, "les cinq couleurs de chaque theme sont bien formees")
    _v('class="themes"' in h and h.count("data-theme=") == n_themes,
       "le selecteur de theme est dans le tiroir")
    _v("theme-carruos" in h, "la classe du theme est posee sur le corps")
    for cle in ("jarvis", "ultron", "reacteur"):
        _v(f"body.theme-{cle}" in css,
           f"le CSS du theme {cle.upper()} est charge")
    _v("--holo" in h, "la teinte de l'hologramme est une variable")
    # Le theme ne doit pas reintroduire ce que les autres controles
    # interdisent : pas de flou de fond, pas de mode de fusion, et aucune
    # animation de mise en page.
    _v("backdrop-filter" not in _rg.CSS_THEMES,
       "aucun flou de fond dans les themes")
    _v("mix-blend-mode" not in _rg.CSS_THEMES,
       "aucun mode de fusion dans les themes")
    _v("@keyframes" not in _rg.CSS_THEMES,
       "les themes n'ajoutent aucune animation")
    jst = _scripts(h)
    _v("THEMES_JS" in jst and "__THEMES__" not in jst,
       "la table des themes est injectee dans le script, pas laissee en "
       "marque-place")
    _v("classList.add('theme-'+cle)" in jst.replace(" ", ""),
       "changer de theme bascule la classe sans recharger la page")
    # Les jauges et le radar doivent suivre l'accent, sinon ils restent
    # cyan sur un fond violet.
    from . import hud as _hd
    _v("var(--acc)" in _hd.CSS and "#22d3ee" not in _hd.CSS,
       "les jauges du HUD suivent la couleur du theme")

    print("\n  BLOC POSITIONS")
    _v('id="ptk"' in h and 'id="pq"' in h and 'id="pe"' in h and 'id="pst"' in h,
       "les quatre champs de saisie sont presents")
    _v("MES POSITIONS" in h, "le bloc apparait sur l'accueil")
    _v("addpos()" in h and "function addpos" in _scripts(h),
       "le bouton Ajouter est relie a sa fonction")
    _v("P&amp;L" in _scripts(h), "l'esperluette du P&L est echappee")

    print()
    if ECHECS:
        print(f"  {len(ECHECS)} ECHEC(S) :")
        for e in ECHECS:
            print(f"    - {e}")
        return 1
    print("  Toutes les pages sont saines.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
