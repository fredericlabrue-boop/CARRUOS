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

import json
import re
import sys
from pathlib import Path

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


def _objet(doc, marqueur):
    """L'objet JSON qui suit un marqueur, par comptage d'accolades."""
    i = doc.index(marqueur) + len(marqueur)
    prof, k, dans = 0, i, False
    while k < len(doc):
        c = doc[k]
        if dans:
            if c == "\\":
                k += 2
                continue
            if c == '"':
                dans = False
        elif c == '"':
            dans = True
        elif c == "{":
            prof += 1
        elif c == "}":
            prof -= 1
            if prof == 0:
                return json.loads(doc[i:k + 1])
        k += 1
    raise ValueError("objet non termine")


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
        # --- apostrophe francaise NUE dans un litteral a simple quote ---
        #
        # L'ancienne version cherchait le motif DANS un litteral extrait
        # par paires de quotes. C'est aveugle par construction : une
        # apostrophe nue TERMINE le litteral, donc elle n'est jamais
        # dedans. « aujourd'hui » passait, et cassait toute la page.
        #
        # On regarde donc la ligne entiere, apres avoir neutralise ce qui
        # est entre guillemets doubles — la, l'apostrophe est un
        # caractere ordinaire et ne pose aucun probleme.
        sans_double = re.sub(r'"[^"\n]*"', '""', ligne)
        if re.search(r"(?<!\\)[a-zA-Z]'[a-zA-Z]", sans_double):
            fautes.append(f"ligne {i} (apostrophe francaise nue) : "
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


def _contenus_css(css: str) -> list[str]:
    """Les valeurs de `content:` qui ne sont pas du pur ASCII.

    Une sequence d'echappement CSS (\\25B8) s'est deja affichee en
    charabia a l'ecran : l'escape voyage mal entre la source Python, le
    fichier et le navigateur, et un caractere hors ASCII depend en plus
    de la fonte. Le test refuse les deux.
    """
    mauvais = []
    for v in re.findall(r'content\s*:\s*"([^"]*)"', css):
        if any(ord(c) > 126 for c in v) or "\\" in v:
            mauvais.append(v)
    return mauvais


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
                 "graphique": app._page_graphique("AAA"),
                 "strategie": app._page_strategie(),
                 "maliste": app._page_palmares()}
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
    # LISTE BLANCHE, pas liste noire. L'ancienne version enumerait les
    # proprietes interdites a la main : top, left, width, height, margin,
    # padding, background-position. Elle a laissé passer `letter-spacing`
    # et `text-indent` dans l'animation du titre d'ouverture pendant tout
    # ce temps — deux proprietes de mise en page, sur un titre centre,
    # donc toute la ligne qui se recalcule a chaque image. C'est le saut
    # que Frederic voyait au lancement, et d'autant plus large que
    # l'ecran l'est. Une liste d'interdits oublie toujours quelque chose ;
    # une liste d'autorises ne peut rien laisser passer en silence.
    PERMISES = {"transform", "opacity", "visibility", "filter", "box-shadow",
                "color", "background-color", "border-color", "fill",
                "stroke", "stroke-dashoffset", "text-shadow"}

    def _corps_keyframes(texte):
        """Chaque @keyframes avec son corps complet, accolades imbriquees
        comprises. Une expression reguliere a un seul niveau ratait les
        blocs a plusieurs etapes."""
        out = []
        for m in re.finditer(r"@keyframes\s+([\w-]+)\s*\{", texte):
            i = m.end() - 1
            prof, j = 0, i
            while j < len(texte):
                if texte[j] == "{":
                    prof += 1
                elif texte[j] == "}":
                    prof -= 1
                    if prof == 0:
                        break
                j += 1
            out.append((m.group(1), texte[i:j + 1]))
        return out

    # Et sur les TROIS pages, pas seulement l'accueil : le controle ne
    # regardait que la premiere, donc la page graphique et la page
    # STRATEGIE pouvaient animer ce qu'elles voulaient.
    fautives, total_kf = [], 0
    for nom_page, htm in pages.items():
        bloc_css = re.search(r"<style>(.*?)</style>", htm, re.S)
        if not bloc_css:
            continue
        blocs = _corps_keyframes(bloc_css.group(1))
        total_kf += len(blocs)
        for nom_kf, corps in blocs:
            props = set(re.findall(r"([a-z-]+)\s*:", corps))
            # les variables CSS ne sont pas des proprietes animees
            interdites = sorted(x for x in props - PERMISES
                                if not x.startswith("--"))
            if interdites:
                fautives.append((nom_page, nom_kf, interdites))
    _v(not fautives,
       f"les {total_kf} animations des {len(pages)} pages n'animent que des "
       f"proprietes composees")
    for nom_page, nom_kf, pr in fautives:
        print(f"          -> {nom_page} / {nom_kf} anime {', '.join(pr)}")

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
    # --- La page STRATEGIE --------------------------------------------
    # --- Le panneau de detail de l'accueil ----------------------------
    print("\n  FICHE ET RAPPORTS")
    ja = _scripts(h)
    _v('id="voile"' in h and 'id="dcorps"' in h and 'id="dtitre"' in h,
       "le panneau de detail existe sur l'accueil")
    _v("function fiche" in ja and "function rapports" in ja,
       "la fiche d'un titre et la liste des rapports sont cablees")
    _v('onclick="fiche(' in ja,
       "cliquer un titre surveille ouvre sa fiche, pas seulement le "
       "graphique")
    _v("Pourquoi ce titre est surveille" in ja,
       "la fiche dit d'abord POURQUOI le titre est la")
    _v("function voileClic" in ja and "'Escape'" in ja,
       "le panneau se ferme au clic dehors et par Echap")
    _v("/api/rapports" in ja,
       "la case PHASE 0 interroge la liste des rapports")
    _v("cliq" in h and "rapports()" in h,
       "la case PHASE 0 est cliquable")
    # La fiche est ECRITE UNE FOIS : deux copies finiraient par diverger,
    # et c'est toujours celle qu'on ne regarde pas qui garde le bug.
    _v("function carte" in ja,
       "le rendu de fiche est disponible sur l'accueil")
    _v(".kv2" in css and ".trajet" in css,
       "le style de la fiche voyage avec elle sur l'accueil")
    _v(ja.count("function carte") == 1,
       "le rendu de fiche n'est ecrit qu'une fois")

    # « A SURVEILLER » se lisait comme une liste d'achats. C'etait un
    # comptage de SES propres lignes. Le libelle ne doit pas revenir.
    _v("A SURVEILLER" not in h,
       "le libelle trompeur « A SURVEILLER » a disparu de l'accueil")
    _v("MES LIGNES A TRAITER" in h,
       "le rail dit desormais de quoi il parle : MES LIGNES A TRAITER")
    _v("function lignesATraiter" in ja and "lignesATraiter()" in h,
       "le rail est cliquable et ouvre son explication")
    _v("pas des titres a acheter" in ja,
       "l'explication dit noir sur blanc que ce ne sont pas des achats")
    _v("/api/positions" in ja,
       "elle relit les positions plutot que de recopier un chiffre")

    print("\n  PAGE STRATEGIE")
    st = pages["strategie"]
    jss = _scripts(st)
    _v("STRATEGIE" in h, "l'accueil donne acces a la page")
    _v('id="pcap"' in st and 'id="ptaux"' in st and 'id="pans"' in st
       and 'id="pmens"' in st,
       "les quatre champs de la projection sont presents")
    _v("/api/projection" in jss and "/api/lignes" in jss,
       "la page interroge ses deux routes")
    _v("hypothese" in st.lower() and "prevision" in jss.lower(),
       "le taux est annonce comme une hypothese, pas une prevision")
    _v("basculePea" in jss and "17,2" in jss,
       "la bascule compte-titres / PEA existe")
    # La regle absolue du projet : aucun verdict directionnel, aucun
    # score composite. La page doit montrer les conditions de sortie
    # ECRITES, pas en inventer une synthese.
    _v("LES CONDITIONS DE SORTIE, UNE PAR UNE" in jss
       and "CE QUE DIT VOTRE" in jss,
       "les conditions de sortie sont presentees comme celles du plan")
    # L'etat en gros ne doit pas devenir un verdict deguise : il compte
    # les conditions et renvoie la decision a son proprietaire.
    _v("CONDITION" in jss and "premiere" in jss,
       "l'etat en gros cite la regle — fermeture a la PREMIERE condition")
    _v("la prend pas a votre place" in jss,
       "il dit explicitement que le programme ne decide pas")
    mauvais = _contenus_css(css)
    _v(not mauvais,
       "aucun content: CSS en echappement ou hors ASCII")
    if mauvais:
        print(f"          -> {mauvais}")
    _v(".manque span" in css,
       "les blocs manquants sont styles hors du panneau de detail aussi")
    _v("NO-GO en Phase 0" in jss,
       "un declenchement d'entree rappelle que l'hypothese est NO-GO")
    interdits = [m for m in ("HAUSSIER", "BAISSIER", "ACHETER", "SIGNAL ACHAT",
                             "confiance", "score global", "recommandation")
                 if m.lower() in st.lower()]
    _v(not interdits,
       "aucun verdict directionnel ni score compose sur la page")
    if interdits:
        print(f"          -> trouves : {', '.join(interdits)}")
    _v("geopolitique" in jss.lower() and "aucune" in jss.lower(),
       "le geopolitique est declare non chiffre")
    _v("recul_depuis_haut_pct" in jss and "gain_rendu_pct" in jss,
       "le recul depuis le sommet et le gain rendu sont affiches")
    # On doit pouvoir examiner N'IMPORTE QUEL titre, pas seulement ceux
    # du registre des positions.
    _v('id="rtk"' in st and "/api/revue" in jss,
       "un champ permet d'examiner n'importe quel titre")
    _v("function carte" in jss and jss.count("carte(") >= 3,
       "le rendu d'une carte est commun au registre et a l'examen")
    _v("non detenu" in jss,
       "un titre non detenu est annonce comme tel")
    _v("r.detenu" in jss,
       "les mesures qui exigent un prix d'entree sont conditionnees")
    _v("recul_52s_pct" in jss,
       "le recul depuis le haut 52 semaines est affiche, meme sans position")
    # `css` vient de l'accueil : le style propre a cette page se lit
    # dans SON bloc <style>, pas dans celui d'une autre.
    css_st = re.search(r"<style>(.*?)</style>", st, re.S).group(1)
    _v(".app.strat-page" in css_st and "grid-template-rows" in css_st,
       "la page a son propre gabarit de rangees")
    _v('class="app strat-page"' in st,
       "le corps de la page porte bien cette classe")

    print("\n  MISE EN PAGE QUI NE SAUTE PAS")
    # `transition:.18s` sans nom de propriete vaut `transition: all` : le
    # navigateur anime alors AUSSI la largeur, le remplissage et la
    # police quand ils changent. C'est exactement ce que la regle du
    # projet interdit, et c'etait present a cinq endroits.
    nus = re.findall(r"transition:\s*[.0-9]", css)
    _v(not nus, f"aucune transition sans nom de propriete ({len(nus)})")
    # La premiere colonne des rails en `auto` suivait le texte : un
    # libelle plus long au rafraichissement decalait toute la grille.
    # On verifie la PROPRIETE, pas la lettre du correctif. L'ancienne
    # version exigeait la chaine exacte « 128px 1fr 62px » : elle aurait
    # refuse une largeur tout aussi independante du texte mais ecrite
    # autrement, et n'aurait rien dit d'une largeur dependante du texte
    # ecrite avec les memes chiffres. Ce qui compte, c'est qu'aucune
    # piste ne se regle sur son CONTENU.
    m_rail = re.search(r"\.rail\{[^}]*grid-template-columns:([^;]+);",
                       css.replace("\n", " "))
    _v(bool(m_rail), "la grille des rails est declaree")
    if m_rail:
        pistes = m_rail.group(1)
        suit_texte = [k for k in ("auto", "min-content", "max-content",
                                  "fit-content")
                      if re.search(r"\b" + k + r"\b", pistes)]
        _v(not suit_texte,
           "aucune colonne de rail ne se regle sur son texte"
           + (f" ({', '.join(suit_texte)})" if suit_texte else ""))
    _v("tabular-nums" in css,
       "les chiffres des rails ont une chasse fixe : 0/5 et 12/5 "
       "occupent la meme largeur")

    print("\n  AUCUN SECRET DANS LE DEPOT")
    import subprocess
    racine = str(Path(__file__).resolve().parent.parent)
    suivis = subprocess.run(["git", "ls-files"], cwd=racine,
                            capture_output=True, text=True).stdout.split()
    # Une cle Alpha Vantage est une chaine de 16 caracteres majuscules et
    # chiffres. Aucune ne doit se trouver dans un fichier SUIVI par git :
    # la pousser reviendrait a la publier.
    motif = re.compile(r"\b[A-Z0-9]{16}\b")
    fautifs = []
    for rel in suivis:
        f = Path(racine) / rel
        if f.suffix.lower() in (".png", ".ico", ".zip") or not f.is_file():
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in motif.findall(txt):
            # Les empreintes SHA256 sont en minuscules, les constantes en
            # snake_case : seul un jeton tout en majuscules alarme.
            if m.isdigit() or m.isalpha() and m.islower():
                continue
            if any(m in ligne and ("cle" in ligne.lower()
                                   or "apikey" in ligne.lower()
                                   or "alphavantage" in ligne.lower())
                   for ligne in txt.splitlines()):
                fautifs.append(f"{rel}: {m}")
    _v(not fautifs, "aucune cle d'API dans un fichier suivi par git")
    if fautifs:
        print(f"          -> {fautifs[:5]}")
    gi = (Path(racine) / ".gitignore").read_text(encoding="utf-8")
    _v(".bruce_cache/" in gi,
       ".bruce_cache est ignore : la cle ne peut pas etre commitee")

    print("\n  ONGLET 5 ANS ET FENETRES HONNETES")
    from . import chart as _ch2
    cles = [u[0] for u in _ch2.UNITES]
    _v("cinq_ans" in cles, "l'onglet 5 ANS existe")
    _v(len(set(cles)) == len(cles), "aucune cle d'unite en double")
    # Deux unites partagent la meme regle de reechantillonnage : la cle
    # doit etre passee explicitement, sinon la seconde herite des
    # longueurs de la premiere.
    regles = [u[2] for u in _ch2.UNITES]
    _v(regles.count("W-FRI") == 2,
       "5 ANS et 1 SEMAINE partagent la taille de bougie")
    import inspect as _i
    src = _i.getsource(_ch2._analyse)
    _v("cle or next(" in src,
       "l'unite est identifiee par sa CLE, pas par sa regle")
    _v("cle=cle" in _i.getsource(_ch2.build_html),
       "et la cle est bien transmise a chaque appel")
    g2 = pages["graphique"]
    _v(g2.count('data-u="') == len(cles),
       f"les {len(cles)} onglets sont dans la page")
    _v("5 ANS" in g2, "le libelle 5 ANS est affiche")
    # La fenetre couverte est CALCULEE : une constante mentirait des que
    # l'historique du titre est plus court.
    _v("def fenetre_reelle" in _i.getsource(_ch2),
       "la fenetre affichee est calculee sur les vraies dates")

    print("\n  VERSEMENTS CONTRE CAPITALISATION")
    jstrat = _scripts(pages["strategie"])
    _v("GENERE SEUL" in jstrat,
       "la colonne separe l'epargne du rendement")
    _v("tout seul" in jstrat and "sortis de votre poche" in jstrat,
       "le montant genere par le fonds est annonce en clair")
    _v("an_bascule" in jstrat,
       "l'annee ou le fonds depasse l'epargne est affichee")

    print("\n  DEVISE ET COHERENCE DU PRIX D'ENTREE")
    _v("function mt(" in ja and "SYMBOLE" in ja,
       "les montants portent la devise du titre, pas l'euro par defaut")
    _v("'USD':" in ja or "USD:'$'" in ja.replace(" ", ""),
       "le dollar est connu")
    _v("GBp" in ja, "les pence de Londres aussi — le piege du facteur 100")
    _v("function alerteCoherence" in ja,
       "un prix d'entree hors bornes est signale")
    _v("est donc <b>faux</b>" in ja,
       "et la carte dit que le gain latent affiche est faux")
    from . import strategie as _sg
    _v(_sg.devise_du_titre("NVDA") == "USD"
       and _sg.devise_du_titre("MC.PA") == "EUR"
       and _sg.devise_du_titre("SHEL.L") == "GBp",
       "la devise se deduit du suffixe de place")

    print("\n  GRAPHIQUE SANS RESEAU")
    from . import chart as _ch
    g = pages["graphique"]
    jg = _scripts(g)
    # Le test precedent validait un mecanisme CASSE : il verifiait que la
    # fonction de repli etait definie avant la balise, alors que le vrai
    # defaut etait que ce repli ajoutait le script de facon ASYNCHRONE —
    # le code de la page tournait avant, et ne trouvait jamais la
    # bibliotheque. Un test peut confirmer une mecanique et rater ce
    # qu'elle produit ; celui-ci regarde maintenant le resultat.
    srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', g)
    _v(len(srcs) == 1,
       f"une SEULE balise de script externe, donc bloquante ({len(srcs)})")
    if len(srcs) != 1:
        print(f"          -> {srcs}")
    _v(srcs and (srcs[0] == _ch.LOCAL or srcs[0] == _ch.CDN),
       "elle pointe sur la copie locale ou sur le CDN, choisi par le serveur")
    _v("chargeDistant" not in g,
       "aucun repli asynchrone : il arrivait toujours trop tard")
    _v(_ch.source_trace() in (_ch.LOCAL, _ch.CDN),
       "source_trace() tranche cote serveur, la ou l'on sait si le "
       "fichier local existe")
    _v("GRAPHIQUE INDISPONIBLE" in jg,
       "sans bibliotheque, la page explique au lieu de rester vide")
    # L'antislash d'un chemin Windows est mange par une chaine Python non
    # brute : le chemin s'affichait colle, donc inutilisable.
    _v("equity_scanner/statique/lightweight-charts.js" in jg,
       "le chemin du fichier a poser est lisible en entier")
    _v("MUET" in jg and "LightweightCharts!=='undefined'"
       in jg.replace(" ", ""),
       "un faux graphique avale les appels au lieu de tuer le script")

    print("\n  THEMES")
    from . import reglages as _rg
    ATTENDUS = {"carruos", "jarvis", "ultron", "reacteur", "monolithe",
                "orbite", "nocturne", "cristal", "terminal",
                "matrix", "saiyan", "avengers", "olympe"}
    _v(set(_rg.THEMES) == ATTENDUS,
       f"{len(ATTENDUS)} themes : " + ", ".join(
           _rg.THEMES[k]["nom"] for k in sorted(_rg.THEMES)))
    if set(_rg.THEMES) != ATTENDUS:
        print(f"          -> en trop : {set(_rg.THEMES) - ATTENDUS}")
        print(f"          -> manquants : {ATTENDUS - set(_rg.THEMES)}")

    # Le controle de validite des couleurs ne regardait que le theme
    # ACTIF : un theme inactif pouvait embarquer une couleur cassee sans
    # que rien ne bronche — et c'est arrive. On verifie les dix.
    casses = []
    for cle in _rg.THEMES:
        valeurs = dict(_rg.THEMES[cle])
        valeurs.pop("forme", None)
        valeurs.update(_rg.forme(cle))
        for nom, v in valeurs.items():
            if (isinstance(v, str) and v.startswith("#")
                    and not re.fullmatch(r"#[0-9a-fA-F]{3,8}", v)):
                casses.append(f"{cle}.{nom}={v!r}")
    _v(not casses, "aucune couleur invalide dans AUCUN des themes")
    if casses:
        print(f"          -> {casses}")

    # Un theme qui change la FORME, pas seulement la couleur : c'est la
    # demande, et sans controle elle se perd au premier ajout.
    avec_forme = [k for k in _rg.THEMES if _rg.THEMES[k].get("forme")]
    _v(len(avec_forme) >= 9,
       f"{len(avec_forme)} themes changent la geometrie, pas que la teinte")
    distinctes = {_rg.forme(k)["coin"] + "|" + _rg.forme(k)["rayon"]
                  + "|" + _rg.forme(k)["pad"] for k in _rg.THEMES}
    _v(len(distinctes) >= 9,
       f"{len(distinctes)} geometries de panneau reellement differentes")
    # Chaque theme de caractere doit avoir son CSS, pas seulement sa
    # palette : sans lui, il ne se distingue que par la couleur.
    sans_css = [k for k in _rg.THEMES
                if k != "carruos" and f"body.theme-{k}" not in _rg.CSS_THEMES]
    _v(not sans_css, "chaque theme a son propre CSS de fond et d'hologramme")
    if sans_css:
        print(f"          -> sans CSS : {sans_css}")
    _v("papier" not in _rg.THEMES and "theme-papier" not in _rg.CSS_THEMES,
       "aucun theme clair : ce n'est pas au gout du proprietaire")
    # Les variables de forme doivent TOUTES sortir dans :root, sinon une
    # regle de base tomberait sur sa valeur de repli sans qu'on le voie.
    racine = _rg.variables(_rg.DEFAUTS)
    manquantes = [n for n in ("--coin", "--rayon", "--equerre", "--pad",
                              "--gap", "--bord", "--bord-fort", "--pan-fond",
                              "--pan-ombre", "--txt", "--txt-fort",
                              "--txt-doux", "--txt-mi", "--txt-faible",
                              "--titre-police", "--titre-espace",
                              "--titre-casse", "--corps-police",
                              "--champ-fond")
                  if n + ":" not in racine]
    _v(not manquantes, "toutes les variables de forme sont declarees")
    if manquantes:
        print(f"          -> absentes : {manquantes}")
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

    print("\n  LE MOT DANS LE CERCLE, LES GRAPHIQUES DANS LEUR BOITE")
    from . import chart as _ch5
    js5 = _scripts(pages["graphique"])
    css5 = re.sub(r"/\*.*?\*/", " ",
                  re.search(r"<style>(.*?)</style>", pages["graphique"],
                            re.S).group(1), flags=re.S)
    # 16 px en dur : « HORS CRITERES » debordait le disque de 48 px. La
    # taille se MESURE maintenant, parce qu'une formule serait fausse
    # des qu'un theme change la police.
    _v("function poseVerdict" in js5,
       "le mot du verdict est pose par une fonction qui l'ajuste")
    _v("scrollWidth" in js5 and "scrollHeight" in js5,
       "elle mesure le texte au lieu de calculer sa largeur")
    _v("overflow-wrap:normal" in css5.replace(" ", ""),
       "le mot ne se coupe qu'aux espaces, jamais en plein milieu")
    _v("vh.textContent=v.titre" not in js5.replace(" ", ""),
       "plus personne ne pose le mot sans l'ajuster")
    # Les graphiques : la hauteur se LIT, elle ne se devine plus.
    _v("function hauteurUtile" in js5,
       "la hauteur du trace vient d'une seule fonction")
    for mauvais in ("clientHeight-30", "Math.max(90,"):
        _v(mauvais not in js5.replace(" ", ""),
           f"plus de hauteur devinee ({mauvais})")
    m_pc = re.search(r"\.pil-c\{[^}]*\}", css5.replace("\n", " "))
    _v(bool(m_pc) and "overflow:hidden" in m_pc.group(0).replace(" ", ""),
       "la colonne centrale ne peut plus deborder sur le bandeau du bas")
    _v("minmax(190px" not in css5.replace(" ", ""),
       "les panneaux n'imposent plus un plancher de hauteur")
    m_box = re.search(r"\.pil-c \.box\{[^}]*\}", css5.replace("\n", " "))
    _v(bool(m_box) and "flex" in m_box.group(0),
       "la boite donne au trace une hauteur definie, en colonne flex")

    print("\n  PAGE MA LISTE")
    from . import palmares as _pm
    hm = pages["maliste"]
    jm = _scripts(hm)
    _v('id="ptitres"' in hm and 'id="ptri"' in hm and 'id="psleeve"' in hm,
       "les champs de saisie sont presents")
    _v("classe()" in hm and "function classe" in jm,
       "le bouton CLASSER est relie a sa fonction")
    _v("MA LISTE" in pages["accueil"] and "/palmares" in pages["accueil"],
       "l'accueil porte le bouton vers la page")
    # Les cinq tris doivent etre proposes, avec leur libelle.
    manque_tri = [k for k in _pm.TRIS if f'value="{k}"' not in hm]
    _v(not manque_tri, f"les {len(_pm.TRIS)} tris sont proposes ({manque_tri})")
    # LES DEUX AVERTISSEMENTS. Sans eux la page laisse croire a un
    # classement valide et a un ratio risque/gain qui n'existe pas.
    _v("avertissement_ratio" in jm and "avertissement_tri" in jm,
       "les deux avertissements sont affiches avec les resultats")
    # Le piege documente du projet : une apostrophe echappee dans une
    # chaine Python NON brute devient une apostrophe nue et tue tout le
    # script. C'est arrive ici, sur un onclick en ligne.
    _v("onclick=\"ouvre(" not in jm,
       "plus d'onclick en ligne avec un ticker entre apostrophes")
    _v("data-tk" in jm, "le ticker voyage dans un attribut, pas dans du code")
    _v("closest('.tk[data-tk]')" in jm,
       "un seul ecouteur delegue ouvre le graphique")
    _v("_page_palmares" in open(_app.__file__, encoding="utf-8").read(),
       "la page a sa fonction dediee")
    # Et la grille de saisie ne doit pas se regler sur son contenu.
    cssm = re.sub(r"/\*.*?\*/", " ",
                  re.search(r"<style>(.*?)</style>", hm, re.S).group(1),
                  flags=re.S)
    m_sai = re.search(r"\.palm \.saisie\{[^}]*\}", cssm.replace("\n", " "))
    _v(bool(m_sai) and "minmax" in m_sai.group(0),
       "la grille de saisie a des colonnes bornees, pas fixes")

    print("\n  LECTURE DES CHANDELIERS DANS LA PAGE")
    from . import chandeliers as _cd2
    js6 = _scripts(pages["graphique"])
    _v("const CHAND=" in js6, "la lecture est injectee dans la page")
    _v("function carteChandeliers" in js6,
       "et posee dans la colonne de droite")
    _v("h+=carteChandeliers();" in js6.replace(" ", ""),
       "la carte est bien ajoutee au tirage")
    C6 = _objet(js6, "const CHAND=") if "const CHAND={" in js6 else None
    if C6 is not None:
        _v("presentes" in C6 and "comptage" in C6,
           "elle porte les figures du jour et le compte des mesures")
        _v("hasard" in (C6.get("comptage") or {}).get("phrase", ""),
           "le piege des comparaisons multiples voyage avec la carte")
        _v(all("suivi" in f and "forme" in f for f in C6["presentes"]),
           "chaque figure du jour porte sa definition et son suivi")
    # Ce qui compte : le taux de base doit etre affiche A COTE du taux.
    _v("un jour quelconque" in js6,
       "le taux de base est affiche a cote de chaque taux mesure")
    _v("indiscernable" in js6,
       "une figure dans le bruit est nommee comme telle")
    # Les seize figures du code doivent toutes avoir un libelle francais.
    sans_nom = [c for c in _cd2.NOMS if c not in _cd2.FORMES
                and not c.startswith(("hausse_", "baisse_"))]
    _v(not sans_nom, f"chaque figure a sa definition ecrite ({sans_nom})")

    print("\n  BANDEAU DES MODULES")
    # Le defaut trouve : `.mods`, `.mod`, `.hdr2`, `.gg`, `.zone`, `.val`,
    # `.nw2`... n'etaient definis NULLE PART. Le bandeau du bas de la page
    # graphique s'affichait en texte brut empile pendant que tout le reste
    # de la page etait soigne, et les deux seules regles existantes —
    # `.pil-l .mod` et `.pil-l .kv` — surchargeaient du vide.
    #
    # On ne verifie donc pas une liste de noms ecrite a la main : on
    # RELEVE les classes que le generateur produit vraiment, et on exige
    # que chacune existe dans la feuille de style. Un module ajoute
    # demain avec une classe nouvelle fera tomber ce test.
    from . import chart as _ch4
    _g = {"rsi": 49.0, "rvol": 0.88, "atr": 3.0, "atr_pct": 2.8,
          "ema20": {"pct": 1.2, "atr": 0.3}, "sma50": {"pct": -2.1, "atr": -0.5},
          "sma200": {"pct": -8.0, "atr": -1.9}, "h52": 10, "b52": 5,
          "d_h52": -17.4, "d_b52": 18.5, "squeeze": 85,
          "p1m": {"titre": 1.2, "ecart": 0.4},
          "p3m": {"titre": -3.0, "ecart": -1.1},
          "p6m": {"titre": 9.0, "ecart": 2.0},
          "p12m": {"titre": -12.0, "ecart": -4.0}}
    _perf = {"n": 11, "gagnants": 5, "taux": 45, "evR": -0.05, "pf": 0.64,
             "duree": 9, "derniers": [{"d": "03/25", "R": -1.0, "m": "stop"}]}
    _actus = [{"titre": "Un titre d'actualite", "source": "Reuters",
               "quand": "il y a 2 h", "url": "https://exemple.invalid",
               "score": 0.3}]
    mods = _ch4._modules(_g, _perf, "SMH", "us",
                         {"date": "date inconnue", "jours": None}, _actus)
    produites = set()
    for att in re.findall(r'class="([^"]+)"', mods):
        produites.update(att.split())
    css_g = re.search(r"<style>(.*?)</style>", pages["graphique"], re.S).group(1)
    sans_style = sorted(c for c in produites
                        if not re.search(r"\." + re.escape(c) + r"[^a-zA-Z0-9_-]",
                                         css_g))
    _v(not sans_style,
       f"aucune des {len(produites)} classes du bandeau n'est orpheline"
       + (f" (absentes de la feuille : {', '.join(sans_style)})"
          if sans_style else ""))
    # Et le bandeau doit se replier sur sa largeur, pas s'etaler en une
    # ligne illisible sur un ecran large.
    m_mods = re.search(r"\.mods\{[^}]*\}", css_g.replace("\n", " "))
    _v(bool(m_mods) and "auto-fit" in m_mods.group(0),
       "le bandeau se replie sur la largeur disponible")

    print("\n  COLONNE GAUCHE DE LA PAGE GRAPHIQUE")
    from . import hud as _hd4
    # Le bandeau HUD est pose dans une colonne de 190 px. Sa grille
    # etait en `1fr auto 1fr` avec un repli en `@media(max-width:900px)` :
    # la requete regarde la FENETRE, pas le conteneur, donc sur un grand
    # ecran elle ne se declenchait jamais et deux blocs entiers — les
    # seuils et les rails — partaient HORS CHAMP, invisibles.
    m_hg = re.search(r"\.hud-g\{[^}]*\}", _hd4.CSS.replace("\n", " "))
    _v(bool(m_hg) and "auto-fit" in m_hg.group(0),
       "la grille du HUD se replie sur la largeur de son CONTENEUR")
    _v("@media(max-width:900px){.hud-g" not in _hd4.CSS.replace(" ", ""),
       "elle ne depend plus d'une requete sur la taille de la fenetre")
    _v("min-width:0" in _hd4.CSS,
       "les enfants de grille peuvent descendre sous leur contenu")
    # Un SVG avec width="104" en attribut garde ses 104 px dans une
    # piste plus etroite et deborde sans rien dire.
    _v(".cad svg{width:100%" in _hd4.CSS.replace(" ", "").replace(
           ".cadsvg{", ".cad svg{"),
       "les cadrans se mettent a l'echelle de leur piste")
    _v("width:min(100%,250px)" in _hd4.CSS.replace(" ", ""),
       "le noyau ne deborde plus sa colonne")
    # Un guillemet orphelin s'affichait sous la note des seuils :
    # `'</div>")'.replace('")', '"')` rend `</div>"`.
    jauges = {"rsi": 49.0, "rvol": 0.88, "atr_pct": 2.8,
              "sma200": {"atr": -1.0}, "ema20": {"pct": 1, "atr": .2},
              "sma50": {"pct": 1, "atr": .3}, "h52": 10, "b52": 5,
              "d_h52": -2, "d_b52": 3, "squeeze": 36, "atr": 3.0,
              "p3m": {"titre": 1, "ecart": 2}}
    tete = _hd4.entete("SMH", jauges, "AUCUN - 8/13 BLOCS", {"n": 0},
                       _hd4.TRACE, "USD")
    orphelins = re.findall(r">\s*[\"\']\s*<", tete)
    _v(not orphelins,
       f"aucun guillemet orphelin dans le HUD ({len(orphelins)})")

    print("\n  LOGO ET ICONES")
    from . import hud as _hd3
    for nom_page, htm in pages.items():
        _v('rel="icon"' in htm and "/carruos.svg" in htm,
           f"{nom_page} : le logo est declare pour l'onglet")
    _v("/favicon.ico" in pages["accueil"],
       "une icone de repli est declaree pour les navigateurs anciens")
    ico = Path(_app.__file__).resolve().parent.parent / "carruos.ico"
    _v(ico.exists(), "carruos.ico existe a cote de Carruos.vbs")
    if ico.exists():
        import struct
        brut = ico.read_bytes()
        res, typ, nimg = struct.unpack("<HHH", brut[:6])
        _v(res == 0 and typ == 1 and nimg >= 5,
           f"carruos.ico est un vrai fichier d'icone ({nimg} tailles)")
        tailles, coherent = [], True
        for i in range(nimg):
            o = 6 + 16 * i
            w, _h, _c, _r, _pl, _bc, taille, dec = struct.unpack(
                "<BBBBHHII", brut[o:o + 16])
            tailles.append(w or 256)
            if dec + taille > len(brut):
                coherent = False
        _v(coherent, "chaque image de l'icone tient dans le fichier")
        # 16 px, c'est la barre des taches et l'onglet ; 256, l'affichage
        # en grandes icones de l'explorateur. Sans les deux, Windows
        # reechantillonne et le cerf devient une tache.
        _v(16 in tailles and 256 in tailles,
           f"les tailles 16 et 256 sont presentes ({sorted(tailles)})")
    # Une seule source pour l'onglet et pour le raccourci : le meme trace.
    _v("<svg" in _hd3.icone(_app.TRACE_D)
       and _app.TRACE_D[:40] in _hd3.icone(_app.TRACE_D),
       "l'icone est dessinee a partir du trace du cerf, pas recopiee")

    print("\n  FLUIDITE")
    from . import reglages as _rg3
    _v(_rg3.DEFAUTS.get("fluidite") == "auto",
       "la fluidite est automatique par defaut")
    for v, att in (("auto", "auto"), ("sobre", "sobre"),
                   ("complet", "complet"), ("n importe quoi", "auto")):
        _v(f'data-fluidite="{att}"' in _rg3.corps_attrs({"fluidite": v}),
           f"le reglage {v!r} donne data-fluidite={att!r}")
    for nom_page, htm in pages.items():
        _v("data-fluidite=" in htm,
           f"{nom_page} : la consigne de fluidite est posee sur <body>")
        _v("CARRUOS_FLUIDITE" in _scripts(htm),
           f"{nom_page} : la sonde de cadence est embarquee")
    # Le decor est dimensionne en vh : sans plafond son cout double quand
    # l'ecran double, et c'est exactement le symptome decrit.
    for sel in ("fond-anneaux", "fond-cerf", "fond-lueur"):
        bloc = re.search(r"\." + sel + r"\{[^}]*\}", _hd3.FOND_CSS)
        _v(bool(bloc) and "px)" in bloc.group(0),
           f".{sel} a une taille plafonnee en pixels")
    _v("contain:strict" in _hd3.FOND_CSS,
       "le decor est isole du reste de la page")
    _v(".fluide-sobre" in _hd3.FOND_CSS,
       "un mode sobre existe pour les machines qui ne suivent pas")
    _v("prefers-reduced-motion" in _hd3.FOND_CSS,
       "le reglage systeme d'animations reduites est respecte")

    print("\n  CARTE INTERET")
    from . import interet as _it
    g3 = pages["graphique"]
    j3 = _scripts(g3)


    _v("const INTERET=" in j3, "la carte d'interet est injectee dans la page")
    _v("h+=carteInteret(d);" in j3.replace(" ", ""),
       "et posee dans la colonne de droite au tirage")
    I3 = _objet(j3, "const INTERET=")
    _v(bool(I3.get("accord", {}).get("lignes")),
       "les unites de temps sont alignees, une ligne chacune")
    _v(I3.get("rappel") == _it.RAPPEL_PHASE0
       and I3.get("pas_un_avis") == _it.PAS_UN_AVIS,
       "les deux rappels voyagent avec la carte")

    # Le RESULTAT, pas le montage : chaque unite doit porter sa lecture,
    # et elle ne peut pas contredire la pastille du haut.
    D3 = _objet(j3, "const DATA=")
    from . import chart as _ch3
    faits = [(k, b) for k, b in D3.items()
             if b and not b.get("insuffisant")]
    _v(bool(faits), "au moins une unite de temps est exploitable")
    _v(all(b.get("interet") for _k, b in faits),
       "chaque unite exploitable porte sa lecture d'interet")
    _v(all(_ch3.VERDICT_CSS[b["interet"]["niveau"]] == b["verdict"]["type"]
           and _ch3.VERDICT_MOT[b["interet"]["niveau"]] == b["verdict"]["titre"]
           for _k, b in faits),
       "la pastille et la carte ne peuvent pas se contredire")
    _v(all(m["code"] != "?" and m["texte"]
           for _k, b in faits for m in b["interet"]["manquants"]),
       "chaque bloc manquant est chiffre, jamais seulement nomme")

    # Le defaut trouve en relisant : `etat` est une CHAINE, la comparer
    # a 1 rendait toujours zero — « 0 / 13 BLOCS » sur un titre complet.
    _v("b.etat===1" not in j3.replace(" ", "")
       and "b.etat==='ok'" in j3.replace(" ", ""),
       "le compteur central compare des chaines, pas des entiers")
    # Et la table de couleurs etait indexee sur une cle qui n'existe pas.
    m_coul = re.search(r"const coul=\{(.*?)\}\[v\.type\]", j3, re.S)
    _v(bool(m_coul), "la table de couleurs du cercle est trouvable")
    if m_coul:
        cles_coul = set(re.findall(r"(\w+)\s*:", m_coul.group(1)))
        attendues = set(_ch3.VERDICT_CSS.values())
        _v(attendues <= cles_coul,
           "chaque etat possible a sa couleur (" +
           ", ".join(sorted(attendues - cles_coul)) + " manquant)"
           if attendues - cles_coul else
           "chaque etat possible a sa couleur")
    # Et une classe CSS pour chaque marche, des deux cotes.
    manque = [c for c in _ch3.VERDICT_CSS.values() if ".v-" + c not in _ch3.CSS]
    _v(not manque, "chaque pastille a sa classe CSS (" + ",".join(manque) + ")"
       if manque else "chaque pastille a sa classe CSS")
    manque2 = [c for c in _it.TITRES if ".n-" + c not in _ch3.CSS]
    _v(not manque2, "chaque marche a sa couleur dans la carte ("
       + ",".join(manque2) + ")" if manque2 else
       "chaque marche a sa couleur dans la carte")

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
