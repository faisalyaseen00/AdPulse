"""End-to-end agent loop against the real warehouse, with a scripted LLM."""
import io
import re

import pandas as pd
import pytest

from adpulse import warehouse
from adpulse.agent.core import AdPulseAgent
from adpulse.agent.prompts import semantic
from adpulse.agent.schemas import ChartSpec, CriticReview, Narrative, SQLPlan, SuggestedAction
from adpulse.llm.fake import ScriptedLLM

pytestmark = pytest.mark.integration
GOOD_SQL = semantic()["examples"][0]["sql"].replace(
    "toStartOfMonth(today() - INTERVAL 1 MONTH)", "toStartOfMonth((SELECT max(date) FROM fct_ad_daily) - INTERVAL 1 MONTH)")


def _result_from_prompt(user: str) -> pd.DataFrame:
    csv = user.split("Result (verified SQL):\n", 1)[1]
    csv = csv.split("\n", 1)[1]  # drop "N rows. Columns: ..." line
    csv = csv.split("\n\nYour previous draft")[0]
    return pd.read_csv(io.StringIO(csv))


def _honest_narrative(user: str) -> Narrative:
    df = _result_from_prompt(user)
    top = df.iloc[0]
    return Narrative(
        headline=f"{top.ad_name} brought the highest-LTV customers last month.",
        answer_markdown=(f"**{top.ad_name}** acquired {int(top.new_customers)} customers with an average LTV of "
                         f"${top.avg_customer_ltv:,.2f} at a CAC of ${top.cac:,.2f}."),
        suggested_actions=[SuggestedAction(action="scale_ad", platform=top.platform, ad_name=top.ad_name,
                                           rationale="best LTV"),
                           SuggestedAction(action="pause_ad", platform="meta", ad_name="Made Up Ad", rationale="x")])


def make_llm(sql_sequence, critic_sequence=("pass",), lie_first=False):
    state = {"sql": list(sql_sequence), "critic": list(critic_sequence), "narr": 0}

    def responder(step, user, schema):
        if step == "write_sql":
            sql = state["sql"].pop(0) if len(state["sql"]) > 1 else state["sql"][0]
            return SQLPlan(reasoning="Customers by acquisition ad, spend separately.", sql=sql,
                           assumptions=["last month = previous calendar month"],
                           chart=ChartSpec(type="bar", x="ad_name", y="avg_customer_ltv"))
        if step == "critic":
            v = state["critic"].pop(0) if len(state["critic"]) > 1 else state["critic"][0]
            return CriticReview(verdict=v, issues=[] if v == "pass" else ["wrong window"],
                                fix_instructions="" if v == "pass" else "use last month")
        if step == "narrate":
            state["narr"] += 1
            if lie_first and state["narr"] == 1:
                return Narrative(headline="Big win", answer_markdown="LTV was $999.99 across 4321 customers.")
            return _honest_narrative(user)
        raise AssertionError(step)

    return ScriptedLLM(responder)


def test_happy_path_verified(db):
    ans = AdPulseAgent(make_llm([GOOD_SQL])).ask("Which ads brought customers with the highest LTV last month?")
    assert ans.ok, ans.error
    assert ans.verified
    assert not ans.data.empty and "avg_customer_ltv" in ans.data.columns
    assert ans.numbers_checked >= 3 and ans.numbers_checked == ans.numbers_verified
    # the invented ad is dropped, the real one kept
    assert [a.ad_name for a in ans.suggested_actions] == [ans.data.iloc[0].ad_name]
    logged = warehouse.query_df("SELECT verified FROM app_questions WHERE id = {i:String}", {"i": ans.id})
    assert logged.iloc[0]["verified"] == 1


def test_db_error_is_repaired(db):
    llm = make_llm(["SELECT no_such_column FROM dim_ads", GOOD_SQL])
    ans = AdPulseAgent(llm).ask("highest LTV ads last month?")
    assert ans.ok and ans.attempts == 2
    assert any(s.name == "run in ClickHouse" and s.status == "retry" for s in ans.steps)


def test_guard_rejection_is_repaired(db):
    ans = AdPulseAgent(make_llm(["DROP TABLE dim_ads", GOOD_SQL])).ask("highest LTV ads last month?")
    assert ans.ok
    assert any(s.name == "SQL guard" and s.status == "retry" for s in ans.steps)
    assert warehouse.query_df("SELECT count() AS n FROM dim_ads").iloc[0]["n"] > 0


def test_critic_failure_triggers_rewrite(db):
    llm = make_llm([GOOD_SQL], critic_sequence=["fail", "pass"])
    ans = AdPulseAgent(llm).ask("highest LTV ads last month?")
    assert ans.ok and ans.critic.verdict == "pass"
    sql_prompts = [u for s, u in llm.calls if s == "write_sql"]
    assert len(sql_prompts) == 2 and "reviewer rejected" in sql_prompts[1]


def test_hallucinated_numbers_are_caught_and_rewritten(db):
    llm = make_llm([GOOD_SQL], lie_first=True)
    ans = AdPulseAgent(llm).ask("highest LTV ads last month?")
    assert ans.verified
    retry = [u for s, u in llm.calls if s == "narrate"][1]
    assert "$999.99" in retry and "NOT in the result" in retry


def test_reader_user_is_read_only(db):
    with pytest.raises(Exception):
        warehouse.reader().command("CREATE TABLE evil (x UInt8) ENGINE = Memory")
    with pytest.raises(Exception):
        warehouse.reader().query("SELECT * FROM app_recommendations")
    assert len(warehouse.run_untrusted("SELECT count() FROM dim_ads").index) == 1


def test_numbers_in_answer_match_warehouse(db):
    """The LTV the agent quotes equals an independent recomputation."""
    ans = AdPulseAgent(make_llm([GOOD_SQL])).ask("highest LTV ads last month?")
    top = ans.data.iloc[0]
    check = warehouse.query_df(
        """SELECT round(avg(c.ltv), 2) AS v FROM dim_customers c JOIN dim_ads d
           ON d.ad_id = c.acquisition_ad_id AND d.platform = c.acquisition_platform
           WHERE d.ad_name = {n:String}
             AND c.acquisition_month = toStartOfMonth((SELECT max(date) FROM fct_ad_daily) - INTERVAL 1 MONTH)""",
        {"n": top.ad_name}).iloc[0]["v"]
    assert abs(check - top.avg_customer_ltv) < 0.01
    assert re.search(re.escape(f"${top.avg_customer_ltv:,.2f}"), ans.answer_markdown)
