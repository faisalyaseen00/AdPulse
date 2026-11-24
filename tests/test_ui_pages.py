"""Render every Streamlit page headlessly against the live warehouse and assert no exceptions."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adpulse import warehouse

pytestmark = pytest.mark.integration
APP = Path(__file__).resolve().parents[1] / "app" / "main.py"
PAGES = ["views/overview.py", "views/ask.py", "views/audit.py", "views/recommendations.py",
         "views/reports.py", "views/pipeline.py"]


@pytest.fixture(scope="module", autouse=True)
def _need_db():
    if not warehouse.health().ok:
        pytest.skip("ClickHouse not running")


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    at.switch_page(page)
    at.run()
    assert not at.exception, [e.message for e in at.exception]


def test_approve_shows_confirmation_and_moves_card(db):
    import streamlit as st

    from adpulse.actions import recommendations as recs
    recs.refresh_pending(30)
    st.cache_data.clear()  # earlier tests in this process cached the old list
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["reviewer"] = "Test reviewer"
    at.run()
    at.switch_page("views/recommendations.py")
    at.run()
    approve = [b for b in at.button if b.label == "Approve"]
    assert approve and not approve[0].disabled
    rid = approve[0].key.split("_", 1)[1]
    approve[0].click()
    at.run()
    assert not at.exception
    assert any(t.value.startswith("Approved:") for t in at.toast)
    assert recs.latest().set_index("id").loc[rid, "status"] == "approved"
    recs.decide(rid, "rejected", "Test reviewer", "test cleanup")
    recs.refresh_pending(30)


def test_approving_a_stale_card_does_not_crash(db):
    import streamlit as st

    from adpulse.actions import recommendations as recs
    recs.refresh_pending(30)
    st.cache_data.clear()
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["reviewer"] = "Test reviewer"
    at.run()
    at.switch_page("views/recommendations.py")
    at.run()
    recs.refresh_pending(30)  # the list changes behind the page's back
    next(b for b in at.button if b.label == "Approve").click()
    at.run()
    assert not at.exception
    assert any("already changed elsewhere" in t.value for t in at.toast)
