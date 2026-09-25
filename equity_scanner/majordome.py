"""Le majordome compagnon : le cerf de CARRUOS, et sa bulle.

« Je veux que quand j'active l'onglet MAJORDOME, le logo apparaisse avec
une bulle ou je peux converser avec lui, et que je puisse le deplacer ou
bon me semble. »

Le majordome vivait sur l'ACCUEIL seulement — un disque avec un micro,
un panneau fixe en bas a droite, et son script dans celui de la page.
Les six autres fenetres n'en avaient pas. Il est ici, en un seul
endroit, et chaque page le pose :

* l'avatar est le cerf du logo, celui qui est en fond de chaque page ;
* la bulle s'ouvre du cote ou il y a de la place, avec sa queue tournee
  vers le cerf ;
* on le prend par le cerf ou par l'entete de la bulle et on le pose ou
  l'on veut. La position est enregistree cote serveur (`reglages`), en
  FRACTION de la fenetre : une fenetre plus petite ne l'envoie pas hors
  champ ;
* l'onglet MAJORDOME de la barre le fait apparaitre, ouvre la bulle,
  puis le range. Toutes les fenetres suivent, par la meme verification
  que le visuel.

Ce qui ne change pas, c'est le contrat. Les FAITS d'abord, calcules par
le serveur avant tout appel au modele et affiches quoi qu'il arrive ; la
prose du modele par-dessus, jamais a la place ; chaque chiffre du modele
confronte au dossier envoye, et ceux qui n'en viennent pas NOMMES. Le
majordome ne dit ni « achete », ni « vends », ni « garde ».

Les commandes propres a l'accueil (ACTUALISER, lancer un scan) ne sont
executees que la ou elles existent. Ailleurs, le majordome le dit et
ouvre l'accueil, plutot que d'appeler une fonction absente — ce qui
planterait sans un mot.
"""
from __future__ import annotations

import html as _html

from . import hud as hd
from . import reglages as rg

# La taille de l'avatar, en pixels. Le script la relit dans le DOM :
# une seule valeur, pas deux qui divergent.
TAILLE = 58

CSS = """
/* --- Le majordome compagnon (majordome.py). Pose sur TOUTES les pages :
       ses classes sont prefixees `mj-` et ne dependent d'aucune regle
       d'une page — un bouton ou un champ ne ressemblent pas a ceux de
       l'accueil par hasard, ils sont regles ici. --- */
/* Sous le tiroir des reglages (59) : ouvert, il passe devant le cerf au
   lieu d'avoir le bas de sa liste cache par lui. */
.mjc{position:fixed;left:0;top:0;z-index:58;width:58px;height:58px;
 transform:translate3d(-300px,-300px,0);visibility:hidden}
.mjc.pret{visibility:visible}
.mjc.cache{display:none}
.mj-a{position:relative;z-index:3;width:58px;height:58px;padding:0;
 border-radius:50%;display:grid;place-items:center;cursor:grab;
 touch-action:none;user-select:none;
 background:radial-gradient(circle at 50% 36%,rgba(var(--holo),.16),
 var(--fond) 70%);
 border:1px solid var(--bord-fort);
 box-shadow:0 0 22px rgba(var(--holo),.2),0 6px 18px rgba(0,0,0,.5);
 transition:box-shadow .18s ease,border-color .18s ease}
.mj-a:hover{border-color:var(--acc);
 box-shadow:0 0 32px rgba(var(--holo),.38),0 6px 18px rgba(0,0,0,.5)}
.mjc.glisse .mj-a{cursor:grabbing}
.mj-a svg{width:40px;height:46px;pointer-events:none;overflow:visible}
.mj-a .mj-cerf{fill:none;stroke:url(#mj-or);stroke-width:13;
 stroke-linejoin:round;stroke-linecap:round}
.mj-a .mj-ombre{fill:none;stroke:#0b1016;stroke-width:26;
 stroke-linejoin:round;opacity:.55}
.mj-o{position:absolute;inset:-5px;border-radius:50%;pointer-events:none;
 border:1px dashed rgba(var(--holo),.5);animation:mj-tour 24s linear infinite}
.mjc.parle .mj-o{border-color:var(--marque);border-style:solid;
 animation:mj-tour 24s linear infinite,mj-pouls 1.2s ease-in-out infinite}
.mjc.ecoute .mj-o{border-color:var(--pos);border-style:solid;
 animation:mj-tour 24s linear infinite,mj-pouls 1.4s ease-in-out infinite}
@keyframes mj-tour{to{transform:rotate(360deg)}}
@keyframes mj-pouls{0%,100%{opacity:.35}50%{opacity:1}}
/* La bulle. Placee par le script, du cote ou il y a de la place. */
.mj-b{position:absolute;z-index:2;display:none;width:350px;
 max-height:420px;overflow-y:auto;overscroll-behavior:contain;
 padding:11px 13px 12px;border-radius:14px;
 background:var(--fond);border:1px solid var(--bord-fort);
 box-shadow:0 14px 42px rgba(0,0,0,.6),0 0 26px rgba(var(--holo),.1);
 font:400 12px/1.58 var(--corps-police);color:var(--txt-fort);
 text-align:left;letter-spacing:0}
.mjc.ouvert .mj-b{display:block}
/* La queue : un carre tourne SOUS la bulle, dont seule la moitie
   depasse. Elle ne vit pas dans la bulle, qui defile et la couperait. */
.mj-q{position:absolute;z-index:1;display:none;width:14px;height:14px;
 background:var(--fond);border:1px solid var(--bord-fort);
 transform:rotate(45deg)}
.mjc.ouvert .mj-q{display:block}
.mj-h{display:flex;align-items:center;gap:6px;margin:-1px 0 8px;
 cursor:grab;user-select:none;touch-action:none}
.mj-t{flex:1;min-width:0;font:500 8.5px ui-monospace,Consolas,monospace;
 letter-spacing:.26em;color:var(--marque);white-space:nowrap}
.mj-t span{color:var(--txt-faible);letter-spacing:.14em}
.mjc button.mj-p{flex:none;background:var(--champ-fond);
 border:1px solid var(--bord);color:var(--txt-doux);cursor:pointer;
 font:500 8.5px ui-monospace,Consolas,monospace;letter-spacing:.12em;
 padding:4px 7px;border-radius:6px;
 transition:color .16s ease,border-color .16s ease}
.mjc button.mj-p:hover{color:var(--acc);border-color:var(--acc)}
.mjc button.mj-x{font-size:13px;line-height:1;padding:2px 7px}
.mjc button.mj-x:hover{color:var(--neg);border-color:var(--neg)}
.mj-r{min-height:36px;word-wrap:break-word}
.mj-r b{color:var(--acc);font-weight:500}
.mj-l{display:flex;gap:6px;margin-top:9px}
.mj-l input,.mj-l select{flex:1;min-width:0;background:var(--champ-fond);
 border:1px solid var(--bord);color:var(--txt-fort);padding:7px 9px;
 border-radius:7px;font:400 12px var(--corps-police);outline:none}
.mj-l select{flex:0 0 122px;font-size:11px}
.mj-l input:focus{border-color:var(--acc)}
.mjc button.mj-g{flex:none;background:var(--champ-fond);
 border:1px solid var(--bord-fort);color:var(--acc);cursor:pointer;
 font:500 9.5px ui-monospace,Consolas,monospace;letter-spacing:.12em;
 padding:6px 10px;border-radius:7px;
 transition:background-color .16s ease,color .16s ease}
.mjc button.mj-g:hover{background:var(--bord)}
.mjc button.mj-g.mj-ko{color:var(--txt-faible);border-color:var(--bord)}
.mj-e{margin-top:8px;font-size:10px;line-height:1.55;color:var(--txt-faible)}
.mj-ia{margin-top:10px;padding:8px 10px;border:1px solid var(--bord);
 border-left:2px solid var(--acc);border-radius:8px;
 background:rgba(var(--holo),.05)}
.mj-iat{display:block;font:500 8px ui-monospace,Consolas,monospace;
 letter-spacing:.22em;color:var(--acc);margin-bottom:5px}
.mj-iax{margin-top:7px;padding-top:6px;border-top:1px solid var(--bord);
 font-size:10px;line-height:1.55;color:var(--neg)}
.mj-iao{margin-top:7px;padding-top:6px;border-top:1px solid var(--bord);
 font-size:10px;line-height:1.55;color:var(--txt-faible)}
.mj-ias{margin-top:7px;display:flex;flex-direction:column;gap:3px}
.mj-ias a{color:var(--acc);overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
.mj-cle{margin-top:10px;padding-top:8px;border-top:1px solid var(--bord)}
.mj-cle summary{cursor:pointer;list-style:none;
 font:500 8px ui-monospace,Consolas,monospace;letter-spacing:.2em;
 color:var(--txt-faible)}
.mj-cle summary::-webkit-details-marker{display:none}
.mj-cle summary.on{color:var(--acc)}
/* L'onglet de la barre dit si le majordome est sorti. */
.raf.ong.mj-on{border-color:var(--acc);color:var(--txt-fort)}
"""


