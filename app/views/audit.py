import plotly.graph_objects as go
import streamlit as st
import ui

from adpulse import plain
from adpulse.actions import recommendations as recs
from adpulse.audit import search_terms
from adpulse.config import get_settings
from adpulse.llm import LLMError, get_llm

ui.hero("Wasted searches", "The exact words people typed into Google before clicking your ad. Some of them were "
        "never going to buy. Block those and stop paying for their clicks.")
if not ui.require_warehouse():
    st.stop()

c1, c2, c3 = st.columns([2, 2, 3], vertical_alignment="bottom")
days = c1.selectbox("Period", [7, 14, 30, 90], index=2, format_func=lambda d: f"Last {d} days")
min_cost = c2.number_input("Only show searches that cost at least ($)", 0.0, 500.0, 5.0, 5.0)
use_llm = c3.toggle("Let AI sort the unusual searches", value=get_settings().llm_configured,
                    disabled=not get_settings().llm_configured,
                    help="Simple rules catch the common cases (jobs, free stuff, store hours). The AI sorts the rest.")


@st.cache_data(ttl=300, show_spinner="Checking your searches…")
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
    st.info("No Google searches in this period.")
    st.stop()
s = search_terms.summary(df)
ui.kpi_row([
    ui.kpi("Searches checked", f"{s['terms']:,}", note=f"last {days} days"),
    ui.kpi("Not buyers", f"{s['flagged']:,}", note="searches to block"),
    ui.kpi(plain.label("wasted"), ui.money(s["wasted_spend"], 2), note="paid for clicks that won't sell",
           help=plain.explain("wasted")),
    ui.kpi("Share of search budget", f"{s['wasted_share']:.0%}", note="went to these searches"),
])
df = df.assign(kind=df.intent.map(plain.intent), by=df.classified_by.map({"rule": "Rule", "llm": "AI"}).fillna("Rule"))

left, right = st.columns([3, 2])
with right:
    by = df[df.flagged].groupby("kind", as_index=False)["wasted_spend"].sum().sort_values("wasted_spend")
    fig = go.Figure(go.Bar(y=by.kind, x=by.wasted_spend, orientation="h",
                           marker_color=ui.SERIES[1], text=[ui.money(v) for v in by.wasted_spend],
                           textposition="outside", hovertemplate="%{y}: $%{x:,.2f}<extra></extra>"))
    fig.update_layout(title="Where the money went", showlegend=False)
    fig = ui.style_fig(fig, height=250)
    fig.update_xaxes(tickprefix="$", showgrid=True, gridcolor="#EEF0F4")
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")
    camp = df[df.flagged].groupby("campaign_name", as_index=False)["wasted_spend"].sum().sort_values(
        "wasted_spend", ascending=False)
    st.dataframe(camp, hide_index=True, width="stretch", column_config={
        "campaign_name": "Campaign", "wasted_spend": st.column_config.NumberColumn("Wasted", format="$%.2f")})

with left:
    ui.section("Searches to block")
    st.caption("Untick any you want to keep. Blocking only happens after you approve it on the Suggestions page.")
    flagged = df[df.flagged].copy()
    flagged.insert(0, "block", True)
    edited = st.data_editor(
        flagged[["block", "search_term", "reason", "cost", "clicks", "conversions", "campaign_name", "kind",
                 "suggested_negative", "by"]],
        hide_index=True, width="stretch", height=min(520, 40 + 35 * len(flagged)),
        disabled=[c for c in flagged.columns if c != "block"],
        column_config={
            "block": st.column_config.CheckboxColumn("Block", width="small"),
            "search_term": st.column_config.TextColumn(plain.label("search_term"), width="medium",
                                                      help=plain.explain("search_term")),
            "reason": st.column_config.TextColumn("Why it's wasted", width="medium"),
            "cost": st.column_config.NumberColumn("Cost", format="$%.2f"),
            "conversions": st.column_config.NumberColumn("Sales", format="%.0f"),
            "campaign_name": "Campaign", "kind": "Type of searcher",
            "suggested_negative": st.column_config.TextColumn("Block as", help="What gets added to Google's blocked "
                                                              "list. Quotes block any search containing the words; "
                                                              "[brackets] block only that exact search."),
            "by": st.column_config.TextColumn("Sorted by", width="small"),
        })
    chosen = edited[edited.block]["search_term"].tolist()
    b1, b2 = st.columns(2)
    if b1.button(f"Add {len(chosen)} search(es) to suggestions", type="primary", disabled=not chosen,
                 width="stretch"):
        n = recs.save(recs.audit_recommendations(df, chosen))
        ui.suggestions_changed()
        st.success(f"Added {n} search(es) to **Suggestions**"
                   + ("." if n == len(chosen) else f" ({len(chosen) - n} were already there)."))
    b2.download_button("Download all searches (CSV)", df.to_csv(index=False), f"wasted_searches_{days}d.csv",
                       "text/csv", width="stretch")

with st.expander(f"See all {len(df)} searches, including good ones"):
    view = df.drop(columns=["rule", "intent", "classified_by"], errors="ignore")
    st.dataframe(ui.friendly_df(view), hide_index=True, width="stretch")
