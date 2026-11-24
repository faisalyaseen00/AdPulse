"""Shared UI building blocks: styling, KPI tiles, badges, charts, cached queries."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from adpulse import warehouse
from adpulse.config import get_settings

# Chart palette (validated for colour-blind safety; order matters). Meta = blue, Google = orange.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
PLATFORM_COLORS = {"meta": SERIES[0], "google": SERIES[1], "unpaid": "#8a8f98"}
INK, MUTED, GOOD, BAD, PULSE = "#14213D", "#5B6475", "#157A4A", "#C23B2E", "#F4B400"
GOOD_SOFT, BAD_SOFT = "#E6F4EC", "#FBE9E7"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,650;12..96,750&family=Figtree:wght@400;500;600;700&display=swap');
:root {
  --ink:#14213D; --ink-2:#2C3A57; --muted:#5B6475; --faint:#8A92A3; --line:#E3E6EC; --line-2:#EEF0F4;
  --paper:#F7F8FA; --surface:#FFFFFF; --pulse:#F4B400; --pulse-soft:#FFF6D9;
  --good:#157A4A; --good-soft:#E6F4EC; --bad:#C23B2E; --bad-soft:#FBE9E7; --info-soft:#EAF0FB;
  --display:'Bricolage Grotesque', 'Figtree', system-ui, sans-serif;
  --body:'Figtree', system-ui, -apple-system, 'Segoe UI', sans-serif;
}
html, body, .stApp, .stMarkdown p, .stMarkdown li, button, input, textarea, label { font-family: var(--body); }
code, pre, .stCode * { font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important; }
.stApp { background: var(--paper); color: var(--ink); }
.block-container { padding-top: 3.2rem; padding-bottom: 4rem; max-width: 1240px; }
h1, h2, h3, h4 { font-family: var(--display); color: var(--ink); letter-spacing: -0.01em; }
.stMarkdown p, .stMarkdown li { font-size: 1rem; line-height: 1.6; color: var(--ink-2); }
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; height: 0; }
/* hosting toolbar (Fork / GitHub / deploy buttons) is noise for business readers */
/* hide only the actions (Fork, GitHub, deploy). Never the toolbar itself: it holds the open-menu button */
[data-testid="stToolbarActions"], .stAppDeployButton { display: none !important; }
/* The transparent top bar is 60px tall and sat on top of the first row of buttons, swallowing clicks.
   Let clicks pass through it, except on its own controls (the open-menu button). */
header[data-testid="stHeader"] { background: transparent; pointer-events: none; }
header[data-testid="stHeader"] button, header[data-testid="stHeader"] a,
[data-testid="stExpandSidebarButton"] { pointer-events: auto; }
:focus-visible { outline: 2px solid var(--pulse) !important; outline-offset: 2px; }

/* Sidebar */
[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--line); }
[data-testid="stSidebarHeader"] img, [data-testid="stLogo"] { height: 2.1rem !important; max-width: 100%; }
[data-testid="stSidebarNav"] a { border-radius: 8px; margin: 1px 6px; }
[data-testid="stSidebarNav"] a span { color: var(--ink-2) !important; font-size: .95rem; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: var(--pulse-soft); box-shadow: inset 3px 0 0 var(--pulse); }
[data-testid="stSidebarNav"] a[aria-current="page"] span { color: var(--ink) !important; font-weight: 650; }
.ap-side-label { font-size: .82rem; font-weight: 650; color: var(--muted); margin: 12px 0 6px; }
.ap-status { display:flex; flex-direction:column; gap:7px; }
.ap-status .row { display:flex; align-items:center; gap:9px; font-size:.88rem; color: var(--ink-2); }
.ap-status .dot { width:8px; height:8px; border-radius:50%; flex:none; background:#B6BCC8; }
.ap-status .dot.good { background: var(--good); } .ap-status .dot.info { background: var(--ink); }
.ap-status .dot.warn { background: var(--pulse); } .ap-status .dot.bad { background: var(--bad); }

/* ---- The stage: dark, glowing, dot-grid header (Overview hero + every page header) ---- */
.ap-stage, .ap-head { position: relative; overflow: hidden; color: #E9EDF5;
  background:
    radial-gradient(620px 320px at 95% -15%, rgba(244,180,0,.24), transparent 62%),
    radial-gradient(540px 300px at -8% 115%, rgba(24,169,153,.22), transparent 62%),
    linear-gradient(160deg, #0B1226 0%, #14213D 100%); }
.ap-stage::before, .ap-head::before { content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image: radial-gradient(rgba(255,255,255,.075) 1px, transparent 1.3px); background-size: 18px 18px;
  -webkit-mask-image: linear-gradient(100deg, transparent 0%, #000 45%, #000 75%, transparent 100%);
          mask-image: linear-gradient(100deg, transparent 0%, #000 45%, #000 75%, transparent 100%); }
.ap-stage > *, .ap-head > * { position: relative; }
.ap-head { border-radius: 20px; padding: 22px 28px 20px; margin: 0 0 1.4rem; }
.ap-head h1 { font-size: 2rem; font-weight: 750; margin: 0; padding: 0; line-height: 1.15; color: #fff; }
.ap-head p { color: #B8C2D6; font-size: 1.03rem; margin: .45rem 0 0; line-height: 1.5; max-width: 720px; }

.ap-stage { border-radius: 26px; padding: 34px 38px 30px; margin: 0 0 1.6rem;
  display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 34px; align-items: end; }
.ap-stage .eyebrow { font-size: .95rem; color: #9AA6BD; margin-bottom: 10px; }
.ap-stage .lead { font-family: var(--display); font-size: clamp(1.25rem, 2.2vw, 1.75rem); font-weight: 600;
  color: #fff; line-height: 1.2; margin: 0; }
.ap-stage .big { font-family: var(--display); font-weight: 750; font-size: clamp(3.6rem, 8.5vw, 6.6rem);
  line-height: .95; letter-spacing: -0.045em; margin: 6px 0 4px; font-variant-numeric: tabular-nums;
  background: linear-gradient(100deg, #FFD566 0%, #F4B400 45%, #FF8A5B 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.ap-stage .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; margin-top: 18px; }
.ap-stage .detail { color: #B8C2D6; font-size: .98rem; }
.ap-pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px;
  font-size: .86rem; font-weight: 650; border: 1px solid rgba(255,255,255,.14); background: rgba(255,255,255,.06); }
.ap-pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.ap-pill.good { color: #5FD39A; } .ap-pill.ok { color: #FFD566; } .ap-pill.bad { color: #FF8F80; }
.ap-spark .cap { font-size: .82rem; color: #8592AB; margin-top: 8px; }
.ap-stage .detail b { color: #fff; font-weight: 650; }
.ap-stage .up { color: #5FD39A; font-weight: 650; } .ap-stage .down { color: #FF8F80; font-weight: 650; }
.ap-stage .flat { color: #B8C2D6; font-weight: 650; }
.ap-spark .legend { display: flex; gap: 16px; font-size: .84rem; color: #9AA6BD; margin-bottom: 6px; }
.ap-spark .legend i { display: inline-block; width: 18px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
.ap-spark svg { width: 100%; height: auto; display: block; overflow: visible; }
.ap-mini-unused { display: grid; grid-template-columns: repeat(3, 1fr); border-top: 1px solid rgba(255,255,255,.12); margin-top: 12px; }
.ap-mini div { padding: 12px 8px 0 0; }
.ap-mini b { display: block; font-family: var(--display); font-size: 1.3rem; color: #fff; font-variant-numeric: tabular-nums; }
.ap-mini span { font-size: .82rem; color: #9AA6BD; }

/* ---- Motion: one orchestrated entrance, then calm ---- */
@keyframes ap-rise { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
@keyframes ap-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes ap-draw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
@keyframes ap-ping { 0% { r: 5; opacity: .9; } 80%, 100% { r: 16; opacity: 0; } }
.ap-rise { animation: ap-rise .75s cubic-bezier(.2,.7,.2,1) both; }
.ap-d1 { animation-delay: .08s; } .ap-d2 { animation-delay: .18s; } .ap-d3 { animation-delay: .3s; } .ap-d4 { animation-delay: .45s; }
.ap-head h1, .ap-head p { animation: ap-rise .6s cubic-bezier(.2,.7,.2,1) both; } .ap-head p { animation-delay: .1s; }
.ap-spark .line { stroke-dasharray: 1; stroke-dashoffset: 1; animation: ap-draw 1.8s .35s cubic-bezier(.45,0,.2,1) forwards; }
.ap-spark .line.b { animation-delay: .55s; }
.ap-spark .area { opacity: 0; animation: ap-fade 1s 1.3s ease forwards; }
.ap-spark .dot { opacity: 0; animation: ap-fade .3s 2.1s forwards; }
.ap-spark .ping { opacity: 0; animation: ap-fade .1s 2.1s forwards, ap-ping 2.4s 2.2s ease-out infinite; }
.ap-strip .m { animation: ap-rise .6s cubic-bezier(.2,.7,.2,1) both; }
.ap-strip .m:nth-child(2) { animation-delay: .05s; } .ap-strip .m:nth-child(3) { animation-delay: .1s; }
.ap-strip .m:nth-child(4) { animation-delay: .15s; } .ap-strip .m:nth-child(5) { animation-delay: .2s; }
.ap-strip .m:nth-child(6) { animation-delay: .25s; }
.ap-todo .t { transition: background .2s ease; } .ap-todo .t:hover { background: #FBFCFD; }
@media (prefers-reduced-motion: reduce) {
  .ap-spark .line { stroke-dashoffset: 0; } .ap-spark .area, .ap-spark .dot { opacity: 1; } .ap-spark .ping { display: none; }
}

/* Section header */
.ap-section { display:flex; align-items:baseline; gap:12px; flex-wrap: wrap; margin: 2rem 0 .7rem; }
.ap-section h3 { font-size: 1.3rem; font-weight: 650; margin:0; padding:0; }
.ap-section span { color: var(--muted); font-size: .95rem; }

/* Numbers at a glance: one panel, hairline dividers */
.ap-strip { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); background: var(--surface);
  border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
.ap-strip .m { padding: 16px 18px 15px; border-right: 1px solid var(--line-2); border-bottom: 1px solid var(--line-2);
  margin: 0 -1px -1px 0; container-type: inline-size; }
.ap-strip .l { font-size: .9rem; color: var(--muted); font-weight: 500; display:flex; gap:6px; align-items:center;
  cursor: help; white-space: nowrap; min-width: 0; }
.ap-strip .l .i { font-size: .72rem; color: var(--faint); border: 1px solid var(--line); border-radius: 50%;
  width: 15px; height: 15px; display:inline-grid; place-items:center; flex: none; }
.ap-strip .v { font-family: var(--display); font-weight: 700; font-size: clamp(1.15rem, 17cqi, 1.9rem);
  letter-spacing: -0.02em; margin-top: 4px; white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--ink); }
.ap-strip .d { font-size: .85rem; color: var(--muted); margin-top: 3px; }
.ap-strip .d .up { color: var(--good); font-weight: 650; } .ap-strip .d .down { color: var(--bad); font-weight: 650; }
.ap-strip .d .flat { color: var(--muted); font-weight: 650; }

/* What to do this week */
.ap-todo { display:flex; flex-direction:column; background: var(--surface); border:1px solid var(--line); border-radius: 14px; }
.ap-todo .t { display:grid; grid-template-columns: 10px 1fr auto; gap: 14px; align-items: start; padding: 15px 18px;
  border-top: 1px solid var(--line-2); }
.ap-todo .t:first-child { border-top: none; }
.ap-todo .bar { width: 4px; border-radius: 4px; align-self: stretch; }
.ap-todo .bar.good { background: var(--good); } .ap-todo .bar.bad { background: var(--bad); } .ap-todo .bar.warn { background: var(--pulse); }
.ap-todo .h { font-weight: 650; color: var(--ink); font-size: 1.02rem; }
.ap-todo .x { color: var(--ink-2); font-size: .95rem; margin-top: 2px; line-height: 1.5; }
.ap-todo .n { font-family: var(--display); font-weight: 700; font-size: 1.15rem; color: var(--ink); white-space: nowrap;
  text-align: right; min-width: 210px; font-variant-numeric: tabular-nums; }
.ap-todo .n small { display:block; font-family: var(--body); font-weight: 500; font-size: .78rem; color: var(--muted); }
.ap-todo .t { align-items: center; }

/* Journey: ad view to customer */
.ap-flow { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); background: var(--surface);
  border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
.ap-flow .node { padding: 14px 16px; border-right: 1px solid var(--line-2); border-bottom: 1px solid var(--line-2);
  margin: 0 -1px -1px 0; }
.ap-flow .node:last-child { border-right: none; background: var(--pulse-soft); }
.ap-flow .node .t { font-size: .88rem; color: var(--muted); font-weight: 500; }
.ap-flow .node .v { font-family: var(--display); font-weight: 700; font-size: 1.35rem; color: var(--ink);
  font-variant-numeric: tabular-nums; margin-top: 2px; }
.ap-flow .node .s { font-size: .82rem; color: var(--ink-2); margin-top: 2px; }
.ap-flow .arr { display: none; }

/* Badges */
.ap-badge { display:inline-flex; align-items:center; gap:5px; padding: 3px 10px; border-radius: 999px;
  font-size: .82rem; font-weight: 600; white-space: nowrap; background: var(--line-2); color: var(--ink-2); }
.ap-badge.good { background: var(--good-soft); color: var(--good); }
.ap-badge.bad { background: var(--bad-soft); color: var(--bad); }
.ap-badge.warn { background: var(--pulse-soft); color: #7A5600; }
.ap-badge.info { background: var(--info-soft); color: var(--ink); }

/* Streamlit widgets */
div[data-testid="stExpander"] details { border-radius: 12px; border-color: var(--line); background: var(--surface); }
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button { border-radius: 10px; font-weight: 600; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] { background: var(--ink); border-color: var(--ink); color: #fff; }
.stButton > button[kind="primary"]:hover { background: var(--ink-2); border-color: var(--ink-2); }
.stButton > button[kind="secondary"] { background: var(--surface); border-color: var(--line); color: var(--ink); }
.stButton > button[kind="secondary"]:hover { border-color: var(--ink); color: var(--ink); }
.stButton > button p { white-space: normal; text-align: left; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border:1px solid var(--line); border-radius: 12px; overflow:hidden; background: var(--surface); }
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { padding: 8px 4px; font-weight: 600; }
.stTabs [aria-selected="true"] { color: var(--ink); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--pulse); height: 3px; }
[data-testid="stPlotlyChart"] { background: var(--surface); border:1px solid var(--line); border-radius: 14px; padding: 10px 12px 4px; }
[data-testid="stChatMessage"] { background: var(--surface); border:1px solid var(--line); border-radius: 14px; padding: 16px 18px; }
[data-testid="stAlert"] { border-radius: 12px; }
[data-testid="stCaptionContainer"] { color: var(--muted); }

.ap-impact { text-align: right; margin: 2px 0 10px; }
.ap-impact .n { font-family: var(--display); font-weight: 750; font-size: 1.7rem; color: var(--ink);
  letter-spacing: -0.02em; font-variant-numeric: tabular-nums; line-height: 1.1; }
.ap-impact .c { font-size: .82rem; color: var(--muted); }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { font-size: .8rem; line-height: 1.45; }
/* Bordered containers = control bars and cards: white, rounded, aligned */
/* panels: st.container(border=True, key="panel_...") get a white card look */
[class*="st-key-panel_"] { background: var(--surface); border-radius: 16px !important; border-color: var(--line) !important; }
.ap-bars { display: flex; flex-direction: column; gap: 12px; }
.ap-bars .r { display: grid; grid-template-columns: 1fr auto; grid-template-areas: "k v" "t t"; gap: 6px 12px; }
.ap-bars .k { grid-area: k; font-size: .92rem; color: var(--ink-2); min-width: 0; }
.ap-bars .v { grid-area: v; }
.ap-bars .track { grid-area: t; }
.ap-bars .track { height: 10px; border-radius: 999px; background: var(--line-2); overflow: hidden; }
.ap-bars .fill { height: 100%; border-radius: 999px; transform-origin: left; animation: ap-grow .9s .2s cubic-bezier(.2,.7,.2,1) both; }
.ap-bars .v { font-weight: 650; font-variant-numeric: tabular-nums; color: var(--ink); font-size: .95rem; }
@keyframes ap-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
.ap-share { height: 14px; border-radius: 999px; background: #E8F5EE; overflow: hidden; display: flex; margin: 10px 0 6px; }
.ap-share .w { background: linear-gradient(90deg, #FF8A5B, #C23B2E); transform-origin: left;
  animation: ap-grow 1s .25s cubic-bezier(.2,.7,.2,1) both; }
.ap-share-legend { display: flex; justify-content: space-between; font-size: .85rem; color: var(--muted); }
.ap-big { font-family: var(--display); font-weight: 750; font-size: clamp(2.4rem, 5vw, 3.4rem); letter-spacing: -0.03em;
  color: var(--ink); line-height: 1; font-variant-numeric: tabular-nums; }
.ap-big.bad { color: var(--bad); }
.ap-sub { color: var(--ink-2); font-size: 1rem; margin-top: 6px; }
.ap-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
.ap-list { display: flex; flex-direction: column; }
.ap-list .i { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; padding: 12px 0; border-top: 1px solid var(--line-2); }
.ap-list .i:first-child { border-top: none; padding-top: 2px; }
.ap-list .n { font-weight: 650; color: var(--ink); }
.ap-list .m { font-size: .88rem; color: var(--muted); grid-column: 1 / -1; }
.ap-list .x { font-family: var(--display); font-weight: 700; color: var(--ink); white-space: nowrap; }
.ap-list .x.good { color: var(--good); } .ap-list .x.bad { color: var(--bad); }
.ap-card-h { font-family: var(--display); font-weight: 650; font-size: 1.12rem; color: var(--ink); margin: 0 0 10px;
  display: flex; align-items: center; gap: 8px; }
.ap-card-h .dot { width: 9px; height: 9px; border-radius: 50%; }
.ap-summary { margin: 0; padding-left: 0; list-style: none; display: flex; flex-direction: column; gap: 10px; }
.ap-summary li { position: relative; padding-left: 22px; color: var(--ink-2); font-size: 1rem; line-height: 1.55; }
.ap-summary li::before { content: ""; position: absolute; left: 4px; top: .6em; width: 8px; height: 8px; border-radius: 50%;
  background: var(--pulse); }
/* Animated chart cards */
.ap-chart { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 18px 20px 12px; height: 100%; }
.ap-chart .hd { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }
.ap-chart .t { font-family: var(--display); font-weight: 650; font-size: 1.12rem; color: var(--ink); }
.ap-chart .nt { font-size: .86rem; color: var(--muted); margin-top: 2px; }
.ap-chart .lg { display: flex; gap: 16px; flex-wrap: wrap; font-size: .88rem; color: var(--ink-2); }
.ap-chart .lg i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.ap-chart .lg b { font-variant-numeric: tabular-nums; }
.ap-area { width: 100%; height: auto; display: block; overflow: visible; }
.ap-area .g { stroke: #EEF0F4; stroke-width: 1; }
.ap-area .yl { font: 500 13px Figtree, sans-serif; fill: #8A92A3; text-anchor: end; }
.ap-area .xl { font: 500 13px Figtree, sans-serif; fill: #8A92A3; text-anchor: start; }
.ap-area .ln { stroke-dasharray: 1; stroke-dashoffset: 1; animation: ap-draw 1.9s .2s cubic-bezier(.45,0,.2,1) forwards; }
.ap-area .ln.l1 { animation-delay: .45s; }
.ap-area .fillp { opacity: 0; animation: ap-fade 1s 1.2s ease forwards; }
.ap-area .end { opacity: 0; animation: ap-fade .3s 2s forwards; }
.ap-area .hit { fill: transparent; cursor: crosshair; }
.ap-area .hit:hover { fill: rgba(20,33,61,.05); }
.cmp { display: flex; flex-direction: column; gap: 18px; margin-top: 14px; }
.cmp .cr { display: grid; grid-template-columns: 1fr auto; grid-template-areas: "n v" "t t"; gap: 8px 12px; }
.cmp .cn { grid-area: n; font-weight: 600; color: var(--ink-2); }
.cmp .cv { grid-area: v; font-family: var(--display); font-weight: 750; font-size: 1.5rem; color: var(--ink); font-variant-numeric: tabular-nums; }
.cmp .ct { grid-area: t; height: 14px; border-radius: 999px; background: var(--line-2); overflow: hidden; }
.cmp .cf { height: 100%; border-radius: 999px; transform-origin: left; animation: ap-grow 1s .25s cubic-bezier(.2,.7,.2,1) both; }
.ap-chart .vd { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line-2); font-size: .95rem; color: var(--ink-2); }
@media (prefers-reduced-motion: reduce) { .ap-area .ln { stroke-dashoffset: 0; } .ap-area .fillp, .ap-area .end { opacity: 1; } }
.ap-card-title { font-family: var(--display); font-weight: 650; font-size: 1.15rem; color: var(--ink); }
.ap-muted { color: var(--muted); font-size: .92rem; }
.ap-why { color: var(--ink-2); font-size: 1rem; line-height: 1.55; margin: 8px 0 6px; }
.ap-facts { display:flex; flex-wrap: wrap; gap: 6px 18px; font-size: .92rem; color: var(--muted); }
.ap-facts b { color: var(--ink); font-variant-numeric: tabular-nums; }
.ap-how { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 0; background: var(--surface);
  border:1px solid var(--line); border-radius: 14px; margin: 2px 0 8px; }
.ap-how .st { padding: 14px 16px; border-right: 1px solid var(--line-2); }
.ap-how .st:last-child { border-right: none; }
.ap-how .n { font-family: var(--display); font-weight: 750; color: var(--pulse); font-size: 1.1rem; }
.ap-how .h { font-weight: 650; font-size: .98rem; color: var(--ink); margin-top: 2px; }
.ap-how .d { font-size: .88rem; color: var(--muted); margin-top: 3px; line-height: 1.45; }
.ap-step { display:flex; gap:10px; align-items:flex-start; padding:7px 0; border-bottom:1px dashed var(--line); font-size:.9rem; }
.ap-step:last-child { border-bottom:none; }
.ap-step .ic { width: 20px; text-align:center; }
.ap-step .nm { font-weight:600; min-width: 130px; }
.ap-step .dt { color: var(--muted); flex:1; }
.ap-step .ms { color: var(--muted); font-variant-numeric: tabular-nums; }
.ap-gloss { display:grid; grid-template-columns: minmax(160px, 220px) 1fr; gap: 8px 18px; font-size: .95rem; }
.ap-gloss dt { font-weight: 650; color: var(--ink); } .ap-gloss dd { margin: 0; color: var(--ink-2); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
@media (max-width: 900px) {
  .ap-stage { grid-template-columns: 1fr; gap: 22px; padding: 26px 22px 22px; border-radius: 20px; }
}
@media (max-width: 900px) { .ap-how { grid-template-columns: 1fr 1fr; } .ap-how .st:nth-child(2) { border-right: none; } }
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 3.6rem; }
  .ap-head { padding: 20px 18px; border-radius: 16px; } .ap-head h1 { font-size: 1.55rem; }
  .ap-todo .t { grid-template-columns: 6px 1fr; } .ap-todo .n { grid-column: 2; text-align: left; min-width: 0; }
  .ap-gloss { grid-template-columns: 1fr; }
  .ap-impact { text-align: left; }
}
</style>
"""

