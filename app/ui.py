"""Shared UI building blocks: styling, KPI tiles, badges, charts, cached queries."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from adpulse import warehouse
from adpulse.config import get_settings

# Validated categorical palette (slot order matters for colour-blind safety).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
PLATFORM_COLORS = {"meta": SERIES[0], "google": SERIES[1], "unpaid": "#8a8985"}
GOOD, BAD, WARN, MUTED = "#008300", "#c0392b", "#b26b00", "#6b6a66"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
  --ap-brand:#2a78d6; --ap-brand-2:#5b5bd6; --ap-brand-soft:#eaf2fc;
  --ap-ink:#0f1419; --ap-muted:#667085; --ap-border:#e6e8ec; --ap-surface:#ffffff; --ap-soft:#f6f7f9;
  --ap-good:#15803d; --ap-bad:#b42318; --ap-radius:14px;
  --ap-shadow:0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.06);
  --ap-shadow-lg:0 8px 24px -6px rgba(16,24,40,.12);
}
html, body, .stApp, .stMarkdown p, button, input, textarea { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
code, pre, .stCode * { font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important; }
.stApp { background: #fafbfc; }
.block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1360px; }
h1, h2, h3, h4, h5 { letter-spacing: -0.015em; color: var(--ap-ink); }
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; height: 0; }
header[data-testid="stHeader"] { background: transparent; }

/* Sidebar */
[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid var(--ap-border); }
[data-testid="stSidebarHeader"] img, [data-testid="stLogo"] { height: 2.1rem !important; max-width: 100%; }
[data-testid="stSidebarNav"] a { border-radius: 10px; margin: 1px 6px; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: var(--ap-brand-soft); }
[data-testid="stSidebarNav"] a[aria-current="page"] span { color: var(--ap-brand) !important; font-weight: 600; }
.ap-brand { display:flex; align-items:center; gap:10px; padding: 2px 0 8px; }
.ap-brand .logo { width:36px; height:36px; border-radius:10px; display:grid; place-items:center; color:#fff;
  font-weight:700; font-size:1.05rem; background: linear-gradient(135deg, var(--ap-brand), var(--ap-brand-2));
  box-shadow: 0 4px 12px -2px rgba(42,120,214,.45); }
.ap-brand .nm { font-weight:700; font-size:1.08rem; color:var(--ap-ink); line-height:1.1; }
.ap-brand .tg { font-size:.74rem; color:var(--ap-muted); }
.ap-status { display:flex; flex-direction:column; gap:6px; margin: 4px 0; }
.ap-status .row { display:flex; align-items:center; gap:8px; font-size:.8rem; color:#344054; }
.ap-status .dot { width:8px; height:8px; border-radius:50%; flex: none; }
.ap-status .dot.good { background:#12b76a; box-shadow:0 0 0 3px #d1fadf; }
.ap-status .dot.info { background:var(--ap-brand); box-shadow:0 0 0 3px #d6e6f8; }
.ap-status .dot.warn { background:#f79009; box-shadow:0 0 0 3px #fef0c7; }
.ap-status .dot.bad { background:#f04438; box-shadow:0 0 0 3px #fee4e2; }
.ap-status .dot.muted { background:#98a2b3; box-shadow:0 0 0 3px #eaecf0; }
.ap-side-label { font-size:.7rem; font-weight:600; text-transform:uppercase; letter-spacing:.06em; color:var(--ap-muted); margin: 10px 0 4px; }

/* Page header */
.ap-hero { position:relative; display:flex; align-items:center; gap:16px; margin: 0 0 1.1rem; padding: 18px 22px;
  background: linear-gradient(120deg, #ffffff 0%, #f3f7fd 60%, #eef0fc 100%); border:1px solid var(--ap-border);
  border-radius: 18px; box-shadow: var(--ap-shadow); overflow:hidden; }
.ap-hero::before { content:""; position:absolute; inset:0 auto 0 0; width:5px;
  background: linear-gradient(180deg, var(--ap-brand), var(--ap-brand-2)); }
.ap-hero .ic { width:46px; height:46px; border-radius:12px; display:grid; place-items:center; font-size:1.4rem;
  background:#fff; border:1px solid var(--ap-border); box-shadow: var(--ap-shadow); flex:none; }
.ap-hero h1 { font-size: 1.6rem; font-weight:700; margin: 0; padding: 0; line-height:1.2; }
.ap-hero p { color: var(--ap-muted); margin: .25rem 0 0; font-size: .93rem; }

/* Section header */
.ap-section { display:flex; align-items:baseline; gap:10px; margin: 1.4rem 0 .5rem; }
.ap-section h3 { font-size: 1.05rem; font-weight: 650; margin:0; padding:0; }
.ap-section span { color: var(--ap-muted); font-size: .84rem; }

/* KPI tiles */
.ap-kpi { container-type: inline-size; position:relative; background: var(--ap-surface); border:1px solid var(--ap-border); border-radius: var(--ap-radius);
  padding: 14px 16px 13px; height: 100%; box-shadow: var(--ap-shadow); transition: box-shadow .15s, transform .15s; overflow:hidden; }
.ap-kpi::after { content:""; position:absolute; left:0; right:0; top:0; height:3px;
  background: linear-gradient(90deg, var(--ap-brand), var(--ap-brand-2)); opacity:.85; }
.ap-kpi:hover { box-shadow: var(--ap-shadow-lg); transform: translateY(-1px); }
.ap-kpi .lbl { color: var(--ap-muted); font-size: .7rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight:600; text-transform: uppercase; letter-spacing: .05em; }
.ap-kpi .val { font-size: clamp(0.85rem, 15cqi, 1.6rem); white-space: nowrap; font-weight: 700; margin-top: 4px; color: var(--ap-ink); font-variant-numeric: tabular-nums; letter-spacing:-.02em; }
.ap-kpi .sub { font-size: .78rem; margin-top: 4px; color: var(--ap-muted); font-variant-numeric: tabular-nums; }
.ap-kpi .chip { display:inline-block; padding:1px 7px; border-radius:999px; font-weight:600; margin-right:4px; }
.ap-kpi .up { color: var(--ap-good); background:#ecfdf3; } .ap-kpi .down { color: var(--ap-bad); background:#fef3f2; }
.ap-kpi .flat { color: var(--ap-muted); background:#f2f4f7; }

/* Badges */
.ap-badge { display:inline-flex; align-items:center; gap:4px; padding: 3px 10px; border-radius: 999px;
            font-size: .75rem; font-weight: 600; border: 1px solid transparent; white-space: nowrap; }
.ap-badge.good { background:#ecfdf3; color:#067647; border-color:#abefc6; }
.ap-badge.bad { background:#fef3f2; color:#b42318; border-color:#fecdca; }
.ap-badge.warn { background:#fffaeb; color:#b54708; border-color:#fedf89; }
.ap-badge.info { background:#eff8ff; color:#175cd3; border-color:#b2ddff; }
.ap-badge.muted { background:#f2f4f7; color:#344054; border-color:#eaecf0; }

/* Flow / funnel */
.ap-flow { display:flex; align-items:stretch; gap:8px; flex-wrap:nowrap; margin: 4px 0 10px; overflow-x:auto; padding-bottom:2px; }
.ap-flow .node { flex:1 1 0; min-width:110px; background:#fff; border:1px solid var(--ap-border); border-radius:12px;
  padding:12px 14px; box-shadow: var(--ap-shadow); }
.ap-flow .node:last-child { background: linear-gradient(135deg, #f3f7fd, #eef0fc); border-color:#c9d9f2; }
.ap-flow .node .t { font-size:.7rem; color:var(--ap-muted); font-weight:600; text-transform:uppercase; letter-spacing:.05em; }
.ap-flow .node .v { font-weight:700; font-size:1.2rem; color:var(--ap-ink); font-variant-numeric: tabular-nums; margin-top:2px; }
.ap-flow .node .s { font-size:.75rem; color:var(--ap-brand); font-weight:500; margin-top:1px; }
.ap-flow .arr { align-self:center; color:#98a2b3; font-size:1rem; font-weight:700; }

/* Streamlit widgets */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { border-radius: var(--ap-radius); }
div[data-testid="stVerticalBlockBorderWrapper"][style*="border"] , .stContainer { border-radius: var(--ap-radius); }
[data-testid="stVerticalBlockBorderWrapper"] { background: transparent; }
div[data-testid="stExpander"] details { border-radius: 12px; border-color: var(--ap-border); background:#fff; }
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button { border-radius: 10px; font-weight: 600;
  transition: transform .1s, box-shadow .15s; }
.stButton > button:hover, .stDownloadButton > button:hover { box-shadow: var(--ap-shadow-lg); }
.stButton > button[kind="secondary"] { background:#fff; border-color: var(--ap-border); }
.stButton > button[kind="secondary"]:hover { border-color: var(--ap-brand); color: var(--ap-brand); }
.stButton > button p { white-space: normal; text-align: left; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: linear-gradient(135deg, var(--ap-brand), #3b6fe0); border: none; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border:1px solid var(--ap-border); border-radius: 12px;
  overflow:hidden; box-shadow: var(--ap-shadow); background:#fff; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--ap-border); }
.stTabs [data-baseweb="tab"] { padding: 8px 14px; font-weight: 500; }
.stTabs [aria-selected="true"] { color: var(--ap-brand); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--ap-brand); }
[data-testid="stPlotlyChart"] { background:#fff; border:1px solid var(--ap-border); border-radius: var(--ap-radius);
  padding: 8px 10px 4px; box-shadow: var(--ap-shadow); }
[data-testid="stChatMessage"] { background: #fff; border:1px solid var(--ap-border); border-radius: var(--ap-radius);
  box-shadow: var(--ap-shadow); padding: 14px 16px; }
[data-testid="stChatInput"] { border-radius: 14px; }
[data-testid="stAlert"] { border-radius: 12px; }

.ap-how { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:10px; margin: 2px 0 6px; }
.ap-how .st { display:flex; gap:10px; background:#fff; border:1px solid var(--ap-border); border-radius:12px;
  padding:12px 14px; box-shadow: var(--ap-shadow); }
.ap-how .n { width:26px; height:26px; flex:none; border-radius:8px; display:grid; place-items:center; font-weight:700;
  font-size:.8rem; color:#fff; background: linear-gradient(135deg, var(--ap-brand), var(--ap-brand-2)); }
.ap-how .h { font-weight:650; font-size:.88rem; color:var(--ap-ink); }
.ap-how .d { font-size:.78rem; color:var(--ap-muted); margin-top:2px; line-height:1.35; }
@media (max-width: 900px) { .ap-how { grid-template-columns: repeat(2, minmax(0,1fr)); } }
.ap-card-title { font-weight: 650; font-size: 1.02rem; color: var(--ap-ink); }
.ap-muted { color: var(--ap-muted); font-size: .86rem; }
.ap-step { display:flex; gap:10px; align-items:flex-start; padding:7px 0; border-bottom:1px dashed var(--ap-border); font-size:.88rem; }
.ap-step:last-child { border-bottom:none; }
.ap-step .ic { width: 20px; text-align:center; }
.ap-step .nm { font-weight:600; min-width: 130px; }
.ap-step .dt { color: var(--ap-muted); flex:1; }
.ap-step .ms { color: var(--ap-muted); font-variant-numeric: tabular-nums; }
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 3.6rem; }
  .ap-hero { padding: 14px 16px; } .ap-hero .ic { display:none; } .ap-hero h1 { font-size: 1.3rem; }
}
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def hero(title: str, subtitle: str = "", icon: str = "") -> None:
    ic = f'<div class="ic">{icon}</div>' if icon else ""
    st.html(f'<div class="ap-hero">{ic}<div><h1>{html.escape(title)}</h1>'
            f'<p>{html.escape(subtitle)}</p></div></div>')


def section(title: str, note: str = "") -> None:
    """Consistent section header with an optional muted note."""
    st.html(f'<div class="ap-section"><h3>{html.escape(title)}</h3>'
            + (f"<span>{html.escape(note)}</span>" if note else "") + "</div>")


def status_list(*items: tuple[str, str]) -> None:
    st.html('<div class="ap-status">' + "".join(
        f'<div class="row"><span class="dot {k}"></span>{html.escape(t)}</div>' for t, k in items) + "</div>")


def badge(text: str, kind: str = "muted") -> str:
    return f'<span class="ap-badge {kind}">{html.escape(text)}</span>'


def badges(*items: tuple[str, str]) -> None:
    st.html('<div style="display:flex;gap:6px;flex-wrap:wrap">' + "".join(badge(t, k) for t, k in items) + "</div>")


def md(text: str) -> str:
    """Escape `$` so Streamlit doesn't render dollar amounts as LaTeX math."""
    return (text or "").replace("\\$", "$").replace("$", "\\$")


