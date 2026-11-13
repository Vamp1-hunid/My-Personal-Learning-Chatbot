"""docshell.py - the shared look of QuantaKai's HTML documents (guide and report).

Everything a page needs is inline (CSS and JavaScript), so each document is ONE file that
opens in any browser, offline. Light and dark follow Windows automatically.
"""
from __future__ import annotations

import html
import re

E = html.escape

CSS = r"""
:root{--bg:#f7f8fb;--panel:#fff;--panel2:#f1f3f8;--text:#1b2030;--muted:#5b6478;--faint:#8a92a6;--line:#e3e6ee;
--accent:#0f9d8a;--accent2:#5b5bd6;--warn:#b7791f;--danger:#c53030;--ok:#2f855a;--code:#0f1420;--codetext:#e6e9f2;
--shadow:0 1px 2px rgba(16,24,40,.06),0 4px 14px rgba(16,24,40,.06);--mono:ui-monospace,"Cascadia Code","Consolas",monospace}
@media (prefers-color-scheme:dark){:root{--bg:#0d1017;--panel:#151a24;--panel2:#1b2130;--text:#e8ebf3;--muted:#a3abbd;
--faint:#7a8296;--line:#262d3d;--accent:#2dd4bf;--accent2:#8b8cf6;--warn:#f6ad55;--danger:#fc8181;--ok:#68d391;
--code:#0a0d14;--codetext:#e6e9f2;--shadow:0 1px 2px rgba(0,0,0,.4)}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:16px}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 "Segoe UI",system-ui,-apple-system,sans-serif}
a{color:var(--accent2)}code{font-family:var(--mono);font-size:.88em;background:var(--panel2);padding:.1em .35em;border-radius:5px}
.wrap{display:grid;grid-template-columns:290px 1fr;min-height:100vh}
nav.toc{position:sticky;top:0;height:100vh;overflow:auto;padding:22px 14px 40px;border-right:1px solid var(--line);background:var(--panel)}
nav.toc .brand{font-weight:800;font-size:18px;margin:0 8px 2px}nav.toc .sub{color:var(--faint);font-size:12.5px;margin:0 8px 14px}
nav.toc a{display:flex;gap:8px;align-items:baseline;padding:4px 8px;border-radius:7px;color:var(--muted);text-decoration:none;font-size:14px}
nav.toc a:hover{background:var(--panel2);color:var(--text)}nav.toc a.sub2{padding-left:26px;font-size:13px}
nav.toc a.done::after{content:"\2713";color:var(--ok);margin-left:auto;font-weight:700}
nav.toc .bar{height:6px;border-radius:9px;background:var(--panel2);margin:6px 8px 14px;overflow:hidden}
nav.toc .bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .3s}
main{padding:34px clamp(18px,5vw,64px) 120px;max-width:1080px}
h1{font-size:clamp(28px,4vw,40px);line-height:1.15;margin:0 0 10px;letter-spacing:-.02em}
h2{font-size:25px;margin:56px 0 12px;padding-top:6px;border-top:1px solid var(--line);letter-spacing:-.01em}
h2 .n{display:inline-grid;place-items:center;min-width:34px;height:34px;padding:0 6px;border-radius:10px;margin-right:10px;
background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-size:16px;vertical-align:3px}
h3{font-size:19px;margin:34px 0 8px}h4{font-size:16px;margin:22px 0 6px}
.lead{font-size:18px;color:var(--muted);max-width:60em}
table{border-collapse:collapse;width:100%;margin:12px 0 18px;font-size:14.5px;background:var(--panel);box-shadow:var(--shadow);border-radius:10px;overflow:hidden}
th,td{text-align:left;vertical-align:top;padding:8px 11px;border-bottom:1px solid var(--line)}th{background:var(--panel2);font-weight:650}
tr:last-child td{border-bottom:0}td code{white-space:nowrap}
.note{border-left:4px solid var(--accent2);background:var(--panel);box-shadow:var(--shadow);padding:12px 16px;border-radius:0 10px 10px 0;margin:14px 0}
.note b.t{display:block;margin-bottom:2px}.note.warn{border-color:var(--warn)}.note.danger{border-color:var(--danger)}.note.ok{border-color:var(--ok)}
.note.ai{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,var(--panel))}
.codebox{margin:12px 0 18px;border-radius:12px;overflow:hidden;box-shadow:var(--shadow);border:1px solid var(--line)}
.codebox .hd{display:flex;align-items:center;gap:8px;padding:7px 10px 7px 14px;background:var(--panel2);font-size:13px;color:var(--muted)}
.codebox .hd b{color:var(--text);font-family:var(--mono);font-weight:600}.codebox .hd .sp{flex:1}
.codebox button{font:inherit;font-size:12.5px;border:1px solid var(--line);background:var(--panel);color:var(--text);padding:3px 10px;border-radius:7px;cursor:pointer}
.codebox button:hover{border-color:var(--accent)}
pre{margin:0;padding:14px 16px;background:var(--code);color:var(--codetext);overflow:auto;font:13px/1.55 var(--mono);tab-size:4;max-height:560px}
.codebox.short pre{max-height:none}
details.file{margin:10px 0 26px;border:1px solid var(--line);border-radius:12px;background:var(--panel);box-shadow:var(--shadow)}
details.file>summary{cursor:pointer;padding:12px 16px;font-weight:650;list-style:none;display:flex;gap:10px;align-items:center}
details.file>summary::before{content:"\25B8";color:var(--faint)}details.file[open]>summary::before{content:"\25BE"}
details.file .in{padding:0 16px 14px}
.meta{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;color:var(--faint);margin:2px 0 10px}
.meta code{font-size:12px}
.tick{display:flex;gap:10px;align-items:center;margin:14px 0;padding:10px 14px;border-radius:10px;background:var(--panel2);cursor:pointer;font-weight:600}
.tick input{width:18px;height:18px;accent-color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:14px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px;box-shadow:var(--shadow)}
.card b{display:block}.card small{color:var(--muted)}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;margin:14px 0}
.flow .card{flex:1 1 180px}.flow .arr{align-self:center;color:var(--faint);font-size:22px}
ol.steps>li,ul>li{margin:5px 0}kbd{font-family:var(--mono);font-size:.85em;border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;padding:0 .35em;background:var(--panel)}
.pill{display:inline-block;font-size:12px;padding:1px 8px;border-radius:99px;background:var(--panel2);color:var(--muted);margin-left:6px;vertical-align:2px}
.top{position:fixed;right:18px;bottom:18px;width:42px;height:42px;border-radius:50%;border:1px solid var(--line);background:var(--panel);
box-shadow:var(--shadow);cursor:pointer;font-size:18px;color:var(--text)}
@media (max-width:900px){.wrap{grid-template-columns:1fr}nav.toc{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}}
@media print{nav.toc,.top,.codebox button{display:none}.wrap{display:block}pre{max-height:none;white-space:pre-wrap}details.file{break-inside:auto}}
"""

