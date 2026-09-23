"""Interface HUD facon poste de pilotage.

Trait fin cyan sur noir, cadrans radiaux, angles coupes, cerf filaire au
centre entoure d'anneaux en rotation. Tout est en SVG et CSS : aucune image,
aucune dependance, net a toutes les tailles.

Le cyan est la couleur des donnees, le champagne reste celle de la marque —
le cerf garde sa teinte pour ne pas se fondre dans l'instrumentation.
"""

from __future__ import annotations

import html

# Cerf allege (247 points) : suffisant a 168 px, et n'alourdit pas la page.
TRACE = "M186 376C184 377 183 376 183 375C182 374 181 373 180 369C179 366 180 362 179 355C177 349 174 338 171 332C169 325 165 322 162 318C160 313 158 308 157 304C157 300 158 294 159 294C160 294 161 302 163 304C164 306 166 307 166 306C165 305 162 298 161 297C161 295 162 295 163 294C164 294 164 293 165 295C167 297 170 305 172 306C173 307 174 305 174 304C174 302 175 301 173 297C171 293 166 285 164 281C162 276 162 268 162 268C163 268 166 279 167 281C168 282 167 277 168 278C169 279 171 284 172 286C173 288 175 288 175 287C175 286 173 282 173 281C173 280 175 278 177 280C178 282 182 291 184 293C185 295 186 294 185 293C185 291 182 288 182 286C182 283 186 282 185 279C185 277 180 273 179 272C178 270 179 269 180 268C181 267 185 267 185 266C185 264 181 262 179 260C178 258 176 252 175 252C174 251 176 255 175 255C173 256 169 255 167 253C166 251 166 246 165 244C164 242 161 248 161 240C161 232 162 202 163 197C165 192 167 206 169 212C170 217 170 226 171 229C172 233 174 230 176 232C178 233 181 238 182 239C183 239 181 234 182 234C182 234 183 238 184 238C185 238 185 234 186 234C188 235 192 239 194 240C196 240 199 236 200 236C202 236 202 239 203 239C204 239 205 240 206 239C208 237 215 232 212 230C209 229 192 230 188 230C183 229 182 228 183 227C185 227 195 227 196 226C197 225 191 222 190 220C189 218 190 217 190 216C190 215 190 215 191 214C193 214 196 215 197 215C199 216 199 218 201 218C202 218 206 216 208 216C209 216 209 218 209 220C209 221 205 225 206 226C207 227 213 227 215 225C216 224 216 219 215 215C214 211 208 207 208 201C208 196 213 186 214 182C216 177 218 178 218 177C217 176 214 174 212 175C210 175 211 178 207 179C202 179 191 179 185 177C179 175 174 168 171 168C168 168 169 174 168 176C166 177 163 177 162 179C162 180 164 183 164 184C164 185 163 186 161 186C159 185 157 182 154 180C150 178 143 177 139 175C136 174 135 171 132 168C130 165 127 160 126 156C124 153 124 149 124 147C124 145 125 143 126 144C128 144 134 147 136 148C137 149 137 149 136 150C134 151 130 150 129 152C127 153 128 156 129 157C130 159 132 159 134 161C137 164 140 170 144 173C148 176 154 179 157 179C160 179 160 174 162 173C163 172 163 174 164 174C165 173 167 171 168 169C169 168 170 164 170 163C169 162 165 162 164 163C162 165 164 169 163 170C162 172 159 171 158 171C157 171 156 171 156 169C156 167 159 162 156 159C153 156 139 150 139 149C138 148 147 151 152 153C157 155 164 160 167 161C170 161 170 159 170 158C170 157 169 156 168 156C167 155 164 156 163 155C161 154 160 152 157 149C153 147 153 145 141 141C129 137 96 128 85 124C74 121 77 121 73 118C68 115 64 110 61 107C58 103 56 100 55 97C54 95 53 89 55 91C57 93 65 105 68 108C70 111 71 109 72 109C72 109 73 109 73 107C74 106 78 107 74 102C71 96 58 84 53 77C48 69 45 63 42 57C40 51 40 45 40 40C40 36 42 33 43 30C44 27 47 23 47 24C47 26 45 36 44 39C44 43 44 43 46 48C48 52 54 63 57 67C61 71 63 77 65 72C66 67 65 44 66 37C66 29 67 28 67 25C68 22 70 16 71 21C71 25 70 43 71 53C72 64 75 75 77 82C79 89 80 92 84 96C87 101 91 105 97 109C102 113 116 122 119 123C121 123 112 115 110 110C109 106 110 97 111 97C111 96 112 106 114 109C116 113 117 114 121 118C124 121 130 127 137 131C144 136 158 143 163 145C167 147 164 145 163 143C162 141 158 137 157 133C155 130 153 129 153 123C152 118 152 105 152 101C153 97 154 95 155 99C156 103 156 117 159 125C162 132 169 142 173 145C177 149 179 146 181 146C183 147 182 148 186 149C189 150 197 150 200 149C203 149 202 151 206 147C209 143 217 134 221 126C224 118 224 103 225 99C226 95 227 98 228 102C228 105 228 117 227 122C227 127 226 128 224 131C223 135 218 141 217 143C216 145 213 147 217 145C222 143 236 135 243 131C250 127 253 123 257 120C261 116 262 116 264 112C266 108 269 97 269 97C270 96 270 106 270 110C269 113 268 115 266 117C265 119 257 124 261 123C264 121 280 111 286 107C292 102 293 101 296 97C299 93 301 89 303 81C306 74 308 63 309 52C310 42 309 25 309 20C310 16 312 23 313 25C313 28 314 30 314 38C315 45 314 67 315 72C316 77 319 72 322 68C325 64 331 53 334 49C336 44 336 43 336 39C335 36 333 28 332 25C332 23 332 22 333 24C335 26 338 34 340 38C341 42 340 43 340 46C340 49 340 52 338 57C336 62 333 68 328 75C323 82 312 93 308 97C304 102 305 102 305 103C305 105 307 108 308 109C309 110 309 112 311 109C314 106 323 93 325 91C327 89 326 96 325 98C324 101 322 104 319 107C316 111 312 114 308 117C304 120 308 120 296 124C284 128 250 138 238 142C226 146 227 147 224 149C221 151 219 153 219 154C218 156 219 157 220 158C221 159 218 161 224 159C230 156 251 145 257 143C264 141 261 143 262 145C263 147 263 151 261 155C259 159 255 168 251 172C248 176 245 177 241 179C237 180 231 179 228 180C225 182 226 179 225 189C224 199 223 229 224 242C226 254 229 259 232 266C234 273 239 278 239 283C240 287 236 290 236 293C235 297 238 301 237 303C236 306 231 306 231 307C231 309 235 311 236 312C236 313 236 315 236 316C236 317 235 318 233 319C232 319 230 317 228 318C227 318 225 319 224 321C224 322 226 323 226 325C226 327 226 330 225 331C225 332 224 332 223 332C222 332 220 330 219 330C218 330 218 332 216 332C215 332 213 329 213 331C212 332 213 339 213 341C212 343 212 343 210 343C209 343 206 340 204 342C203 343 202 351 201 353C199 354 195 349 194 351C192 354 191 366 190 370C188 374 187 375 186 376ZM127 248C126 249 125 247 124 247C124 246 127 243 126 243C125 243 122 246 120 247C118 247 115 248 113 247C112 247 114 246 112 245C110 244 99 240 100 240C101 239 111 241 118 240C124 239 135 236 139 234C143 232 143 232 144 229C146 226 149 215 150 217C150 219 148 235 147 239C147 243 146 240 145 240C145 240 146 237 144 238C143 239 139 245 137 245C135 246 136 240 135 241C133 241 129 247 127 248ZM176 193C174 193 170 191 169 189C167 188 165 184 166 183C168 182 174 184 176 184C178 185 178 185 179 186C179 188 181 191 180 192C180 193 178 194 176 193Z"

