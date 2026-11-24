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