def inject_css() -> None:
    st.html(CSS)


def hero(title: str, subtitle: str = "", icon: str = "") -> None:
    st.html(f'<div class="ap-head"><h1>{html.escape(title)}</h1>'
            + (f"<p>{html.escape(subtitle)}</p>" if subtitle else "") + "</div>")


def sparkline(values: list[float], compare: list[float] | None = None, w: int = 600, h: int = 190) -> str:
    """Smooth gradient line (+ optional faint comparison line) as one-line SVG that draws itself on load."""
    series = [v for v in values if v is not None] + [v for v in (compare or []) if v is not None]
    if len(values) < 2 or not series:
        return ""
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1.0
    top, bottom = 14, h - 10

    def pts(vals):
        n = len(vals)
        return [(i * w / (n - 1), bottom - (v - lo) / span * (bottom - top)) for i, v in enumerate(vals)]

    def smooth(p):  # Catmull-Rom -> cubic Bezier
        d = f"M{p[0][0]:.1f},{p[0][1]:.1f}"
        for i in range(len(p) - 1):
            p0, p1, p2 = p[max(i - 1, 0)], p[i], p[i + 1]
            p3 = p[min(i + 2, len(p) - 1)]
            c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
            c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
            d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
        return d

    main = pts(values)
    line = smooth(main)
    area = f"{line} L{w},{h} L0,{h} Z"
    ex, ey = main[-1]
    comp = (f'<path class="line b" pathLength="1" d="{smooth(pts(compare))}" fill="none" '
            f'stroke="rgba(255,255,255,.38)" stroke-width="2" stroke-dasharray="1"/>') if compare else ""
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Weekly trend">'
            '<defs><linearGradient id="apS" x1="0" x2="1"><stop offset="0" stop-color="#2DD4BF"/>'
            '<stop offset=".55" stop-color="#F4B400"/><stop offset="1" stop-color="#FF8A5B"/></linearGradient>'
            '<linearGradient id="apA" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="rgba(244,180,0,.32)"/>'
            '<stop offset="1" stop-color="rgba(244,180,0,0)"/></linearGradient></defs>'
            f'<path class="area" d="{area}" fill="url(#apA)"/>{comp}'
            f'<path class="line" pathLength="1" d="{line}" fill="none" stroke="url(#apS)" stroke-width="3.5" '
            'stroke-linecap="round"/>'
            f'<circle class="ping" cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="none" stroke="#FF8A5B" stroke-width="2"/>'
            f'<circle class="dot" cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="#FF8A5B"/></svg>')


