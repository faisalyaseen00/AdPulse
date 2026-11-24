"""Plain-English layer: shorthand is detected and swapped, numbers and look-alike words are untouched."""
import re

import pytest

from adpulse import plain


@pytest.mark.parametrize("text,expected", [
    ("ROAS was 1.03x", ["ROAS"]),
    ("LTV:CAC 0.46 at a CAC of $155", ["LTV:CAC", "CAC"]),
    ("click-through (CTR) and cvr", ["CTR", "cvr"]),
    ("the SQL query returned a cohort", ["SQL", "query", "cohort"]),
])
def test_finds_shorthand(text, expected):
    found = plain.find_jargon(text)
    assert all(e in found for e in expected)


@pytest.mark.parametrize("text", ["cacao beans", "tractor", "Salty caching", "$LTV1", "Every customer spends $85"])
def test_ignores_lookalikes(text):
    assert plain.find_jargon(text) == []


def test_unjargon_keeps_numbers():
    text = "Spent $3,301.43 for $260.75 (ROAS 0.08); LTV:CAC 0.46; CAC $155.13."
    out = plain.unjargon(text)
    assert plain.find_jargon(out) == []
    assert re.findall(r"[\d.,]+\d", out) == re.findall(r"[\d.,]+\d", text)
    assert "money back per $1" in out and "value vs cost" in out and "cost per new customer" in out


def test_every_term_has_label_and_explanation():
    for key, (label, explain) in plain.TERMS.items():
        assert label and explain.endswith("."), key
        assert not plain.find_jargon(label), key
