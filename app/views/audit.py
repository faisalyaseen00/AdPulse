import plotly.graph_objects as go
import streamlit as st
import ui

from adpulse.actions import recommendations as recs
from adpulse.audit import search_terms
from adpulse.config import get_settings
from adpulse.llm import LLMError, get_llm

ui.hero("Search term audit", "What people actually typed before you paid for the click, and which terms have no buyer intent.")
if not ui.require_warehouse():
    st.stop()

c1, c2, c3 = st.columns([2, 2, 3])
days = c1.selectbox("Window", [7, 14, 30, 90], index=2, format_func=lambda d: f"Last {d} days")
min_cost = c2.number_input("Min. cost to flag ($)", 0.0, 500.0, 5.0, 5.0)
use_llm = c3.toggle("Classify unmatched terms with AI", value=get_settings().llm_configured,
                    disabled=not get_settings().llm_configured,
                    help="Rules handle known patterns (jobs, free, DIY, support...). The LLM classifies the rest.")


@st.cache_data(ttl=300, show_spinner="Auditing search terms…")
def run(days: int, min_cost: float, use_llm: bool):
    llm = None
    if use_llm:
        try:
            llm = get_llm()
        except LLMError:
            llm = None
    return search_terms.audit(days, llm=llm, min_cost=min_cost)


df = run(days, min_cost, use_llm)
if df.empty:
    st.info("No search term data in this window.")
    st.stop()
s = search_terms.summary(df)
ui.kpi_row([
    ui.kpi("Search terms", f"{s['terms']:,}"),
    ui.kpi("Flagged", f"{s['flagged']:,}", note="no buyer intent"),
    ui.kpi("Wasted spend", ui.money(s["wasted_spend"], 2)),
    ui.kpi("Share of search spend", f"{s['wasted_share']:.1%}"),
])

left, right = st.columns([3, 2])
with right:
    by = df[df.flagged].groupby("intent", as_index=False)["wasted_spend"].sum().sort_values("wasted_spend")
    fig = go.Figure(go.Bar(y=by.intent.str.title(), x=by.wasted_spend, orientation="h",
                           marker_color=ui.SERIES[1], text=[ui.money(v) for v in by.wasted_spend],
                           textposition="outside", hovertemplate="%{y}: $%{x:,.2f}<extra></extra>"))
    fig.update_layout(title="Wasted spend by intent", showlegend=False)
    fig = ui.style_fig(fig, height=240)
    fig.update_xaxes(tickprefix="$", showgrid=True, gridcolor="#eeede9")
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")
    camp = df[df.flagged].groupby("campaign_name", as_index=False)["wasted_spend"].sum().sort_values(
        "wasted_spend", ascending=False)
    st.dataframe(camp, hide_index=True, width="stretch", column_config={
        "campaign_name": "Campaign", "wasted_spend": st.column_config.NumberColumn("Wasted", format="$%.2f")})

with left:
    st.markdown("##### Flagged terms")
    st.caption("Tick the terms to block, then queue them. Negatives are only added after approval.")
    flagged = df[df.flagged].copy()
    flagged.insert(0, "queue", True)
    edited = st.data_editor(
        flagged[["queue", "search_term", "campaign_name", "ad_group_name", "clicks", "cost", "conversions", "intent",
                 "reason", "suggested_negative", "classified_by"]],
        hide_index=True, width="stretch", height=min(520, 40 + 35 * len(flagged)),
        disabled=[c for c in flagged.columns if c != "queue"],
        column_config={
            "queue": st.column_config.CheckboxColumn("Block", width="small"),
            "search_term": st.column_config.TextColumn("Search term", width="medium"),
            "campaign_name": "Campaign", "ad_group_name": "Ad group",
            "cost": st.column_config.NumberColumn("Cost", format="$%.2f"),
            "conversions": st.column_config.NumberColumn("Conv.", format="%.0f"),
            "suggested_negative": "Negative keyword", "classified_by": "By",
        })
    chosen = edited[edited.queue]["search_term"].tolist()
    b1, b2 = st.columns(2)
    if b1.button(f"Queue {len(chosen)} negative keyword(s) for approval", type="primary", disabled=not chosen,
                 width="stretch"):
        n = recs.save(recs.audit_recommendations(df, chosen))
        st.success(f"{n} new negative keyword recommendation(s) added to **Approvals**"
                   + ("" if n == len(chosen) else f" ({len(chosen) - n} were already pending)."))
    b2.download_button("Download full audit (CSV)", df.to_csv(index=False), f"search_term_audit_{days}d.csv",
                       "text/csv", width="stretch")

with st.expander(f"All {len(df)} terms"):
    st.dataframe(df.drop(columns=["rule"]), hide_index=True, width="stretch")
