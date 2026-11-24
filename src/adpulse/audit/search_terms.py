"""Google Ads search term audit: find paid clicks on queries with no buyer intent.

Two passes:
1. Deterministic rules (jobs, free, DIY / how-to, support / navigational, wholesale, ...).
2. Optional LLM classification for terms the rules can't place, in one batched call.
Terms with no buyer intent that spent money without converting are flagged as negative
keyword candidates. Nothing is changed in Google Ads: candidates go to the approval queue.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from .. import warehouse
from ..llm import LLM, LLMError

Intent = Literal["buyer", "research", "navigational", "irrelevant"]


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: str
    intent: Intent
    reason: str


RULES: list[Rule] = [
    Rule("jobs", r"\b(jobs?|careers?|hiring|salary|salaries|resume|internship)\b", "irrelevant",
         "Looking for a job, not to buy"),
    Rule("free", r"\b(free|samples?|giveaway|coupon free)\b", "irrelevant", "Looking for something free"),
    Rule("diy", r"\b(diy|how to|recipe|homemade|without)\b", "research", "Looking for a recipe or how-to"),
    Rule("learn", r"\b(what is|what are|meaning|definition|history of)\b", "research", "Learning about coffee, not shopping"),
    Rule("info", r"\b(calories|nutrition|tattoo|meme|wallpaper|drawing|clipart)\b", "irrelevant",
         "Off-topic search, not shopping"),
    Rule("support", r"\b(login|log in|sign in|cancel|cancellation|refund|customer service|phone number|tracking)\b",
         "navigational", "Existing customer who needs help"),
    Rule("local", r"\b(near me|hours|open now|menu|directions)\b", "irrelevant", "Looking for a café nearby"),
    Rule("brand", r"\b(ember (and |& )?oak)\b", "buyer", "Searching for your brand"),
    Rule("b2b", r"\b(wholesale|bulk|\d+\s?lb|distributor|supplier)\b", "irrelevant", "Wholesale buyer, not your customer"),
    Rule("community", r"\b(reddit|forum|quora)\b", "research", "Reading forums, not shopping yet"),
    Rule("switching", r"\b(alternative to|instead of|better than|vs\.?|versus)\b", "buyer",
         "Comparing brands, ready to switch"),
    Rule("competitor", r"\b(big chain)\b", "research", "Searching for a competitor"),
    Rule("buy", r"\b(buy|order|shop|subscription|subscribe|delivery|online|best|gift|beans)\b", "buyer",
         "Ready to buy"),
]
NON_BUYER: set[str] = {"irrelevant", "navigational", "research"}


class TermIntent(BaseModel):
    term: str
    intent: Intent
    reason: str = Field(description="Under 12 words.")


class TermIntents(BaseModel):
    items: list[TermIntent]


def classify_rules(term: str) -> tuple[Intent | None, str, str]:
    t = term.lower()
    for r in RULES:
        if re.search(r.pattern, t):
            return r.intent, r.reason, r.name
    return None, "", ""


def load_terms(days: int = 30) -> pd.DataFrame:
    return warehouse.query_df(
        """
        SELECT search_term, campaign_name, ad_group_name, any(match_type) AS match_type,
               sum(impressions) AS impressions, sum(clicks) AS clicks, round(sum(cost), 2) AS cost,
               sum(conversions) AS conversions, round(sum(conversions_value), 2) AS conversion_value
        FROM fct_search_terms
        WHERE date > (SELECT max(date) FROM fct_search_terms) - {days:UInt32}
        GROUP BY search_term, campaign_name, ad_group_name
        ORDER BY cost DESC
        """,
        {"days": days},
    )


def _negative_for(term: str, rule: str, intent: str) -> str:
    """Narrowest negative that blocks the bad intent without blocking buyers.

    Clearly irrelevant intents (jobs, free, local...) get a phrase negative on the trigger word;
    research / navigational / unclassified terms get an exact-match negative on the full term.
    """
    t = term.lower()
    if intent != "irrelevant":
        return f"[{t}]"
    for r in RULES:
        if r.name == rule and (m := re.search(r.pattern, t)):
            return f'"{m.group(0)}"'
    return f"[{t}]"


def audit(days: int = 30, llm: LLM | None = None, min_cost: float = 5.0) -> pd.DataFrame:
    df = load_terms(days)
    if df.empty:
        return df
    res = df["search_term"].map(classify_rules)
    df["intent"] = [r[0] for r in res]
    df["reason"] = [r[1] for r in res]
    df["rule"] = [r[2] for r in res]
    df["classified_by"] = df["intent"].map(lambda x: "rules" if x else "")

    unknown = df[df["intent"].isna()]["search_term"].unique().tolist()
    if unknown and llm is not None:
        try:
            out = llm.structured(
                system=("You classify Google Ads search terms for a DTC specialty coffee brand by intent: "
                        "buyer (wants to purchase coffee/subscription now), research (learning, comparing), "
                        "navigational (existing customer / specific site), irrelevant (jobs, free stuff, "
                        "unrelated)."),
                user="Classify each term:\n" + "\n".join(f"- {t}" for t in unknown),
                schema=TermIntents, step="search_term_intent")
            got = {i.term.lower(): i for i in out.items}
            for idx in df.index[df["intent"].isna()]:
                hit = got.get(df.at[idx, "search_term"].lower())
                if hit:
                    df.at[idx, "intent"], df.at[idx, "reason"] = hit.intent, hit.reason
                    df.at[idx, "classified_by"] = "llm"
        except LLMError:
            pass
    df["intent"] = df["intent"].fillna("unknown")
    df.loc[df["intent"] == "unknown", "reason"] = "Unclassified (no rule matched)"

    df["cpa"] = (df["cost"] / df["conversions"].where(df["conversions"] > 0)).round(2)
    df["flagged"] = (df["intent"].isin(NON_BUYER) & (df["cost"] >= min_cost) & (df["conversions"] < 1)) | (
        (df["intent"] == "irrelevant") & (df["cost"] >= min_cost))
    df["wasted_spend"] = df["cost"].where(df["flagged"], 0.0)
    df["suggested_negative"] = [
        _negative_for(t, r, i) if f else ""
        for t, r, i, f in zip(df["search_term"], df["rule"], df["intent"], df["flagged"])]
    return df.sort_values(["flagged", "wasted_spend", "cost"], ascending=[False, False, False]).reset_index(drop=True)


def summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"terms": 0, "flagged": 0, "wasted_spend": 0.0, "total_cost": 0.0, "wasted_share": 0.0}
    total = float(df["cost"].sum())
    wasted = float(df["wasted_spend"].sum())
    return {"terms": len(df), "flagged": int(df["flagged"].sum()), "wasted_spend": round(wasted, 2),
            "total_cost": round(total, 2), "wasted_share": round(wasted / total, 4) if total else 0.0}
