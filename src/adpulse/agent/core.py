"""The AdPulse agent: question -> SQL -> guard -> warehouse -> critic -> narrative -> number check.

    plan SQL ─▶ guard ─▶ run (read-only user) ─┬─ error ─▶ repair (≤ N times)
                                                 ▼
                                              critic ── fail ─▶ rewrite SQL with critic feedback
                                                 ▼ pass
                                              narrate ─▶ verify every number ── unverified ─▶ rewrite once
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pandas as pd

from .. import warehouse
from ..config import get_settings
from ..llm import LLM, LLMError
from . import prompts
from .schemas import ChartSpec, CriticReview, Narrative, SQLPlan, SuggestedAction
from .sql_guard import SQLRejected, check_sql
from .verify import NumberCheck, summarize, verify_numbers

log = logging.getLogger(__name__)
MAX_CRITIC_ROUNDS = 2


@dataclass
class Step:
    name: str
    status: str  # ok | retry | fail | info
    detail: str = ""
    ms: int = 0


@dataclass
class Turn:
    """Prior question in the chat, used as context for follow-ups."""
    question: str
    sql: str
    headline: str


@dataclass
class AgentAnswer:
    question: str
    ok: bool
    headline: str = ""
    answer_markdown: str = ""
    sql: str = ""
    reasoning: str = ""
    assumptions: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    data: pd.DataFrame = field(default_factory=pd.DataFrame)
    chart: ChartSpec | None = None
    critic: CriticReview | None = None
    number_checks: list[NumberCheck] = field(default_factory=list)
    suggested_actions: list[SuggestedAction] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    attempts: int = 0
    latency_ms: int = 0
    error: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def numbers_checked(self) -> int:
        return summarize(self.number_checks)[0]

    @property
    def numbers_verified(self) -> int:
        return summarize(self.number_checks)[1]

    @property
    def verified(self) -> bool:
        return (self.ok and self.critic is not None and self.critic.verdict == "pass"
                and self.numbers_checked == self.numbers_verified)


def data_context() -> str:
    df = warehouse.query_df(
        "SELECT (SELECT min(date) FROM fct_ad_daily) AS spend_from, (SELECT max(date) FROM fct_ad_daily) AS spend_to,"
        " (SELECT max(order_date) FROM fct_orders) AS orders_to"
    )
    r = df.iloc[0]
    today = date.today()
    return (f"TODAY is {today.isoformat()} ({today.strftime('%A')}). Ad spend data covers "
            f"{r['spend_from']} to {r['spend_to']}; orders through {r['orders_to']}.")


class AdPulseAgent:
    def __init__(self, llm: LLM):
        self.llm = llm
        self.settings = get_settings()
        self._sql_system = prompts.sql_system_prompt()
        self._critic_system = prompts.critic_system_prompt()
        self._allowed = prompts.allowed_tables()

    # ------------------------------------------------------------------ public
    def ask(self, question: str, history: list[Turn] | None = None) -> AgentAnswer:
        t0 = time.perf_counter()
        ans = AgentAnswer(question=question, ok=False)
        try:
            self._run(question, history or [], ans)
        except LLMError as e:
            ans.error = str(e)
            ans.steps.append(Step("llm", "fail", str(e)))
        except Exception as e:
            log.exception("agent failure")
            ans.error = f"{type(e).__name__}: {e}"
            ans.steps.append(Step("agent", "fail", ans.error))
        ans.latency_ms = int((time.perf_counter() - t0) * 1000)
        self._log(ans)
        return ans

    # ------------------------------------------------------------------ pipeline
    def _run(self, question: str, history: list[Turn], ans: AgentAnswer) -> None:
        context = data_context()
        hist = ""
        if history:
            hist = "Earlier in this conversation (for follow-up questions):\n" + "\n".join(
                f"- Q: {h.question}\n  SQL: {h.sql.strip()[:600]}\n  Answer: {h.headline}" for h in history[-3:]
            ) + "\n\n"
        base_prompt = f"{context}\n\n{hist}Question: {question}"

        feedback = ""
        df = pd.DataFrame()
        plan: SQLPlan | None = None
        for critic_round in range(MAX_CRITIC_ROUNDS + 1):
            plan, df = self._plan_and_execute(base_prompt + feedback, ans)
            review = self._critic(context, question, plan, df, ans)
            ans.critic = review
            if review.verdict == "pass" or critic_round == MAX_CRITIC_ROUNDS:
                break
            feedback = (
                "\n\nA reviewer rejected your previous query.\nPrevious SQL:\n```sql\n"
                f"{plan.sql}\n```\nIssues:\n" + "\n".join(f"- {i}" for i in review.issues)
                + f"\nFix: {review.fix_instructions}\nWrite a corrected query."
            )

        assert plan is not None
        ans.sql, ans.reasoning, ans.assumptions, ans.chart, ans.data = (
            plan.sql, plan.reasoning, plan.assumptions, plan.chart, df)

        narrative = self._narrate(context, question, plan, df, ans)
        checks = _check(narrative, df, question)
        bad = [c for c in checks if not c.verified]
        if bad:
            ans.steps.append(Step("verify numbers", "retry",
                                  f"{len(bad)} number(s) not found in result: {', '.join(c.text for c in bad)}"))
            narrative = self._narrate(context, question, plan, df, ans, unverified=[c.text for c in bad])
            checks = _check(narrative, df, question)
        n, ok = summarize(checks)
        ans.steps.append(Step("verify numbers", "ok" if n == ok else "fail", f"{ok}/{n} numbers traced to the result"))

        ans.headline = narrative.headline
        ans.answer_markdown = narrative.answer_markdown
        ans.caveats = narrative.caveats
        ans.number_checks = checks
        ans.suggested_actions = self._valid_actions(narrative.suggested_actions, df)
        ans.ok = True

    def _plan_and_execute(self, prompt: str, ans: AgentAnswer) -> tuple[SQLPlan, pd.DataFrame]:
        error_feedback = ""
        for attempt in range(self.settings.agent_max_repairs + 1):
            ans.attempts += 1
            t = time.perf_counter()
            plan = self.llm.structured(system=self._sql_system, user=prompt + error_feedback, schema=SQLPlan,
                                       step="write_sql")
            ans.steps.append(Step("write SQL", "ok", plan.reasoning, _ms(t)))
            try:
                check_sql(plan.sql, self._allowed, self.settings.clickhouse_database)
            except SQLRejected as e:
                ans.steps.append(Step("SQL guard", "retry", str(e)))
                error_feedback = f"\n\nYour previous SQL was rejected by the safety guard: {e}\nRewrite it."
                continue
            ans.steps.append(Step("SQL guard", "ok", "read-only SELECT on approved tables"))
            t = time.perf_counter()
            try:
                df = warehouse.run_untrusted(plan.sql)
            except Exception as e:  # noqa: BLE001
                msg = _short_db_error(e)
                ans.steps.append(Step("run in ClickHouse", "retry", msg, _ms(t)))
                error_feedback = (f"\n\nYour previous SQL failed in ClickHouse:\n```sql\n{plan.sql}\n```\n"
                                  f"Error: {msg}\nFix the query.")
                continue
            ans.steps.append(Step("run in ClickHouse", "ok", f"{len(df)} rows", _ms(t)))
            return plan, df
        raise RuntimeError("Could not produce a valid query after repairs. " + error_feedback.strip())

    def _critic(self, context: str, question: str, plan: SQLPlan, df: pd.DataFrame,
                ans: AgentAnswer) -> CriticReview:
        t = time.perf_counter()
        review = self.llm.structured(
            system=self._critic_system,
            user=(f"{context}\n\nQuestion: {question}\n\nAnalyst reasoning: {plan.reasoning}\n\n"
                  f"SQL:\n```sql\n{plan.sql}\n```\n\nResult:\n{prompts.format_result(df, 25)}"),
            schema=CriticReview, step="critic")
        detail = "query looks correct" if review.verdict == "pass" else "; ".join(review.issues)
        ans.steps.append(Step("critic review", "ok" if review.verdict == "pass" else "retry", detail, _ms(t)))
        return review

    def _narrate(self, context: str, question: str, plan: SQLPlan, df: pd.DataFrame, ans: AgentAnswer,
                 unverified: list[str] | None = None) -> Narrative:
        t = time.perf_counter()
        extra = ""
        if unverified:
            extra = ("\n\nYour previous draft quoted numbers that are NOT in the result: "
                     f"{', '.join(unverified)}. Rewrite using only numbers from the result table, and declare "
                     "any ratio or difference in `computations` with its arithmetic.")
        nar = self.llm.structured(
            system=NARRATOR, user=(f"{context}\n\nQuestion: {question}\n\nAssumptions: {plan.assumptions}\n\n"
                                   f"Result (verified SQL):\n{prompts.format_result(df)}{extra}"),
            schema=Narrative, step="narrate")
        ans.steps.append(Step("write answer", "ok", nar.headline, _ms(t)))
        return nar

    def _valid_actions(self, actions: list[SuggestedAction], df: pd.DataFrame) -> list[SuggestedAction]:
        if not actions:
            return []
        names = set(warehouse.query_df("SELECT ad_name FROM dim_ads")["ad_name"])
        return [a for a in actions if a.ad_name in names]

    def _log(self, ans: AgentAnswer) -> None:
        try:
            warehouse.admin().insert(
                "app_questions",
                [[ans.id, datetime.now(timezone.utc).replace(tzinfo=None), ans.question, ans.sql,
                  ans.answer_markdown, int(ans.verified), ans.critic.verdict if ans.critic else "",
                  ans.numbers_checked, ans.numbers_verified, ans.attempts, ans.latency_ms,
                  self.llm.name, ans.error]],
                column_names=["id", "asked_at", "question", "sql", "answer", "verified", "critic_verdict",
                              "numbers_checked", "numbers_verified", "attempts", "latency_ms", "provider",
                              "error"],
            )
        except Exception:
            log.warning("could not log question", exc_info=True)


NARRATOR = prompts.NARRATOR_SYSTEM


def _check(n: Narrative, df: pd.DataFrame, question: str) -> list[NumberCheck]:
    comps = [(c.quoted, c.expression) for c in n.computations]
    return verify_numbers(n.answer_markdown + "\n" + n.headline, df, question, comps)


def _ms(t: float) -> int:
    return int((time.perf_counter() - t) * 1000)


def _short_db_error(e: Exception) -> str:
    msg = str(e)
    if "DB::Exception:" in msg:
        msg = msg.split("DB::Exception:", 1)[1]
    return msg.split("(version")[0].strip()[:800]