def _svg_cerf() -> str:
    # Le meme cerf que l'icone et que le fond : une seule source, le trace
    # de hud.py. Degrade propre (`mj-or`) : l'identifiant `or` de
    # hud.icone() pourrait un jour cohabiter dans la meme page.
    return ('<svg viewBox="34 11 313 371" aria-hidden="true">'
            '<defs><linearGradient id="mj-or" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0" stop-color="#f3dfae"/>'
            '<stop offset=".45" stop-color="#d8bd86"/>'
            '<stop offset="1" stop-color="#b8945a"/>'
            '</linearGradient></defs>'
            f'<path class="mj-ombre" d="{hd.TRACE}"/>'
            f'<path class="mj-cerf" d="{hd.TRACE}"/></svg>')


def etat(reg: dict | None) -> dict:
    """Sorti ou range, et ou. La lecture bornee vit dans `reglages` : la
    page et la verification du visuel lisent la meme."""
    return rg.majordome(reg or {})


def html(reg: dict | None = None, ticker: str = "", champ: str = "") -> str:
    """Le compagnon. `ticker` est le titre de la page (graphique) : c'est
    lui dont on parle quand la question n'en nomme aucun. `champ` est
    l'identifiant d'un champ de saisie de la page dont la valeur, si elle
    existe, passe avant (« analyser un titre » sur l'accueil)."""
    e = etat(reg)
    tk = _html.escape((ticker or "").strip().upper(), quote=True)
    ch = _html.escape(champ or "", quote=True)
    return (
        f'<div class="mjc{"" if e["actif"] else " cache"}" id="mjc" '
        f'data-actif="{1 if e["actif"] else 0}" data-x="{e["x"]:.4f}" '
        f'data-y="{e["y"]:.4f}" data-ticker="{tk}" data-champ="{ch}">'
        '<button class="mj-a" id="mja" type="button" '
        'title="Majordome : cliquer pour lui parler, glisser pour le '
        'déplacer" aria-label="Majordome">' + _svg_cerf()
        + '<i class="mj-o"></i></button>'
        '<i class="mj-q" id="mjq"></i>'
        '<div class="mj-b" id="mjb" role="dialog" aria-label="Majordome">'
        '<div class="mj-h" id="mjh">'
        '<div class="mj-t">MAJORDOME <span>· MENTOR</span></div>'
        '<button class="mj-p" type="button" data-vers="/majordome" '
        'data-fen="carruos-majordome" title="Les faits et le cerveau, '
        'sur une page entière">VUE COMPLÈTE</button>'
        '<button class="mj-p" id="mjrange" type="button" '
        'title="Ranger le majordome (l\'onglet MAJORDOME le rappelle)">'
        'RANGER</button>'
        '<button class="mj-p mj-x" id="mjx" type="button" '
        'title="Fermer la bulle (Echap)">&times;</button></div>'
        '<div class="mj-r" id="mjr">Parlez-moi d\'un titre, de votre '
        'portefeuille, d\'un projet. Je réponds à partir de faits, à voix '
        'haute. Glissez-moi où vous voulez.</div>'
        '<div class="mj-l"><input id="mji" placeholder="votre question" '
        'autocomplete="off" spellcheck="false">'
        '<button class="mj-g" id="mjenv" type="button">ENVOYER</button>'
        '</div>'
        '<div class="mj-l">'
        '<button class="mj-g" id="mjmic" type="button">MICRO</button>'
        '<button class="mj-g" id="mjdiag" type="button">DIAGNOSTIC</button>'
        '<button class="mj-g" id="mjweb" type="button">EDGE</button></div>'
        '<div class="mj-e">je sors quand sur TLX &middot; combien je peux '
        'perdre sur Coin &middot; que penses-tu de Nvidia &middot; une '
        'figure sur Hood ? &middot; on garde TLX combien de temps &middot; '
        'ouvre sanofi &middot; scan cac 40 &middot; état du marché '
        '&middot; mes positions &middot; la veille sur mes lignes</div>'
        '<details class="mj-cle"><summary id="mjiae">CERVEAU &mdash;'
        '</summary>'
        '<div class="mj-l"><select id="mjiaf">'
        '<option value="anthropic">Claude (Anthropic)</option>'
        '<option value="openai">OpenAI</option></select>'
        '<input id="mjiak" type="password" placeholder="votre clé API" '
        'autocomplete="off"></div>'
        '<div class="mj-l">'
        '<button class="mj-g" id="mjiapose" type="button">BRANCHER</button>'
        '<button class="mj-g" id="mjiaoubli" type="button">EFFACER</button>'
        '</div>'
        '<div class="mj-e">CARRUOS n\'embarque aucune clé et ne peut pas '
        'en fabriquer une : celle-ci est la vôtre, prise chez le '
        'fournisseur, rangée dans ~/.carruos/ia.json — jamais dans le '
        'programme ni dans l\'archive. Sans elle, le majordome répond '
        'quand même : les faits sont calculés en local.</div>'
        '</details></div></div>')