# Couleur d'accent. `var(--acc)` plutot qu'un code fige : les
# cadrans et le radar suivent alors le theme choisi, au lieu de
# rester cyan sur un fond violet. Les SVG en ligne comprennent les
# variables CSS comme n'importe quel element de la page.
CYAN = "var(--acc)"
OR = "#c9b28a"

CSS = """
.hud{background:#05080d;border:1px solid var(--bord);padding:24px 22px 20px;
 margin-bottom:12px;position:relative;
 clip-path:polygon(18px 0,100% 0,100% calc(100% - 18px),calc(100% - 18px) 100%,0 100%,0 18px)}
.hud::before,.hud::after{content:"";position:absolute;width:34px;height:34px;
 border:1px solid var(--bord-fort);pointer-events:none}
.hud::before{top:6px;right:6px;border-left:0;border-bottom:0}
.hud::after{bottom:6px;left:6px;border-right:0;border-top:0}
/* LA GRILLE SUIT SON CONTENEUR, PAS L'ECRAN.
   `1fr auto 1fr` avec un repli en `@media(max-width:900px)` : la requete
   media regarde la fenetre, alors que ce bandeau est pose dans la
   COLONNE GAUCHE de la page graphique, large de 190 px. Sur un ecran de
   1920 la requete ne se declenchait donc jamais, la grille gardait ses
   trois colonnes, et comme un `1fr` ne descend pas sous la taille
   minimale de son contenu, les pistes prenaient 332 px et 208 px dans
   une boite de 192 : le panneau des seuils et les rails se retrouvaient
   entierement HORS CHAMP, caches par le defilement. Invisibles, sans
   rien qui le signale.
   `auto-fit` + `minmax` n'ont besoin d'aucune requete : le nombre de
   colonnes se deduit de la largeur disponible, quelle que soit la
   fenetre. `min(100%,190px)` autorise en plus la piste a descendre sous
   190 px quand le conteneur est plus etroit que cela. */
.hud-g{display:grid;gap:20px;align-items:center;
 grid-template-columns:repeat(auto-fit,minmax(min(100%,190px),1fr))}
/* Sans `min-width:0`, un enfant de grille refuse de descendre sous la
   taille minimale de son contenu et deborde sa piste en silence. */
.hud-g>*{min-width:0}
/* Trois cadrans cote a cote font 332 px de large : en colonne etroite
   ils passent a deux, puis a un, au lieu d'etre tronques. */
.cadrans{display:grid;gap:10px;
 grid-template-columns:repeat(auto-fit,minmax(min(100%,86px),1fr))}
/* Le SVG porte width="104" en attribut : sans cette regle il garde ses
   104 px meme dans une piste de 91, et deborde. `width:100%` laisse
   l'attribut servir de taille MAXIMALE, pas de taille imposee. */
.cad{text-align:center;min-width:0}
.cad svg{width:100%;height:auto;max-width:104px;display:block;margin:0 auto}
.cad .lb{font:400 8.5px ui-monospace,Consolas,monospace;letter-spacing:.2em;
 color:var(--txt-faible);margin-top:2px}
/* 250 px en dur debordait la colonne gauche de la page graphique, large
   de 192. `min(100%,250px)` garde la taille voulue quand la place y est
   et se replie sinon ; `aspect-ratio` tient le cercle rond. */
.noyau{position:relative;display:flex;align-items:center;justify-content:center;
 width:min(100%,250px);height:auto;aspect-ratio:1;margin:0 auto}
.noyau svg{position:absolute;inset:0}
.rot1{animation:tour 26s linear infinite;transform-origin:50% 50%}
.rot2{animation:tour 17s linear infinite reverse;transform-origin:50% 50%}
.rot3{animation:tour 40s linear infinite;transform-origin:50% 50%}
@keyframes tour{to{transform:rotate(360deg)}}
/* --- Traitement holographique ---------------------------------------
   Quatre effets combines, chacun tres discret pris isolement :
   bloom, lignes de balayage, vacillement irregulier, cone de projection.
   C'est leur superposition qui fait l'hologramme, pas leur intensite. */
.cerf-fil{animation:vacille 5.4s steps(1,end) infinite}
@keyframes vacille{
 0%,100%{opacity:.93}6%{opacity:1}7%{opacity:.72}8%{opacity:.98}
 34%{opacity:.88}35%{opacity:1}61%{opacity:.8}62%{opacity:.99}
 83%{opacity:.91}84%{opacity:1}}
.holo{position:relative}
/* lignes de balayage : le signe distinctif d'une projection */
.holo::after{content:"";position:absolute;inset:-8%;pointer-events:none;
 background:repeating-linear-gradient(180deg,transparent 0 2px,
 rgba(34,211,238,.062) 2px 3px);
 animation:balayage 6.5s linear infinite}
@keyframes balayage{to{transform:translateY(260px)}}
/* halo diffus autour du noyau */
.holo::before{content:"";position:absolute;inset:6%;pointer-events:none;
 background:radial-gradient(circle,rgba(34,211,238,.11) 0%,transparent 62%);
 animation:pulse 4.2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:.55;transform:scale(.97)}
 50%{opacity:1;transform:scale(1.03)}}
.spectre{opacity:.32;mix-blend-mode:screen}
.socle{animation:socle 4.2s ease-in-out infinite}
@keyframes socle{0%,100%{opacity:.42}50%{opacity:.78}}
.cone{animation:cone 7s ease-in-out infinite}
@keyframes cone{0%,100%{opacity:.16}50%{opacity:.3}}
.hud-id{text-align:center;margin-top:6px}
.hud-id .tk{font:300 27px ui-sans-serif,system-ui;letter-spacing:.34em;
 text-indent:.34em;color:var(--txt-fort)}
.hud-id .st{font:400 9px ui-monospace,Consolas,monospace;letter-spacing:.28em;
 color:var(--txt-faible);margin-top:3px}
.rails{display:flex;flex-direction:column;gap:7px}
.rail.cliq{cursor:pointer}
.rail.cliq:hover .n{color:var(--acc)}
/* Largeur FIXE de la premiere colonne. En `auto`, elle suivait le texte :
   a chaque rafraichissement de l'etat, un libelle plus long decalait
   toute la grille — c'est le « visuel qui saute ». 128 px tiennent
   « MES LIGNES A TRAITER » sans retour a la ligne. */
/* La premiere colonne ne doit JAMAIS suivre son texte — en `auto`, un
   libelle plus long au rafraichissement decalait toute la grille. Mais
   128 px en dur plus 62 plus les ecarts depassent une colonne etroite.
   `clamp` garde la propriete qui compte : la largeur ne depend que du
   CONTENEUR, jamais du contenu. Deux libelles de longueurs differentes
   donnent toujours la meme colonne. */
.rail{display:grid;grid-template-columns:clamp(78px,44%,128px) 1fr 62px;
 gap:9px;
 align-items:center;
 font:400 10px ui-monospace,Consolas,monospace;letter-spacing:.1em}
.rail .n{color:var(--txt-faible);white-space:nowrap}
.rail .v{text-align:right;color:var(--txt-fort);font-size:11.5px;
 font-variant-numeric:tabular-nums}
.rail .t{height:3px;background:var(--bord);position:relative;overflow:hidden}
.rail .t i{position:absolute;top:0;height:100%;background:var(--acc)}
.rail .t .z{background:#134a56}
.rail.ok .v{color:var(--pos)}.rail.ko .v{color:var(--neg)}
.bandeau{display:flex;flex-wrap:wrap;gap:0;margin-top:16px;border-top:1px solid var(--bord);
 padding-top:11px;font:400 10px ui-monospace,Consolas,monospace;letter-spacing:.12em}
.bandeau .cliq{cursor:pointer}
.bandeau .cliq:hover .v{color:var(--acc)}
.bandeau .cliq .n::after{content:" >";opacity:.6}
.bandeau div{flex:1;min-width:104px;padding:0 9px;border-left:1px solid var(--bord)}
.bandeau div:first-child{border-left:0;padding-left:0}
.bandeau .n{color:var(--txt-faible);font-size:8.5px;letter-spacing:.2em}
.bandeau .v{color:var(--txt-fort);font-size:14px;margin-top:3px}
.bandeau .v.pos{color:var(--pos)}.bandeau .v.neg{color:var(--neg)}
.bandeau .v.or{color:#c9b28a}
"""