def _smooth(p: list[tuple[float, float]]) -> str:
    """Catmull-Rom spline through points, as an SVG path."""
    d = f"M{p[0][0]:.1f},{p[0][1]:.1f}"
    for i in range(len(p) - 1):
        p0, p1, p2, p3 = p[max(i - 1, 0)], p[i], p[i + 1], p[min(i + 2, len(p) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def _k(v: float) -> str:
    return f"${v / 1000:,.0f}k" if abs(v) >= 1000 else f"${v:,.0f}"


def area_chart(dates: list, series: list[tuple[str, list[float], str]], tip: str = "Week of %b %-d",
               w: int = 640, h: int = 250) -> str:
    """Light, animated trend chart as one-line SVG (st.markdown keeps SVG; st.html strips it).
    series: (name, values, colour). The first series gets a soft gradient fill. Native hover tips per point."""
    n = len(dates)
    if n < 2:
        return ""
    allv = [v for _, vals, _ in series for v in vals]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.12 or 1
    lo, hi = max(0, lo - pad), hi + pad
    L, R, T, B = 48, 12, 12, 28
    pw, ph = w - L - R, h - T - B

    def xy(i, v):
        return L + i * pw / (n - 1), T + (1 - (v - lo) / (hi - lo)) * ph

    out = [f'<svg class="ap-area" viewBox="0 0 {w} {h}" role="img" aria-label="Trend chart"><defs>']
    out.append('<linearGradient id="apAreaFill" x1="0" x2="0" y1="0" y2="1">'
               f'<stop offset="0" stop-color="{series[0][2]}" stop-opacity=".28"/>'
               f'<stop offset="1" stop-color="{series[0][2]}" stop-opacity="0"/></linearGradient></defs>')
    for j in range(5):  # gridlines + y labels
        v = lo + (hi - lo) * j / 4
        y = T + (1 - j / 4) * ph
        out.append(f'<line x1="{L}" x2="{w - R}" y1="{y:.1f}" y2="{y:.1f}" class="g"/>'
                   f'<text x="{L - 10}" y="{y + 4:.1f}" class="yl">{_k(v)}</text>')
    seen = set()
    for i, d in enumerate(dates):  # month labels at the first point of each month
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            x = xy(i, lo)[0]
            out.append(f'<text x="{x:.1f}" y="{h - 6}" class="xl">{d:%b}</text>')
    for k, (name, vals, color) in enumerate(series):
        pts = [xy(i, v) for i, v in enumerate(vals)]
        path = _smooth(pts)
        if k == 0:
            out.append(f'<path class="fillp" d="{path} L{pts[-1][0]:.1f},{T + ph} L{pts[0][0]:.1f},{T + ph} Z" '
                       'fill="url(#apAreaFill)"/>')
        out.append(f'<path class="ln l{k}" pathLength="1" d="{path}" fill="none" stroke="{color}" '
                   f'stroke-width="{3 if k == 0 else 2.2}" stroke-linecap="round"/>')
        ex, ey = pts[-1]
        out.append(f'<circle class="end" cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="{color}" stroke="#fff" '
                   'stroke-width="2"/>')
    for i, d in enumerate(dates):  # hover columns with native tooltips
        x = xy(i, lo)[0]
        label = d.strftime(tip) + "&#10;" + "&#10;".join(f"{nm}: ${vals[i]:,.0f}" for nm, vals, _ in series)
        out.append(f'<rect class="hit" x="{x - pw / (n - 1) / 2:.1f}" y="{T}" width="{pw / (n - 1):.1f}" '
                   f'height="{ph}"><title>{label}</title></rect>')
    out.append("</svg>")
    return "".join(out)


def chart_card(title: str, note: str, svg: str, legend: list[tuple[str, str, str]]) -> None:
    """A white card with title, note, legend (name, colour, value text) and an animated SVG chart."""
    leg = "".join(f'<span><i style="background:{c}"></i>{html.escape(n)} <b>{html.escape(v)}</b></span>'
                  for n, c, v in legend)
    st.markdown(f'<div class="ap-chart"><div class="hd"><div><div class="t">{html.escape(title)}</div>'
                f'<div class="nt">{html.escape(note)}</div></div><div class="lg">{leg}</div></div>{svg}</div>',
                unsafe_allow_html=True)


def compare_card(title: str, note: str, rows: list[tuple[str, float, str, str]], verdict: str = "") -> None:
    """Side-by-side comparison with growing bars: (name, value, value text, colour). Lower is better here."""
    top = max((v for _, v, _, _ in rows), default=0) or 1
    body = "".join(
        f'<div class="cr"><div class="cn">{html.escape(n)}</div><div class="cv">{html.escape(t)}</div>'
        f'<div class="ct"><div class="cf" style="width:{v / top * 100:.1f}%;background:{c}"></div></div></div>'
        for n, v, t, c in rows)
    st.html(f'<div class="ap-chart"><div class="hd"><div><div class="t">{html.escape(title)}</div>'
            f'<div class="nt">{html.escape(note)}</div></div></div><div class="cmp">{body}</div>'
            + (f'<div class="vd">{html.escape(verdict)}</div>' if verdict else "") + "</div>")


def stage(eyebrow: str, lead: str, big: str, after: str, detail_html: str = "", spark_svg: str = "",
          legend: list[tuple[str, str]] | None = None, pill: tuple[str, str] | None = None,
          caption: str = "") -> None:
    """The dark hero. Rendered with st.markdown because st.html strips SVG. Pass trusted HTML only."""
    leg = "".join(f'<span><i style="background:{c}"></i>{html.escape(t)}</span>' for t, c in (legend or []))
    pill_html = (f'<span class="ap-pill {pill[0]}">{html.escape(pill[1])}</span>') if pill else ""
    right = (f'<div class="ap-spark ap-rise ap-d2"><div class="legend">{leg}</div>{spark_svg}'
             + (f'<div class="cap">{html.escape(caption)}</div>' if caption else "") + "</div>"
             ) if spark_svg else "<div></div>"
    block = (f'<div class="ap-stage"><div><div class="eyebrow ap-rise">{html.escape(eyebrow)}</div>'
             f'<p class="lead ap-rise ap-d1">{html.escape(lead)}</p><div class="big ap-rise ap-d1">{big}</div>'
             f'<p class="lead ap-rise ap-d2">{html.escape(after)}</p>'
             f'<div class="row ap-rise ap-d3">{pill_html}<span class="detail">{detail_html}</span></div></div>'
             f'{right}</div>')
    st.markdown(block, unsafe_allow_html=True)


def section(title: str, note: str = "") -> None:
    st.html(f'<div class="ap-section"><h3>{html.escape(title)}</h3>'
            + (f"<span>{html.escape(note)}</span>" if note else "") + "</div>")


def status_list(*items: tuple[str, str]) -> None:
    st.html('<div class="ap-status">' + "".join(
        f'<div class="row"><span class="dot {k}"></span>{html.escape(t)}</div>' for t, k in items) + "</div>")


def badge(text: str, kind: str = "muted") -> str:
    return f'<span class="ap-badge {kind}">{html.escape(text)}</span>'


def badges(*items: tuple[str, str]) -> None:
    st.html('<div style="display:flex;gap:6px;flex-wrap:wrap">' + "".join(badge(t, k) for t, k in items) + "</div>")


def todo(items: list[tuple[str, str, str, str, str]]) -> None:
    """Action list rows: (tone good|bad|warn, title, detail, number, number caption)."""
    st.html('<div class="ap-todo">' + "".join(
        f'<div class="t"><div class="bar {tone}"></div><div><div class="h">{html.escape(t)}</div>'
        f'<div class="x">{html.escape(x)}</div></div><div class="n">{html.escape(n)}<small>{html.escape(c)}</small></div></div>'
        for tone, t, x, n, c in items) + "</div>")


def bars(items: list[tuple[str, float, str]], color: str = "linear-gradient(90deg,#FF8A5B,#C23B2E)") -> None:
    """Horizontal bars that grow in on load: (label, value, value text)."""
    top = max((v for _, v, _ in items), default=0) or 1
    st.html('<div class="ap-bars">' + "".join(
        f'<div class="r"><div class="k" title="{html.escape(k)}">{html.escape(k)}</div><div class="track">'
        f'<div class="fill" style="width:{max(2, v / top * 100):.1f}%;background:{color}"></div></div>'
        f'<div class="v">{html.escape(t)}</div></div>' for k, v, t in items) + "</div>")


def card_list(title: str, dot: str, rows: list[tuple[str, str, str, str]]) -> None:
    """A titled list card: (name, number text, number tone good|bad|'', detail line)."""
    st.html(f'<div class="ap-card-h"><span class="dot" style="background:{dot}"></span>{html.escape(title)}</div>'
            '<div class="ap-list">' + "".join(
                f'<div class="i"><div class="n">{html.escape(n)}</div><div class="x {tone}">{html.escape(x)}</div>'
                f'<div class="m">{html.escape(m)}</div></div>' for n, x, tone, m in rows) + "</div>")


def glossary(keys: list[str], title: str = "What do these words mean?") -> None:
    from adpulse import plain
    with st.expander(title):
        st.html('<dl class="ap-gloss">' + "".join(
            f"<dt>{html.escape(plain.label(k))}</dt><dd>{html.escape(plain.explain(k))}</dd>" for k in keys) + "</dl>")


_COLUMN_WORDS = [  # longest first: whole-name matches, then word swaps
    ("ltv_to_cac", "value vs cost"), ("ltv_cac", "value vs cost"), ("ltv_90d", "customer value (first 90 days)"),
    ("ltv90", "customer value (first 90 days)"), ("ad_name", "ad"), ("campaign_name", "campaign"),
    ("ad_group_name", "ad group"), ("new_customers", "new customers"), ("search_term", "what people searched"),
    ("acquisition_platform", "where they came from"), ("order_date", "date"),
]
_WORDS = {"ltv": "customer value", "cac": "cost per new customer", "roas": "money back per $1", "ctr": "click rate",
          "cvr": "buy rate", "avg": "average", "cnt": "count", "num": "number of", "pct": "%", "rev": "sales",
          "revenue": "sales", "spend": "ad spend", "impressions": "ad views", "sessions": "site visits",
          "conversions": "sales", "90d": "(first 90 days)", "30d": "(30 days)", "platform": "where", "qty": "quantity"}


def friendly_name(col: str) -> str:
    """'avg_ltv_90d' -> 'Average customer value (first 90 days)'."""
    c = str(col).lower()
    for raw, nice in _COLUMN_WORDS:
        if c == raw:
            return nice[0].upper() + nice[1:]
        c = c.replace(raw, nice.replace(" ", "\0"))
    words = [_WORDS.get(w, w) for w in c.replace("\0", " ").replace("_", " ").split()]
    out = " ".join(dict.fromkeys(words)) if words else str(col)  # drop accidental repeats
    return out[0].upper() + out[1:]


def friendly_df(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={c: friendly_name(c) for c in df.columns})


def md(text: str) -> str:
    """Escape `$` so Streamlit doesn't render dollar amounts as LaTeX math."""
    return (text or "").replace("\\$", "$").replace("$", "\\$")


def money(v, decimals: int = 0) -> str:
    if v is None or pd.isna(v):
        return "–"
    return f"${v:,.{decimals}f}"


def change_text(delta: float | None, better: str = "up", period: str = "") -> str:
    """'▲ 2.2% vs previous 30 days', coloured green when the move is good for the business."""
    if delta is None or pd.isna(delta):
        return ""
    if abs(delta) < 0.0005:
        cls, word = "flat", "No change"
    else:
        cls = "flat" if better == "neutral" else ("up" if (delta > 0) == (better == "up") else "down")
        word = f"{'▲' if delta > 0 else '▼'} {abs(delta):.1%}"
    return f'<span class="{cls}">{word}</span>' + (f" vs {html.escape(period)}" if period else "")


def kpi(label: str, value: str, delta: float | None = None, better: str = "up", note: str = "",
        help: str = "", period: str = "previous period") -> str:
    sub = change_text(delta, better, period) if delta is not None and not pd.isna(delta) else html.escape(note)
    tip = f' title="{html.escape(help)}"' if help else ""
    info = '<span class="i" aria-hidden="true">?</span>' if help else ""
    return (f'<div class="m"><div class="l"{tip}>{html.escape(label)}{info}</div><div class="v">{value}</div>'
            f'<div class="d">{sub}</div></div>')


def kpi_row(tiles: list[str]) -> None:
    st.html('<div class="ap-strip">' + "".join(tiles) + "</div>")


def style_fig(fig: go.Figure, height: int = 320, money_axis: bool = False) -> go.Figure:
    fig.update_layout(
        height=height, margin={"l": 8, "r": 8, "t": 64, "b": 8}, paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font={"family": "Figtree, system-ui, sans-serif", "size": 13, "color": "#2C3A57"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "xanchor": "left", "x": 0, "title": None,
                "font": {"size": 13}},
        hoverlabel={"bgcolor": "white", "font_size": 13, "bordercolor": "#E3E6EC"}, bargap=0.35,
        title={"font": {"family": "Bricolage Grotesque, Figtree, sans-serif", "size": 17, "color": INK},
               "x": 0.01, "xanchor": "left", "y": 0.97, "yanchor": "top"},
    )
    fig.update_xaxes(showgrid=False, linecolor="#E3E6EC", tickcolor="#E3E6EC")
    fig.update_yaxes(gridcolor="#EEF0F4", zeroline=False, tickprefix="$" if money_axis else "", separatethousands=True)
    fig.update_traces(selector={"type": "bar"}, marker_line_width=0)
    return fig


# ---- Cached data access -----------------------------------------------------------------------------------
# The live app talks to a cloud database; every round trip costs 0.2–1.5 s. Cache what doesn't change between
# clicks, and clear the relevant cache right after anything is written.

@st.cache_data(ttl=120, show_spinner=False)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    return warehouse.query_df(sql, dict(params))


@st.cache_data(ttl=30, show_spinner=False)
def _health():
    return warehouse.health()


def health():
    h = _health()
    if not h.ok:
        _health.clear()  # never cache an outage: try again on the next click
    return h


@st.cache_data(ttl=60, show_spinner=False)
def _has_data() -> bool:
    try:
        return bool(warehouse.query_df("SELECT count() AS n FROM fct_ad_daily").iloc[0]["n"])
    except Exception:  # noqa: BLE001
        return False


@st.cache_data(ttl=120, show_spinner=False)
def suggestions(status: str | None = None) -> pd.DataFrame:
    from adpulse.actions import recommendations as recs
    return recs.latest(status)


@st.cache_data(ttl=300, show_spinner=False)
def ad_economics(window: int) -> pd.DataFrame:
    from adpulse.actions import recommendations as recs
    return recs.ad_economics(window)


@st.cache_data(ttl=60, show_spinner=False)
def table_counts() -> pd.DataFrame:
    return warehouse.table_counts()


def suggestions_changed() -> None:
    """Call after saving or deciding a suggestion, so every page shows it straight away."""
    suggestions.clear()


def clear_cache() -> None:
    st.cache_data.clear()


def require_warehouse() -> bool:
    h = health()
    if not h.ok:
        s = get_settings()
        if s.clickhouse_host in ("localhost", "127.0.0.1") and Path("/mount/src").exists():
            st.error("**The app isn't connected to its data yet.** Open the app's **⋮ → Settings → Secrets**, "
                     "paste the contents of `streamlit-secrets.toml`, and click **Save**. The app restarts by itself.")
            return False
        st.error("**Can't reach the data right now.** If the database was asleep, refresh in a few seconds.  \n"
                 f"Technical detail: could not connect to `{s.clickhouse_host}:{s.clickhouse_port}` "
                 f"({h.error[:160]})")
        return False
    if not _has_data():
        _has_data.clear()
        st.warning("**No data loaded yet.** Open **Data status** and click **Load data now**.")
        return False
    return True


def reviewer() -> str:
    return st.session_state.get("reviewer", "").strip()


def step_icon(status: str) -> str:
    return {"ok": "✅", "retry": "🔁", "fail": "❌"}.get(status, "•")
