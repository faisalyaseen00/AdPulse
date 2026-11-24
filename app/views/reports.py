import json
from datetime import timedelta

import pandas as pd
import streamlit as st
import ui

from adpulse.config import get_settings
from adpulse.llm import LLMError, get_llm
from adpulse.reports import weekly

ui.hero("Weekly report", "Every Monday: what changed, what to pause or scale, where search spend leaked.", icon="📨")
if not ui.require_warehouse():
    st.stop()
s = get_settings()

max_d = pd.Timestamp(ui.q("SELECT max(date) AS d FROM fct_ad_daily").iloc[0]["d"]).date()
c1, c2 = st.columns([2, 3])
end = c1.date_input("Week ending", max_d, max_value=max_d, min_value=max_d - timedelta(days=150))
ai = c2.toggle("AI commentary (numbers verified)", value=s.llm_configured, disabled=not s.llm_configured)


@st.cache_data(ttl=300, show_spinner="Building report…")
def build(end, ai: bool):
    llm = None
    if ai:
        try:
            llm = get_llm()
        except LLMError:
            pass
    return weekly.build(end=end, llm=llm)


rep = build(end, ai)
tiles = []
for k in rep.kpis:
    tiles.append(ui.kpi(k.label, k.text(), k.change, k.better))
ui.kpi_row(tiles)

left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        md = weekly.to_markdown(rep)
        st.markdown(ui.md(md[md.index("## Summary"):].replace("\n## ", "\n##### ").replace("## Summary", "##### Summary", 1)))
    st.caption(f"Commentary: {'AI-written, every number checked against the data' if rep.commentary_source == 'llm' else 'template'}")
with right:
    ui.section("Deliver")
    send_slack = st.checkbox("Slack", value=s.slack_configured, disabled=not s.slack_configured,
                             help=None if s.slack_configured else "Set SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN in .env")
    send_mail = st.checkbox("Email", value=s.email_configured, disabled=not s.email_configured,
                            help=None if s.email_configured else "Set SMTP_* and REPORT_EMAIL_* in .env")
    if not (s.slack_configured or s.email_configured):
        st.info("No delivery channel configured yet. You can still save the report and preview the Slack message.")
    if st.button("Send now" if (send_slack or send_mail) else "Save report", type="primary", width="stretch"):
        res = weekly.deliver(rep, slack=send_slack, email=send_mail)
        for ch, r in res.items():
            (st.success if r.startswith("sent") else st.warning)(f"{ch}: {r}")
        if not res:
            st.success("Report saved to history.")
    st.download_button("Download markdown", weekly.to_markdown(rep), f"adpulse_weekly_{rep.period_end}.md",
                       width="stretch")
    with st.expander("Slack message preview (Block Kit)"):
        st.code(json.dumps(weekly.to_slack_blocks(rep, s.app_base_url), indent=2, ensure_ascii=False), language="json")
    try:
        from datetime import datetime, timezone

        from adpulse.scheduler import Schedule
        sched = Schedule.from_settings()
        nxt = sched.next_run(datetime.now(timezone.utc))
        st.caption(f"🗓️ Auto-send **{sched.describe()}** · next: **{nxt:%a %b %d, %H:%M}**  \n"
                   "Runs while `adpulse scheduler` (or the Docker `scheduler` service) is running.")
    except ValueError as e:
        st.warning(f"Schedule setting problem: {e}")

ui.section("History")
h = weekly.history()
if h.empty:
    st.caption("No reports sent yet.")
else:
    st.dataframe(h.drop(columns=["markdown"]), hide_index=True, width="stretch")
