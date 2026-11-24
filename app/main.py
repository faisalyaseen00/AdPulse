"""AdPulse Streamlit app entry point: `streamlit run app/main.py` (or `adpulse ui`)."""
from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="AdPulse", page_icon=str(Path(__file__).parent / "assets" / "icon.svg"), layout="wide", initial_sidebar_state="expanded")

import ui

from adpulse import warehouse
from adpulse.config import get_settings

logging.basicConfig(level=logging.INFO)
ui.inject_css()
settings = get_settings()


pages = {
    "Analyze": [
        st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
        st.Page("views/ask.py", title="Ask AdPulse", icon=":material/forum:", url_path="ask"),
    ],
    "Act": [
        st.Page("views/audit.py", title="Search term audit", icon=":material/search_insights:", url_path="audit"),
        st.Page("views/recommendations.py", title="Approvals", icon=":material/fact_check:",
                url_path="recommendations"),
        st.Page("views/reports.py", title="Weekly report", icon=":material/summarize:", url_path="reports"),
    ],
    "Data": [
        st.Page("views/pipeline.py", title="Data pipeline", icon=":material/database:", url_path="pipeline"),
    ],
}
nav = st.navigation(pages)

ASSETS = Path(__file__).parent / "assets"
st.logo(str(ASSETS / "logo.svg"), size="large", icon_image=str(ASSETS / "icon.svg"))

with st.sidebar:
    h = warehouse.health()
    st.html('<div class="ap-side-label">System</div>')
    ui.status_list(
        ("ClickHouse " + (".".join(h.version.split(".")[:2]) if h.ok else "offline"), "good" if h.ok else "bad"),
        (settings.llm_label if settings.llm_configured else "LLM not configured",
         "info" if settings.llm_configured else "warn"),
        ("Slack connected" if settings.slack_configured else "Slack off",
         "good" if settings.slack_configured else "muted"),
    )
    st.html('<div class="ap-side-label">Reviewer</div>')
    st.text_input("Reviewer name", key="reviewer", placeholder="Your name (needed to approve)",
                  label_visibility="collapsed", help="Recorded on every approve / reject decision.")
    st.caption("🔒 Suggestions never change ad spend on their own. Every action needs human approval.")

nav.run()
