import html
import json

import pandas as pd
import streamlit as st
import ui

from adpulse.actions import recommendations as recs

ui.hero("Suggestions", "Ideas to spend your ad money better. Approve the ones you agree with, then make the "
        "change in Meta or Google. Nothing changes on its own.")
if not ui.require_warehouse():
    st.stop()

top = st.columns([2, 2, 3])
window = top[0].selectbox("Based on", [14, 30, 60], index=1, format_func=lambda d: f"The last {d} days")
if top[1].button("Check my ads for new ideas", type="primary", width="stretch"):
    found = recs.rule_recommendations(window)
    n = recs.save(found)
    st.toast(f"{n} new suggestion(s) added" if n else "No new suggestions: your list is up to date", icon="✅")

who = ui.reviewer()
if not who:
    top[2].info("Type **your name** in the sidebar to approve or reject.", icon=":material/badge:")

df = recs.latest()
if df.empty:
    st.info("No suggestions yet. Click **Check my ads for new ideas**, block searches on **Wasted searches**, "
            "or add ideas from **Ask a question**.")
    st.stop()

KIND = {"pause_ad": ("Pause this ad", "bad"), "scale_ad": ("Give it more budget", "good"),
        "negative_keyword": ("Block this search", "warn")}
STATUS = {"pending": "info", "approved": "good", "rejected": "muted", "applied": "good"}
STATUS_WORDS = {"pending": "Waiting for you", "approved": "Approved", "rejected": "Rejected", "applied": "Done"}
SOURCE_WORDS = {"rules": "from the ad check", "audit": "from wasted searches", "agent": "from a question"}

pending = df[df.status == "pending"]
approved = df[df.status == "approved"]
ui.kpi_row([
    ui.kpi("Waiting for you", f"{len(pending)}", note="suggestions to review"),
    ui.kpi("Possible gain", ui.money(pending.est_impact.sum()), note="per month, if all approved",
           help="Money saved by pausing and blocking, plus extra customer value from bigger budgets. An estimate."),
    ui.kpi("Approved", f"{len(approved)}", note="to change in Meta or Google"),
    ui.kpi("Done", f"{(df.status == 'applied').sum()}", note="changed in the ad account"),
])

METRIC_LABELS = {"spend_window": ("Ad spend", "$"), "new_customers_window": ("New customers", ""),
                 "cac_window": ("Cost per new customer", "$"), "ltv_estimate": ("Customer value", "$"),
                 "ltv_to_cac": ("Value vs cost", "x"), "roas_window": ("Money back per $1", "$1"),
                 "cost": ("Cost", "$"), "clicks": ("Clicks", ""), "conversions": ("Sales", "")}


def evidence(m: dict) -> str:
    out = []
    for k, (label, unit) in METRIC_LABELS.items():
        v = m.get(k)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        txt = (f"${v:,.2f}" if unit in ("$", "$1") else f"{v:.1f}×" if unit == "x" else f"{v:,.0f}")
        out.append(f"<span>{label} <b>{txt}</b></span>")
    return "".join(out)


def how_to(r: pd.Series) -> str:
    name, camp = r.entity_name, r.campaign_name
    tool = "Meta Ads Manager (adsmanager.facebook.com)" if r.platform == "meta" else "Google Ads (ads.google.com)"
    if r.kind == "pause_ad" and r.platform == "meta":
        steps = [f"Open {tool}.", f"Find the ad **{name}** in campaign **{camp}**.", "Switch it **Off**."]
    elif r.kind == "pause_ad":
        steps = [f"Open {tool} and go to **Ads**.", f"Find **{name}** in campaign **{camp}**.",
                 "Set its status to **Paused**."]
    elif r.kind == "scale_ad":
        steps = [f"Open {tool}.", f"Open campaign **{camp}** (the one running **{name}**).",
                 "Raise the **daily budget by 20%**.", "Check the cost per new customer again in a week."]
    else:
        m = r.metrics if isinstance(r.metrics, dict) else {}
        steps = [f"Open {tool}.", f"Go to ad group **{m.get('ad_group_name', '')}** in campaign **{camp}**.",
                 "Open **Keywords → Negative keywords** and click **+**.",
                 f"Add `{m.get('suggested_negative', name)}` and save."]
    return "\n".join(f"{i}. {ui.md(t)}" for i, t in enumerate(steps, 1))


