"""Weekly performance report.

All numbers come from fixed SQL (no LLM math). When an LLM is configured, it writes a short
"what to do" commentary that must pass the same number verification as chat answers;
otherwise a template summary is used.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from pydantic import BaseModel, Field

from .. import warehouse
from ..actions import recommendations as recs
from ..agent.schemas import Computation
from ..agent.verify import verify_numbers
from ..audit import search_terms
from ..config import get_settings
from ..llm import LLM, LLMError


@dataclass
class Kpi:
    label: str
    value: float
    prior: float
    fmt: str  # money | int | ratio | pct
    better: str = "up"  # up | down

    @property
    def change(self) -> float | None:
        return None if not self.prior else (self.value - self.prior) / abs(self.prior)

    def text(self, v: float | None = None) -> str:
        v = self.value if v is None else v
        return {"money": f"${v:,.2f}", "int": f"{v:,.0f}", "ratio": f"{v:.2f}x", "pct": f"{v:.1%}"}[self.fmt]

    @property
    def good(self) -> bool | None:
        c = self.change
        return None if c is None or abs(c) < 0.005 else (c > 0) == (self.better == "up")


@dataclass
class WeeklyReport:
    period_start: date
    period_end: date
    kpis: list[Kpi]
    top_ads: pd.DataFrame
    worst_ads: pd.DataFrame
    platform: pd.DataFrame
    waste: dict
    top_waste_terms: pd.DataFrame
    pending: pd.DataFrame
    commentary: list[str] = field(default_factory=list)
    commentary_source: str = "template"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


class Commentary(BaseModel):
    bullets: list[str] = Field(description="3-4 bullets: what happened and what to do next. Numbers only from data.")
    computations: list[Computation] = Field(
        default_factory=list, description="Each derived number (ratio, % change) with its arithmetic over data values.")


def _kpis(start: date, end: date) -> list[Kpi]:
    q = """
        SELECT
          (SELECT sum(spend) FROM fct_ad_daily WHERE date BETWEEN {s:Date} AND {e:Date}) AS spend,
          (SELECT sum(revenue) FROM fct_orders WHERE order_date BETWEEN {s:Date} AND {e:Date} AND platform != 'unpaid') AS paid_revenue,
          (SELECT sum(revenue) FROM fct_orders WHERE order_date BETWEEN {s:Date} AND {e:Date}) AS total_revenue,
          (SELECT count() FROM dim_customers WHERE acquisition_date BETWEEN {s:Date} AND {e:Date} AND acquisition_platform != 'unpaid') AS new_paid_customers,
          (SELECT sum(clicks) FROM fct_ad_daily WHERE date BETWEEN {s:Date} AND {e:Date}) AS clicks
    """
    cur = warehouse.query_df(q, {"s": start, "e": end}).iloc[0].fillna(0)
    days = (end - start).days + 1
    prv = warehouse.query_df(q, {"s": start - timedelta(days=days), "e": start - timedelta(days=1)}).iloc[0].fillna(0)

    def roas(r):
        return r["paid_revenue"] / r["spend"] if r["spend"] else 0.0

    def cac(r):
        return r["spend"] / r["new_paid_customers"] if r["new_paid_customers"] else 0.0

    return [
        Kpi("Ad spend", round(float(cur["spend"]), 2), round(float(prv["spend"]), 2), "money", "down"),
        Kpi("Paid revenue", round(float(cur["paid_revenue"]), 2), round(float(prv["paid_revenue"]), 2), "money"),
        Kpi("ROAS", round(roas(cur), 2), round(roas(prv), 2), "ratio"),
        Kpi("New paid customers", float(cur["new_paid_customers"]), float(prv["new_paid_customers"]), "int"),
        Kpi("Blended CAC", round(cac(cur), 2), round(cac(prv), 2), "money", "down"),
        Kpi("Total revenue", round(float(cur["total_revenue"]), 2), round(float(prv["total_revenue"]), 2), "money"),
    ]


def _ads(start: date, end: date) -> pd.DataFrame:
    return warehouse.query_df(
        """
        WITH sp AS (SELECT platform, ad_id, round(sum(spend), 2) AS ad_spend FROM fct_ad_daily
                    WHERE date BETWEEN {s:Date} AND {e:Date} GROUP BY platform, ad_id),
             cu AS (SELECT acquisition_platform AS platform, acquisition_ad_id AS ad_id, count() AS new_customers
                    FROM dim_customers WHERE acquisition_date BETWEEN {s:Date} AND {e:Date} GROUP BY platform, ad_id),
             lt AS (SELECT acquisition_platform AS platform, acquisition_ad_id AS ad_id,
                           round(avg(ltv), 2) AS avg_ltv FROM dim_customers
                    WHERE acquisition_platform != 'unpaid' GROUP BY platform, ad_id)
        SELECT d.ad_name AS ad_name, d.platform AS platform, d.campaign_name AS campaign_name,
               sp.ad_spend AS spend, cu.new_customers AS new_customers,
               round(sp.ad_spend / nullIf(cu.new_customers, 0), 2) AS cac, lt.avg_ltv AS avg_ltv,
               round(lt.avg_ltv / nullIf(cac, 0), 2) AS ltv_to_cac
        FROM sp JOIN dim_ads d ON d.platform = sp.platform AND d.ad_id = sp.ad_id
        LEFT JOIN cu ON cu.platform = sp.platform AND cu.ad_id = sp.ad_id
        LEFT JOIN lt ON lt.platform = sp.platform AND lt.ad_id = sp.ad_id
        ORDER BY ltv_to_cac DESC
        SETTINGS join_use_nulls = 1
        """, {"s": start, "e": end})


def _platform(start: date, end: date) -> pd.DataFrame:
    return warehouse.query_df(
        """
        SELECT s.platform AS platform, s.spend AS spend, r.revenue AS revenue, round(r.revenue / nullIf(s.spend, 0), 2) AS roas
        FROM (SELECT platform, round(sum(spend), 2) AS spend FROM fct_ad_daily
              WHERE date BETWEEN {s:Date} AND {e:Date} GROUP BY platform) s
        LEFT JOIN (SELECT platform, round(sum(revenue), 2) AS revenue FROM fct_orders
                   WHERE order_date BETWEEN {s:Date} AND {e:Date} GROUP BY platform) r ON r.platform = s.platform
        ORDER BY spend DESC
        """, {"s": start, "e": end})


def build(end: date | None = None, days: int = 7, llm: LLM | None = None) -> WeeklyReport:
    if end is None:
        end = warehouse.query_df("SELECT max(date) AS d FROM fct_ad_daily").iloc[0]["d"]
        end = pd.Timestamp(end).date()
    start = end - timedelta(days=days - 1)
    ads = _ads(start, end).dropna(subset=["ltv_to_cac"])
    ads = ads[ads["new_customers"] >= 3]
    audit_df = search_terms.audit(days)
    waste = search_terms.summary(audit_df)
    top_terms = audit_df[audit_df["flagged"]].head(5)[["search_term", "campaign_name", "cost", "intent",
                                                       "suggested_negative"]]
    pending = recs.latest("pending")
    rep = WeeklyReport(start, end, _kpis(start, end), ads.head(3), ads.sort_values("ltv_to_cac").head(3),
                       _platform(start, end), waste, top_terms, pending)
    rep.commentary = _template_commentary(rep)
    if llm is not None:
        try:
            rep.commentary, rep.commentary_source = _llm_commentary(rep, llm), "llm"
        except (LLMError, ValueError):
            pass
    return rep


def _template_commentary(r: WeeklyReport) -> list[str]:
    k = {x.label: x for x in r.kpis}
    out = []
    roas = k["ROAS"]
    if roas.change is not None:
        out.append(f"ROAS was {roas.text()} vs {roas.text(roas.prior)} the week before; "
                   f"spend {k['Ad spend'].text()} brought {k['New paid customers'].text()} new paid customers "
                   f"at {k['Blended CAC'].text()} CAC.")
    if not r.top_ads.empty:
        t = r.top_ads.iloc[0]
        out.append(f"Best customer economics: {t['ad_name']} (LTV:CAC {t['ltv_to_cac']:.2f}, CAC ${t['cac']:,.2f}).")
    if not r.worst_ads.empty:
        w = r.worst_ads.iloc[0]
        out.append(f"Weakest: {w['ad_name']} (LTV:CAC {w['ltv_to_cac']:.2f}, CAC ${w['cac']:,.2f}). Review for pause.")
    if r.waste["flagged"]:
        out.append(f"{r.waste['flagged']} search terms with no buyer intent cost ${r.waste['wasted_spend']:,.2f} "
                   f"this week. Negative keywords are waiting for approval.")
    return out


def _llm_commentary(r: WeeklyReport, llm: LLM) -> list[str]:
    facts = pd.concat([
        pd.DataFrame([{"metric": k.label, "this_week": k.value, "prior_week": k.prior} for k in r.kpis]),
        r.top_ads.assign(group="top_ads"), r.worst_ads.assign(group="worst_ads"),
        pd.DataFrame([{"metric": "wasted_search_spend", "this_week": r.waste["wasted_spend"],
                       "prior_week": None, "flagged_terms": r.waste["flagged"]}]),
    ], ignore_index=True)
    out = llm.structured(
        system=("You write the commentary for a weekly paid-media report read by a busy head of growth. "
                "3-4 crisp bullets: what changed, which ads to pause or scale, wasted search spend. "
                "Quote only numbers present in the data; declare any derived number (e.g. a % change) in "
                "`computations` with its arithmetic. Actions are proposals needing human approval."),
        user=f"Week {r.period_start} to {r.period_end}. Data:\n{facts.to_csv(index=False)}",
        schema=Commentary, step="weekly_commentary")
    checks = verify_numbers("\n".join(out.bullets), facts,
                            computations=[(c.quoted, c.expression) for c in out.computations])
    if not all(c.verified for c in checks):
        raise ValueError("commentary quoted unverified numbers")
    return out.bullets


# ------------------------------------------------------------------ rendering
def _arrow(k: Kpi) -> str:
    if k.change is None or abs(k.change) < 0.005:
        return "–"
    icon = "▲" if k.change > 0 else "▼"
    return f"{icon} {abs(k.change):.0%}"


def to_markdown(r: WeeklyReport) -> str:
    lines = [f"# AdPulse weekly report: {r.period_start:%b %d} – {r.period_end:%b %d, %Y}", "",
             "| Metric | This week | Prior week | Change |", "|---|---:|---:|---:|"]
    lines += [f"| {k.label} | {k.text()} | {k.text(k.prior)} | {_arrow(k)} |" for k in r.kpis]
    lines += ["", "## Summary", *[f"- {c}" for c in r.commentary], ""]
    if not r.top_ads.empty:
        lines += ["## Scale candidates (best LTV:CAC)"]
        lines += [f"- **{a.ad_name}** ({a.platform}): CAC ${a.cac:,.2f}, avg LTV ${a.avg_ltv:,.2f}, "
                  f"LTV:CAC {a.ltv_to_cac:.2f}" for a in r.top_ads.itertuples()]
    if not r.worst_ads.empty:
        lines += ["", "## Pause candidates (worst LTV:CAC)"]
        lines += [f"- **{a.ad_name}** ({a.platform}): CAC ${a.cac:,.2f}, avg LTV ${a.avg_ltv:,.2f}, "
                  f"LTV:CAC {a.ltv_to_cac:.2f}" for a in r.worst_ads.itertuples()]
    lines += ["", (f"## Search term waste: ${r.waste['wasted_spend']:,.2f} on {r.waste['flagged']} terms "
                   f"({r.waste['wasted_share']:.0%} of search spend)")]
    lines += [f"- `{t.search_term}` (${t.cost:,.2f}, {t.intent}) → negative {t.suggested_negative}"
              for t in r.top_waste_terms.itertuples()]
    lines += ["", f"**{len(r.pending)} recommendation(s) awaiting approval.** Nothing changes until a human approves."]
    return "\n".join(lines)


def to_slack_blocks(r: WeeklyReport, app_url: str = "") -> list[dict]:
    kpi_fields = [{"type": "mrkdwn", "text": f"*{k.label}*\n{k.text()}  {_arrow(k)}"} for k in r.kpis]
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": f"📊 AdPulse weekly · {r.period_start:%b %d} – {r.period_end:%b %d}"}},
        {"type": "section", "fields": kpi_fields[:6]},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Summary*\n" + "\n".join(f"• {c}" for c in r.commentary)}},
    ]
    if not r.top_ads.empty:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*🚀 Scale candidates*\n" + "\n".join(
            f"• *{a.ad_name}*: LTV:CAC {a.ltv_to_cac:.2f}, CAC ${a.cac:,.2f}" for a in r.top_ads.itertuples())}})
    if not r.worst_ads.empty:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*⏸ Pause candidates*\n" + "\n".join(
            f"• *{a.ad_name}*: LTV:CAC {a.ltv_to_cac:.2f}, CAC ${a.cac:,.2f}" for a in r.worst_ads.itertuples())}})
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
                   f"*🔎 Search term waste:* ${r.waste['wasted_spend']:,.2f} on {r.waste['flagged']} terms with no buyer intent"}})
    ctx = f"{len(r.pending)} recommendation(s) awaiting human approval · no changes are made automatically"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": ctx}]})
    if app_url:
        blocks.append({"type": "actions", "elements": [{"type": "button", "style": "primary",
                       "text": {"type": "plain_text", "text": "Review in AdPulse"},
                       "url": f"{app_url.rstrip('/')}/recommendations"}]})
    return blocks


def to_html(r: WeeklyReport) -> str:
    rows = "".join(
        f"<tr><td>{k.label}</td><td align=right><b>{k.text()}</b></td><td align=right>{k.text(k.prior)}</td>"
        f"<td align=right style='color:{'#15803d' if k.good else '#b91c1c' if k.good is False else '#555'}'>{_arrow(k)}</td></tr>"
        for k in r.kpis)
    bullets = "".join(f"<li>{c}</li>" for c in r.commentary)
    return f"""<div style="font-family:Inter,Segoe UI,Arial,sans-serif;max-width:640px;color:#111">
