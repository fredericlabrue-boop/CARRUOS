"""Rapport HTML lisible en une seconde. Stdlib uniquement."""

from __future__ import annotations

import html
import webbrowser
from pathlib import Path

from .rules import MAX_POSITIONS, position_size

# Noms lisibles. Le code du bloc ne parle qu'au developpeur, ces libelles
# parlent a l'utilisateur.
LABELS = {
    "1a": "marché porteur",
    "1b": "au-dessus de sa MM200",
    "1c": "tendance 50j haussière",
    "1d": "surperforme l'indice",
    "1e": "MACD en territoire positif",
    "2a": "replié au bon niveau",
    "2b": "RSI dans la zone d'achat",
    "2c": "repli resté sain",
    "2d": "repli récent",
    "3a": "momentum qui se retourne",
    "3b": "clôture au-dessus de l'EMA20",
    "3c": "dépasse le plus haut de la veille",
    "4a": "volume confirmé",
}

CSS = """
*{box-sizing:border-box;margin:0}
body{background:#0a0d13;color:#aeb9c9;font:14px ui-sans-serif,Segoe UI,system-ui;padding:30px;max-width:960px;margin:0 auto}
.top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:26px}
.top h1{font-size:13px;font-weight:500;letter-spacing:.24em;color:#4d5e75}
.top .dt{font-size:12px;color:#4d5e75}
.verdict{border-radius:12px;padding:26px 30px;margin-bottom:12px;display:flex;align-items:center;gap:26px}
.v-go{background:#06241f;border:1px solid #10705a}
.v-no{background:#131820;border:1px solid #26313f}
.v-off{background:#2a1114;border:1px solid #7d2530}
.verdict .big{font-size:52px;font-weight:600;line-height:1}
.v-go .big{color:#34d399}.v-no .big{color:#64748b}.v-off .big{color:#f87171}
.verdict .txt{font-size:17px;color:#e2e8f0}
.verdict .sub{font-size:13px;color:#64748b;margin-top:5px}
.regime{display:flex;flex-wrap:wrap;gap:26px;background:#0e131b;border:1px solid #1c2430;border-radius:10px;padding:14px 22px;margin-bottom:30px;font-size:13px}
.regime b{color:#e2e8f0;font-weight:500}
h2{font-size:12px;font-weight:500;letter-spacing:.2em;color:#4d5e75;margin:30px 0 13px}
.card{background:#0e131b;border:1px solid #1c2430;border-left:4px solid;border-radius:10px;padding:17px 21px;margin-bottom:11px}
.ok{border-left-color:#10b981}.near{border-left-color:#f59e0b}.no{border-left-color:#2b3544}
.ch{display:flex;align-items:center;gap:13px;margin-bottom:12px}
.tick{font-size:21px;font-weight:600;color:#f1f5f9;letter-spacing:.03em}
.pill{font-size:11px;letter-spacing:.13em;padding:4px 11px;border-radius:20px;font-weight:500}
.p-ok{background:#06241f;color:#34d399}.p-near{background:#2a1e06;color:#fbbf24}.p-no{background:#1a2029;color:#64748b}
.score{margin-left:auto;font-size:13px;color:#64748b}
.bar{height:5px;background:#1a2029;border-radius:3px;overflow:hidden;margin-bottom:13px}
.bar i{display:block;height:100%}
.b-ok{background:#10b981}.b-near{background:#f59e0b}.b-no{background:#374357}
.miss{font-size:13px;color:#fb7185;line-height:1.85}
.miss b{color:#fda4af;font-weight:500}
.veto{font-size:13px;color:#fbbf24;margin-top:7px}
.lv{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:11px;margin-top:5px}
.lv div{background:#131a24;border-radius:7px;padding:10px 13px}
.lv .k{font-size:10px;letter-spacing:.13em;color:#4d5e75;margin-bottom:4px}
.lv .v{font-size:17px;color:#f1f5f9;font-variant-numeric:tabular-nums}
.rej{font-size:13px;color:#55647a;line-height:2}
.rej b{color:#8ea0b8;font-weight:500}
.nw{margin-top:12px;border-top:1px solid #1c2430;padding-top:11px}
.nw a{display:block;color:#94a3b8;text-decoration:none;font-size:12.5px;line-height:1.6;margin-bottom:5px}
.nw a:hover{color:#e2e8f0}
.nw .sm{color:#4d5e75;font-size:11px}
.s-neg{color:#fb7185}.s-pos{color:#34d399}.s-neu{color:#64748b}
.ft{margin-top:34px;padding-top:15px;border-top:1px solid #1c2430;color:#4d5e75;font-size:12px;line-height:1.8}
"""


def _code(k):
    return k.split("_")[0]