# En dessous de ce mouvement (en pixels), un appui sur le cerf est un
# CLIC : il ouvre ou ferme la bulle. Au-dela, c'est un deplacement.
SEUIL_GLISSE = 5

# Le script. Une fonction anonyme executee tout de suite : rien n'est
# global sauf `window.CARRUOS_MAJ`, que la barre (onglet MAJORDOME) et la
# verification du visuel appellent. Une page qui a son propre `MAJ`,
# son propre `$` ou son propre `scan` ne peut donc pas entrer en
# collision avec lui.
JS = r"""
(function(){
'use strict';
function _mj(i){ return document.getElementById(i); }
var C=_mj('mjc');
if(!C) return;
var A=_mj('mja'), B=_mj('mjb'), Q=_mj('mjq'), H=_mj('mjh'), R=_mj('mjr'),
    I=_mj('mji');
var T=A.offsetWidth || 58;
var E={actif:C.getAttribute('data-actif')==='1',
       x:parseFloat(C.getAttribute('data-x')), y:parseFloat(C.getAttribute('data-y')),
       ouvert:false};
if(!(E.x>=0 && E.x<=1)) E.x=.965;
if(!(E.y>=0 && E.y<=1)) E.y=.9;
var M={ecoute:false, reco:null, micKo:false, recu:false};
var HIST=[];

function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;')
  .replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function borne(v,a,b){ return Math.max(a, Math.min(b, v)); }

// --- Position ----------------------------------------------------------
//
// Le deplacement passe par `transform`, jamais par left/top : c'est la
// regle du projet pour tout ce qui bouge, et elle vient d'une page qui
// sautait. La position est gardee en FRACTION de la fenetre.
var P={x:0, y:0};
function place(px, py){
 var W=window.innerWidth, Ht=window.innerHeight;
 P.x=borne(px, 8, Math.max(8, W-T-8));
 P.y=borne(py, 8, Math.max(8, Ht-T-8));
 C.style.transform='translate3d('+Math.round(P.x)+'px,'+Math.round(P.y)+'px,0)';
}
function pose(){
 place(E.x*window.innerWidth - T/2, E.y*window.innerHeight - T/2);
 if(E.ouvert) bulle();
}
// La bulle s'ouvre du cote ou il y a de la place : au-dessus si le cerf
// est dans la moitie basse, en dessous sinon ; centree sur lui, puis
// ramenee dans la fenetre. La queue reste pointee sur le cerf.
function bulle(){
 var W=window.innerWidth, Ht=window.innerHeight;
 var bw=Math.min(360, W-16);
 B.style.width=bw+'px';
 var cy=P.y+T/2, haut=cy>Ht/2;
 var dispo=haut ? (P.y-14-10) : (Ht-(P.y+T)-14-10);
 B.style.maxHeight=Math.max(150, Math.min(560, dispo))+'px';
 var g=borne(P.x+T/2-bw/2, 8, Math.max(8, W-bw-8));
 B.style.left=Math.round(g-P.x)+'px';
 if(haut){ B.style.top=''; B.style.bottom=(T+14)+'px'; }
 else{ B.style.bottom=''; B.style.top=(T+14)+'px'; }
 Q.style.left=(T/2-7)+'px';
 Q.style.top=(haut ? -21 : T+7)+'px';
}
function enregistre(o){
 try{
  fetch('/api/reglages',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({majordome:o})}).catch(function(){});
 }catch(e){}
}

// --- Glisser -------------------------------------------------------------
//
// On le prend par le cerf OU par l'entete de la bulle. Moins de 5 px de
// mouvement, c'est un clic : il ouvre ou ferme la bulle. Au-dela, c'est
// un deplacement, et le clic qui suit est ignore.
var G=null, apresGlisse=false;
function debut(ev){
 if(ev.button!=null && ev.button!==0) return;
 if(ev.currentTarget===H && ev.target.closest && ev.target.closest('button'))
  return;
 G={sx:ev.clientX, sy:ev.clientY, px:P.x, py:P.y, bouge:false};
 try{ ev.currentTarget.setPointerCapture(ev.pointerId); }catch(e){}
}
function bouge(ev){
 if(!G) return;
 var dx=ev.clientX-G.sx, dy=ev.clientY-G.sy;
 if(!G.bouge && Math.abs(dx)+Math.abs(dy)<__SEUIL__) return;
 G.bouge=true;
 C.classList.add('glisse');
 place(G.px+dx, G.py+dy);
}
function fin(){
 if(!G) return;
 var g=G; G=null;
 C.classList.remove('glisse');
 if(!g.bouge) return;
 apresGlisse=true;
 setTimeout(function(){ apresGlisse=false; }, 0);
 E.x=+((P.x+T/2)/window.innerWidth).toFixed(4);
 E.y=+((P.y+T/2)/window.innerHeight).toFixed(4);
 if(E.ouvert) bulle();
 enregistre({x:E.x, y:E.y});
}
[A, H].forEach(function(el){
 el.addEventListener('pointerdown', debut);
 el.addEventListener('pointermove', bouge);
 el.addEventListener('pointerup', fin);
 el.addEventListener('pointercancel', fin);
});

// --- Sortir, ouvrir, fermer, ranger -------------------------------------
function onglet(){
 document.querySelectorAll('[data-bascule="majordome"]').forEach(function(b){
  b.classList.toggle('mj-on', E.actif); });
}
function montre(v, garde){
 E.actif=!!v;
 C.classList.toggle('cache', !E.actif);
 if(E.actif) pose();
 onglet();
 if(garde!==false) enregistre({actif:E.actif});
}
function ouvre(){
 if(!E.actif) montre(true);
 E.ouvert=true;
 C.classList.add('ouvert');
 bulle();
 // L'etat du cerveau se relit a chaque ouverture : la cle a pu etre
 // posee ou retiree depuis, et une bulle qui ne dit pas s'il est
 // branche laisse croire qu'il l'est.
 iaEtat();
 try{ I.focus({preventScroll:true}); }catch(e){}
}
function ferme(){
 E.ouvert=false;
 C.classList.remove('ouvert');
 stop();
 try{ if(window.speechSynthesis) speechSynthesis.cancel(); }catch(e){}
 C.classList.remove('parle');
}
function range(){ ferme(); montre(false); }
// L'onglet MAJORDOME : il sort le cerf et ouvre la bulle ; bulle
// ouverte, il le range.
function bascule(){
 if(!E.actif || !E.ouvert){ ouvre(); dit('À votre service.', false); return; }
 range();
}
A.addEventListener('click', function(){
 if(apresGlisse) return;
 if(E.ouvert){ ferme(); return; }
 ouvre();
 dit('À votre service.', false);
});
_mj('mjx').addEventListener('click', ferme);
_mj('mjrange').addEventListener('click', range);
// Echap ferme la bulle depuis n'importe ou : c'est le reflexe, et c'est
// le filet quand la souris ne trouve plus de bouton.
document.addEventListener('keydown', function(e){
 if(e.key==='Escape' && E.ouvert) ferme(); });
I.addEventListener('keydown', function(e){
 if(e.key==='Enter') exec(I.value); });
_mj('mjenv').addEventListener('click', function(){ exec(I.value); });
_mj('mjmic').addEventListener('click', ecoute);
_mj('mjdiag').addEventListener('click', diag);
_mj('mjweb').addEventListener('click', web);
_mj('mjiapose').addEventListener('click', iaPose);
_mj('mjiaoubli').addEventListener('click', iaOublie);
window.addEventListener('resize', pose);

// Les autres fenetres suivent : la verification du visuel (reglages.py)
// transmet l'etat enregistre. On ne deplace pas un cerf qu'on est en
// train de tenir, ni une bulle ouverte sous les doigts.
function sync(m){
 if(!m || G) return;
 if(!!m.actif!==E.actif){
  if(!m.actif) ferme();
  montre(m.actif, false);
 }
 if(!E.ouvert && (Math.abs(m.x-E.x)>1e-3 || Math.abs(m.y-E.y)>1e-3)){
  E.x=m.x; E.y=m.y; pose();
 }
}

// --- La voix -------------------------------------------------------------
//
// Voix posee, phrases courtes, aucune flatterie et aucune incitation.
if(window.speechSynthesis){
 try{
  speechSynthesis.getVoices();
  speechSynthesis.addEventListener('voiceschanged', function(){
   speechSynthesis.getVoices(); });
 }catch(e){}
}
function dit(txt, ecrire){
 // Une legere ponctuation fait respirer la synthese.
 txt=String(txt).replace(/\. /g, '.  ');
 if(ecrire!==false) R.textContent=txt;
 if(!window.speechSynthesis) return;
 try{
  speechSynthesis.cancel();
  var u=new SpeechSynthesisUtterance(txt);
  u.lang='fr-FR'; u.rate=0.88; u.pitch=0.7; u.volume=1.0;
  // Voix masculines francaises connues, puis toute voix masculine, puis
  // n'importe quelle voix francaise. Les voix « Natural » de Windows 11
  // sont nettement meilleures que les anciennes.
  var v=speechSynthesis.getVoices().filter(function(x){
   return x.lang && x.lang.toLowerCase().indexOf('fr')===0; });
  var ordre=[/Henri.*Natural/i,/Paul.*Natural/i,/Remy.*Natural/i,
   /Claude.*Natural/i,/Natural/i,/Henri|Paul|Remy|Thierry|Guillaume|Claude/i,
   /Male|Homme/i];
  var choix=null;
  for(var i=0;i<ordre.length && !choix;i++)
   choix=v.find(function(x){ return ordre[i].test(x.name); });
  if(choix||v[0]) u.voice=choix||v[0];
  u.onstart=function(){ C.classList.add('parle'); };
  u.onend=function(){ C.classList.remove('parle'); };
  speechSynthesis.speak(u);
 }catch(e){}
}

// --- Ce qu'on lui demande -----------------------------------------------
var UNIV={'cac':'cac40','cac 40':'cac40','dax':'dax','europe':'europe_total',
 'stoxx':'stoxx600','nasdaq':'nasdaq100','sp 500':'sp500','s&p 500':'sp500',
 'etats-unis':'us_total','amerique':'us_total','us':'us'};
function accueil(){
 if(typeof window.ouvreFenetre==='function') ouvreFenetre('/', 'carruos-accueil');
}
async function exec(txt){
 var brut=(txt||'').trim();
 // Les motifs sont ecrits sans accents : « état du marché » et « etat du
 // marche » doivent aller au meme endroit.
 var q=brut.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
 if(!q){ dit('Je vous écoute.'); return; }
 I.value='';

 if(/actualise|rafraich|met a jour/.test(q)){
  if(typeof window.toutRafraichir==='function'){
   dit('Je rafraîchis les données.');
   await window.toutRafraichir();
   dit('Données à jour.');
  }else{
   try{ await fetch('/api/actus?force=1'); }catch(e){}
   dit('Actualités rafraîchies. Pour le reste, rechargez la page, '
    +'ou utilisez ACTUALISER sur l\'accueil.');
  }
  return;
 }
 // « Mes positions », pas « je garde ma position sur TLX ? » : cette
 // question-la est une question de SORTIE, et c'est le cerveau qui
 // rend les quatre conditions.
 if(/^(?:mes |les )?positions?\s*\??$|\bmes positions\b/.test(q)){
  try{
   var j=await (await fetch('/api/positions')).json();
   var L=j.lignes||[], n=L.length;
   if(!n) return dit('Aucune position enregistrée.');
   // Des COMPTES, pas un avis : combien ont une condition de sortie
   // de la specification active, combien sont sous leur stop inscrit.
   var s=L.filter(function(l){ return (l.n_sorties||0)>0; }).length;
   var st=L.filter(function(l){ return l.marge_stop!=null && l.marge_stop<=0; }).length;
   dit(n+(n>1?' lignes ouvertes. ':' ligne ouverte. ')
    +(s ? s+(s>1?' ont':' a')+' au moins une condition de sortie active. '
        : 'Aucune condition de sortie active. ')
    +(st ? st+(st>1?' sont':' est')+' sous le stop inscrit.' : ''));
  }catch(e){ dit('Je n\'arrive pas à lire vos positions.'); }
  return;
 }
 if(/^(?:l')?etat du marche|^(?:le )?regime|^marche\s*\??$/.test(q)){
  try{
   var je=await (await fetch('/api/etat')).json();
   dit(je.verdict ? je.verdict.toLowerCase().replace(/_/g,' ')
    : 'État du marché indisponible.');
  }catch(e){ dit('État du marché indisponible.'); }
  return;
 }
 if(/actualit|nouvelle|news|geopolit|veille|mes lignes/.test(q)){
  try{
   var jv=await (await fetch('/api/veille')).json();
   var it=(jv.items||[])[0];
   if(it && (it.erreur || it.sans_cle)){
    dit(it.titre || 'Aucune clé Alpha Vantage : pas d\'actualités.'); return; }
   // Ce qui touche SES lignes passe devant une depeche quelconque.
   var n1=[], n2=[];
   (jv.items||[]).forEach(function(a){ var v=a.vous||{};
    (v.titres||[]).forEach(function(t){ if(n1.indexOf(t)<0) n1.push(t); });
    Object.keys(v.secteurs||{}).forEach(function(sec){
     (v.secteurs[sec]||[]).forEach(function(t){
      if(n2.indexOf(t)<0 && n1.indexOf(t)<0) n2.push(t); }); }); });
   var h='';
   if(n1.length) h+='<b>Nommés par la source :</b> '+esc(n1.join(', '))+'.<br>';
   if(n2.length) h+='<b>Même secteur déclaré :</b> '+esc(n2.join(', '))
     +' &mdash; correspondance de noms, pas de causes.<br>';
   if(!h) h='Aucune actualité du jour ne rencontre vos lignes.<br>';
   (jv.items||[]).slice(0,4).forEach(function(a){
    var t=a.ton;
    h+='<br>'+(t && t.libelle ? '<b>'+esc(t.libelle)+'</b> &middot; ' : '')
      +esc(a.titre||''); });
   h+='<br><br><span class="mj-e">'+esc(jv.rappel||'')
     +' Positif / négatif : l\'étiquette d\'Alpha Vantage, pas une '
     +'prévision du cours.</span>';
   R.innerHTML=h;
   dit(n1.length ? ('Ces titres sont nommés aujourd\'hui : '+n1.join(', ')+'.')
    : (n2.length ? ('Rien ne vous nomme. Même secteur déclaré : '+n2.join(', ')+'.')
       : 'Aucune actualité du jour ne rencontre vos lignes.'), false);
  }catch(e){ dit('Actualités indisponibles.'); }
  return;
 }
 var ms=q.match(/scan(?:ne|ner)?\s+(.+)/);
 if(ms){
  var cle=Object.keys(UNIV).find(function(k){ return ms[1].indexOf(k)>=0; });
  if(!cle) return dit('Quel univers ? Cac 40, Dax, Europe, Nasdaq, '
   +'S et P 500, ou toute la cote américaine.');
  if(typeof window.scan==='function'){
   dit('Je lance le scan. Cela peut prendre plusieurs minutes.');
   window.scan(UNIV[cle], 'us');
  }else{
   dit('Le scan se lance depuis l\'accueil : je vous l\'ouvre.');
   accueil();
  }
  return;
 }
 var ma=q.match(/^(?:analyse|regarde|ouvre|affiche)\s+(.+)/);
 if(ma && !/portefeuille|mes lignes/.test(q)){
  var t=ma[1].replace(/[.?!]/g,'').trim();
  dit('J\'ouvre '+t+'.');
  try{
   var ja=await (await fetch('/api/analyse?ticker='+encodeURIComponent(t))).json();
   if(ja.ok && typeof window.ouvreFenetre==='function'){
    ouvreFenetre('/graphique?ticker='+encodeURIComponent(ja.ticker),
                 'carruos-'+ja.ticker);
    return;
   }
   dit(ja.erreur || ('Je ne trouve pas '+t+'.'));
  }catch(e){ dit('Je n\'ai pas pu ouvrir '+t+'.'); }
  return;
 }
 // Tout le reste part au cerveau : il rend les FAITS calcules par le
 // serveur, et par-dessus, si une cle est enregistree, la mise en
 // phrases d'un modele. C'est le serveur qui tranche quel mot est un
 // ticker : il a les donnees, le navigateur non.
 if(await cerveau(brut)) return;

 dit('Je n\'ai pas compris. Essayez : je sors quand sur TLX, combien je '
  +'peux perdre sur Coin, que penses-tu de Nvidia, ouvre Sanofi, '
  +'scan Cac 40, état du marché, la veille sur mes lignes, ou mes positions.');
}

// --- Le dossier, et le cerveau par-dessus -------------------------------
//
// Rien n'est genere ici. Le serveur rend des LIGNES deja ecrites a partir
// des chiffres des modules ; le majordome les affiche et en lit la
// premiere a voix haute.
async function cerveau(q){
 // Le titre dont on parle quand la question n'en nomme aucun : celui du
 // champ que la page a DECLARE (l'accueil : « analyser un titre »), ou
 // celui de la page (un graphique).
 var dflt='';
 try{
  var ch=C.getAttribute('data-champ'), el=ch ? document.getElementById(ch) : null;
  dflt=(el && el.value ? el.value.trim() : '') || C.getAttribute('data-ticker') || '';
 }catch(e){}
 try{
  dit('Je regarde.', false);
  var j=await (await fetch('/api/cerveau',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({q:q, ticker:dflt, historique:HIST})})).json();
  if(!j.ok) return false;

  var f=j.faits, h='';
  // Les FAITS. Calcules avant tout appel reseau, affiches quoi qu'il
  // advienne du modele.
  if(f && f.ok){
   h+='<b>'+esc(f.ticker)+'</b> &mdash; '+esc(f.titre)+'<br><br>';
   f.lignes.forEach(function(l){ h+=(l ? esc(l) : '')+'<br>'; });
  }else if(f && f.erreur){
   h+='<span style="color:var(--neg)">'+esc(f.erreur)+'</span><br><br>';
  }

  // La prose du modele, par-dessus, jamais a la place.
  var m=j.modele || {};
  if(m.ok && m.texte){
   h+='<div class="mj-ia"><span class="mj-iat">CERVEAU &middot; '
     +esc(m.modele||'')+'</span>'+esc(m.texte).replace(/\n/g,'<br>');
   var src=m.sources || [];
   if(src.length){
    h+='<div class="mj-ias"><span class="mj-iat">SOURCES WEB</span>';
    src.forEach(function(s){
     h+='<a href="'+esc(s.url)+'" target="_blank" rel="noopener">'
       +esc(s.titre)+'</a>'; });
    h+='</div>';
   }
   var c=m.chiffres || {};
   if(c.n_hors){
    h+='<div class="mj-iax">'+c.n_hors+' chiffre'+(c.n_hors>1?'s':'')
      +' de cette réponse ne vien'+(c.n_hors>1?'nent':'t')+' pas du dossier : '
      +esc(c.hors_dossier.join(', '))
      +(src.length ? '. S\'ils viennent d\'une source Web citée, c\'est elle '
         +'qui fait foi ; sinon, ils ne sont pas vérifiables ici.</div>'
         : '. Ils ne sont pas vérifiables ici.</div>');
   }else if(c.n_traces){
    h+='<div class="mj-iao">Les '+c.n_traces
      +' chiffres de cette réponse viennent tous du dossier.</div>';
   }
   if((m.omis||[]).length){
    h+='<div class="mj-iao">Non envoyé au modèle, faute de place : '
      +esc(m.omis.join(', '))+'.</div>';
   }
   h+='</div>';
   HIST.push({role:'user',content:q},{role:'assistant',content:m.texte});
   if(HIST.length>20) HIST=HIST.slice(-20);
  }else if(m.configure===false){
   h+='<div class="mj-iax">Le cerveau n\'est pas branché : aucune clé '
     +'enregistrée. Les faits ci-dessus sont calculés par le programme '
     +'et ne demandent aucune clé.</div>';
  }else if(m.erreur && m.configure){
   h+='<div class="mj-iax">Le cerveau n\'a pas répondu : '+esc(m.erreur)
     +'. Les faits ci-dessus restent valables.</div>';
  }

  if(!h) return false;
  if(f && f.ok) h+='<br><span class="mj-e">'+esc(j.rappel)+'</span>';
  R.innerHTML=h;
  if(E.ouvert) bulle();
  dit((m.ok && m.texte) ? m.texte.split(/[.!?]\s/)[0]
                        : (f && f.ok ? f.titre : 'Voilà.'), false);
  return true;
 }catch(e){ return false; }
}

// --- La cle du cerveau ----------------------------------------------------
//
// Le programme n'embarque aucune cle. Celle-ci est la votre, rangee dans
// ~/.carruos/ia.json en 0600. Elle part au serveur, jamais elle n'en
// revient : la page n'en affiche que l'etat.
async function iaEtat(){
 try{
  var j=await (await fetch('/api/cerveau/etat')).json();
  var e=_mj('mjiae');
  e.textContent=j.configure
   ? ('CERVEAU BRANCHÉ · '+j.fournisseur_nom+' · '+j.modele)
   : ('CERVEAU NON BRANCHÉ · clé à prendre sur '+j.ou);
  e.classList.toggle('on', !!j.configure);
 }catch(e){}
}
async function iaPose(){
 var k=(_mj('mjiak').value||'').trim();
 if(!k){ _mj('mjiae').textContent='Collez la clé puis rappuyez.'; return; }
 _mj('mjiae').textContent='Enregistrement…';
 try{
  await fetch('/api/cerveau/config',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({fournisseur:_mj('mjiaf').value, cle:k})});
  _mj('mjiak').value='';
 }catch(e){}
 iaEtat();
}
async function iaOublie(){
 try{ await fetch('/api/cerveau/config',{method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({action:'oublie'})}); }catch(e){}
 iaEtat();
}

async function web(){
 // window.open() est bloque ou detourne dans la fenetre Windows : on
 // demande au serveur d'ouvrir le navigateur par defaut.
 try{
  var j=await (await fetch('/api/navigateur')).json();
  if(j.ok){
   dit('Page ouverte dans le navigateur. Le micro y fonctionne.', false);
   R.innerHTML='CARRUOS est ouvert dans votre navigateur. Le micro y '
    +'fonctionne.<br><span class="mj-e">'+esc(j.url)+'</span>';
   return;
  }
 }catch(e){}
 try{ window.open(location.href, '_blank'); }catch(e){}
 R.innerHTML='Ouvrez cette adresse dans Edge ou Chrome :<br>'
  +'<span style="color:var(--marque)">'+esc(location.href)+'</span>';
}

// --- Micro -----------------------------------------------------------------
//
// La reconnaissance vocale n'existe pas dans la fenetre Windows : le
// moteur WebView2 n'embarque pas le service de transcription de Chrome.
// Ce n'est pas un reglage a trouver, c'est une brique absente. On le dit
// une fois, et le champ texte fait le meme travail, a voix haute.
var MICRO_DIT={
 'no-speech':'Je n\'ai rien entendu. Le micro fonctionne, mais aucune '
  +'parole n\'est arrivée. Réessayez en parlant plus près.',
 'audio-capture':'Aucun micro détecté. Vérifiez qu\'il est branché et '
  +'choisi dans les réglages de son de Windows.',
 'not-allowed':'Le micro est refusé dans cette fenêtre. C\'est une '
  +'limite du cadre Windows, pas un réglage à corriger.',
 'service-not-allowed':'Le service de transcription n\'est pas '
  +'disponible dans cette fenêtre.',
 'network':'Le service de transcription n\'est pas joignable depuis '
  +'cette fenêtre. C\'est le cas normal du cadre Windows.',
 'aborted':'Écoute interrompue.'
};
function microIndispo(txt){
 var b=_mj('mjmic');
 b.classList.add('mj-ko'); b.textContent='MICRO INDISPO';
 M.micKo=true;
 R.innerHTML=esc(txt)+'<br><span style="color:var(--marque)">Écrivez '
  +'ci-dessous</span> : je réponds à voix haute, exactement comme à '
  +'l\'oral. Le bouton EDGE ouvre la même page dans le navigateur, où '
  +'le micro fonctionne.';
 try{ I.focus(); }catch(e){}
}

// « J'appuie sur micro et rien ne se passe » : symptome d'une
// autorisation jamais DEMANDEE. getUserMedia pose franchement la
// question et repond toujours — accorde, refuse, ou aucun micro.
async function permission(){
 if(!window.isSecureContext && location.protocol!=='http:')
  return {ok:false, motif:'contexte'};
 if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia)
  return {ok:false, motif:'absent'};
 try{
  var flux=await navigator.mediaDevices.getUserMedia({audio:true});
  try{ flux.getTracks().forEach(function(t){ t.stop(); }); }catch(e){}
  return {ok:true};
 }catch(e){
  return {ok:false, motif:(e && e.name) || 'refus'};
 }
}
var PERM_DIT={
 'NotAllowedError':'Le micro est REFUSÉ pour cette page. Cliquez le '
  +'cadenas à gauche de l\'adresse, puis Micro, puis Autoriser. Si le '
  +'réglage est grisé, c\'est Windows qui bloque : Paramètres, '
  +'Confidentialite, Microphone, et activez l\'accès pour les '
  +'applications de bureau.',
 'NotFoundError':'Aucun micro n\'est branché, ou aucun n\'est choisi '
  +'comme périphérique d\'entrée dans les réglages de son de Windows.',
 'NotReadableError':'Le micro est occupé par une autre application. '
  +'Fermez Teams, Discord ou Zoom, puis réessayez.',
 'SecurityError':'Le navigateur refuse le micro sur cette adresse.',
 'absent':'Ce navigateur n\'expose pas le micro. Utilisez Edge ou Chrome.',
 'contexte':'Le micro exige une adresse locale ou sécurisée.',
 'refus':'Le micro a été refusé.'
};

// Un bouton qui repond a la seule question utile : qu'est-ce qui
// bloque, exactement ? Chaque ligne est un fait verifiable.
async function diag(){
 ouvre();
 R.textContent='Diagnostic du micro en cours…';
 var L=[];
 var Rc=window.SpeechRecognition || window.webkitSpeechRecognition;
 L.push((window.isSecureContext?'OK':'NON')+' &nbsp; adresse considérée comme sûre');
 L.push(((navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
  ?'OK':'NON')+' &nbsp; le navigateur expose le micro');
 L.push((Rc?'OK':'NON')+' &nbsp; moteur de reconnaissance vocale présent');
 var etat='inconnu';
 try{
  if(navigator.permissions && navigator.permissions.query){
   var p0=await navigator.permissions.query({name:'microphone'});
   etat=p0.state;
  }
 }catch(e){}
 L.push((etat==='granted'?'OK':(etat==='denied'?'NON':'?  '))
  +' &nbsp; autorisation : '+esc(etat));
 var micros=0;
 try{
  var d=await navigator.mediaDevices.enumerateDevices();
  micros=d.filter(function(x){ return x.kind==='audioinput'; }).length;
 }catch(e){}
 L.push((micros?'OK':'NON')+' &nbsp; '+micros+' micro(s) détecté(s)');
 var p=await permission();
 L.push((p.ok?'OK':'NON')+' &nbsp; accès effectif au micro'
  +(p.ok?'':' ('+esc(p.motif)+')'));
 var conseil;
 if(!Rc) conseil='Le moteur de reconnaissance manque : ouvrez cette page '
  +'dans Edge ou Chrome (bouton EDGE).';
 else if(!p.ok) conseil=PERM_DIT[p.motif] || PERM_DIT['refus'];
 else conseil='Tout est en place. Cliquez MICRO et parlez.';
 R.innerHTML='<div style="font:11px ui-monospace,monospace;line-height:1.85">'
  +L.join('<br>')+'</div><div style="margin-top:9px;color:var(--marque)">'
  +esc(conseil)+'</div>';
 bulle();
}

function stop(){
 if(M.reco){ try{ M.reco.abort(); }catch(e){
   try{ M.reco.stop(); }catch(e2){} } }
 M.ecoute=false;
 C.classList.remove('ecoute');
}
function ecoute(){
 ouvre();
 if(M.ecoute){ stop(); R.textContent='Écoute arrêtée.'; return; }
 var Rc=window.SpeechRecognition || window.webkitSpeechRecognition;
 if(!Rc){
  microIndispo('Le micro n\'existe pas dans cette fenêtre.');
  dit('Le micro n\'est pas disponible ici. Écrivez votre question.', false);
  return;
 }
 R.textContent='Autorisation du micro…';
 permission().then(function(p){
  if(!p.ok){
   R.innerHTML=esc(PERM_DIT[p.motif] || PERM_DIT['refus'])
    +'<br><span class="mj-e">Le bouton DIAGNOSTIC dit précisément ce '
    +'qui bloque.</span>';
   dit('Le micro est refusé. Voyez le diagnostic.', false);
   try{ I.focus(); }catch(e){}
   return;
  }
  demarre(Rc);
 });
}
function demarre(Rc){
 var r;
 try{ r=new Rc(); }catch(e){ microIndispo('Le micro n\'a pas pu démarrer.'); return; }
 r.lang='fr-FR'; r.interimResults=false; r.maxAlternatives=1;
 M.reco=r; M.ecoute=true; M.recu=false;
 C.classList.add('ecoute');
 var b=_mj('mjmic');
 b.textContent='J\'ÉCOUTE…';
 R.textContent='Je vous écoute. Cliquez MICRO pour arrêter.';
 r.onresult=function(e){
  M.recu=true;
  var txt=e.results[0][0].transcript;
  R.textContent='« '+txt+' »';
  exec(txt);
 };
 r.onerror=function(e){
  var code=(e && e.error) || 'inconnu';
  var d=MICRO_DIT[code] || ('Le micro a rendu une erreur ('+code+').');
  // Une panne de service ne se repare pas en reessayant.
  if(code==='not-allowed' || code==='service-not-allowed'
     || code==='network' || code==='audio-capture'){
   microIndispo(d);
  }else{
   R.textContent=d;
   try{ I.focus(); }catch(e2){}
  }
  dit(d, false);
 };
 r.onend=function(){
  M.ecoute=false;
  C.classList.remove('ecoute');
  if(!M.micKo) _mj('mjmic').textContent='MICRO';
  if(!M.recu && R.textContent.indexOf('écoute')>=0){
   R.textContent='Rien n\'est arrivé. Écrivez ci-dessous.';
   try{ I.focus(); }catch(e){}
  }
 };
 // Un demarrage refuse ne leve pas toujours : il se passe TOUJOURS
 // quelque chose a l'ecran.
 try{ r.start(); }catch(e){
  stop();
  microIndispo('Le micro n\'a pas pu démarrer ('+(e.name || 'erreur')+').');
  return;
 }
 setTimeout(function(){
  if(M.ecoute && !M.recu && R.textContent.indexOf('écoute')>=0){
   R.innerHTML='Le micro ne répond pas. Cliquez <b>DIAGNOSTIC</b> pour '
    +'savoir pourquoi, ou écrivez ci-dessous.';
  }
 }, 9000);
}

window.CARRUOS_MAJ={bascule:bascule, ouvre:ouvre, ferme:ferme, range:range,
 exec:exec, dit:dit, sync:sync, etat:E};
pose();
onglet();
C.classList.add('pret');
})();
"""

JS = JS.replace("__SEUIL__", str(SEUIL_GLISSE))