JS = r"""
(function () {
  const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
  const KEY = document.body.dataset.key || "qk-doc";
  // copy and save buttons on every code box
  document.querySelectorAll(".codebox").forEach(box => {
    const pre = box.querySelector("pre"), copy = box.querySelector("[data-copy]"), save = box.querySelector("[data-save]");
    if (copy) copy.onclick = async () => {
      const t = pre.innerText;
      try { await navigator.clipboard.writeText(t); }
      catch (e) { const r = document.createRange(); r.selectNodeContents(pre); getSelection().removeAllRanges(); getSelection().addRange(r); document.execCommand("copy"); }
      copy.textContent = "Copied"; setTimeout(() => copy.textContent = "Copy", 1400);
    };
    if (save) save.onclick = () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([pre.innerText], {type: "text/plain"}));
      a.download = save.dataset.save; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    };
  });
  // progress ticks
  const ticks = [...document.querySelectorAll(".tick input")];
  const bar = document.querySelector("nav.toc .bar i");
  const paint = () => {
    const done = ticks.filter(t => t.checked).length;
    if (bar) bar.style.width = (ticks.length ? 100 * done / ticks.length : 0) + "%";
    ticks.forEach(t => { const a = document.querySelector(`nav.toc a[href="#${t.dataset.sec}"]`); if (a) a.classList.toggle("done", t.checked); });
  };
  ticks.forEach(t => { t.checked = store.get(KEY + ":" + t.id) === "1"; t.onchange = () => { store.set(KEY + ":" + t.id, t.checked ? "1" : "0"); paint(); }; });
  paint();
  const top = document.querySelector(".top"); if (top) top.onclick = () => scrollTo({top: 0});
})();
"""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class Doc:
    """Collects sections, then renders one complete HTML page with a contents menu."""

    def __init__(self, title: str, subtitle: str, key: str):
        self.title, self.subtitle, self.key = title, subtitle, key
        self.parts: list[str] = []
        self.toc: list[tuple[str, str, str, bool]] = []   # (id, number, title, is_sub)
        self.n = 0
        self.ticks = 0
        self.current = ""

    # -------------------------------------------------------------- structure
    def raw(self, h: str) -> None:
        self.parts.append(h)

    def section(self, title: str, sid: str | None = None, numbered: bool = True) -> None:
        sid = sid or slug(title)
        if numbered:
            self.n += 1
            num = str(self.n)
            self.parts.append(f'<h2 id="{sid}"><span class="n">{num}</span>{E(title)}</h2>')
        else:
            num = ""
            self.parts.append(f'<h2 id="{sid}">{E(title)}</h2>')
        self.toc.append((sid, num, title, False))
        self.current = sid

    def sub(self, title: str, sid: str | None = None, in_toc: bool = True) -> None:
        sid = sid or (self.current + "-" + slug(title))
        self.parts.append(f'<h3 id="{sid}">{E(title)}</h3>')
        if in_toc:
            self.toc.append((sid, "", title, True))

    def tick(self, label: str) -> None:
        self.ticks += 1
        self.parts.append(f'<label class="tick"><input type="checkbox" id="t{self.ticks}" data-sec="{self.current}">{E(label)}</label>')

    # -------------------------------------------------------------- blocks
    def p(self, h: str) -> None:
        self.parts.append(f"<p>{h}</p>")

    def ul(self, items: list[str], ordered: bool = False, cls: str = "") -> None:
        tag = "ol" if ordered else "ul"
        c = f' class="{cls}"' if cls else ""
        self.parts.append(f"<{tag}{c}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{tag}>")

    def note(self, title: str, h: str, kind: str = "") -> None:
        self.parts.append(f'<div class="note {kind}"><b class="t">{E(title)}</b>{h}</div>')

    def table(self, head: list[str], rows: list[list[str]]) -> None:
        th = "".join(f"<th>{E(x)}</th>" for x in head)
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
        self.parts.append(f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>")

    def code(self, text: str, label: str = "", save_as: str = "", short: bool | None = None) -> None:
        text = text.rstrip("\n") + "\n"
        lines = text.count("\n")
        if short is None:
            short = lines <= 40
        btns = '<button data-copy>Copy</button>'
        if save_as:
            btns += f'<button data-save="{E(save_as)}">Save file</button>'
        hd = f'<div class="hd"><b>{E(label)}</b><span>{lines} line{"s" if lines != 1 else ""}</span><span class="sp"></span>{btns}</div>'
        self.parts.append(f'<div class="codebox{" short" if short else ""}">{hd}<pre>{E(text)}</pre></div>')

    # -------------------------------------------------------------- page
    def render(self) -> str:
        nav = []
        for sid, num, title, is_sub in self.toc:
            label = f"{num}. {E(title)}" if num else E(title)
            nav.append(f'<a href="#{sid}" class="{"sub2" if is_sub else ""}">{label}</a>')
        bar = '<div class="bar"><i></i></div>' if self.ticks else ""
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(self.title)}</title><style>{CSS}</style></head>
<body data-key="{self.key}"><div class="wrap">
<nav class="toc"><div class="brand">{E(self.title)}</div><div class="sub">{E(self.subtitle)}</div>{bar}{''.join(nav)}</nav>
<main>{''.join(self.parts)}</main></div>
<button class="top" title="Back to top">&#8593;</button>
<script>{JS}</script></body></html>
"""
