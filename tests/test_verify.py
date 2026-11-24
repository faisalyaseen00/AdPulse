import numpy as np
import pandas as pd

from adpulse.agent.verify import extract_numbers, verify_numbers

DF = pd.DataFrame({"ad_name": ["Static - 20% Off", "RSA - Coffee Subscription"], "new_customers": [312, 41],
                   "avg_ltv": [34.81, 125.75], "spend": [6642.48, 3823.25], "share": [0.35, 0.12]})


def _bad(text, q="", comps=()):
    return [c.text for c in verify_numbers(text, DF, q, comps) if not c.verified]


def test_cells_and_formats():
    assert _bad("LTV $125.75 vs $34.81; 312 and 41 customers; spend $6,642.48") == []


def test_aggregates_and_rounded_forms():
    assert _bad("353 customers in total; spend $6.6k; LTV about $126") == []


def test_percent_of_fraction():
    assert _bad("35% share vs 12%") == []


def test_declared_computation_is_recomputed():
    assert _bad("3.6x higher LTV", comps=[("3.6x", "125.75 / 34.81")]) == []
    assert _bad("LTV is 261% higher", comps=[("261%", "(125.75 - 34.81) / 34.81")]) == []


def test_undeclared_ratio_fails():
    assert _bad("3.6x higher LTV") == ["3.6x"]


def test_wrong_math_fails():
    assert _bad("5.1x higher LTV", comps=[("5.1x", "125.75 / 34.81")]) == ["5.1x"]


def test_computation_with_invented_operand_fails():
    assert _bad("3.0x", comps=[("3.0x", "300 / 100")]) == ["3.0x"]  # 2.0 would match the row count


def test_numbers_in_entity_names_ignored():
    assert extract_numbers("Static - 20% Off", ["Static - 20% Off"]) == []


def test_question_numbers_ignored():
    assert _bad("Here are the top 15 ads", "show the top 15 ads") == []


def test_hallucination_flagged():
    assert _bad("Average LTV was $77.10 and CAC $19.99") == ["$77.10", "$19.99"]


def test_dates_ignored():
    assert _bad("In 2026-10 (October 2026) LTV was $125.75") == []


def test_random_numbers_rarely_pass():
    rng = np.random.default_rng(0)
    big = pd.DataFrame(rng.uniform(1, 5000, size=(10, 8)).round(2), columns=[f"c{i}" for i in range(8)])
    for fmt, gen in [("${:,.2f}", lambda: rng.uniform(10, 5000)), ("{:.1f}%", lambda: rng.uniform(1, 90)),
                     ("{:.1f}x", lambda: rng.uniform(1.1, 9))]:
        xs = [fmt.format(gen()) for _ in range(300)]
        rate = np.mean([c.verified for c in verify_numbers(" ; ".join(xs), big)])
        assert rate < 0.03, (fmt, rate)
