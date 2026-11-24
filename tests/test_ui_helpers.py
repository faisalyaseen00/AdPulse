"""Shared UI helpers: change colours follow the business meaning, column names read as plain words."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import ui


@pytest.mark.parametrize("delta,better,cls", [
    (0.10, "up", "up"), (-0.10, "up", "down"),        # sales: up is good
    (0.10, "down", "down"), (-0.10, "down", "up"),    # cost per customer: down is good
    (0.10, "neutral", "flat"), (-0.10, "neutral", "flat"),  # ad spend: neither
    (0.0001, "up", "flat"),
])
def test_change_colour_follows_meaning(delta, better, cls):
    assert f'class="{cls}"' in ui.change_text(delta, better)


@pytest.mark.parametrize("raw,nice", [
    ("ltv_to_cac", "Value vs cost"), ("cac", "Cost per new customer"), ("roas", "Money back per $1"),
    ("avg_ltv_90d", "Average customer value (first 90 days)"), ("ad_name", "Ad"), ("month", "Month"),
])
def test_friendly_column_names(raw, nice):
    assert ui.friendly_name(raw) == nice


def test_dollar_signs_never_become_math():
    assert ui.md("spent $10 and $20") == "spent \\$10 and \\$20"


def test_sparkline_draws_and_is_one_line():
    svg = ui.sparkline([10, 14, 9, 20, 18], [8, 9, 9, 12, 11])
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "\n" not in svg  # st.markdown would turn indented/blank lines into code blocks
    assert svg.count('class="line') == 2 and 'pathLength="1"' in svg and "ping" in svg
    assert ui.sparkline([5]) == ""  # not enough points: no chart rather than a broken one


def test_menu_button_is_never_hidden():
    # the open-menu button lives inside stToolbar; hiding the toolbar strands phone users
    assert '[data-testid="stToolbar"]' not in ui.CSS.split("hide only the actions")[-1].split("}")[0]
    assert "display: none" not in [rule for rule in ui.CSS.split("}") if 'data-testid="stToolbar"]' in rule][:1]


def test_motion_respects_reduced_motion_setting():
    assert "prefers-reduced-motion" in ui.CSS and ".ap-spark .line { stroke-dashoffset: 0; }" in ui.CSS


def test_area_chart_has_months_tooltips_and_draws():
    import pandas as pd
    dates = list(pd.date_range("2026-06-01", periods=20, freq="W-MON"))
    svg = ui.area_chart(dates, [("Sales", [float(i % 7 + 10) for i in range(20)], "#EB6834"),
                                ("Spend", [float(i % 5 + 8) for i in range(20)], "#2A78D6")])
    assert "\n" not in svg and svg.count('class="ln') == 2 and 'pathLength="1"' in svg
    assert svg.count("<title>") == 20 and "Week of Jun 1" in svg  # one hover tip per week
    assert ">Jun<" in svg and ">Oct<" in svg  # month labels on the axis


def test_header_does_not_block_clicks():
    assert 'header[data-testid="stHeader"] { background: transparent; pointer-events: none; }' in ui.CSS
