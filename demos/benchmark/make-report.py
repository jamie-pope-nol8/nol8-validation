#!/usr/bin/env python3
"""Render run.json into a self-contained, on-brand NOL8 pre-index report.

Reproduces the Design handoff (`Pre-Index Web Report.dc.html`) as a single static
HTML file: brand fonts, logos, and the hero pattern are inlined as data URIs, so
the file opens anywhere and prints to a clean light PDF leave-behind (the "deck").
Interactivity (theme toggle, engine-compare tabs, nav scroll-spy, back-to-top)
is vanilla JS and degrades to fully-visible content with no JS and in print.

  python demos/benchmark/make-report.py \
      [demos/benchmark/run.json] [demos/benchmark/pre-index-report.html]

Data contract: demos/benchmark/run.json (see the Design handoff README). Brand
assets: demos/benchmark/brand/ (fonts/, assets/).
"""
from __future__ import annotations

import base64
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAND = HERE / "brand"
GREEN = "#33B046"


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def font_face(family: str, weight: int, path: Path) -> str:
    return (
        f'@font-face{{font-family:"{family}";font-style:normal;font-weight:{weight};'
        f'font-display:swap;src:url("{data_uri(path, "font/woff2")}") format("woff2");}}'
    )


def build_fonts() -> str:
    f = BRAND / "fonts"
    faces = [
        font_face("Google Sans", 400, f / "GoogleSans-400.woff2"),
        font_face("Google Sans", 500, f / "GoogleSans-500.woff2"),
        font_face("Google Sans", 600, f / "GoogleSans-600.woff2"),
        font_face("Google Sans", 700, f / "GoogleSans-700.woff2"),
        font_face("Space Grotesk", 500, f / "SpaceGrotesk-500.woff2"),
        font_face("Space Grotesk", 700, f / "SpaceGrotesk-700.woff2"),
    ]
    return "\n".join(faces)


def logo(name: str) -> str:
    return data_uri(BRAND / "assets" / name, "image/svg+xml")


# ---- CSS: tokens (dark default), light override, print (light) ----
def build_css() -> str:
    pattern = data_uri(BRAND / "assets" / "brand-pattern.png", "image/png")
    return f"""
{build_fonts()}
*{{box-sizing:border-box;}}
html{{scroll-behavior:smooth;}}
body{{margin:0;background:#404040;}}
[data-rpt]{{
  --nol8-green:{GREEN}; --accent:{GREEN}; --accent-hover:#2C9A3D;
  --bg:#404040; --fg1:#FFFFFF; --fg2:#D2D2D2; --fg3:rgba(210,210,210,0.60);
  --hairline:rgba(210,210,210,0.40); --hairline-soft:rgba(210,210,210,0.20);
  --card:rgba(255,255,255,0.06); --cardline:rgba(255,255,255,0.09); --rowline:rgba(255,255,255,0.12);
  --seg-net:rgba(255,255,255,0.14); --seg-tls:rgba(255,255,255,0.30); --tint:rgba(51,176,70,0.10);
  --navbg:rgba(48,48,48,0.82); --herofade:64,64,64; --pattern-op:0.4; --silver:#D2D2D2;
  --font-ui:"Google Sans","Helvetica Neue",Arial,sans-serif;
  --font-display:"Space Grotesk","Google Sans",sans-serif;
}}
[data-rpt][data-theme="light"]{{
  --bg:#FFFAEF; --fg1:#404040; --fg2:#5b5b5b; --fg3:rgba(91,91,91,0.72);
  --hairline:#cfccc2; --hairline-soft:#e2ded3;
  --card:rgba(0,0,0,0.035); --cardline:rgba(0,0,0,0.08); --rowline:rgba(0,0,0,0.10);
  --seg-net:rgba(0,0,0,0.10); --seg-tls:rgba(0,0,0,0.24); --tint:rgba(51,176,70,0.12);
  --navbg:rgba(255,250,239,0.85); --herofade:255,250,239; --pattern-op:0.24;
}}
.brand-pattern{{background:url("{pattern}") right center / cover no-repeat;}}
.logo-light{{display:none;}} .logo-dark{{display:block;}}
[data-theme="light"] .logo-dark{{display:none;}} [data-theme="light"] .logo-light{{display:block;}}
a.cta:hover{{background:var(--accent-hover) !important;}}
a.ghost:hover{{background:var(--card) !important;}}
a.foot:hover{{color:var(--accent) !important;}}
.trow:hover{{background:var(--tint);}}
@keyframes navIn{{from{{opacity:0;transform:translateY(-10px);}}to{{opacity:1;transform:none;}}}}
@media (prefers-reduced-motion:reduce){{
  html{{scroll-behavior:auto;}}
}}
@media print{{
  [data-rpt]{{
    --bg:#FFFAEF !important; --fg1:#404040 !important; --fg2:#555 !important; --fg3:#777 !important;
    --hairline:#c9c9c9 !important; --hairline-soft:#e0ddd4 !important;
    --card:rgba(0,0,0,0.035) !important; --cardline:rgba(0,0,0,0.1) !important; --rowline:rgba(0,0,0,0.12) !important;
    --seg-net:rgba(0,0,0,0.12) !important; --seg-tls:rgba(0,0,0,0.26) !important; --tint:rgba(51,176,70,0.12) !important;
    background:#FFFAEF !important;
  }}
  body{{background:#fff !important;-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
  .no-print{{display:none !important;}}
  .logo-dark{{display:none !important;}} .logo-light{{display:block !important;}}
  [data-wf]{{opacity:1 !important;}}
  .method-body,.raw-body{{display:block !important;}}
  [data-card],section,.avoid-break{{break-inside:avoid;}}
  @page{{margin:14mm;}}
}}
"""


