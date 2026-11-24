import html
import json

import pandas as pd
import streamlit as st
import ui

from adpulse.actions import recommendations as recs

ui.hero("Approvals", "Pause / scale / negative keyword suggestions. Nothing touches ad spend without a human yes.")
if not ui.require_warehouse():
    st.stop()

top = st.columns([2, 2, 3])
window = top[0].selectbox("Rule window", [14, 30, 60], index=1, format_func=lambda d: f"Last {d} days")
if top[1].button("Run pause / scale rules", type="primary", width="stretch"):
    found = recs.rule_recommendations(window)
    n = recs.save(found)
    st.toast(f"{len(found)} found · {n} new in queue", icon="🧮")

who = ui.reviewer()
if not who:
    top[2].warning("Enter your **reviewer name** in the sidebar to approve or reject.", icon="✍️")

df = recs.latest()
if df.empty:
    st.info("No recommendations yet. Run the rules, queue negatives from the search term audit, "
            "or queue actions suggested in chat.")
    st.stop()

KIND = {"pause_ad": ("⏸ Pause ad", "bad"), "scale_ad": ("🚀 Scale ad", "good"),
        "negative_keyword": ("🚫 Negative keyword", "warn")}
STATUS = {"pending": "info", "approved": "good", "rejected": "muted", "applied": "good"}

pending = df[df.status == "pending"]
approved = df[df.status == "approved"]
ui.kpi_row([
    ui.kpi("Pending", f"{len(pending)}"),
    ui.kpi("Est. monthly impact pending", ui.money(pending.est_impact.sum())),
    ui.kpi("Approved, to apply", f"{len(approved)}"),
    ui.kpi("Applied", f"{(df.status == 'applied').sum()}"),
])

METRIC_LABELS = {"spend_window": ("Spend", "$"), "new_customers_window": ("New customers", ""),
                 "cac_window": ("CAC", "$"), "ltv_estimate": ("LTV", "$"), "ltv_to_cac": ("LTV:CAC", "x"),
                 "roas_window": ("ROAS", "x"), "cost": ("Cost", "$"), "clicks": ("Clicks", ""),
                 "conversions": ("Conversions", "")}


def evidence(m: dict) -> str:
    out = []
    for k, (label, unit) in METRIC_LABELS.items():
        v = m.get(k)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        txt = f"${v:,.2f}" if unit == "$" else (f"{v:.2f}x" if unit == "x" else f"{v:,.0f}")
        out.append(f"<span class='ap-muted'>{label}</span> <b>{txt}</b>")
    return " &nbsp;·&nbsp; ".join(out)


def card(r: pd.Series, actions: str) -> None:
    with st.container(border=True):
        k_label, k_kind = KIND.get(r.kind, (r.kind, "muted"))
        head = (f"{ui.badge(k_label, k_kind)} {ui.badge(r.platform.title(), 'muted')} "
                f"{ui.badge(r.status, STATUS[r.status])} {ui.badge('from ' + r.source, 'muted')}")
        st.html(f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px'>{head}</div>"
                f"<div class='ap-card-title'>{html.escape(r.entity_name)}</div>"
                f"<div class='ap-muted'>{html.escape(r.campaign_name)}</div>"
                f"<div style='margin:8px 0 4px'>{html.escape(r.reason)}</div>"
                f"<div style='font-size:.85rem'>{evidence(r.metrics)}</div>")
        c = st.columns([3, 1.2, 1.2])
        impact = "spend saved / month" if r.kind != "scale_ad" else "est. added customer value"
        c[0].caption(f"Impact ≈ **{ui.money(r.est_impact)}** {impact} · created {pd.Timestamp(r.created_at):%b %d %H:%M}"
                     + (f" · decided by **{r.decided_by}**" if r.decided_by else "")
                     + (f" · note: _{r.note}_" if r.note else ""))
        if actions == "decide":
            note = st.text_input("Note (optional)", key=f"note_{r.id}", label_visibility="collapsed",
                                 placeholder="Optional note for the audit trail")
            if c[1].button("Approve", key=f"ap_{r.id}", type="primary", disabled=not who, width="stretch"):
                recs.decide(r.id, "approved", who, note)
                st.rerun()
            if c[2].button("Reject", key=f"rj_{r.id}", disabled=not who, width="stretch"):
                recs.decide(r.id, "rejected", who, note)
                st.rerun()
        elif actions == "apply":
            if c[1].button("Mark applied", key=f"apl_{r.id}", type="primary", disabled=not who, width="stretch",
                           help="Confirm you made this change in the ad platform."):
                recs.decide(r.id, "applied", who, r.note)
                st.rerun()
            if c[2].button("Withdraw", key=f"wd_{r.id}", disabled=not who, width="stretch"):
                recs.decide(r.id, "rejected", who, "withdrawn after approval")
                st.rerun()
        if actions in ("apply", "decide"):
            with st.expander("Change to apply in the ad platform"):
                st.code(json.dumps(recs.change_payload(r.to_dict()), indent=2), language="json")


tab_p, tab_a, tab_h = st.tabs([f"Pending ({len(pending)})", f"Approved ({len(approved)})", "History"])
with tab_p:
    kinds = st.pills("Filter", list(KIND), selection_mode="multi", default=list(KIND),
                     format_func=lambda k: KIND[k][0], label_visibility="collapsed")
    view = pending[pending.kind.isin(kinds or list(KIND))].sort_values("est_impact", ascending=False)
    if view.empty:
        st.success("Queue is clear.")
    for _, r in view.iterrows():
        card(r, "decide")
with tab_a:
    if approved.empty:
        st.caption("Nothing approved and waiting to be applied.")
    for _, r in approved.iterrows():
        card(r, "apply")
with tab_h:
    hist = df[df.status.isin(["rejected", "applied"])]
    st.dataframe(hist[["decided_at", "status", "kind", "entity_name", "campaign_name", "decided_by", "note",
                       "est_impact"]], hide_index=True, width="stretch",
                 column_config={"est_impact": st.column_config.NumberColumn("Impact", format="$%.0f")})
