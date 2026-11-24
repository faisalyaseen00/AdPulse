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
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1240px; }
h1, h2, h3, h4 { font-family: var(--display); color: var(--ink); letter-spacing: -0.01em; }
.stMarkdown p, .stMarkdown li { font-size: 1rem; line-height: 1.6; color: var(--ink-2); }
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; height: 0; }
/* hosting toolbar (Fork / GitHub / deploy buttons) is noise for business readers */
[data-testid="stToolbar"], [data-testid="stToolbarActions"], .stAppDeployButton { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }
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

/* Page header: quiet, left aligned */
.ap-head { margin: 0 0 1.4rem; max-width: 760px; }
.ap-head h1 { font-size: 2rem; font-weight: 750; margin: 0; padding: 0; line-height: 1.15; }
.ap-head p { color: var(--muted); font-size: 1.05rem; margin: .4rem 0 0; line-height: 1.5; }

/* The one loud moment: the plain-English verdict on Overview */
.ap-verdict { margin: .2rem 0 1.6rem; max-width: 900px; }
.ap-verdict .say { font-family: var(--display); font-weight: 650; font-size: clamp(1.6rem, 3.2vw, 2.55rem);
  line-height: 1.18; letter-spacing: -0.02em; color: var(--ink); margin: 0; }
.ap-verdict .say b { font-weight: 750; background: linear-gradient(transparent 64%, rgba(244,180,0,.38) 64%); padding: 0 2px; }
.ap-verdict .pulse { display:block; width: 180px; height: 22px; margin: 14px 0 10px;
  background: no-repeat left center / contain url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 180 22'%3E%3Cpolyline fill='none' stroke='%23F4B400' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' points='2,12 52,12 62,12 70,3 80,20 90,8 98,12 178,12'/%3E%3C/svg%3E"); }
.ap-verdict .more { font-size: 1.05rem; color: var(--ink-2); line-height: 1.6; max-width: 760px; margin: 0; }
.ap-verdict .more .up { color: var(--good); font-weight: 650; } .ap-verdict .more .down { color: var(--bad); font-weight: 650; }

/* Section header */
.ap-section { display:flex; align-items:baseline; gap:12px; flex-wrap: wrap; margin: 2rem 0 .7rem; }
.ap-section h3 { font-size: 1.3rem; font-weight: 650; margin:0; padding:0; }
.ap-section span { color: var(--muted); font-size: .95rem; }

/* Numbers at a glance: one panel, hairline dividers */
.ap-strip { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); background: var(--surface);
  border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
.ap-strip .m { padding: 16px 18px 15px; border-right: 1px solid var(--line-2); border-bottom: 1px solid var(--line-2);
  margin: 0 -1px -1px 0; container-type: inline-size; }
.ap-strip .l { font-size: .9rem; color: var(--muted); font-weight: 500; display:flex; gap:6px; align-items:center; cursor: help; }
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
.ap-todo .n { font-family: var(--display); font-weight: 700; font-size: 1.15rem; color: var(--ink); white-space: nowrap; }
.ap-todo .n small { display:block; font-family: var(--body); font-weight: 500; font-size: .78rem; color: var(--muted); text-align: right; }

/* Journey: ad view to customer */
.ap-flow { display:flex; align-items:stretch; flex-wrap: nowrap; overflow-x:auto; background: var(--surface);
  border: 1px solid var(--line); border-radius: 14px; }
.ap-flow .node { flex: 1 1 0; min-width: 128px; padding: 14px 16px; border-right: 1px solid var(--line-2); }
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
@media (max-width: 900px) { .ap-how { grid-template-columns: 1fr 1fr; } .ap-how .st:nth-child(2) { border-right: none; } }
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 3.6rem; }
  .ap-head h1 { font-size: 1.6rem; }
  .ap-todo .t { grid-template-columns: 6px 1fr; } .ap-todo .n { grid-column: 2; }
  .ap-gloss { grid-template-columns: 1fr; }
}
</style>
"""

PULSE_SVG = '<div class="pulse" aria-hidden="true"></div>'


def inject_css() -> None:
    st.html(CSS)


def hero(title: str, subtitle: str = "", icon: str = "") -> None:
    st.html(f'<div class="ap-head"><h1>{html.escape(title)}</h1>'
            + (f"<p>{html.escape(subtitle)}</p>" if subtitle else "") + "</div>")


def verdict(say_html: str, more_html: str = "") -> None:
    """The plain-English headline at the top of Overview. Pass trusted HTML (numbers escaped by caller)."""
    st.html(f'<div class="ap-verdict"><p class="say">{say_html}</p>{PULSE_SVG}'
            + (f'<p class="more">{more_html}</p>' if more_html else "") + "</div>")


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
        cls = "up" if (delta > 0) == (better == "up") else "down"
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


@st.cache_data(ttl=120, show_spinner=False)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    return warehouse.query_df(sql, dict(params))


def clear_cache() -> None:
    q.clear()


def require_warehouse() -> bool:
    h = warehouse.health()
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
    try:
        n = warehouse.query_df("SELECT count() AS n FROM fct_ad_daily").iloc[0]["n"]
    except Exception:  # noqa: BLE001
        n = 0
    if not n:
        st.warning("**No data loaded yet.** Open **Data status** and click **Load data now**.")
        return False
    return True


def reviewer() -> str:
    return st.session_state.get("reviewer", "").strip()


def step_icon(status: str) -> str:
    return {"ok": "✅", "retry": "🔁", "fail": "❌"}.get(status, "•")
