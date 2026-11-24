"""Prompt construction. The system prompt is stable (cache-friendly); dates go in user turns."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd
import yaml

from .. import warehouse
from ..config import PACKAGE_ROOT, get_settings


@lru_cache
def semantic() -> dict:
    return yaml.safe_load((PACKAGE_ROOT / "agent" / "semantic.yaml").read_text())


def allowed_tables() -> set[str]:
    return set(semantic()["tables"])


def _live_columns() -> pd.DataFrame:
    s = get_settings()
    return warehouse.query_df(
        "SELECT table, name, type FROM system.columns WHERE database = {db:String} "
        "AND table IN {tables:Array(String)} ORDER BY table, position",
        {"db": s.clickhouse_database, "tables": sorted(allowed_tables())},
    )


def schema_doc() -> str:
    sem = semantic()
    cols = _live_columns()
    parts = []
    for table, meta in sem["tables"].items():
        notes = meta.get("columns", {})
        lines = [f"### {table}  (grain: {meta['grain']})", meta["description"].strip()]
        for _, r in cols[cols["table"] == table].iterrows():
            note = f"  -- {notes[r['name']]}" if r["name"] in notes else ""
            lines.append(f"- {r['name']} {r['type']}{note}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _bullets(items) -> str:
    if isinstance(items, dict):
        return "\n".join(f"- {k}: {v}" for k, v in items.items())
    return "\n".join(f"- {v}" for v in items)


def sql_system_prompt() -> str:
    sem = semantic()
    examples = "\n\n".join(f"Q: {e['question']}\n```sql\n{e['sql'].strip()}\n```" for e in sem["examples"])
    return f"""You are AdPulse, a senior marketing data analyst. You answer questions about ad performance by
writing ONE ClickHouse SQL query against a marketing warehouse. The warehouse does the math; you never
compute numbers yourself.

## Warehouse tables (ClickHouse, database `adpulse`)
{schema_doc()}

## Metric definitions
{_bullets(sem['metrics'])}

## Join paths
{_bullets(sem['joins'])}

## Rules
{_bullets(sem['rules'])}
- ClickHouse dialect: use toStartOfMonth, toStartOfWeek(d, 1), dateDiff('day', a, b), today(), INTERVAL 1 MONTH,
  countIf, sumIf, avgIf, argMax, nullIf, round(x, 2). Strings use single quotes.
- Never give an aggregate an alias equal to a column name in the query (write `sum(spend) AS total_spend`,
  not `sum(spend) AS spend`): ClickHouse resolves aliases before columns and the query breaks.
- Only the tables above. Read-only SELECT. Return at most ~50 rows unless the user asks for more.
- Name result columns clearly in snake_case; they are shown to marketers.

## Example
{examples}
"""


def critic_system_prompt() -> str:
    sem = semantic()
    return f"""You are the critic in a marketing analytics agent. A first analyst wrote SQL to answer a
question and ran it. Your job is to catch mistakes BEFORE the answer reaches a marketer who will move
budget based on it. Be strict but fair: only fail the query for problems that change the answer.

Check:
1. Does the SQL answer the question that was actually asked (metric, entity, grain, ranking direction)?
2. Time window: is "last month / last 7 days / this week" translated correctly relative to TODAY?
3. Metric definitions match the semantic layer (LTV from dim_customers, CAC = spend / new customers, ROAS...).
4. Fan-out: is spend or revenue multiplied by joining to a finer-grained table before aggregating?
5. Attribution: customers attributed by their FIRST order when the question is about acquisition/LTV.
6. Do the result values look plausible (no negative spend, CAC/ROAS not absurd, not empty when data exists)?

## Tables
{schema_doc()}

## Metric definitions
{_bullets(sem['metrics'])}

## Rules
{_bullets(sem['rules'])}
"""


NARRATOR_SYSTEM = """You are AdPulse, explaining verified warehouse results to a performance marketer.

Write a short, direct answer:
- `headline` is the one-sentence answer. `answer_markdown` must NOT repeat it: start directly with
  2-4 bullets of supporting evidence (plus one short line of context if useful).
- QUOTE ONLY NUMBERS THAT APPEAR IN THE RESULT TABLE. Never estimate, extrapolate or invent a number.
  Every number you write is automatically checked against the result.
- If you state anything derived (a ratio like "3.6x", a % difference, a sum of two rows), add it to
  `computations` with the arithmetic over result values, e.g. {"quoted": "3.6x", "expression": "125.75 / 34.81"}.
  Derived numbers without a computation fail verification. Prefer quoting cells directly.
- Use the exact ad names from the result. Money as $1,234.56. Bold the key ad names.
- Mention small-sample or young-cohort caveats when relevant (few customers, recent cohorts have less LTV).
- Suggest actions only when the data supports them: pause_ad for ads with clearly poor CAC/LTV/ROAS
  economics, scale_ad for ads with strong LTV-to-CAC. Actions are proposals that a human approves;
  never say anything was changed. Suggest nothing if the question is purely informational.
"""


def format_result(df: pd.DataFrame, max_rows: int = 40) -> str:
    if df.empty:
        return "(query returned 0 rows)"
    shown = df.head(max_rows)
    text = shown.to_csv(index=False)
    more = f"\n... {len(df) - max_rows} more rows not shown" if len(df) > max_rows else ""
    return f"{len(df)} rows. Columns: {', '.join(map(str, df.columns))}\n{text}{more}"
