import pytest

from adpulse.audit.search_terms import _negative_for, classify_rules


@pytest.mark.parametrize("term,intent", [
    ("coffee shop jobs near me", "irrelevant"), ("barista salary", "irrelevant"),
    ("free coffee samples", "irrelevant"), ("how to roast coffee beans at home", "research"),
    ("what is single origin coffee", "research"), ("coffee subscription cancel", "navigational"),
    ("buy specialty coffee beans online", "buyer"), ("alternative to big chain coffee", "buyer"),
    ("ember and oak coffee", "buyer"), ("coffee beans wholesale 50 lb", "irrelevant"),
])
def test_rule_intents(term, intent):
    assert classify_rules(term)[0] == intent


def test_negative_keyword_shape():
    assert _negative_for("coffee shop jobs near me", "jobs", "irrelevant") == '"jobs"'
    assert _negative_for("big chain coffee beans", "competitor", "research") == "[big chain coffee beans]"