# ---- section builders ----
def hero(d) -> str:
    h = d["headline"]
    return f"""
  <section id="top" data-section="overview" style="position:relative;overflow:hidden;scroll-margin-top:80px;">
    <div class="brand-pattern" style="position:absolute;top:0;right:0;bottom:0;width:56%;opacity:var(--pattern-op);">
      <div style="position:absolute;inset:0;background:linear-gradient(100deg,var(--bg) 6%,rgba(var(--herofade),0.55) 42%,rgba(var(--herofade),0) 74%);"></div>
    </div>
    <div style="position:relative;max-width:1200px;margin:0 auto;padding:64px 40px 56px;">
      <div style="max-width:720px;">
        <div style="color:var(--accent);font-weight:600;font-size:13px;letter-spacing:.18em;text-transform:uppercase;">{esc(d["eyebrow"])}</div>
        <h1 style="font-family:var(--font-display);font-weight:500;font-size:56px;line-height:1.03;letter-spacing:-.015em;color:var(--fg1);margin:22px 0 0;">{esc(h["lead"])}<span style="color:var(--accent);">{esc(h["accent"])}</span></h1>
        <p style="color:var(--fg2);font-size:18px;line-height:1.6;max-width:60ch;margin:24px 0 0;">{esc(d["lede"])}</p>
        <div class="no-print" style="display:flex;flex-wrap:wrap;gap:12px;margin-top:32px;">
          <a class="cta" href="#latency" style="display:inline-flex;align-items:center;gap:9px;background:var(--accent);color:#fff;font-weight:600;font-size:15px;padding:13px 22px;border-radius:8px;text-decoration:none;">See where the time goes <span style="font-weight:700;">&rsaquo;</span></a>
          <a class="ghost" href="#benchmark" style="display:inline-flex;align-items:center;background:transparent;color:var(--fg1);font-weight:600;font-size:15px;padding:13px 22px;border-radius:8px;border:1px solid var(--hairline);text-decoration:none;">The benchmark</a>
        </div>
      </div>
    </div>
  </section>"""


def stat_band(d) -> str:
    cells = ""
    for s in d["stats"]:
        color = "var(--accent)" if s["key"] else "var(--fg1)"
        cells += f"""
          <div data-card style="padding:34px 30px;border-left:1px solid var(--hairline-soft);">
            <div style="font-family:var(--font-display);font-weight:700;font-size:40px;line-height:1;color:{color};">{esc(s["value"])}<span style="font-size:.4em;color:var(--fg2);margin-left:2px;">{esc(s["unit"])}</span></div>
            <div style="color:var(--fg3);font-size:12.5px;line-height:1.4;margin-top:10px;">{esc(s["label"])}</div>
          </div>"""
    return f"""
  <section style="border-top:1px solid var(--hairline-soft);border-bottom:1px solid var(--hairline-soft);">
    <div style="max-width:1200px;margin:0 auto;padding:0 40px;">
      <div style="display:grid;grid-template-columns:repeat(4,1fr);background:var(--card);">{cells}
      </div>
    </div>
  </section>"""


APPROACH_STYLE = {
    "baseline":  dict(surface="var(--card)", border="var(--cardline)", rail="var(--hairline)",
                      metric="var(--fg3)", opacity="0.72", shadow="none", tag="var(--fg3)"),
    "benchmark": dict(surface="var(--card)", border="var(--cardline)", rail="var(--silver)",
                      metric="var(--fg1)", opacity="1", shadow="none", tag="var(--fg2)"),
    "nol8":      dict(surface="var(--tint)", border="rgba(51,176,70,0.45)", rail="var(--accent)",
                      metric="var(--accent)", opacity="1",
                      shadow="0 0 0 1px rgba(51,176,70,0.28), 0 0 26px rgba(51,176,70,0.12)", tag="var(--accent)"),
}


