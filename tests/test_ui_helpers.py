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