# --- La barre du haut, ECRITE UNE SEULE FOIS --------------------------
#
# Elle etait recopiee a la main sur quatre pages : accueil, MA LISTE,
# STRATEGIE, graphique. Quatre copies divergent, et elles avaient
# diverge : seule l'accueil portait des onglets, le majordome n'existait
# que la, et le graphique n'avait qu'un bouton « Retour ».
#
# L'horloge, elle, portait `class="etat"` — le nom deja pris par une
# CARTE de l'accueil, qui vaut marge 10/12 px, ecart interieur 13 px et
# une bordure. `.bar .etat` ne surchargeait que la police, donc la barre
# heritait de la boite d'une carte : 61 px de haut au lieu de 30. Ces
# 31 px etaient pris a la grille de contenu a CHAQUE ouverture de la
# page d'accueil, et les trois familles d'elements y flottaient a trois
# hauteurs differentes. C'est le « mal dimensionne » signale.
#
# La lecon tient en une ligne : un element de barre ne doit jamais
# porter le nom de classe d'une carte. Et comme une relecture ne
# l'attrape pas, `test_pages` compare la hauteur RENDUE de la barre
# entre les pages — deux valeurs differentes veulent dire qu'une page a
# ramasse un style qui ne la concerne pas.

BARRE_CSS = """
.bar{display:flex;align-items:center;gap:11px;padding:0 50px 0 3px;flex:none;
 flex-wrap:wrap;row-gap:7px}
.bar h1{font-size:15px;font-weight:300;color:var(--marque);letter-spacing:.4em;
 margin:0;white-space:nowrap}
.bar .sst{font:400 9px ui-monospace,Consolas,monospace;letter-spacing:.24em;
 color:var(--txt-faible);white-space:nowrap}
.bar .sep{flex:1;min-width:12px}
/* L'horloge a SON nom. `etat` etait celui d'une carte. */
.bar .horl{font:400 10px ui-monospace,Consolas,monospace;letter-spacing:.18em;
 color:var(--txt-faible);white-space:nowrap;font-variant-numeric:tabular-nums;
 margin:0;padding:0;border:0;background:none}
.bar .horl b{color:var(--txt-fort);font-weight:400}
.raf{background:#08222a;border:1px solid var(--bord-fort);color:var(--acc);
 padding:6px 12px;font:500 10px ui-monospace,monospace;letter-spacing:.14em;
 cursor:pointer;flex:none;white-space:nowrap;
 transition:background .16s ease,color .16s ease,border-color .16s ease;
 clip-path:polygon(6px 0,100% 0,100% calc(100% - 6px),
 calc(100% - 6px) 100%,0 100%,0 6px)}
.raf:hover{background:#0e3b48}
/* L'onglet de la page ouverte : on doit savoir ou l'on est. */
.raf.actif{background:#0c3340;color:var(--txt-fort);border-color:var(--acc)}
.raf.actif::before{content:"";display:inline-block;width:5px;height:5px;
 margin-right:6px;vertical-align:1px;background:var(--acc);border-radius:50%}
"""

CSS = CSS + BARRE_CSS

# Les onglets : (adresse, libelle, cle). La cle nomme aussi la FENETRE,
# pour qu'ouvrir deux fois MA LISTE ne donne pas deux fenetres mais
# rappelle celle qui est deja la.
ONGLETS = (("/", "ACCUEIL", "accueil"),
           ("/palmares", "MA LISTE", "palmares"),
           ("/strategie", "STRATEGIE", "strategie"),
           ("/carnet", "CARNET", "carnet"))


