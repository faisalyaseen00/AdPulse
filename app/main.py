"""AdPulse Streamlit app entry point: `streamlit run app/main.py` (or `adpulse ui`)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="AdPulse", page_icon=str(Path(__file__).parent / "assets" / "icon.svg"), layout="wide", initial_sidebar_state="auto")



def _load_streamlit_secrets() -> None:
    """Streamlit Cloud keeps settings in st.secrets. Copy top-level values into the environment, where
    AdPulse's settings read them. Values already in the environment win; no secrets file is fine."""
    try:
        items = {k: st.secrets[k] for k in st.secrets}
    except Exception:  # noqa: BLE001  (no secrets.toml locally)
        return
    loaded = False
    for key, value in items.items():
        if isinstance(value, (str, int, float, bool)) and key.upper() not in os.environ:
            os.environ[key.upper()] = str(value)
            loaded = True
    if loaded:
        from adpulse import warehouse as _wh
        from adpulse.config import get_settings as _gs
        _gs.cache_clear()
        _wh.admin.cache_clear()
        _wh.reader.cache_clear()


_load_streamlit_secrets()

import ui

from adpulse.config import get_settings

logging.basicConfig(level=logging.INFO)
ui.inject_css()
settings = get_settings()


pages = {
    "Insights": [
        st.Page("views/overview.py", title="Overview", icon=":material/space_dashboard:", default=True),
        st.Page("views/ask.py", title="Ask a question", icon=":material/chat:", url_path="ask"),
    ],
    "Actions": [
        st.Page("views/recommendations.py", title="Suggestions", icon=":material/task_alt:",
                url_path="recommendations"),
        st.Page("views/audit.py", title="Wasted searches", icon=":material/money_off:", url_path="audit"),
        st.Page("views/reports.py", title="Weekly report", icon=":material/mail:", url_path="reports"),
    ],
    "Data": [
        st.Page("views/pipeline.py", title="Data status", icon=":material/sync:", url_path="pipeline"),
    ],
}
nav = st.navigation(pages)


with st.sidebar:
    h = ui.health()
    st.html('<div class="ap-side-label">Status</div>')
    ui.status_list(
        ("Data connected" if h.ok else "Data offline", "good" if h.ok else "bad"),
        ("AI assistant ready" if settings.llm_configured else "AI assistant off",
         "good" if settings.llm_configured else "warn"),
        ("Slack reports on" if settings.slack_configured else "Slack reports off",
         "good" if settings.slack_configured else "muted"),
    )
    if settings.slack_configured and h.ok and st.button("Send weekly report to Slack", icon=":material/send:",
                                                          width="stretch", key="side_slack"):
        from adpulse.llm import LLMError, get_llm
        from adpulse.reports import weekly
        with st.spinner("Preparing and sending…"):
            try:
                llm = get_llm() if settings.llm_configured else None
            except LLMError:
                llm = None
            res = weekly.deliver(weekly.build(llm=llm), slack=True, email=False)
        r = res.get("slack", "")
        if r.startswith("sent"):
            st.toast("Weekly report sent to Slack", icon="✅")
        else:
            st.error(f"Couldn't send to Slack. {r.removeprefix('error: ')}")
    st.html('<div class="ap-side-label">Your name</div>')
    st.text_input("Your name", key="reviewer", placeholder="Needed to approve suggestions",
                  label_visibility="collapsed", help="Saved with every approve or reject, so the team knows who decided.")
    st.caption("Nothing changes in your ad accounts until a person approves it.")

# ---- Top bar on every page: where you are, data freshness, who you are ----------------
section = next((g for g, ps in pages.items() if any(p.title == nav.title for p in ps)), "")
until = ""
if h.ok:
    try:
        until = f"{ui.q('SELECT max(date) AS d FROM fct_ad_daily').iloc[0]['d']:%b %-d}"
    except Exception:  # noqa: BLE001, S110  (empty warehouse: the page itself explains)
        pass
ui.topbar(section, nav.title, until, ui.reviewer())
if nav.title != "Ask a question":
    ui.robot_icon()

nav.run()