<h2 style="margin:0 0 4px">AdPulse weekly report</h2>
<div style="color:#666;margin-bottom:16px">{r.period_start:%b %d} – {r.period_end:%b %d, %Y}</div>
<table cellpadding=6 style="border-collapse:collapse;width:100%;border:1px solid #eee">
<tr style="background:#f6f6f8"><th align=left>Metric</th><th align=right>This week</th><th align=right>Prior</th><th align=right>Δ</th></tr>
{rows}</table><h3>Summary</h3><ul>{bullets}</ul>
<p><b>{len(r.pending)}</b> recommendation(s) awaiting approval. Nothing changes until a human approves.</p></div>"""


def save(r: WeeklyReport, channels: list[str], status: str) -> None:
    payload = {"kpis": [asdict(k) for k in r.kpis], "commentary": r.commentary, "waste": r.waste,
               "commentary_source": r.commentary_source}
    warehouse.admin().insert(
        "app_reports",
        [[r.id, datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0), r.period_start, r.period_end,
          json.dumps(payload, default=str), to_markdown(r), ",".join(channels), status]],
        column_names=["id", "created_at", "period_start", "period_end", "payload", "markdown", "channels", "status"])


def history(limit: int = 20) -> pd.DataFrame:
    return warehouse.query_df("SELECT id, created_at, period_start, period_end, channels, status, markdown "
                              "FROM app_reports ORDER BY created_at DESC LIMIT {n:UInt32}", {"n": limit})


def deliver(r: WeeklyReport, slack: bool = True, email: bool = True) -> dict[str, str]:
    from . import delivery
    s = get_settings()
    results: dict[str, str] = {}
    if slack:
        results["slack"] = delivery.send_slack(r, s) if s.slack_configured else "skipped: Slack not configured"
    if email:
        results["email"] = delivery.send_email(r, s) if s.email_configured else "skipped: email not configured"
    sent = [k for k, v in results.items() if v == "sent"]
    failed = [k for k, v in results.items() if v.startswith("error")]
    save(r, sent, "failed" if failed and not sent else ("sent" if sent else "generated"))
    return results