def barre(trace: str, nom: str, actif: str = "", soustitre: str = "",
          avant: str = "", fenetre: str = "") -> str:
    """La barre du haut, identique sur toutes les pages.

    `actif` est la cle de l'onglet courant : il s'affiche marque et ne
    reouvre pas sa propre page. `avant` recoit les boutons propres a la
    page (ACTUALISER sur l'accueil) — ils se rangent avant les onglets.

    Aucun `onclick` n'est ecrit ici. L'adresse voyage dans `data-vers`
    et un SEUL ecouteur delegue la lit : c'est la regle du projet, et
    elle vient d'un vrai degat — un `onclick="ouvre('X')"` fabrique
    depuis une chaine Python non brute transformait `\'` en apostrophe
    nue et tuait tout le script de la page.
    """
    cerf = ('<svg viewBox="0 0 380 400" width="28" height="30">'
            f'<path class="fx" d="{trace}"/></svg>')
    ong = "".join(
        f'<button class="raf ong{" actif" if cle == actif else ""}"'
        f' data-vers="{adr}" data-fen="carruos-{cle}">{lab}</button>'
        for adr, lab, cle in ONGLETS)
    sst = f'<span class="sst">{soustitre}</span>' if soustitre else ""
    fen = fenetre or (f"carruos-{actif}" if actif else "")
    return (f'<div class="bar" data-fenetre="{fen}">' + cerf
            + f"<h1>{nom}</h1>" + sst
            + '<span class="sep"></span>' + avant + ong
            + '<span class="horl" id="horloge">&mdash;</span></div>')


# Le script de la barre : l'horloge, et l'ouverture des onglets.
#
# « je veux que la premiere reste et quand j'ouvre un onglet ca m'ouvre
# une autre fenetre » — donc jamais `location.href`, qui remplace la
# page ouverte. `window.open` avec un NOM de fenetre : deux clics sur le
# meme onglet rappellent la meme fenetre au lieu d'en empiler une
# seconde. Sous pywebview, c'est Python qui ouvre la fenetre ; dans un
# navigateur, si la fenetre est bloquee, on navigue sur place plutot que
# de ne rien faire du tout.
BARRE_JS = r"""
function ouvreFenetre(adr, nom){
 if(!adr) return;
 if(window.pywebview && window.pywebview.api && window.pywebview.api.fenetre){
  try{ window.pywebview.api.fenetre(adr, nom || ''); return; }catch(e){}
 }
 var f=null;
 try{ f=window.open(adr, nom || '_blank'); }catch(e){ f=null; }
 if(f){ try{ f.focus(); }catch(e){} return; }
 location.href=adr;          // fenetre bloquee : au moins on y va
}
document.addEventListener('click', function(ev){
 var b=ev.target.closest ? ev.target.closest('[data-vers]') : null;
 if(!b) return;
 ev.preventDefault();
 if(b.classList.contains('actif')) return;   // deja sur cette page
 ouvreFenetre(b.getAttribute('data-vers'), b.getAttribute('data-fen'));
});
// La fenetre porte son nom des le chargement : sans lui, un onglet
// rouvert depuis une fenetre fille creerait un doublon au lieu de
// rappeler la fenetre existante.
(function(){
 var b=document.querySelector('.bar');
 var n=b && b.getAttribute('data-fenetre');
 if(n){ try{ window.name=n; }catch(e){} }
})();
function horloge(){
 var h=document.getElementById('horloge'); if(!h) return;
 var d=new Date();
 var p=d.toLocaleTimeString('fr-FR',{timeZone:'Europe/Paris',hour:'2-digit',
   minute:'2-digit',second:'2-digit'});
 var j=d.toLocaleDateString('fr-FR',{timeZone:'Europe/Paris',weekday:'short',
   day:'2-digit',month:'short'});
 h.innerHTML=j.toUpperCase()+'  <b>'+p+'</b>  PARIS';
}
horloge(); setInterval(horloge,1000);
"""

R = 46.0
C = 2 * 3.14159265 * R
ARC = 0.72                       # cadran ouvert de 259 degres


def cadran(valeur, mini, maxi, libelle, unite="", zlo=None, zhi=None,
           couleur=CYAN, taille=104) -> str:
    """Cadran radial facon instrument de bord. La bande sombre marque la
    plage recherchee, l'aiguille pleine la valeur."""
    if valeur is None:
        pct = 0.0
        txt = "--"
    else:
        pct = max(0.0, min(1.0, (float(valeur) - mini) / (maxi - mini)))
        txt = f"{valeur:g}{unite}"
    zone = ""
    if zlo is not None:
        a = max(0.0, min(1.0, (zlo - mini) / (maxi - mini)))
        b = max(0.0, min(1.0, (zhi - mini) / (maxi - mini)))
        zone = (f'<circle cx="60" cy="60" r="{R}" fill="none" stroke="#134a56" '
                f'stroke-width="7" stroke-dasharray="{(b - a) * ARC * C:.1f} {C:.1f}" '
                f'stroke-dashoffset="{-a * ARC * C:.1f}" '
                f'transform="rotate(129 60 60)"/>')
    return (
        f'<div class="cad"><svg viewBox="0 0 120 120" width="{taille}" '
        f'height="{taille}">'
        f'<circle cx="60" cy="60" r="{R}" fill="none" stroke="#0b2028" '
        f'stroke-width="7" stroke-dasharray="{ARC * C:.1f} {C:.1f}" '
        f'transform="rotate(129 60 60)"/>'
        + zone +
        f'<circle cx="60" cy="60" r="{R}" fill="none" stroke="{couleur}" '
        f'stroke-width="3" stroke-linecap="round" '
        f'stroke-dasharray="{pct * ARC * C:.1f} {C:.1f}" '
        f'transform="rotate(129 60 60)"/>'
        f'<text x="60" y="57" text-anchor="middle" fill="#e8f6fa" '
        f'font-size="21" font-family="ui-sans-serif,system-ui" '
        f'font-weight="300">{html.escape(txt)}</text>'
        f'<text x="60" y="73" text-anchor="middle" fill="var(--txt-faible)" font-size="8" '
        f'font-family="ui-monospace,monospace" letter-spacing="1.4">'
        f'{html.escape(libelle)}</text></svg></div>')