def card(r: pd.Series, actions: str) -> None:
    with st.container(border=True):
        k_label, k_kind = KIND.get(r.kind, (r.kind, "muted"))
        head = (f"{ui.badge(k_label, k_kind)} {ui.badge(r.platform.title(), 'muted')} "
                f"{ui.badge(STATUS_WORDS.get(r.status, r.status), STATUS[r.status])}")
        st.html(f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px'>{head}</div>"
                f"<div class='ap-card-title'>{html.escape(r.entity_name)}</div>"
                f"<div class='ap-muted'>Campaign: {html.escape(r.campaign_name)}, "
                f"{SOURCE_WORDS.get(r.source, r.source)}</div>"
                f"<div class='ap-why'>{html.escape(r.reason)}</div>"
                f"<div class='ap-facts'>{evidence(r.metrics)}</div>")
        c = st.columns([3, 1.2, 1.2])
        impact = "saved per month" if r.kind != "scale_ad" else "extra customer value per month"
        c[0].caption(f"About **{ui.money(r.est_impact)}** {impact}. Suggested {pd.Timestamp(r.created_at):%b %-d}."
                     + (f" Decided by **{r.decided_by}**." if r.decided_by else "")
                     + (f" Note: _{r.note}_" if r.note else ""))
        if actions == "decide":
            note = st.text_input("Note (optional)", key=f"note_{r.id}", label_visibility="collapsed",
                                 placeholder="Add a note (optional)")
            if c[1].button("Approve", key=f"ap_{r.id}", type="primary", disabled=not who, width="stretch"):
                recs.decide(r.id, "approved", who, note)
                st.rerun()
            if c[2].button("Reject", key=f"rj_{r.id}", disabled=not who, width="stretch"):
                recs.decide(r.id, "rejected", who, note)
                st.rerun()
        elif actions == "apply":
            if c[1].button("Mark as done", key=f"apl_{r.id}", type="primary", disabled=not who, width="stretch",
                           help="Click after you've made this change in Meta or Google."):
                recs.decide(r.id, "applied", who, r.note)
                st.rerun()
            if c[2].button("Undo approval", key=f"wd_{r.id}", disabled=not who, width="stretch"):
                recs.decide(r.id, "rejected", who, "withdrawn after approval")
                st.rerun()
        if actions in ("apply", "decide"):
            with st.expander("How to make this change in Meta or Google"):
                st.markdown(how_to(r))
                st.caption("For developers, the same change as an API request:")
                st.code(json.dumps(recs.change_payload(r.to_dict()), indent=2), language="json")


tab_p, tab_a, tab_h = st.tabs([f"Waiting for you ({len(pending)})", f"Approved ({len(approved)})", "Past decisions"])
with tab_p:
    kinds = st.pills("Filter", list(KIND), selection_mode="multi", default=list(KIND),
                     format_func=lambda k: KIND[k][0], label_visibility="collapsed")
    view = pending[pending.kind.isin(kinds or list(KIND))].sort_values("est_impact", ascending=False)
    if view.empty:
        st.success("You're all caught up.")
    for _, r in view.iterrows():
        card(r, "decide")
with tab_a:
    if approved.empty:
        st.caption("Nothing approved and waiting to be changed.")
    for _, r in approved.iterrows():
        card(r, "apply")
with tab_h:
    hist = df[df.status.isin(["rejected", "applied"])]
    hist = hist.assign(status=hist.status.map(STATUS_WORDS), kind=hist.kind.map(lambda k: KIND.get(k, (k,))[0]))
    st.dataframe(hist[["decided_at", "status", "kind", "entity_name", "campaign_name", "decided_by", "note",
                       "est_impact"]], hide_index=True, width="stretch",
                 column_config={"decided_at": st.column_config.DatetimeColumn("When", format="MMM D, YYYY"),
                                "status": "Decision", "kind": "Suggestion", "entity_name": "Ad or search",
                                "campaign_name": "Campaign", "decided_by": "Decided by", "note": "Note",
                                "est_impact": st.column_config.NumberColumn("Monthly impact", format="$%.0f")})