def benchmark(d) -> str:
    b = d["benchmark"]
    cards = ""
    for a in d["approaches"]:
        s = APPROACH_STYLE[a["role"]]
        cards += f"""
          <div data-card style="position:relative;background:{s['surface']};border:1px solid {s['border']};border-left:4px solid {s['rail']};border-radius:10px;padding:24px 24px 26px;opacity:{s['opacity']};box-shadow:{s['shadow']};">
            <div style="font-weight:700;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{s['tag']};">{esc(a['tag'])}</div>
            <div style="color:var(--fg1);font-weight:600;font-size:15px;line-height:1.3;margin-top:6px;">{esc(a['headline'])}</div>
            <div style="font-family:var(--font-display);font-weight:700;font-size:42px;line-height:1;color:{s['metric']};margin-top:18px;">{esc(a['metric'])}<span style="font-size:.32em;color:var(--fg2);font-weight:600;margin-left:5px;">{esc(a['metricUnit'])}</span></div>
            <p style="color:var(--fg3);font-size:13px;line-height:1.5;margin:14px 0 0;">{esc(a['desc'])}</p>
          </div>"""
    r = d["redaction"]
    after = ""
    for part in r["after"]:
        if part["token"]:
            after += f'<span style="color:var(--accent);font-weight:600;background:var(--tint);padding:2px 6px;border-radius:4px;white-space:nowrap;">{esc(part["text"])}</span>'
        else:
            after += f'<span style="white-space:pre-wrap;">{esc(part["text"])}</span>'
    return f"""
  <section id="benchmark" data-section="benchmark" style="scroll-margin-top:80px;">
    <div style="max-width:1200px;margin:0 auto;padding:88px 40px;">
      <div>
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:22px;">
          <span style="color:var(--accent);font-weight:600;font-size:13px;letter-spacing:.18em;text-transform:uppercase;">01 · The benchmark</span>
          <span style="flex:1;height:1px;background:var(--hairline-soft);"></span>
        </div>
        <h2 style="font-weight:700;font-size:38px;line-height:1.08;letter-spacing:-.01em;color:var(--fg1);margin:0;max-width:20ch;">{esc(b['heading'])}</h2>
        <p style="color:var(--fg2);font-size:17px;line-height:1.6;max-width:66ch;margin:14px 0 0;">{esc(b['lede'])}</p>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:18px;margin-top:36px;">{cards}
      </div>
      <div data-card style="background:var(--card);border:1px solid var(--cardline);border-radius:10px;padding:26px 28px;margin-top:18px;">
        <div style="color:var(--fg3);font-size:13.5px;line-height:1.9;">{esc(r['before'])}</div>
        <div style="color:var(--accent);font-weight:700;font-size:11px;letter-spacing:.12em;text-transform:uppercase;margin:14px 0 10px;">NOL8 governs &rsaquo;</div>
        <div style="font-size:14.5px;line-height:2;color:var(--fg2);">{after}</div>
        <div style="display:inline-flex;align-items:center;gap:9px;margin-top:20px;color:var(--accent);font-size:13px;font-weight:600;">
          <span style="width:8px;height:8px;border-radius:50%;background:var(--accent);"></span>{esc(r['note'])}
        </div>
      </div>
    </div>
  </section>"""