def noyau(trace: str) -> str:
    """Cerf projete en hologramme : cone de lumiere, socle lumineux, bloom,
    aberration chromatique, anneaux en rotation et lignes de balayage."""
    return (
        '<div class="noyau holo">'
        '<svg viewBox="0 0 250 250">'
        '<defs>'
        '<filter id="bloom" x="-45%" y="-45%" width="190%" height="190%">'
        '<feGaussianBlur stdDeviation="3.4" result="f"/>'
        '<feMerge><feMergeNode in="f"/><feMergeNode in="f"/>'
        '<feMergeNode in="SourceGraphic"/></feMerge></filter>'
        '<radialGradient id="pad" cx="50%" cy="50%">'
        '<stop offset="0" stop-color="var(--acc)" stop-opacity=".62"/>'
        '<stop offset="1" stop-color="var(--acc)" stop-opacity="0"/>'
        '</radialGradient>'
        '<linearGradient id="rai" x1="0" y1="1" x2="0" y2="0">'
        '<stop offset="0" stop-color="var(--acc)" stop-opacity=".34"/>'
        '<stop offset="1" stop-color="var(--acc)" stop-opacity="0"/>'
        '</linearGradient>'
        '</defs>'
        # cone de projection, depuis le socle vers le haut
        '<polygon class="cone" points="118,234 132,234 196,34 54,34" '
        'fill="url(#rai)"/>'
        '<ellipse class="socle" cx="125" cy="234" rx="56" ry="9" fill="url(#pad)"/>'
        '<circle class="rot3" cx="125" cy="125" r="119" fill="none" '
        'stroke="var(--bord)" stroke-width="1"/>'
        '<circle class="rot1" cx="125" cy="125" r="110" fill="none" '
        'stroke="var(--bord-fort)" stroke-width="1" stroke-dasharray="2 9"/>'
        '<circle class="rot2" cx="125" cy="125" r="100" fill="none" '
        'stroke="var(--acc)" stroke-width="1" stroke-dasharray="42 26 8 26" '
        'opacity=".55" filter="url(#bloom)"/>'
        '<circle class="rot1" cx="125" cy="125" r="90" fill="none" '
        'stroke="var(--bord)" stroke-width="6" stroke-dasharray="1 15"/>'
        '</svg>'
        '<svg viewBox="0 0 380 400" width="168" height="177" '
        'style="position:relative">'
        # Trace declare UNE fois, reference trois fois : les deux copies
        # decalees creent l'aberration chromatique sans tripler le poids.
        f'<defs><path id="cerf-t" d="{trace}"/></defs>'
        '<use href="#cerf-t" class="spectre" fill="none" stroke="var(--acc)" '
        'stroke-width="1.1" transform="translate(-1.6,0)"/>'
        '<use href="#cerf-t" class="spectre" fill="none" stroke="#f0b76b" '
        'stroke-width="1.1" transform="translate(1.6,0)"/>'
        '<use href="#cerf-t" class="cerf-fil" fill="none" stroke="#c9b28a" '
        'stroke-width="1.1" stroke-linejoin="round" filter="url(#bloom)"/>'
        '</svg></div>')


def rail(nom, valeur, pct, txt, etat="", action="") -> str:
    """Un rail peut porter une action au clic, comme une case du bandeau."""
    p = max(0.0, min(100.0, pct))
    clic = f' cliq" onclick="{action}" title="Cliquer pour voir' if action else ""
    return (f'<div class="rail {etat}{clic}">'
            f'<span class="n">{html.escape(nom)}</span>'
            f'<span class="t"><i style="width:{p:.0f}%"></i></span>'
            f'<span class="v">{html.escape(txt)}</span></div>')


def bandeau(cases) -> str:
    """Chaque case peut porter une action au clic : (nom, valeur, classe,
    action). Un chiffre qu'on ne peut pas ouvrir n'apprend rien — la case
    PHASE 0 affichait « 2 RAPPORT(S) » sans dire lesquels."""
    out = []
    for case in cases:
        nom, val, cls = case[0], case[1], case[2]
        action = case[3] if len(case) > 3 else ""
        attr = (f' class="cliq" onclick="{action}" title="Cliquer pour voir"'
                if action else "")
        out.append(f'<div{attr}><div class="n">{html.escape(nom)}</div>'
                   f'<div class="v {cls}">{html.escape(str(val))}</div></div>')
    return '<div class="bandeau">' + "".join(out) + "</div>"


def entete(ticker, g, verdict, perf, trace, ccy="") -> str:
    """Le bloc HUD complet : cadrans a gauche, cerf au centre, rails a droite,
    bandeau de chiffres en bas."""
    e = html.escape
    rsi = g.get("rsi")
    rvol = g.get("rvol")
    s200 = (g.get("sma200") or {}).get("atr")

    # Chaque cadran porte son seuil sous lui. Un 47 sans reference ne
    # veut rien dire ; "47, zone d'achat 40-55" se lit tout seul.
    def _lig(lib, val, regle, ok):
        c = "#34d399" if ok else "#f87171"
        return (f'<div class="sfx"><span>{lib}</span>'
                f'<b style="color:{c}">{regle}</b></div>')

    gauche = ('<div class="cadrans">'
              + cadran(None if rsi is None else round(rsi), 0, 100, "RSI 14",
                       zlo=40, zhi=55)
              + cadran(None if rvol is None else round(rvol, 2), 0, 3, "RVOL",
                       zlo=1.2, zhi=3)
              + cadran(g.get("atr_pct"), 0, 8, "ATR %", unite="")
              + "</div>"
              + '<div class="seuils">'
              + _lig("RSI 14", rsi, "zone 40 a 55",
                     rsi is not None and 40 <= rsi <= 55)
              + _lig("RVOL", rvol, "au moins 1,20",
                     rvol is not None and rvol >= 1.20)
              + _lig("ATR %", g.get("atr_pct"), "mesure, sans seuil", True)
              + '<div class="sfn">Un bloc ne passe que si sa mesure est '
                'du bon cote de son seuil. Les seuils sont ceux de la '
                'strategie, geles.</div>'
              + '</div>')

    rails = ['<div class="rails">']
    for nom, cle in (("EMA 20", "ema20"), ("SMA 50", "sma50"), ("SMA 200", "sma200")):
        v = g.get(cle)
        if not v:
            continue
        pct = 50 + max(-50, min(50, v["atr"] * 12))
        rails.append(rail(nom, v["atr"], pct, f'{v["atr"]:+.1f} ATR',
                          "ok" if v["atr"] > 0 else "ko"))
    for nom, cle in (("REL 3M", "p3m"), ("REL 6M", "p6m"), ("REL 12M", "p12m")):
        v = g.get(cle)
        if not v:
            continue
        rails.append(rail(nom, v["ecart"], 50 + max(-50, min(50, v["ecart"] * 1.4)),
                          f'{v["ecart"]:+.1f}%', "ok" if v["ecart"] > 0 else "ko"))
    rails.append("</div>")

    cases = [("PLUS HAUT 52S", f'{g.get("d_h52", 0):+.1f}%',
              "pos" if g.get("d_h52", 0) > -5 else "neg"),
             ("PLUS BAS 52S", f'{g.get("d_b52", 0):+.1f}%', "pos"),
             ("COMPRESSION BB", "--" if g.get("squeeze") is None
              else f'{g["squeeze"]}e pct', "")]
    if perf and perf.get("n"):
        cases += [("SIGNAUX PASSES", perf["n"], ""),
                  ("REUSSITE", f'{perf["taux"]}%',
                   "pos" if perf["taux"] >= 50 else "neg"),
                  ("PROFIT FACTOR", perf["pf"],
                   "pos" if perf["pf"] >= 1.15 else "neg"),
                  ("GAIN MOYEN", f'{perf["evR"]:+.2f} R',
                   "pos" if perf["evR"] > 0 else "neg")]
    else:
        cases.append(("SIGNAUX PASSES", "0", ""))

    return ('<div class="hud"><div class="hud-g">'
            + gauche
            + '<div>' + noyau(trace)
            + f'<div class="hud-id"><div class="tk">{e(ticker)}</div>'
            f'<div class="st">{e(verdict)}</div></div></div>'
            + "".join(rails)
            + "</div>" + bandeau(cases) + "</div>")


