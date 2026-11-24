"""Structured outputs exchanged with the LLM."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChartSpec(BaseModel):
    type: Literal["bar", "line", "scatter", "none"] = Field(
        description="Best chart for the result. 'none' if a table is clearer.")
    x: str = Field(default="", description="Result column for the x axis (or categories).")
    y: str = Field(default="", description="Numeric result column for the y axis.")
    color: str = Field(default="", description="Optional result column to colour by.")
    title: str = Field(default="", description="Chart title in plain words a business owner understands, "
                                             "e.g. 'Cost to win one new customer, by month'. No abbreviations.")


class SQLPlan(BaseModel):
    reasoning: str = Field(description="2-4 sentences: tables, joins, time window, metric definitions used.")
    sql: str = Field(description="One ClickHouse SELECT statement. No trailing semicolon.")
    assumptions: list[str] = Field(default_factory=list,
                                   description="Interpretations made, e.g. 'last month = October 2026'.")
    chart: ChartSpec


class CriticReview(BaseModel):
    verdict: Literal["pass", "fail"]
    issues: list[str] = Field(default_factory=list, description="Concrete problems found. Empty if pass.")
    fix_instructions: str = Field(default="", description="How to rewrite the SQL if verdict is fail.")


class SuggestedAction(BaseModel):
    action: Literal["pause_ad", "scale_ad", "investigate"]
    platform: Literal["meta", "google"]
    ad_name: str = Field(description="Exact ad_name from the result.")
    rationale: str = Field(description="One sentence citing the numbers from the result.")


class Computation(BaseModel):
    quoted: str = Field(description='The figure exactly as written in the answer, e.g. "3.6x" or "+42%".')
    expression: str = Field(description='Arithmetic over values copied from the result, e.g. "125.75 / 34.81".')


class Narrative(BaseModel):
    headline: str = Field(description="One confident sentence in everyday words that answers the question, "
                                      "with the key number. No marketing abbreviations.")
    answer_markdown: str = Field(description="2-4 short markdown bullets in plain words, each starting with a bold phrase, optionally "
                                 "ending with a '**What to do:**' line. Under 140 words. Do not repeat the headline. "
                                 "Only numbers from the result.")
    computations: list[Computation] = Field(
        default_factory=list,
        description="Every number in the answer that is NOT copied verbatim from a result cell, with its arithmetic.")
    caveats: list[str] = Field(default_factory=list)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
