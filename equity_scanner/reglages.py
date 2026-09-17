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

DEFAUTS = {
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


def sauve(r: dict) -> dict:
    fusionne = _fusion(charge(), r)
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(fusionne, indent=1), encoding="utf-8")
    return fusionne


def variables(r: dict) -> str:
    """Les variables CSS : changer une couleur ici la propage partout."""
    d = {"normale": ("1", "14px"), "compacte": (".82", "13px"),
         "large": ("1.18", "15px")}
    ech, police = d.get(r.get("densite", "normale"), d["normale"])
    return (f":root{{--acc:{r['accent']};--marque:{r['marque']};"
            f"--fond:{r['fond']};--pos:{r['pos']};--neg:{r['neg']};"
            f"--ech:{ech};--police:{police}}}")


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
 font-size:12.5px;color:#94a3b8;padding:5px 0;cursor:pointer}
.sw{width:34px;height:18px;border-radius:10px;background:#1c2635;position:relative;
 flex:none;transition:.18s}
.sw::after{content:"";position:absolute;top:2px;left:2px;width:14px;height:14px;
 border-radius:50%;background:#5b6d85;transition:.18s}
.opt.on .sw{background:var(--acc)}
.opt.on .sw::after{left:18px;background:#05080d}
.dens{display:flex;gap:6px}
.dens button{flex:1;background:#121a24;border:1px solid #223044;color:#94a3b8;
 border-radius:7px;padding:7px;font-size:11.5px;cursor:pointer}
.dens button.sel{border-color:var(--acc);color:var(--acc)}
#tiroir .pied{margin-top:22px;padding-top:12px;border-top:1px solid #1a2330;
 font-size:11px;color:#3f5168;line-height:1.8}
#tiroir .raz{width:100%;margin-top:10px;background:#121a24;border:1px solid #223044;
 color:#94a3b8;border-radius:7px;padding:9px;font-size:12px;cursor:pointer}
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

    return (
        '<button id="roue" title="Reglages">&#9881;</button>'
        '<div id="tiroir">'
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