# ---------------------------------------------------------------------
# Console d'accueil : le meme traitement holographique, mais au service
# de l'etat du marche au lieu d'un titre particulier. Les cadrans sont
# remplis apres coup par /api/etat pour que la page s'ouvre sans attendre
# le reseau — l'hologramme, lui, est la immediatement.
# ---------------------------------------------------------------------

VIDE_CAD = ('<div class="cadrans">'
            + cadran(None, 0, 1, "S&P 500") + cadran(None, 0, 1, "EURO STOXX")
            + cadran(None, 0, 5, "LIGNES") + '</div>')


RADAR_CSS = """
/* Balayage de veille. Les chiffres du marche sont deja dans les rails a
   droite : ici on montre l'activite, pas une seconde fois la donnee. */
.radar{position:relative;width:132px;height:132px;margin:0 auto}
.radar svg{width:100%;height:100%;display:block}
.radar .bal{transform-origin:66px 66px;animation:tour 4.2s linear infinite}
.radar .bl{animation:blip 4.2s ease-out infinite}
.radar .bl:nth-of-type(2){animation-delay:1.1s}
.radar .bl:nth-of-type(3){animation-delay:2.4s}
.radar .bl:nth-of-type(4){animation-delay:3.3s}
@keyframes blip{0%,88%{opacity:0}90%{opacity:1}100%{opacity:0}}
.radar .lab{position:absolute;left:0;right:0;bottom:-3px;text-align:center;
 font:400 7.5px ui-monospace,monospace;letter-spacing:.22em;color:var(--txt-faible)}
"""


def radar() -> str:
    """Radar de detection. Les echos sont poses par le JS a partir du
    dernier scan : plus un titre est proche de declencher, plus son echo
    est pres du centre."""
    return (
        '<div class="radar"><svg viewBox="0 0 132 132">'
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{CYAN}" stop-opacity=".34"/>'
        f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>'
        '</linearGradient></defs>'
        + "".join(f'<circle cx="66" cy="66" r="{r}" fill="none" '
                  f'stroke="rgba(var(--holo),.16)" stroke-width=".7"/>'
                  for r in (20, 36, 52))
        + '<circle cx="66" cy="66" r="60" fill="none" '
          'stroke="rgba(var(--holo),.3)" stroke-width="1" '
          'stroke-dasharray="3 6"/>'
          '<line x1="6" y1="66" x2="126" y2="66" stroke="rgba(var(--holo),.1)"/>'
          '<line x1="66" y1="6" x2="66" y2="126" stroke="rgba(var(--holo),.1)"/>'
        + '<path class="bal" d="M66 66 L126 66 A60 60 0 0 0 108 24 Z" '
          'fill="url(#bg)"/>'
        + '<g id="echos"></g>'
        + f'<circle cx="66" cy="66" r="3" fill="{CYAN}"/>'
        '</svg><div class="lab" id="rad-lab">AUCUN SCAN</div></div>')


CSS += """
.seuils{margin-top:9px;padding-top:8px;border-top:1px solid #0b2028}
.sfx{display:flex;justify-content:space-between;align-items:baseline;
 font-size:9.5px;letter-spacing:.08em;color:var(--txt-mi);padding:3px 0}
.sfx b{font-weight:500;font-size:10px}
.sfn{font-size:9px;line-height:1.5;color:#2f5462;margin-top:7px}
"""

CSS += RADAR_CSS


def console(trace: str, hologramme: bool = True) -> str:
    """Bandeau HUD de l'accueil. Coquille seule : le contenu arrive ensuite.

    hologramme=False quand le cerf est deja projete en fond de page : un
    second exemplaire au centre ferait doublon et volerait 180 px de
    hauteur aux panneaux."""
    return (
        '<div class="hud" id="hud"><div class="hud-g">'
        '<div id="hud-cad">' + radar() + '</div>'
        '<div class="hud-c">' + (noyau(trace) if hologramme else "")
        + '<div class="hud-id"><div class="tk">CARRUOS</div>'
        '<div class="st" id="hud-verdict">RELEVE DU MARCHE...</div></div></div>'
        '<div id="hud-rails"><div class="rails">'
        + rail("REGIME US", 0, 0, "--") + rail("REGIME EUR", 0, 0, "--")
        + rail("LIGNES", 0, 0, "--") + rail("MES LIGNES A TRAITER", 0, 0, "--")
        + '</div></div></div>'
        '<div id="hud-band">'
        + bandeau([("SEANCE", "--", ""), ("EXECUTION", "21H40", "or"),
                   ("POSITIONS", "--", ""), ("PHASE 0", "NON LANCEE", "neg")])
        + '</div></div>')


def console_etat(e: dict) -> dict:
    """Les trois fragments a injecter une fois les donnees recues."""
    def bloc(v, libelle):
        """Ecart a la MM200, borne a +/-20 %. Zone recherchee : au-dessus."""
        return cadran(None if v is None else round(v, 1), -20, 20, libelle,
                      unite="%", zlo=0, zhi=20,
                      couleur=CYAN if (v or 0) >= 0 else "#f87171")

    us, eu = e.get("us"), e.get("eu")
    n, nmax = e.get("n_lignes", 0), e.get("max_lignes", 5)
    surv = e.get("n_surveiller", 0)

    cad = ('<div class="cadrans">'
           + bloc(us, "S&P 500") + bloc(eu, "EURO STOXX")
           + cadran(n, 0, nmax, "LIGNES", zlo=0, zhi=nmax,
                    couleur=CYAN if n < nmax else "#f59e0b")
           + '</div>')

    def r(nom, ok, txt, pct, action=""):
        return rail(nom, 0, pct, txt, "ok" if ok else "ko", action)

    rails = ('<div class="rails">'
             + r("REGIME US", (us or -1) >= 0,
                 "--" if us is None else f"{us:+.1f}%",
                 50 + max(-50, min(50, (us or 0) * 2.5)))
             + r("REGIME EUR", (eu or -1) >= 0,
                 "--" if eu is None else f"{eu:+.1f}%",
                 50 + max(-50, min(50, (eu or 0) * 2.5)))
             + r("LIGNES", n < nmax, f"{n}/{nmax}", n / nmax * 100)
             + r("MES LIGNES A TRAITER", surv == 0, str(surv),
                 0 if not n else surv / max(n, 1) * 100,
                 action="lignesATraiter()")
             + '</div>')

    band = bandeau([
        # Le libelle disait « SEANCE US » et ne parlait que de New York.
        # La case ouvre maintenant les neuf places, europeennes comprises.
        ("LES PLACES", e.get("places_resume", e.get("seance", "--")),
         "pos" if e.get("places_ouvertes") else "", "lesPlaces()"),
        ("EXECUTION", e.get("execution", "--"), "or", "lesPlaces()"),
        ("POSITIONS", f"{n}/{nmax}", "" if n < nmax else "neg"),
        ("PHASE 0", e.get("phase0", "NON LANCEE"),
         "pos" if e.get("phase0_ok") else "neg", "rapports()"),
    ])
    return {"rails": rails, "bandeau": band,
            "verdict": e.get("verdict", "--")}


