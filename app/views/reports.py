import html
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
import ui

from adpulse import plain
from adpulse.config import get_settings
from adpulse.llm import LLMError, get_llm
from adpulse.reports import weekly
from adpulse.scheduler import Schedule

ui.hero("Weekly report", "Your Monday summary, one click to Slack.")
if not ui.require_warehouse():
    st.stop()
s = get_settings()
max_d = pd.Timestamp(ui.q("SELECT max(date) AS d FROM fct_ad_daily").iloc[0]["d"]).date()


@st.cache_data(ttl=300, show_spinner="Preparing your report…")
def build(end, ai: bool):
    llm = None
    if ai:
        try:
            llm = get_llm()
        except LLMError:
            pass
    return weekly.build(end=end, llm=llm)


# ---- Controls and delivery, in one aligned bar ------------------------------------------------------------
with st.container(border=True, key="panel_controls"):
    c1, c2, c3, c4, c5 = st.columns([1.25, 1.45, 1, 1, 1], vertical_alignment="bottom")
    end = c1.date_input("Week ending", max_d, max_value=max_d, min_value=max_d - timedelta(days=150))
    ai = c2.toggle("AI writes the summary", value=s.llm_configured, disabled=not s.llm_configured,
                   help="Every number the AI writes is still checked against your data.")
    rep = build(end, ai)
    send_slack = c3.button("Send to Slack", type="primary", icon=":material/send:", width="stretch",
                           disabled=not s.slack_configured,
                           help=None if s.slack_configured else "Add a Slack webhook in the app settings first.")
    send_mail = c4.button("Email it", icon=":material/mail:", width="stretch", disabled=not s.email_configured,
                          help=None if s.email_configured else "Email needs a Gmail app password "
                                                               "(run scripts/setup_email.sh).")
    c5.download_button("Download", weekly.to_markdown(rep), f"adpulse_weekly_{rep.period_end}.md",
                       icon=":material/download:", width="stretch")

try:
    sched = Schedule.from_settings()
    nxt = sched.next_run(datetime.now(timezone.utc))
    auto = (f"Sends by itself {sched.describe()}, next on {nxt:%a %b %-d}", "info")
except ValueError:
    auto = ("Automatic Monday send has a setting problem", "warn")
ui.badges(("Slack connected" if s.slack_configured else "Slack not connected",
           "good" if s.slack_configured else "muted"),
          ("Email ready" if s.email_configured else "Email not set up", "good" if s.email_configured else "muted"),
          auto)

if send_slack or send_mail:
    with st.spinner("Sending…"):
        res = weekly.deliver(rep, slack=send_slack, email=send_mail)
    for ch, r in res.items():
        where = "Slack" if ch == "slack" else "email"
        if r.startswith("sent"):
            st.toast(f"Sent to {where}", icon="✅")
        else:
            st.error(f"Couldn't send to {where}. {r.removeprefix('error: ')}", icon="⚠️")

# ---- The report ---------------------------------------------------------------------------------------------
ui.section("This week", f"{rep.period_start:%B %-d} to {rep.period_end:%B %-d}, compared with the week before")
SHORT = {plain.label("new_customers"): "New customers", plain.label("cac"): "Cost per customer"}
ui.kpi_row([ui.kpi(SHORT.get(k.label, k.label), k.text(), k.change, k.better, period="week before")
            for k in rep.kpis])

with st.container(border=True, key="panel_summary"):
    src = "written by AI, every number checked" if rep.commentary_source == "llm" else "built from your data"
    st.html(f'<div class="ap-card-h">Summary <span class="ap-muted" style="font-weight:400">{src}</span></div>'
            '<ul class="ap-summary">' + "".join(f"<li>{html.escape(c)}</li>" for c in rep.commentary) + "</ul>")


def ad_rows(df: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    return [(a.ad_name, f"{a.ltv_to_cac:.1f}×", "good" if a.ltv_to_cac >= 1 else "bad",
             f"{str(a.platform).title()}: each customer costs ${a.cac:,.2f} and is worth ${a.avg_ltv:,.2f}")
            for a in df.itertuples()]


left, right = st.columns(2, gap="medium")
with left, st.container(border=True, key="panel_scale"):
    ui.card_list("Top ads", "#157A4A", ad_rows(rep.top_ads))
with right, st.container(border=True, key="panel_pause"):
    ui.card_list("Losing ads", "#C23B2E", ad_rows(rep.worst_ads))

with st.container(border=True, key="panel_waste"):
    w1, w2 = st.columns([1, 1.6], gap="large", vertical_alignment="center")
    w1.html('<div class="ap-card-h">Wasted searches</div>'
            f'<div class="ap-big bad">{ui.money(rep.waste["wasted_spend"])}</div>'
            f'<div class="ap-sub">on {rep.waste["flagged"]} searches, {rep.waste["wasted_share"]:.0%} of search '
            'spend this week</div>')
    with w2:
        t = rep.top_waste_terms
        if not t.empty:
            ui.bars([(x.search_term, x.cost, ui.money(x.cost)) for x in t.itertuples()])
st.caption(f"{len(rep.pending)} suggestion(s) are waiting for approval. Nothing changes until someone approves.")

# ---- History ------------------------------------------------------------------------------------------------
ui.section("History")
h = weekly.history()
if h.empty:
    st.caption("No reports sent yet.")
else:
    h = h.assign(channels=h.channels.replace("", "not sent").str.replace("slack", "Slack").str.replace(",", " and "),
                 status=h.status.map({"sent": "Sent", "generated": "Saved only", "failed": "Failed"}).fillna(h.status))
    st.dataframe(h[["created_at", "period_start", "period_end", "channels", "status"]], hide_index=True,
                 width="stretch", column_config={
                     "created_at": st.column_config.DatetimeColumn("When", format="MMM D, YYYY HH:mm"),
                     "period_start": st.column_config.DateColumn("From", format="MMM D"),
                     "period_end": st.column_config.DateColumn("To", format="MMM D"),
                     "channels": "Sent to", "status": "Result"})

with st.expander("For developers: the Slack message format"):
    st.code(json.dumps(weekly.to_slack_blocks(rep, s.app_base_url), indent=2, ensure_ascii=False), language="json")