def money(v, decimals: int = 0) -> str:
    if v is None or pd.isna(v):
        return "–"
    return f"${v:,.{decimals}f}"


def kpi(label: str, value: str, delta: float | None = None, better: str = "up", note: str = "") -> str:
    sub = note
    if delta is not None and not pd.isna(delta):
        good = (delta > 0) == (better == "up")
        cls = "flat" if abs(delta) < 0.0005 else ("up" if good else "down")
        arrow = "–" if cls == "flat" else ("▲" if delta > 0 else "▼")
        sub = f'<span class="chip {cls}">{arrow} {abs(delta):.1%}</span>vs prior {note}'.strip()
    return (f'<div class="ap-kpi"><div class="lbl">{html.escape(label)}</div><div class="val">{value}</div>'
            f'<div class="sub">{sub}</div></div>')


def kpi_row(tiles: list[str]) -> None:
    cols = st.columns(len(tiles))
    for c, t in zip(cols, tiles):
        c.html(t)


def style_fig(fig: go.Figure, height: int = 320, money_axis: bool = False) -> go.Figure:
    fig.update_layout(
        height=height, margin={"l": 8, "r": 8, "t": 72, "b": 8}, paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font={"family": "Inter, system-ui, sans-serif", "size": 12, "color": "#344054"},
        # legend sits on its own line under the title, so they never overlap or clip
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "xanchor": "left", "x": 0, "title": None,
                    "font": {"size": 12}},
        hoverlabel={"bgcolor": "white", "font_size": 12, "bordercolor": "#e6e8ec"}, bargap=0.3,
        title={"font": {"size": 14, "color": "#0f1419"}, "x": 0.01, "xanchor": "left", "y": 0.97, "yanchor": "top"},
    )
    fig.update_xaxes(showgrid=False, linecolor="#d8d7d2", tickcolor="#d8d7d2")
    fig.update_yaxes(gridcolor="#eeede9", zeroline=False, tickprefix="$" if money_axis else "",
                     separatethousands=True)
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
            st.error("**No database settings found.** On Streamlit Cloud, open the app's **⋮ → Settings → Secrets**, "
                     "paste the contents of `streamlit-secrets.toml`, and click **Save**. The app restarts by itself.")
            return False
        st.error(f"Cannot reach ClickHouse at {s.clickhouse_host}:{s.clickhouse_port}.\n\n"
                 f"`{h.error[:300]}`\n\nLocally, start it with `docker compose up -d clickhouse` (see README). "
                 "On ClickHouse Cloud, check the service is running and its IP access list allows connections.")
        return False
    try:
        n = warehouse.query_df("SELECT count() AS n FROM fct_ad_daily").iloc[0]["n"]
    except Exception:  # noqa: BLE001
        n = 0
    if not n:
        st.warning("The warehouse is empty. Load data on the **Data pipeline** page, or run `adpulse setup`.")
        return False
    return True


def reviewer() -> str:
    return st.session_state.get("reviewer", "").strip()


def step_icon(status: str) -> str:
    return {"ok": "✅", "retry": "🔁", "fail": "❌"}.get(status, "•")