def latency(d) -> str:
    lat = d["latency"]
    bars = ""
    for i, wf in enumerate(d["waterfall"]):
        gap = "22px" if i < len(d["waterfall"]) - 1 else "0"
        segs = ""
        for seg in wf["segments"]:
            if seg["kind"] == "net":
                bg, fg, glow, mw = "var(--seg-net)", "var(--fg1)", "none", "0"
            elif seg["kind"] == "tls":
                bg, fg, glow, mw = "var(--seg-tls)", "var(--fg1)", "none", "0"
            else:
                bg, fg, glow, mw = "var(--accent)", "#0e2a13", "inset 0 0 0 1px rgba(255,255,255,0.4)", "6px"
            segs += f'<div style="flex:{seg["ms"]};min-width:{mw};background:{bg};box-shadow:{glow};display:flex;align-items:center;justify-content:center;color:{fg};font-size:11.5px;font-weight:600;white-space:nowrap;overflow:hidden;">{esc(seg["label"])}</div>'
        bars += f"""
        <div data-wf data-engine="{esc(wf['key'])}" style="margin-bottom:{gap};transition:opacity .3s ease;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:9px;">
            <b style="color:var(--fg1);font-weight:600;font-size:14px;">{esc(wf['name'])}</b>
            <span style="color:var(--fg3);font-size:13px;letter-spacing:-.01em;">{esc(wf['total'])}</span>
          </div>
          <div style="display:flex;height:52px;border-radius:8px;overflow:hidden;border:1px solid var(--hairline-soft);">{segs}</div>
        </div>"""
    head = """
          <div style="text-align:left;padding:14px 16px;color:var(--fg3);font-weight:600;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Engine</div>"""
    for col in ["Network RTT", "Warm (pooled)", "Cold (TLS/call)", "TLS tax", "Engine"]:
        head += f'<div style="text-align:right;padding:14px 16px;color:var(--fg3);font-weight:600;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">{col}</div>'
    rows = ""
    for i, row in enumerate(d["table"]):
        border = "1px solid var(--rowline)" if i < len(d["table"]) - 1 else "none"
        rows += f"""
          <div class="trow" style="display:grid;grid-template-columns:1.5fr repeat(5,1fr);border-bottom:{border};">
            <div style="text-align:left;padding:15px 16px;color:var(--fg1);font-weight:600;">{esc(row['engine'])}</div>
            <div style="text-align:right;padding:15px 16px;color:var(--fg2);">{esc(row['rtt'])}</div>
            <div style="text-align:right;padding:15px 16px;color:var(--fg2);">{esc(row['warm'])}</div>
            <div style="text-align:right;padding:15px 16px;color:var(--fg2);">{esc(row['cold'])}</div>
            <div style="text-align:right;padding:15px 16px;color:var(--fg2);">{esc(row['tls'])}</div>
            <div style="text-align:right;padding:15px 16px;color:var(--accent);font-weight:700;">{esc(row['eng'])}</div>
          </div>"""
    return f"""
  <section id="latency" data-section="latency" style="scroll-margin-top:80px;border-top:1px solid var(--hairline-soft);">
    <div style="max-width:1200px;margin:0 auto;padding:88px 40px;">
      <div>
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:22px;">
          <span style="color:var(--accent);font-weight:600;font-size:13px;letter-spacing:.18em;text-transform:uppercase;">02 · Where the time goes</span>
          <span style="flex:1;height:1px;background:var(--hairline-soft);"></span>
        </div>
        <h2 style="font-weight:700;font-size:38px;line-height:1.08;letter-spacing:-.01em;color:var(--fg1);margin:0;">{esc(lat['heading'])}</h2>
        <p style="color:var(--fg2);font-size:17px;line-height:1.6;max-width:66ch;margin:14px 0 0;">{esc(lat['lede'])}</p>
      </div>
      <div data-card style="background:var(--card);border:1px solid var(--cardline);border-radius:12px;padding:28px 30px;margin-top:34px;">
        <div class="no-print" style="display:flex;align-items:center;gap:10px;margin-bottom:24px;flex-wrap:wrap;">
          <span style="color:var(--fg3);font-size:11px;letter-spacing:.1em;text-transform:uppercase;margin-right:4px;">Compare</span>
          <button class="etab" data-view="both" style="cursor:pointer;font-family:inherit;font-size:12.5px;font-weight:600;padding:7px 15px;border-radius:999px;">Both</button>
          <button class="etab" data-view="themis" style="cursor:pointer;font-family:inherit;font-size:12.5px;font-weight:600;padding:7px 15px;border-radius:999px;">Themis (NOL8)</button>
          <button class="etab" data-view="aergia" style="cursor:pointer;font-family:inherit;font-size:12.5px;font-weight:600;padding:7px 15px;border-radius:999px;">Aergia (RE2)</button>
        </div>{bars}
        <div style="display:flex;flex-wrap:wrap;gap:20px;margin-top:22px;">
          <span style="display:inline-flex;align-items:center;gap:8px;color:var(--fg2);font-size:12.5px;"><i style="width:11px;height:11px;border-radius:3px;background:var(--seg-net);display:inline-block;"></i>Network round-trip</span>
          <span style="display:inline-flex;align-items:center;gap:8px;color:var(--fg2);font-size:12.5px;"><i style="width:11px;height:11px;border-radius:3px;background:var(--seg-tls);display:inline-block;"></i>TLS handshake, per call, removable by pooling</span>
          <span style="display:inline-flex;align-items:center;gap:8px;color:var(--fg2);font-size:12.5px;"><i style="width:11px;height:11px;border-radius:3px;background:var(--accent);display:inline-block;"></i>Engine processing</span>
        </div>
        <div style="margin-top:22px;padding:14px 18px;border-left:3px solid var(--accent);background:var(--tint);border-radius:0 8px 8px 0;font-size:14px;line-height:1.55;color:var(--fg1);">{esc(lat['callout'])}</div>
      </div>
      <div data-card style="background:var(--card);border:1px solid var(--cardline);border-radius:12px;padding:8px 8px;margin-top:18px;overflow-x:auto;">
        <div style="min-width:640px;font-variant-numeric:tabular-nums;letter-spacing:-.01em;">
          <div style="display:grid;grid-template-columns:1.5fr repeat(5,1fr);border-bottom:1px solid var(--rowline);">{head}
          </div>{rows}
        </div>
      </div>
      <p style="color:var(--fg3);font-size:12.5px;line-height:1.55;max-width:84ch;margin:16px 0 0;">{esc(d['tableNote'])}</p>
    </div>
  </section>"""