# ---------------------------------------------------------------------
# Fond de page : le cerf en projection geante derriere toute l'interface.
#
# Contrainte de performance : un trace de cette taille avec un filtre de
# flou coute cher a repeindre. Aucun filtre SVG ici — l'aberration se
# fait par deux copies decalees, et les animations ne touchent que des
# proprietes composees (transform, opacity, background-position), donc
# le GPU s'en charge sans repeindre le trace.
# ---------------------------------------------------------------------

FOND_CSS = """
/* `contain:strict` isole le decor du reste de la page : le navigateur
   sait que rien de ce qui s'y anime ne peut deplacer, redimensionner ou
   repeindre quoi que ce soit au-dehors, et cesse donc de recalculer le
   document a chaque image. Mesure : le temps par image passe de 350 ms
   a 183 ms en 2560x1440 sur la machine d'essai, soit la moitie.
   Les quatre confinements sont sans effet visible ICI, et on peut le
   demontrer plutot que l'esperer : `paint` ne change rien parce que
   l'element decoupe deja a la fenetre (`overflow:hidden` sur un
   `position:fixed;inset:0`), `layout` non plus parce que TOUS les
   enfants sont en `position:absolute`, `style` n'agit que sur les
   compteurs et les guillemets dont il n'y a aucun ici, et `size` ne
   change rien parce que la taille vient de `inset:0`, pas du contenu. */
.fond{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden;
 contain:strict;
 display:flex;align-items:center;justify-content:center}
/* --- Anneaux : diametre 142vh, ils sortent de l'ecran en haut et en bas.
   On est a l'interieur de la projection, pas devant. -------------- */
/* Plafonne : le cout d'un anneau qui tourne est proportionnel a sa
   surface, et une surface en `vh` double quand l'ecran double. Au-dela
   de 1080 px le dessin ne gagne plus rien a l'oeil et coute le double. */
.fond-anneaux{position:absolute;width:min(150vh,150vw,1180px);
 height:min(150vh,150vw,1180px);flex:none}
/* --- Le cerf. viewBox serre sur la boite reelle du trace, width:auto :
   la hauteur commande seule. Pas de filtre SVG a cette taille — la
   lueur est obtenue par un second trace epais sous le premier, ce qui
   ne coute rien au repeint. --------------------------------------- */
.fond-cerf{position:absolute;height:min(97vh,940px);width:auto;flex:none;
 will-change:transform;backface-visibility:hidden;
 will-change:transform;animation:respire 15s ease-in-out infinite}
@keyframes respire{0%,100%{transform:scale(1) translateY(0)}
 50%{transform:scale(1.045) translateY(-12px)}}
.f-c1,.f-c2{opacity:.62}
.f-m{animation:fvacille 11s steps(1,end) infinite}
@keyframes fvacille{0%,100%{opacity:.92}3%{opacity:1}4%{opacity:.78}
 5%{opacity:.96}47%{opacity:.88}48%{opacity:1}79%{opacity:.82}80%{opacity:.98}}
/* --- Cone de projection, ancre au bas de l'ecran ----------------- */
.fond-cone{position:absolute;bottom:0;left:50%;width:124vh;height:100vh;
 transform:translateX(-50%);
 background:linear-gradient(0deg,rgba(34,211,238,.19),rgba(34,211,238,0) 84%);
 clip-path:polygon(43.5% 100%,56.5% 100%,100% 0,0 0);
 animation:fcone 7s ease-in-out infinite}
@keyframes fcone{0%,100%{opacity:.5}50%{opacity:1}}
.fond-socle{position:absolute;bottom:1.5vh;left:50%;width:62vh;height:8vh;
 transform:translateX(-50%);border-radius:50%;
 background:radial-gradient(ellipse at center,rgba(90,235,255,.72) 0%,
 rgba(34,211,238,.24) 40%,transparent 70%);
 animation:fsocle 4.2s ease-in-out infinite}
@keyframes fsocle{0%,100%{opacity:.45}50%{opacity:.85}}
.fond-lueur{position:absolute;width:min(80vh,820px);height:min(80vh,820px);border-radius:50%;
 background:radial-gradient(circle,rgba(34,211,238,.10) 0%,
 rgba(34,211,238,.038) 42%,transparent 68%);
 animation:lueur 9s ease-in-out infinite}
@keyframes lueur{0%,100%{opacity:.6;transform:scale(.95)}
 50%{opacity:1;transform:scale(1.06)}}
.fond-scan{position:absolute;left:0;right:0;top:-100vh;height:300vh;
 background:repeating-linear-gradient(180deg,transparent 0 3px,
 rgba(34,211,238,.032) 3px 4px);
 will-change:transform;animation:fbalaye 9s linear infinite}
@keyframes fbalaye{to{transform:translateY(400px)}}
.fond-sol{position:absolute;left:-30%;right:-30%;bottom:-7%;height:48%;
 background:repeating-linear-gradient(90deg,rgba(34,211,238,.10) 0 1px,
 transparent 1px 66px),repeating-linear-gradient(0deg,
 rgba(34,211,238,.09) 0 1px,transparent 1px 48px);
 transform:perspective(330px) rotateX(69deg);transform-origin:50% 100%;
 -webkit-mask-image:linear-gradient(to top,#000 0,transparent 76%);
 mask-image:linear-gradient(to top,#000 0,transparent 76%)}
.fond-ray{position:absolute;left:0;right:0;top:0;height:150px;
 background:linear-gradient(180deg,transparent,rgba(34,211,238,.055),transparent);
 will-change:transform;animation:ray 13s ease-in-out infinite}
@keyframes ray{0%{transform:translateY(-150px)}
 100%{transform:translateY(100vh)}}

/* --- MODE SOBRE -----------------------------------------------------
   Le decor reste, il se calme. Ce qui coute vraiment, mesure element
   par element : le cerf trace CINQ fois et mis a l'echelle a chaque
   image (61 % du temps), et cinq anneaux qui tournent (41 %). Ici le
   cerf ne garde que son trait net et son halo, et ne fait plus que
   monter et descendre ; trois anneaux sur cinq s'immobilisent, donc
   sont dessines une fois pour toutes. La trame de balayage et le rayon
   s'effacent : ce sont deux grandes surfaces repeintes en continu pour
   un effet que personne ne regarde.
   Ce mode s'allume tout seul quand la machine ne suit pas — voir
   FLUIDITE_JS — et se force depuis le tiroir des reglages. */
.fluide-sobre .fond-cerf{animation-name:respire-sobre}
@keyframes respire-sobre{0%,100%{transform:translateY(0)}
 50%{transform:translateY(-11px)}}
.fluide-sobre .f-c1,.fluide-sobre .f-c2{display:none}
.fluide-sobre .f-halo:nth-of-type(2){display:none}
.fluide-sobre .f-m{animation:none;opacity:.95}
.fluide-sobre .fond-anneaux .rot1{animation:none}
.fluide-sobre .fond-anneaux .rot3{animation:none}
.fluide-sobre .fond-scan,.fluide-sobre .fond-ray{display:none}
.fluide-sobre .fond-lueur{animation-name:lueur-sobre}
@keyframes lueur-sobre{0%,100%{opacity:.6}50%{opacity:1}}

/* Quand le systeme demande des animations reduites, on obeit sans
   attendre la mesure : c'est un reglage d'accessibilite, pas un gout. */
@media (prefers-reduced-motion: reduce){
 .fond-cerf{animation-name:respire-sobre}
 .f-c1,.f-c2{display:none}
 .fond-scan,.fond-ray{display:none}
 .fond-anneaux .rot1,.fond-anneaux .rot3{animation:none}
}
"""


