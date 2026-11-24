import streamlit as st
import ui

from adpulse import plain
from adpulse.actions import recommendations as recs
from adpulse.audit import search_terms
from adpulse.config import get_settings
from adpulse.llm import LLMError, get_llm

ui.hero("Wasted searches", "Stop paying for clicks that will never buy.")
if not ui.require_warehouse():
    st.stop()
llm_ready = get_settings().llm_configured

with st.container(border=True, key="panel_controls"):
    c1, c2, c3 = st.columns([1.2, 1.2, 1.6], vertical_alignment="bottom")
    days = c1.selectbox("Period", [7, 14, 30, 90], index=2, format_func=lambda d: f"Last {d} days")
    min_cost = c2.number_input("Hide searches that cost less than ($)", 0.0, 500.0, 5.0, 5.0)
    use_llm = c3.toggle("Let AI sort the unusual searches", value=llm_ready, disabled=not llm_ready,
                        help="Simple rules catch the common cases (jobs, free stuff, store hours). "
                             "The AI sorts the rest.")


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
    st.info("No Google searches in this period. Try a longer period or a lower minimum cost.")
    st.stop()
s = search_terms.summary(df)
df = df.assign(kind=df.intent.map(plain.intent), by=df.classified_by.map({"rule": "Rule", "llm": "AI"}).fillna("Rule"))
flagged = df[df.flagged].copy()

# ---- The answer: how much leaked, and why ---------------------------------------------------------------
left, right = st.columns([1.05, 1], gap="medium")
with left, st.container(border=True, key="panel_waste"):
    share = float(s["wasted_share"] or 0)
    sales = float(flagged.conversions.sum()) if not flagged.empty else 0
    st.html(
        f'<div class="ap-muted">Wasted in the last {days} days</div>'
        f'<div class="ap-big bad">{ui.money(s["wasted_spend"])}</div>'
        f'<div class="ap-sub">spent on <b>{s["flagged"]}</b> searches from people who were never going to buy.</div>'
        f'<div class="ap-share"><div class="w" style="width:{share * 100:.1f}%"></div></div>'
        f'<div class="ap-share-legend"><span><b style="color:var(--bad)">{share:.0%}</b> of search budget wasted</span>'
        f'<span>{1 - share:.0%} reached real shoppers</span></div>'
        '<div class="ap-chips" style="margin-top:16px">'
        + ui.badge(f"{s['terms']} searches checked", "muted")
        + ui.badge(f"{s['flagged']} to block", "warn")
        + ui.badge(f"{sales:.0f} sale{'s' if sales != 1 else ''} from them", "muted")
        + "</div>")
    if not flagged.empty:
        camp = flagged.groupby("campaign_name", as_index=False)["wasted_spend"].sum().sort_values(
            "wasted_spend", ascending=False)
        st.html('<div class="ap-card-h" style="margin-top:22px">Which campaigns</div>')
        ui.bars([(r.campaign_name, r.wasted_spend, ui.money(r.wasted_spend)) for r in camp.itertuples()],
                color="linear-gradient(90deg,#2a78d6,#14213D)")
with right, st.container(border=True, key="panel_why"):
    st.html('<div class="ap-card-h">Why they won\'t buy</div>')
    if flagged.empty:
        st.caption("Nothing to block in this period.")
    else:
        why = flagged.groupby("reason", as_index=False)["wasted_spend"].sum().sort_values(
            "wasted_spend", ascending=False).head(6)
        ui.bars([(r.reason, r.wasted_spend, ui.money(r.wasted_spend)) for r in why.itertuples()])

# ---- Pick what to block -----------------------------------------------------------------------------------
ui.section("Searches to block", "untick any you want to keep")
if flagged.empty:
    st.success("No wasted searches in this period.")
else:
    flagged = flagged.sort_values("cost", ascending=False)
    flagged.insert(0, "block", True)
    edited = st.data_editor(
        flagged[["block", "search_term", "reason", "cost", "clicks", "conversions", "campaign_name",
                 "suggested_negative"]],
        hide_index=True, width="stretch", height=min(480, 40 + 35 * len(flagged)),
        disabled=[c for c in flagged.columns if c != "block"],
        column_config={
            "block": st.column_config.CheckboxColumn("Block", width="small"),
            "search_term": st.column_config.TextColumn(plain.label("search_term"), width="medium",
                                                      help=plain.explain("search_term")),
            "reason": st.column_config.TextColumn("Why it's wasted", width="medium"),
            "cost": st.column_config.NumberColumn("Cost", format="$%.2f"),
            "clicks": st.column_config.NumberColumn("Clicks", format="%d", width="small"),
            "conversions": st.column_config.NumberColumn("Sales", format="%.0f", width="small"),
            "campaign_name": st.column_config.TextColumn("Campaign"),
            "suggested_negative": st.column_config.TextColumn(
                "Block as", help="What gets added to Google's blocked list. Quotes block any search containing "
                                 "the words; [brackets] block only that exact search."),
        })
    chosen = edited[edited.block]["search_term"].tolist()
    a1, a2, _ = st.columns([1.3, 1, 1.2], vertical_alignment="center")
    if a1.button(f"Add {len(chosen)} search{'es' if len(chosen) != 1 else ''} to suggestions", type="primary",
                 disabled=not chosen, width="stretch", icon=":material/playlist_add:"):
        n = recs.save(recs.audit_recommendations(df, chosen))
        ui.suggestions_changed()
        st.toast(f"Added {n} to Suggestions" + ("" if n == len(chosen) else f" ({len(chosen) - n} were already there)"),
                 icon="✅")
    a2.download_button("Download as spreadsheet", df.drop(columns=["rule"], errors="ignore").to_csv(index=False),
                       f"wasted_searches_{days}d.csv", "text/csv", width="stretch", icon=":material/download:")
    st.caption("Blocking only happens after you approve it on the Suggestions page.")

with st.expander(f"See all {len(df)} searches, including the good ones"):
    view = df.drop(columns=["rule", "intent", "classified_by", "flagged"], errors="ignore")
    st.dataframe(ui.friendly_df(view), hide_index=True, width="stretch")