def meaning(d) -> str:
    items = ""
    for t in d["takeaways"]:
        items += f"""
          <div style="display:flex;gap:16px;align-items:flex-start;">
            <span style="color:var(--accent);font-size:24px;font-weight:700;line-height:1;flex-shrink:0;">&rsaquo;</span>
            <div><div style="color:var(--fg1);font-weight:600;font-size:16.5px;line-height:1.3;">{esc(t['title'])}</div><p style="color:var(--fg2);font-size:15px;line-height:1.55;margin:6px 0 0;">{esc(t['body'])}</p></div>
          </div>"""
    return f"""
  <section id="meaning" data-section="meaning" style="scroll-margin-top:80px;border-top:1px solid var(--hairline-soft);">
    <div style="max-width:1200px;margin:0 auto;padding:88px 40px;">
      <div>
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:22px;">
          <span style="color:var(--accent);font-weight:600;font-size:13px;letter-spacing:.18em;text-transform:uppercase;">03 · What it means</span>
          <span style="flex:1;height:1px;background:var(--hairline-soft);"></span>
        </div>
        <h2 style="font-weight:700;font-size:38px;line-height:1.08;letter-spacing:-.01em;color:var(--fg1);margin:0;">{esc(d['meaning']['heading'])}</h2>
      </div>
      <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:38px 56px;margin-top:34px;">{items}
      </div>
    </div>
  </section>"""


def method(d) -> str:
    rows = ""
    for i, m in enumerate(d["method"]):
        border = "none" if i == len(d["method"]) - 1 else "1px solid var(--hairline-soft)"
        rows += f"""
          <div style="display:grid;grid-template-columns:180px 1fr;gap:24px;padding:13px 0;border-bottom:{border};">
            <div style="color:var(--fg3);font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;padding-top:1px;">{esc(m['term'])}</div>
            <div style="color:var(--fg2);font-size:13.5px;line-height:1.6;">{esc(m['def'])}</div>
          </div>"""
    return f"""
  <section id="method" data-section="method" style="scroll-margin-top:80px;border-top:1px solid var(--hairline-soft);">
    <div style="max-width:1200px;margin:0 auto;padding:64px 40px;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;">
        <span style="color:var(--accent);font-weight:600;font-size:13px;letter-spacing:.18em;text-transform:uppercase;">Method</span>
        <button id="method-toggle" class="no-print" style="border:1px solid var(--hairline);background:transparent;color:var(--fg2);font-family:inherit;font-size:12px;font-weight:600;padding:6px 14px;border-radius:999px;cursor:pointer;">Hide</button>
      </div>
      <div class="method-body" style="display:block;margin-top:18px;">{rows}
        <p style="color:var(--fg3);font-size:12px;line-height:1.5;margin:16px 0 0;">{esc(d['methodNote'])}</p>
      </div>
    </div>
  </section>"""


WARN = "#cf6a4a"  # semantic "corrupted" hue for the RE2 fragments, not the accent


def _subhead(title: str, first: bool = False) -> str:
    mt = "4px" if first else "40px"
    return (f'<h3 style="font-size:16px;font-weight:700;letter-spacing:-.01em;color:var(--fg1);'
            f'margin:{mt} 0 8px;">{esc(title)}</h3>')


def _note(text: str) -> str:
    return (f'<p style="color:var(--fg3);font-size:12.5px;line-height:1.6;max-width:92ch;'
            f'margin:0 0 14px;">{esc(text)}</p>')