def _card(s, sleeve, kind, ccy="", actus=None):
    e = html.escape
    n = len(s.blocks)
    got = n - len(s.failed_blocks)
    pct = round(got / n * 100) if n else 0
    pill = {"ok": ("p-ok", "PRÊT"), "near": ("p-near", "PROCHE"),
            "no": ("p-no", "ÉCARTÉ")}[kind]
    p = [f'<div class="card {kind}"><div class="ch"><span class="tick">{e(s.ticker)}</span>',
         f'<span class="pill {pill[0]}">{pill[1]}</span>',
         f'<span class="score">{got}/{n} blocs</span></div>',
         f'<div class="bar"><i class="b-{kind}" style="width:{pct}%"></i></div>']

    if s.failed_blocks:
        items = " · ".join(f"<b>{e(LABELS.get(_code(k), k))}</b>" for k in s.failed_blocks)
        p.append(f'<div class="miss">Manque : {items}</div>')
    if s.vetos:
        p.append(f'<div class="veto">Veto : {e("; ".join(s.vetos))}</div>')

    if kind == "ok":
        ps = position_size(s, sleeve)
        cap = " (plafonné)" if ps["capped"] else ""
        p.append(
            f'<div class="lv"><div><div class="k">ENTRÉE</div><div class="v">{s.entry:.2f}</div></div>'
            f'<div><div class="k">STOP</div><div class="v">{s.stop:.2f}</div></div>'
            f'<div><div class="k">RISQUE</div><div class="v">{s.risk_pct*100:.1f}%</div></div>'
            f'<div><div class="k">TITRES</div><div class="v">{ps["shares"]}{cap}</div></div>'
            f'<div><div class="k">MONTANT</div><div class="v">{ps["notional"]:,.0f}</div></div>'
            f'<div><div class="k">RISQUE {e(ccy)}</div><div class="v">{ps["risk_eur"]:,.0f}</div></div></div>')
    if actus:
        p.append('<div class="nw">')
        for a in actus:
            sc = a.get("score")
            cls = "s-neu" if sc is None else ("s-neg" if sc < -0.15 else
                                              "s-pos" if sc > 0.15 else "s-neu")
            lab = "" if sc is None else f" · <span class=\"{cls}\">{sc:+.2f}</span>"
            titre = e(a.get("titre", ""))
            meta = f'<span class="sm">{e(a.get("quand",""))} {e(a.get("source",""))}{lab}</span>'
            url = a.get("url") or "#"
            p.append(f'<a href="{e(url)}" target="_blank">{titre}<br>{meta}</a>')
        p.append("</div>")
    p.append("</div>")
    return "".join(p)


def render(fired, allsig, bench_row, bench_ok, sleeve, date, path="dashboard.html",
           bench_name="SPY", ccy="", actus=None, erreurs=None,
           open_browser=True) -> Path:
    actus = actus or {}
    e = html.escape
    n = len(fired)

    if not bench_ok:
        vc, big, txt = "v-off", "STOP", "Marché sous sa MM200"
        sub = "Aucune entrée autorisée. Liquidation du sleeve sous 3 séances."
    elif n:
        vc, big = "v-go", str(n)
        txt = f"candidat{'s' if n > 1 else ''} validé{'s' if n > 1 else ''}"
        sub = "Les 13 blocs passent et aucun veto ne s'applique."
    else:
        vc, big, txt = "v-no", "0", "aucun candidat aujourd'hui"
        sub = "C'est le cas le plus fréquent. Regarde les titres proches ci-dessous."

    ecart = (bench_row["close"] / bench_row["sma200"] - 1) * 100
    p = [f"<style>{CSS}</style>",
         f'<div class="top"><h1>CARRUOS ALICE</h1><div class="dt">{e(str(date))}</div></div>',
         f'<div class="verdict {vc}"><div class="big">{big}</div>'
         f'<div><div class="txt">{txt}</div><div class="sub">{sub}</div></div></div>',
         f'<div class="regime"><span>Indice <b>{e(bench_name)}</b></span>'
         f'<span>Cours <b>{bench_row["close"]:.2f}</b></span>'
         f'<span>MM200 <b>{bench_row["sma200"]:.2f}</b></span>'
         f'<span>Écart <b>{ecart:+.1f}%</b></span>'
         f'<span>Analysés <b>{len(allsig)}</b></span></div>']

    if fired:
        p.append("<h2>PRÊTS</h2>")
        for s in fired[:MAX_POSITIONS]:
            p.append(_card(s, sleeve, "ok", ccy, actus.get(s.ticker)))

    rest = sorted((s for s in allsig if not s.fired),
                  key=lambda s: (len(s.failed_blocks), s.ticker))
    near = [s for s in rest if len(s.failed_blocks) <= 2]
    far = [s for s in rest if len(s.failed_blocks) > 2]

    if near:
        p.append("<h2>À SURVEILLER — 1 OU 2 BLOCS MANQUANTS</h2>")
        for s in near[:12]:
            p.append(_card(s, sleeve, "near", ccy))

    if far:
        p.append(f"<h2>ÉCARTÉS — {len(far)}</h2>")
        for s in far[:40]:
            miss = ", ".join(LABELS.get(_code(k), k) for k in s.failed_blocks[:3])
            p.append(f'<div class="rej"><b>{e(s.ticker)}</b> — '
                     f'{len(s.failed_blocks)} blocs : {e(miss)}</div>')

    if erreurs:
        p.append(f'<h2>NON ANALYSÉS — {len(erreurs)}</h2>')
        for tk, msg in erreurs[:30]:
            p.append(f'<div class="rej"><b>{e(tk)}</b> — {e(str(msg)[:80])}</div>')

    p.append('<div class="ft">Règles évaluées sur clôture. Généré par equity_scanner.<br>'
             "Candidats, pas ordres : tant que la Phase 0 n'a pas rendu un GO, "
             "cette page est une watchlist.</div>")

    out = Path(path).resolve()
    out.write_text("\n".join(p), encoding="utf-8")
    if open_browser:
        webbrowser.open(out.as_uri())
    return out