def icone(trace: str) -> str:
    """Le cerf en icone : onglet du navigateur, fenetre, raccourci.

    Un contour sombre epais sous le trace dore. Une icone Windows se
    pose aussi bien sur une barre des taches claire que sombre, et un
    trait dore seul disparait sur un fond clair.

    Le meme dessin sert au fichier carruos.ico, fabrique a partir de ce
    SVG : une seule source, donc pas de derive entre l'onglet et le
    raccourci du Bureau.
    """
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="34 11 313 371">'
        '<defs><linearGradient id="or" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#f3dfae"/>'
        '<stop offset=".45" stop-color="#d8bd86"/>'
        '<stop offset="1" stop-color="#b8945a"/>'
        '</linearGradient></defs>'
        f'<path d="{trace}" fill="none" stroke="#0b1016" stroke-width="26" '
        'stroke-linejoin="round" stroke-linecap="round" opacity=".55"/>'
        f'<path d="{trace}" fill="none" stroke="url(#or)" stroke-width="13" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        '</svg>')


def fond(trace: str) -> str:
    """L'hologramme complet en fond de page : anneaux en rotation, cone de
    projection, socle lumineux et le cerf a la hauteur de l'ecran."""
    anneaux = (
        '<svg class="fond-anneaux" viewBox="0 0 250 250">'
        '<circle class="rot3" cx="125" cy="125" r="119" fill="none" '
        'stroke="rgba(var(--holo),.3)" stroke-width="1" vector-effect="non-scaling-stroke"/>'
        '<circle class="rot1" cx="125" cy="125" r="110" fill="none" '
        'stroke="rgba(var(--holo),.55)" stroke-width="1.2" vector-effect="non-scaling-stroke" stroke-dasharray="2 9"/>'
        '<circle class="rot2" cx="125" cy="125" r="100" fill="none" '
        'stroke="rgba(var(--holo),.85)" stroke-width="1.4" vector-effect="non-scaling-stroke" '
        'stroke-dasharray="42 26 8 26"/>'
        '<circle class="rot1" cx="125" cy="125" r="90" fill="none" '
        'stroke="rgba(var(--holo),.26)" stroke-width="3.5" vector-effect="non-scaling-stroke" stroke-dasharray="1 15"/>'
        '<circle class="rot3" cx="125" cy="125" r="77" fill="none" '
        'stroke="rgba(var(--holo),.36)" stroke-width="1" vector-effect="non-scaling-stroke" '
        'stroke-dasharray="18 7 3 7"/>'
        '</svg>')
    cerf = (
        '<svg class="fond-cerf" viewBox="34 11 313 371" '
        'preserveAspectRatio="xMidYMid meet">'
        f'<defs><path id="fond-t" d="{trace}"/></defs>'
        # vector-effect : l'epaisseur est donnee en pixels ECRAN, pas en
        # unites du viewBox. Le trait fait donc exactement 2 px quel que
        # soit l'ecran, au lieu d'etre etire avec le dessin.
        '<g opacity=".52" shape-rendering="geometricPrecision">'
        # Halo serre : un trait large et tres transparent SOUS le trait net.
        # Il ajoute de la lumiere sans toucher au contour, contrairement a
        # un flou qui, lui, deplacerait les pixels du contour lui-meme.
        '<use href="#fond-t" class="f-halo" fill="none" stroke="var(--acc)" '
        'stroke-width="7" vector-effect="non-scaling-stroke" '
        'stroke-linejoin="round" opacity=".13"/>'
        '<use href="#fond-t" class="f-halo" fill="none" stroke="#f5e3b8" '
        'stroke-width="3.6" vector-effect="non-scaling-stroke" '
        'stroke-linejoin="round" opacity=".2"/>'
        '<use href="#fond-t" class="f-c1" fill="none" stroke="#5ce6ff" '
        'stroke-width="1.5" vector-effect="non-scaling-stroke" '
        'transform="translate(-0.8,0)"/>'
        '<use href="#fond-t" class="f-c2" fill="none" stroke="#ffd089" '
        'stroke-width="1.5" vector-effect="non-scaling-stroke" '
        'transform="translate(0.8,0)"/>'
        '<use href="#fond-t" class="f-m" fill="none" stroke="#fff4d6" '
        'stroke-width="2.1" vector-effect="non-scaling-stroke" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        '</g></svg>')
    return ('<div class="fond" aria-hidden="true">'
            '<div class="fond-sol"></div>'
            '<div class="fond-cone"></div>'
            '<div class="fond-lueur"></div>'
            + anneaux + cerf
            + '<div class="fond-socle"></div>'
            '<div class="fond-ray"></div>'
            '<div class="fond-scan"></div>'
            '</div>')