def _num_table(cols, rows, min_width=560) -> str:
    """First column is a left label; the rest are right-aligned readouts."""
    head = "".join(
        f'<th style="text-align:{"left" if i == 0 else "right"};padding:11px 14px;color:var(--fg3);'
        f'font-weight:600;font-size:11px;letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;'
        f'border-bottom:1px solid var(--rowline);">{esc(c)}</th>'
        for i, c in enumerate(cols)
    )
    body = ""
    for r_i, row in enumerate(rows):
        last = r_i == len(rows) - 1
        nol8 = "NOL8" in str(row[0]) or "Themis" in str(row[0])
        div = "" if last else "border-bottom:1px solid var(--hairline-soft);"
        cells = ""
        for i, cell in enumerate(row):
            align = "left" if i == 0 else "right"
            color = "var(--accent)" if (nol8 and i == 0) else ("var(--fg1)" if i == 0 else "var(--fg2)")
            weight = "600" if i == 0 else "400"
            cells += (f'<td style="text-align:{align};padding:12px 14px;color:{color};font-weight:{weight};'
                      f'white-space:nowrap;{div}">{esc(cell)}</td>')
        body += f"<tr>{cells}</tr>"
    return (f'<div data-card style="background:var(--card);border:1px solid var(--cardline);border-radius:12px;'
            f'padding:6px 6px;overflow-x:auto;"><table style="width:100%;min-width:{min_width}px;'
            f'border-collapse:collapse;font-variant-numeric:tabular-nums;letter-spacing:-.01em;font-size:13px;">'
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _strip_table(cols, rows) -> str:
    """Count column (green, narrow) + a wrapping sentence column."""
    head = "".join(
        f'<th style="text-align:left;padding:11px 14px;color:var(--fg3);font-weight:600;font-size:11px;'
        f'letter-spacing:.06em;text-transform:uppercase;border-bottom:1px solid var(--rowline);'
        f'white-space:nowrap;">{esc(c)}</th>'
        for c in cols
    )
    body = ""
    for r_i, (count, sentence) in enumerate(rows):
        div = "" if r_i == len(rows) - 1 else "border-bottom:1px solid var(--hairline-soft);"
        body += (
            f'<tr><td style="padding:11px 14px;color:var(--accent);font-weight:600;white-space:nowrap;'
            f'vertical-align:top;font-variant-numeric:tabular-nums;{div}">{esc(count)}</td>'
            f'<td style="padding:11px 14px;color:var(--fg2);line-height:1.5;{div}">{esc(sentence)}</td></tr>'
        )
    return (f'<div data-card style="background:var(--card);border:1px solid var(--cardline);border-radius:12px;'
            f'padding:6px 6px;overflow-x:auto;"><table style="width:100%;min-width:560px;border-collapse:collapse;'
            f'font-size:13px;"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')


def _chipify(escaped_text: str) -> str:
    return re.sub(
        r"(\[[A-Z0-9_]+\])",
        r'<span style="color:var(--accent);font-weight:600;background:var(--tint);'
        r'padding:1px 5px;border-radius:4px;">\1</span>',
        escaped_text,
    )


def _sample_row(label: str, label_color: str, text: str, role: str) -> str:
    stripped = text.strip()
    if role == "in":
        inner = esc(text)
        color = "var(--fg3)"
        wrap = ""
    elif role == "themis":
        color = "var(--fg1)"
        inner = (_chipify(esc(text)) if stripped
                 else '<span style="color:var(--fg3);font-style:italic;">nothing forwarded, stripped to blank</span>')
        wrap = ""
    else:  # aergia
        color = WARN
        inner = (esc(text) if stripped
                 else '<span style="color:var(--fg3);font-style:italic;">nothing forwarded</span>')
        wrap = (f"background:rgba(207,106,74,0.09);border:1px solid rgba(207,106,74,0.28);"
                f"border-radius:6px;padding:8px 11px;")
    return (
        f'<div><div style="font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;font-weight:600;'
        f'color:{label_color};margin-bottom:5px;">{esc(label)}</div>'
        f'<div style="white-space:pre-wrap;color:{color};font-size:12.5px;line-height:1.7;{wrap}">{inner}</div></div>'
    )


def _samples(items) -> str:
    cards = ""
    for it in items:
        rows = (
            _sample_row("Original in", "var(--fg3)", it["in"], "in")
            + _sample_row("NOL8 Themis · forwarded", "var(--accent)", it["themis"], "themis")
            + _sample_row("RE2 (Aergia) · forwarded", WARN, it["aergia"], "aergia")
        )
        cards += (
            f'<div data-card style="background:var(--card);border:1px solid var(--cardline);border-radius:12px;'
            f'padding:18px 20px;margin-top:14px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px;">'
            f'<span style="color:var(--fg2);font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;">{esc(it["id"])}</span>'
            f'<span style="color:var(--fg3);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;">{esc(it.get("kind",""))}</span>'
            f'</div><div style="display:grid;gap:14px;">{rows}</div></div>'
        )
    return cards


def raw_section(d) -> str:
    raw = d.get("raw")
    if not raw:
        return ""
    bd = raw["breakdown"]
    sr = raw["stripRules"]
    sm = raw["samples"]
    ag = raw["aggregate"]
    dot = '<span style="width:8px;height:8px;border-radius:50%;background:var(--accent);"></span>'
    verified = (f'<div style="display:inline-flex;align-items:center;gap:9px;margin-top:14px;color:var(--accent);'
                f'font-size:13px;font-weight:600;">{dot}{esc(bd["verified"])}</div>')
    return f"""
  <section id="appendix" data-section="appendix" style="scroll-margin-top:80px;border-top:1px solid var(--hairline-soft);">
    <div style="max-width:1200px;margin:0 auto;padding:64px 40px;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;">
        <span style="color:var(--accent);font-weight:600;font-size:13px;letter-spacing:.18em;text-transform:uppercase;">Appendix · {esc(raw['heading'])}</span>
        <button id="raw-toggle" class="no-print" style="border:1px solid var(--hairline);background:transparent;color:var(--fg2);font-family:inherit;font-size:12px;font-weight:600;padding:6px 14px;border-radius:999px;cursor:pointer;">Show</button>
      </div>
      <div class="raw-body" style="display:none;margin-top:22px;">
        <p style="color:var(--fg2);font-size:14px;line-height:1.6;max-width:88ch;margin:0 0 8px;">{esc(raw['intro'])}</p>

        {_subhead(bd['title'])}
        {_num_table(bd['columns'], bd['rows'])}
        {verified}

        {_subhead(sr['title'])}
        {_note(sr['note'])}
        {_strip_table(sr['columns'], sr['rows'])}

        {_subhead(sm['title'])}
        {_note(sm['note'])}
        {_samples(sm['items'])}

        {_subhead(ag.get('title', 'Forwarded payload'))}
        {_num_table(ag['columns'], ag['rows'], min_width=680)}
        <p style="color:var(--fg3);font-size:12px;line-height:1.55;max-width:92ch;margin:16px 0 0;">{esc(ag['note'])}</p>
      </div>
    </div>
  </section>"""


def footer(d) -> str:
    f = d["footer"]
    nxt = "".join(f'<span style="color:var(--fg2);font-size:14px;">{esc(x)}</span>' for x in f["next"])
    return f"""
  <footer style="border-top:1px solid var(--hairline);background:var(--card);">
    <div style="max-width:1200px;margin:0 auto;padding:52px 40px 30px;display:flex;gap:48px;flex-wrap:wrap;align-items:flex-start;">
      <div style="flex:1 1 300px;">
        <img class="logo-dark" src="{logo('logotype-tagline-dark.svg')}" alt="Nol8, The AI Data Plane" style="height:38px;">
        <img class="logo-light" src="{logo('logotype-tagline-full-color.svg')}" alt="Nol8, The AI Data Plane" style="height:38px;">
        <p style="color:var(--fg2);font-size:14px;line-height:1.55;margin:16px 0 0;max-width:34ch;">{esc(f['tagline'])}</p>
      </div>
      <div>
        <div style="color:var(--fg3);font-size:11px;letter-spacing:.14em;text-transform:uppercase;">This readout</div>
        <div style="display:flex;flex-direction:column;gap:10px;margin-top:14px;">
          <a class="foot" href="#benchmark" style="color:var(--fg2);font-size:14px;text-decoration:none;">The benchmark</a>
          <a class="foot" href="#latency" style="color:var(--fg2);font-size:14px;text-decoration:none;">Where the time goes</a>
          <a class="foot" href="#method" style="color:var(--fg2);font-size:14px;text-decoration:none;">Method</a>
        </div>
      </div>
      <div>
        <div style="color:var(--fg3);font-size:11px;letter-spacing:.14em;text-transform:uppercase;">Next</div>
        <div style="display:flex;flex-direction:column;gap:10px;margin-top:14px;">{nxt}</div>
      </div>
    </div>
    <div style="max-width:1200px;margin:0 auto;padding:0 40px 34px;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding-top:24px;border-top:1px solid var(--hairline-soft);">
        <span style="color:var(--fg3);font-size:13px;">{esc(f['copyright'])}</span>
        <span style="color:var(--fg3);font-size:13px;">{esc(f['confidential'])}</span>
      </div>
    </div>
  </footer>"""


def top_bar(d) -> str:
    return f"""
  <header class="no-print" style="position:sticky;top:0;z-index:50;background:var(--navbg);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--hairline-soft);">
    <div style="max-width:1200px;margin:0 auto;padding:0 40px;height:66px;display:flex;align-items:center;gap:20px;">
      <a href="#top" style="display:flex;align-items:center;">
        <img class="logo-dark" src="{logo('logotype-dark.svg')}" alt="Nol8" style="height:23px;">
        <img class="logo-light" src="{logo('logotype-full-color.svg')}" alt="Nol8" style="height:23px;">
      </a>
      <span style="color:var(--fg3);font-size:12px;letter-spacing:.12em;text-transform:uppercase;padding-left:18px;border-left:1px solid var(--hairline-soft);">{esc(d['navLabel'])}</span>
      <div style="margin-left:auto;display:flex;align-items:center;gap:14px;">
        <div style="display:flex;border:1px solid var(--hairline);border-radius:999px;overflow:hidden;">
          <button id="theme-dark" class="ttab" data-theme="dark" style="border:none;cursor:pointer;font-family:inherit;font-size:12px;font-weight:600;padding:7px 14px;">Dark</button>
          <button id="theme-light" class="ttab" data-theme="light" style="border:none;cursor:pointer;font-family:inherit;font-size:12px;font-weight:600;padding:7px 14px;">Light</button>
        </div>
        <button id="nav-toggle" aria-label="Menu" style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;border:1px solid var(--hairline);border-radius:8px;background:transparent;color:var(--fg1);cursor:pointer;">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="7" x2="21" y2="7"></line><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="17" x2="21" y2="17"></line></svg>
        </button>
      </div>
    </div>
  </header>
  <div id="nav-drawer" class="no-print" style="display:none;">
    <div id="nav-scrim" style="position:fixed;inset:66px 0 0 0;z-index:40;background:rgba(0,0,0,0.35);"></div>
    <div style="position:fixed;top:66px;right:0;z-index:45;width:min(340px,86vw);background:var(--bg);border-left:1px solid var(--hairline);border-bottom:1px solid var(--hairline);padding:20px 20px 26px;animation:navIn .28s cubic-bezier(.2,.6,.2,1);">
      <div style="color:var(--fg3);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:0 8px 10px;">On this page</div>
      {"".join(f'<a class="navlink" data-target="{sid}" href="#{sid}" style="display:flex;align-items:center;gap:12px;padding:12px 8px;border-radius:8px;text-decoration:none;font-size:16px;border-bottom:1px solid var(--hairline-soft);"><span class="navdot" style="width:6px;height:6px;border-radius:50%;flex-shrink:0;"></span>{label}</a>' for sid, label in [("overview","Overview"),("benchmark","The benchmark"),("latency","Where the time goes"),("meaning","What it means"),("method","Method"),("appendix","Full data")])}
    </div>
  </div>"""


BACK_TO_TOP = """
  <a id="back-to-top" href="#top" class="no-print" aria-label="Back to top" style="display:none;position:fixed;right:26px;bottom:26px;z-index:40;width:46px;height:46px;align-items:center;justify-content:center;background:var(--accent);color:#fff;border-radius:50%;text-decoration:none;box-shadow:0 6px 20px rgba(0,0,0,.35);">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"></line><polyline points="6 11 12 5 18 11"></polyline></svg>
  </a>"""


SCRIPT = """
<script>
(function(){
  var root=document.querySelector('[data-rpt]');
  var GREEN='#33B046';
  // ---- theme ----
  function paintTheme(){
    var light=root.getAttribute('data-theme')==='light';
    document.querySelectorAll('.ttab').forEach(function(b){
      var on=(b.getAttribute('data-theme')==='light')===light;
      b.style.background=on?GREEN:'transparent'; b.style.color=on?'#fff':'var(--fg2)';
    });
  }
  document.querySelectorAll('.ttab').forEach(function(b){
    b.addEventListener('click',function(){ root.setAttribute('data-theme',b.getAttribute('data-theme')); paintTheme(); });
  });
  // ---- engine compare tabs ----
  function paintEngine(view){
    document.querySelectorAll('[data-wf]').forEach(function(w){
      var k=w.getAttribute('data-engine'); w.style.opacity=(view==='both'||view===k)?'1':'0.3';
    });
    document.querySelectorAll('.etab').forEach(function(t){
      var on=t.getAttribute('data-view')===view;
      t.style.background=on?GREEN:'transparent'; t.style.color=on?'#fff':'var(--fg2)';
      t.style.border='1px solid '+(on?GREEN:'var(--hairline)');
    });
  }
  document.querySelectorAll('.etab').forEach(function(t){
    t.addEventListener('click',function(){ paintEngine(t.getAttribute('data-view')); });
  });
  // ---- nav drawer ----
  var drawer=document.getElementById('nav-drawer');
  function setNav(open){ drawer.style.display=open?'block':'none'; }
  document.getElementById('nav-toggle').addEventListener('click',function(){ setNav(drawer.style.display==='none'); });
  document.getElementById('nav-scrim').addEventListener('click',function(){ setNav(false); });
  document.querySelectorAll('.navlink').forEach(function(a){ a.addEventListener('click',function(){ setNav(false); }); });
  // ---- method toggle ----
  var mt=document.getElementById('method-toggle'), mb=document.querySelector('.method-body');
  mt.addEventListener('click',function(){ var hide=mb.style.display!=='none'; mb.style.display=hide?'none':'block'; mt.textContent=hide?'Show':'Hide'; });
  // ---- raw data appendix (collapsed by default) ----
  var rt=document.getElementById('raw-toggle'), rb=document.querySelector('.raw-body');
  if(rt&&rb){ rt.addEventListener('click',function(){ var open=rb.style.display==='none'; rb.style.display=open?'block':'none'; rt.textContent=open?'Hide':'Show'; }); }
  // ---- back to top + scroll-spy ----
  var btt=document.getElementById('back-to-top');
  var sections=[].slice.call(document.querySelectorAll('[data-section]'));
  function spy(){
    btt.style.display=window.scrollY>560?'flex':'none';
    var active=sections.length?sections[0].getAttribute('data-section'):'overview';
    sections.forEach(function(s){ if(s.getBoundingClientRect().top<150) active=s.getAttribute('data-section'); });
    document.querySelectorAll('.navlink').forEach(function(a){
      var on=a.getAttribute('data-target')===active;
      a.style.color=on?GREEN:'var(--fg2)'; a.style.fontWeight=on?'600':'400';
      a.querySelector('.navdot').style.background=on?GREEN:'var(--hairline)';
    });
  }
  window.addEventListener('scroll',spy,{passive:true});
  // Content is visible by default (no fade-gating), so nothing can get stuck
  // hidden if the page is wrapped by another runtime or JS partially fails.
  // Scroll-spy nav and back-to-top stay live.
  paintTheme(); paintEngine('both'); spy();
})();
</script>"""


def build(run: dict) -> str:
    body = "".join([
        top_bar(run), hero(run), stat_band(run), benchmark(run),
        latency(run), meaning(run), method(run), raw_section(run), footer(run), BACK_TO_TOP,
    ])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="omelette-owns-print" content="true">
<title>NOL8 Pre-Index Governance, Data Point 01</title>
<style>{build_css()}</style>
</head>
<body>
<div data-rpt data-theme="dark" style="background:var(--bg);color:var(--fg1);font-family:var(--font-ui);min-height:100vh;-webkit-font-smoothing:antialiased;">
{body}
</div>
{SCRIPT}
</body>
</html>"""


def main() -> None:
    run_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "run.json"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "pre-index-report.html"
    run = json.loads(run_path.read_text())
    out_path.write_text(build(run))
    kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({kb:.0f} KB) from {run_path.name}")


if __name__ == "__main__":
    main()
