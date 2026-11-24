import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
import ui

from adpulse.config import get_settings
from adpulse.llm import LLMError, get_llm
from adpulse.reports import weekly
from adpulse.scheduler import Schedule

ui.hero("Weekly report", "A one-page summary of how your ads did this week. Send it to Slack with one click, "
        "or let it go out by itself every Monday.")
if not ui.require_warehouse():
    st.stop()
s = get_settings()

max_d = pd.Timestamp(ui.q("SELECT max(date) AS d FROM fct_ad_daily").iloc[0]["d"]).date()
c1, c2 = st.columns([2, 3], vertical_alignment="bottom")
end = c1.date_input("Week ending", max_d, max_value=max_d, min_value=max_d - timedelta(days=150))
ai = c2.toggle("Let AI write the summary (every number is still checked)", value=s.llm_configured,
               disabled=not s.llm_configured)


@st.cache_data(ttl=300, show_spinner="Preparing your report…")
def build(end, ai: bool):
    llm = None
    if ai:
        try:
            llm = get_llm()
        except LLMError:
            pass
    return weekly.build(end=end, llm=llm)


rep = build(end, ai)

# ---- Send ------------------------------------------------------------------------------------------------
b1, b2, b3 = st.columns(3)
send_slack = b1.button("Send to Slack", type="primary", icon=":material/send:", width="stretch",
                       disabled=not s.slack_configured,
                       help=None if s.slack_configured else "Slack isn't connected yet. Add a Slack webhook in the "
                                                            "app settings to turn this on.")
send_mail = b2.button("Send by email", icon=":material/mail:", width="stretch", disabled=not s.email_configured,
                      help=None if s.email_configured else "Email isn't set up yet (needs a Gmail app password).")
b3.download_button("Download report", weekly.to_markdown(rep), f"adpulse_weekly_{rep.period_end}.md",
                   icon=":material/download:", width="stretch")
if send_slack or send_mail:
    with st.spinner("Sending…"):
        res = weekly.deliver(rep, slack=send_slack, email=send_mail)
    for ch, r in res.items():
        where = "Slack" if ch == "slack" else "email"
        if r.startswith("sent"):
            st.success(f"Sent to {where}. Check your {'Slack channel' if ch == 'slack' else 'inbox'}.", icon="✅")
        else:
            st.error(f"Couldn't send to {where}. {r.removeprefix('error: ')}", icon="⚠️")

try:
    sched = Schedule.from_settings()
    nxt = sched.next_run(datetime.now(timezone.utc))
    st.caption(f"Also sends by itself every {sched.describe().removeprefix('every ')}. "
               f"Next one: **{nxt:%A, %B %-d at %H:%M}**.")
except ValueError as e:
    st.warning(f"The automatic Monday send has a setting problem: {e}")

# ---- The report itself -----------------------------------------------------------------------------------
ui.section(f"This week: {rep.period_start:%B %-d} to {rep.period_end:%B %-d}")
ui.kpi_row([ui.kpi(k.label, k.text(), k.change, k.better, period="the week before") for k in rep.kpis])
with st.container(border=True):
    md = weekly.to_markdown(rep)
    body = md[md.index("## Summary"):].replace("\n## ", "\n#### ").replace("## Summary", "#### Summary", 1)
    st.markdown(ui.md(body))
st.caption("Summary written by AI, every number checked against your data." if rep.commentary_source == "llm"
           else "Summary built straight from your data.")

# ---- History ---------------------------------------------------------------------------------------------
ui.section("Reports sent before")
h = weekly.history()
if h.empty:
    st.caption("No reports sent yet.")
else:
    h = h.assign(channels=h.channels.replace("", "not sent").str.replace("slack", "Slack").str.replace(
        "email", "email").str.replace(",", " and "),
        status=h.status.map({"sent": "Sent", "generated": "Saved only", "failed": "Failed"}).fillna(h.status))
    st.dataframe(h[["created_at", "period_start", "period_end", "channels", "status"]], hide_index=True,
                 width="stretch", column_config={
                     "created_at": st.column_config.DatetimeColumn("When", format="MMM D, YYYY HH:mm"),
                     "period_start": st.column_config.DateColumn("From", format="MMM D"),
                     "period_end": st.column_config.DateColumn("To", format="MMM D"),
                     "channels": "Sent to", "status": "Result"})

with st.expander("For developers: the Slack message format"):
    st.code(json.dumps(weekly.to_slack_blocks(rep, s.app_base_url), indent=2, ensure_ascii=False), language="json")
