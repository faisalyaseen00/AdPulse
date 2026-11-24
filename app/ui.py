"""Shared UI building blocks: styling, KPI tiles, badges, charts, cached queries."""
from __future__ import annotations

import html

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
:root { --ap-border:#e7e6e2; --ap-muted:#6b6a66; --ap-surface:#ffffff; --ap-soft:#f6f6f4; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1320px; }
h1, h2, h3 { letter-spacing: -0.01em; }
[data-testid="stSidebar"] { background: #f6f6f4; border-right: 1px solid var(--ap-border); }
.ap-hero { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin-bottom: .6rem; }
.ap-hero h1 { font-size: 1.75rem; margin: 0; padding: 0; }
.ap-hero p { color: var(--ap-muted); margin: .2rem 0 0; font-size: .95rem; }
.ap-kpi { background: var(--ap-surface); border:1px solid var(--ap-border); border-radius: 12px;
          padding: 14px 16px 12px; height: 100%; }
.ap-kpi .lbl { color: var(--ap-muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
.ap-kpi .val { font-size: 1.55rem; font-weight: 650; margin-top: 2px; font-variant-numeric: tabular-nums; }
.ap-kpi .sub { font-size: .8rem; margin-top: 2px; color: var(--ap-muted); font-variant-numeric: tabular-nums; }
.ap-kpi .up { color: #15803d; } .ap-kpi .down { color: #b91c1c; }
.ap-badge { display:inline-flex; align-items:center; gap:4px; padding: 2px 9px; border-radius: 999px;
            font-size: .76rem; font-weight: 600; border: 1px solid transparent; white-space: nowrap; }
.ap-badge.good { background:#e8f5e9; color:#14532d; border-color:#b7dfbf; }
.ap-badge.bad { background:#fdecea; color:#7f1d1d; border-color:#f4c4bf; }
.ap-badge.warn { background:#fff4dc; color:#713f12; border-color:#f3d59a; }
.ap-badge.info { background:#e8f0fb; color:#173f73; border-color:#bcd3f2; }
.ap-badge.muted { background:#f1f1ef; color:#4a4946; border-color:#e2e1dc; }
.ap-flow { display:flex; align-items:stretch; gap:6px; flex-wrap:nowrap; margin: 4px 0 8px; overflow-x:auto; }
.ap-flow .node { flex:1 1 0; min-width:96px; background:#fff; border:1px solid var(--ap-border); border-radius:10px; padding:10px 12px; }
.ap-flow .node .t { font-size:.72rem; color:var(--ap-muted); text-transform:uppercase; letter-spacing:.04em; }
.ap-flow .node .v { font-weight:650; font-size:1.15rem; font-variant-numeric: tabular-nums; }
.ap-flow .node .s { font-size:.75rem; color:var(--ap-muted); }
.ap-flow .arr { align-self:center; color:#a3a29c; font-size:1.1rem; }
.ap-card-title { font-weight: 650; font-size: 1.02rem; }
.ap-muted { color: var(--ap-muted); font-size: .86rem; }
.ap-step { display:flex; gap:10px; align-items:flex-start; padding:6px 0; border-bottom:1px dashed var(--ap-border); font-size:.88rem; }
.ap-step:last-child { border-bottom:none; }
.ap-step .ic { width: 20px; text-align:center; }
.ap-step .nm { font-weight:600; min-width: 130px; }
.ap-step .dt { color: var(--ap-muted); flex:1; }
.ap-step .ms { color: var(--ap-muted); font-variant-numeric: tabular-nums; }
div[data-testid="stChatMessage"] { background: transparent; }
@media (max-width: 640px) { .ap-hero { flex-direction: column; align-items: flex-start; } }
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def hero(title: str, subtitle: str = "") -> None:
    st.html(f'<div class="ap-hero"><div><h1>{html.escape(title)}</h1>'
            f'<p>{html.escape(subtitle)}</p></div></div>')


def badge(text: str, kind: str = "muted") -> str:
    return f'<span class="ap-badge {kind}">{html.escape(text)}</span>'


def badges(*items: tuple[str, str]) -> None:
    st.html('<div style="display:flex;gap:6px;flex-wrap:wrap">' + "".join(badge(t, k) for t, k in items) + "</div>")


def money(v, decimals: int = 0) -> str:
    if v is None or pd.isna(v):
        return "–"
    return f"${v:,.{decimals}f}"


def kpi(label: str, value: str, delta: float | None = None, better: str = "up", note: str = "") -> str:
    sub = note
    if delta is not None and not pd.isna(delta):
        good = (delta > 0) == (better == "up")
        cls = "up" if good else "down"
        arrow = "▲" if delta > 0 else "▼"
        sub = f'<span class="{cls}">{arrow} {abs(delta):.1%}</span> vs prior {note}'.strip()
    return (f'<div class="ap-kpi"><div class="lbl">{html.escape(label)}</div><div class="val">{value}</div>'
            f'<div class="sub">{sub}</div></div>')


def kpi_row(tiles: list[str]) -> None:
    cols = st.columns(len(tiles))
    for c, t in zip(cols, tiles):
        c.html(t)


def style_fig(fig: go.Figure, height: int = 320, money_axis: bool = False) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=36, b=8), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, system-ui, sans-serif", size=12, color="#2b2a28"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None),
        hoverlabel=dict(bgcolor="white", font_size=12), bargap=0.25, title=dict(font=dict(size=14)),
    )
    fig.update_xaxes(showgrid=False, linecolor="#d8d7d2", tickcolor="#d8d7d2")
    fig.update_yaxes(gridcolor="#eeede9", zeroline=False, tickprefix="$" if money_axis else "",
                     separatethousands=True)
    fig.update_traces(selector=dict(type="bar"), marker_line_width=0)
    return fig


@st.cache_data(ttl=120, show_spinner=False)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    return warehouse.query_df(sql, dict(params))


def clear_cache() -> None:
    q.clear()


def require_warehouse() -> bool:
    h = warehouse.health()
    if not h.ok:
        st.error(f"Cannot reach ClickHouse at {get_settings().clickhouse_host}:{get_settings().clickhouse_port}.\n\n"
                 f"`{h.error[:300]}`\n\nStart it with `docker compose up -d clickhouse` (see README).")
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
