"""Plain-English vocabulary shared by the app, the AI answers and the weekly report.

AdPulse is read by business owners, not analysts. Every metric has a short everyday name and a
one-line explanation; marketing shorthand (ROAS, CAC, LTV...) is only ever shown next to its meaning.
"""
from __future__ import annotations

# key -> (everyday name, one-line explanation)
TERMS: dict[str, tuple[str, str]] = {
    "spend": ("Ad spend", "Money paid to Meta and Google for ads."),
    "paid_revenue": ("Sales from ads", "Sales from people who arrived through an ad."),
    "total_revenue": ("All sales", "Every sale, including people who found you without an ad."),
    "roas": ("Money back per $1", "Sales from ads divided by ad spend. Above $1 means ads bring back more than they cost."),
    "new_customers": ("New customers from ads", "First-time buyers who came through an ad."),
    "cac": ("Cost per new customer", "Ad spend divided by new customers: what it costs to win one buyer."),
    "ltv": ("Customer value", "How much an average customer has spent with you so far, including repeat orders."),
    "ltv90": ("Customer value (first 90 days)", "What a customer spends in their first 90 days. Fair to compare across ads."),
    "ltv_to_cac": ("Value vs cost", ("Customer value divided by the cost to win them. 3× means each customer is "
                                     "worth three times what they cost. Below 1× loses money.")),
    "impressions": ("Ad views", "How many times your ads were shown."),
    "clicks": ("Clicks", "How many times people clicked an ad."),
    "ctr": ("Click rate", "Share of ad views that turned into a click."),
    "sessions": ("Site visits", "Visits to your website that came from an ad."),
    "cvr": ("Buy rate", "Share of site visits that became a new customer."),
    "conversions": ("Sales", "Purchases Google counted for this search."),
    "search_term": ("What people searched", "The exact words someone typed into Google before clicking your ad."),
    "wasted": ("Wasted spend", "Money spent on searches from people who were never going to buy."),
    "negative_keyword": ("Block this search", "Tell Google to stop showing your ads for these words."),
}

# search intent (internal value) -> everyday label
INTENTS: dict[str, str] = {
    "buyer": "Ready to buy",
    "research": "Just researching",
    "navigational": "Existing customer",
    "irrelevant": "Not a buyer",
}

# recommendation kind -> (everyday label, what approving it means)
ACTIONS: dict[str, tuple[str, str]] = {
    "pause_ad": ("Pause this ad", "Stop spending on an ad that isn't paying off."),
    "scale_ad": ("Give it more budget", "Spend 20% more on an ad that wins valuable customers cheaply."),
    "negative_keyword": ("Block this search", "Stop paying for clicks from people who won't buy."),
}

# Rules the AI follows when it writes for a non-technical reader.
WRITING_RULES = """Write for a busy business owner, not an analyst:
- Plain, everyday words and short sentences. Lead with what it means for the business.
- Never use bare marketing shorthand. Say "money back per $1 spent" (not ROAS), "cost per new customer"
  (not CAC), "customer value" (not LTV), "value vs cost" (not LTV:CAC), "click rate" (not CTR),
  "block this search" (not negative keyword). If you must name a term, explain it in a few words.
- No database or technical words (SQL, query, table, column, row, cohort, attribution model, warehouse).
- Make it concrete: "each customer from this ad costs $126 but only spends $86" beats "LTV:CAC 0.68".
- Confident and clear, never hype. No exclamation marks."""


def label(key: str) -> str:
    return TERMS[key][0]


def explain(key: str) -> str:
    return TERMS[key][1]


def intent(value: str) -> str:
    return INTENTS.get(value, value.replace("_", " ").capitalize())


def times(x: float | None) -> str:
    """3.456 -> '3.5×' (value-vs-cost style multiples)."""
    return "–" if x is None else f"{x:.1f}×"


def per_dollar(x: float | None) -> str:
    """ROAS 1.03 -> '$1.03' (money back per $1 spent)."""
    return "–" if x is None else f"${x:.2f}"


# Shorthand a business reader shouldn't have to decode (case-insensitive, whole words).
_JARGON = {
    r"ltv\s*[:/]\s*cac|ltv[- ]to[- ]cac": "value vs cost",
    r"roas": "money back per $1",
    r"ltv": "customer value",
    r"cac": "cost per new customer",
    r"ctr": "click rate",
    r"cvr": "buy rate",
    r"cpc": "cost per click",
    r"cpa": "cost per sale",
    r"aov": "average order",
    r"kpis?": "key numbers",
    r"sql|quer(?:y|ies)": "",
    r"cohorts?": "",
}


def find_jargon(text: str) -> list[str]:
    """Shorthand words present in `text`, e.g. ['ROAS', 'CAC']."""
    import re
    found = []
    for pat in _JARGON:
        for m in re.finditer(rf"(?<![\w$]){pat}(?!\w)", text or "", flags=re.IGNORECASE):
            found.append(m.group(0))
    return list(dict.fromkeys(found))


def unjargon(text: str) -> str:
    """Last-resort swap of shorthand for everyday words (numbers untouched)."""
    import re
    for pat, nice in _JARGON.items():
        if nice:
            text = re.sub(rf"(?<![\w$]){pat}(?!\w)", nice, text or "", flags=re.IGNORECASE)
    return text
