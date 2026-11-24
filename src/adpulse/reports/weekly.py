"""Weekly performance report.

All numbers come from fixed SQL (no LLM math). When an LLM is configured, it writes a short
"what to do" commentary that must pass the same number verification as chat answers;
otherwise a template summary is used.
"""
from __future__ import annotations

import html
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from pydantic import BaseModel, Field

from .. import plain, warehouse
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
    better: str = "up"  # up | down | neutral

    @property
    def change(self) -> float | None:
        return None if not self.prior else (self.value - self.prior) / abs(self.prior)

    def text(self, v: float | None = None) -> str:
        v = self.value if v is None else v
        return {"money": f"${v:,.2f}", "int": f"{v:,.0f}", "ratio": f"{v:.2f}x", "pct": f"{v:.1%}",
                "perdollar": f"${v:.2f}"}[self.fmt]

    @property
    def good(self) -> bool | None:
        c = self.change
        if c is None or abs(c) < 0.005 or self.better == "neutral":
            return None  # e.g. more ad spend is neither good nor bad on its own
        return (c > 0) == (self.better == "up")


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


SPEND, SALES, BACK = plain.label("spend"), plain.label("paid_revenue"), plain.label("roas")
NEW, COST, ALL_SALES = plain.label("new_customers"), plain.label("cac"), plain.label("total_revenue")


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
        Kpi(SPEND, round(float(cur["spend"]), 2), round(float(prv["spend"]), 2), "money", "neutral"),
        Kpi(SALES, round(float(cur["paid_revenue"]), 2), round(float(prv["paid_revenue"]), 2), "money"),
        Kpi(BACK, round(roas(cur), 2), round(roas(prv), 2), "perdollar"),
        Kpi(NEW, float(cur["new_paid_customers"]), float(prv["new_paid_customers"]), "int"),
        Kpi(COST, round(cac(cur), 2), round(cac(prv), 2), "money", "down"),
        Kpi(ALL_SALES, round(float(cur["total_revenue"]), 2), round(float(prv["total_revenue"]), 2), "money"),
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
    back = k[BACK]
    if back.change is not None:
        out.append(f"Your ads brought back {back.text()} for every $1 spent (the week before: "
                   f"{back.text(back.prior)}). You spent {k[SPEND].text()} and won {k[NEW].text()} new customers "
                   f"at {k[COST].text()} each.")
    if not r.top_ads.empty:
        t = r.top_ads.iloc[0]
        out.append(f"Best ad: {t['ad_name']}. Each new customer costs ${t['cac']:,.2f} and is worth "
                   f"{t['ltv_to_cac']:.1f}× that.")
    if not r.worst_ads.empty:
        w = r.worst_ads.iloc[0]
        out.append(f"Weakest ad: {w['ad_name']}. Each new customer costs ${w['cac']:,.2f} but is only worth "
                   f"{w['ltv_to_cac']:.1f}× that. Worth pausing.")
    if r.waste["flagged"]:
        out.append(f"{r.waste['flagged']} Google searches from people who weren't going to buy cost "
                   f"${r.waste['wasted_spend']:,.2f}. Blocking them is waiting for your approval.")
    return out


def _llm_commentary(r: WeeklyReport, llm: LLM) -> list[str]:
    parts = [
        pd.DataFrame([{"metric": k.label, "this_week": k.value, "prior_week": k.prior} for k in r.kpis]),
        r.top_ads.assign(group="top_ads"), r.worst_ads.assign(group="worst_ads"),
        pd.DataFrame([{"metric": "wasted_search_spend", "this_week": float(r.waste["wasted_spend"]),
                       "flagged_terms": r.waste["flagged"]}]),
    ]
    # skip empty frames and all-NA columns so pandas doesn't warn about dtype inference
    facts = pd.concat([p.dropna(axis=1, how="all") for p in parts if not p.empty], ignore_index=True)
    out = llm.structured(
        system=("You write the summary for a weekly ad report read by a busy business owner.\n"
                + plain.WRITING_RULES + "\n"
                "Write 3-4 short bullets: how the money did this week, which ad deserves more budget, which ad to "
                "consider pausing, and money wasted on Google searches from non-buyers. One sentence each. "
                "Quote only numbers present in the data; declare any derived number (e.g. a % change) in "
                "`computations` with its arithmetic. Changes are suggestions a person approves; never say "
                "anything was changed."),
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


def _ad_line(a, md: bool = True) -> str:
    name = f"**{a.ad_name}**" if md else f"*{a.ad_name}*"
    link = "and is worth" if a.ltv_to_cac >= 1 else "but is only worth"
    return (f"{name} ({str(a.platform).title()}): each new customer costs ${a.cac:,.2f} {link} "
            f"${a.avg_ltv:,.2f}, {a.ltv_to_cac:.1f}× the cost")


def _waste_title(r: WeeklyReport) -> str:
    return (f"Wasted Google searches: ${r.waste['wasted_spend']:,.2f} on {r.waste['flagged']} searches "
            f"({r.waste['wasted_share']:.0%} of search spend)")


def _pending_line(r: WeeklyReport) -> str:
    return f"{len(r.pending)} suggestion(s) waiting for your approval. Nothing changes until someone approves."


def to_markdown(r: WeeklyReport) -> str:
    lines = [f"# AdPulse weekly report: {r.period_start:%b %d} – {r.period_end:%b %d, %Y}", "",
             "| | This week | Week before | Change |", "|---|---:|---:|---:|"]
    lines += [f"| {k.label} | {k.text()} | {k.text(k.prior)} | {_arrow(k)} |" for k in r.kpis]
    lines += ["", "## Summary", *[f"- {c}" for c in r.commentary], ""]
    if not r.top_ads.empty:
        lines += ["## Ads worth more budget", *[f"- {_ad_line(a)}" for a in r.top_ads.itertuples()]]
    if not r.worst_ads.empty:
        lines += ["", "## Ads losing money", *[f"- {_ad_line(a)}" for a in r.worst_ads.itertuples()]]
    lines += ["", f"## {_waste_title(r)}"]
    lines += [f"- `{t.search_term}` cost ${t.cost:,.2f} ({plain.intent(t.intent).lower()}): block {t.suggested_negative}"
              for t in r.top_waste_terms.itertuples()]
    lines += ["", f"**{_pending_line(r)}**"]
    return "\n".join(lines)


def to_slack_blocks(r: WeeklyReport, app_url: str = "") -> list[dict]:
    kpi_fields = [{"type": "mrkdwn", "text": f"*{k.label}*\n{k.text()}  {_arrow(k)}"} for k in r.kpis]
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": f"📊 AdPulse weekly report: {r.period_start:%b %d} – {r.period_end:%b %d}"}},
        {"type": "section", "fields": kpi_fields[:6]},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Summary*\n" + "\n".join(f"• {c}" for c in r.commentary)}},
    ]
    if not r.top_ads.empty:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*🟢 Ads worth more budget*\n" + "\n".join(
            f"• {_ad_line(a, md=False)}" for a in r.top_ads.itertuples())}})
    if not r.worst_ads.empty:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*🔴 Ads losing money*\n" + "\n".join(
            f"• {_ad_line(a, md=False)}" for a in r.worst_ads.itertuples())}})
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*🔎 {_waste_title(r)}*"}})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": _pending_line(r)}]})
    if app_url:
        blocks.append({"type": "actions", "elements": [{"type": "button", "style": "primary",
                       "text": {"type": "plain_text", "text": "Review suggestions"},
                       "url": f"{app_url.rstrip('/')}/recommendations"}]})
    return blocks


def to_html(r: WeeklyReport, app_url: str = "") -> str:
    """Email-safe HTML (tables + inline styles: renders in Gmail, Outlook, Apple Mail)."""
    e = html.escape
    font = "font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif"

    def delta(k: Kpi) -> str:
        color = "#067647" if k.good else "#b42318" if k.good is False else "#667085"
        bg = "#ecfdf3" if k.good else "#fef3f2" if k.good is False else "#f2f4f7"
        return (f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;"
                f"font-weight:600;color:{color};background:{bg}'>{e(_arrow(k))}</span>")

    kpi_rows = "".join(
        f"<tr><td style='padding:10px 12px;border-top:1px solid #eef0f3;color:#344054'>{e(k.label)}</td>"
        f"<td align='right' style='padding:10px 12px;border-top:1px solid #eef0f3;font-weight:700;color:#0f1419'>{e(k.text())}</td>"
        f"<td align='right' style='padding:10px 12px;border-top:1px solid #eef0f3;color:#667085'>{e(k.text(k.prior))}</td>"
        f"<td align='right' style='padding:10px 12px;border-top:1px solid #eef0f3'>{delta(k)}</td></tr>"
        for k in r.kpis)

    def ad_list(df: pd.DataFrame, accent: str) -> str:
        return "".join(
            f"<tr><td style='padding:8px 12px;border-left:3px solid {accent};background:#fafbfc'>"
            f"<b style='color:#0f1419'>{e(str(a.ad_name))}</b> <span style='color:#667085'>· {e(str(a.platform).title())}</span><br>"
            f"<span style='color:#475467;font-size:13px'>Each new customer costs ${a.cac:,.2f} "
            f"{'and is worth' if a.ltv_to_cac >= 1 else 'but is only worth'} "
            f"${a.avg_ltv:,.2f}, <b>{a.ltv_to_cac:.1f}×</b> the cost</span></td></tr><tr><td style='height:6px'></td></tr>"
            for a in df.itertuples())

    def block(title: str, body: str) -> str:
        return (f"<tr><td style='padding:22px 28px 0'><div style='font-size:15px;font-weight:700;color:#0f1419;"
                f"margin-bottom:10px'>{e(title)}</div>{body}</td></tr>")

    parts = [block("Summary", "<ul style='margin:0;padding-left:18px;color:#344054;line-height:1.6'>"
                   + "".join(f"<li>{e(c)}</li>" for c in r.commentary) + "</ul>")]
    if not r.top_ads.empty:
        parts.append(block("Ads worth more budget",
                           f"<table width='100%' cellpadding='0' cellspacing='0'>{ad_list(r.top_ads, '#12b76a')}</table>"))
    if not r.worst_ads.empty:
        parts.append(block("Ads losing money",
                           f"<table width='100%' cellpadding='0' cellspacing='0'>{ad_list(r.worst_ads, '#f04438')}</table>"))
    terms = "".join(
        f"<tr><td style='padding:7px 0;border-top:1px solid #eef0f3;color:#344054'>{e(str(t.search_term))}"
        f" <span style='color:#667085;font-size:12px'>({e(plain.intent(str(t.intent)).lower())})</span></td>"
        f"<td align='right' style='padding:7px 0;border-top:1px solid #eef0f3;color:#b42318;font-weight:600'>${t.cost:,.2f}</td>"
        f"<td align='right' style='padding:7px 0 7px 10px;border-top:1px solid #eef0f3;color:#475467;font-size:12px'>"
        f"block {e(str(t.suggested_negative))}</td></tr>" for t in r.top_waste_terms.itertuples())
    parts.append(block(
        _waste_title(r),
        f"<table width='100%' cellpadding='0' cellspacing='0' style='font-size:14px'>{terms}</table>"))
    cta = (f"<a href='{e(app_url.rstrip('/'))}/recommendations' style='display:inline-block;background:#2a78d6;"
           f"color:#ffffff;text-decoration:none;font-weight:600;padding:11px 20px;border-radius:10px'>"
           f"Review {len(r.pending)} suggestion(s)</a>") if app_url else ""
    source = ("Summary written by AI, every number checked against your data" if r.commentary_source == "llm"
              else "Summary built from your data")

    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;padding:0;background:#f4f5f7">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;{font}"><tr><td align="center" style="padding:24px 12px">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border:1px solid #e6e8ec;border-radius:16px;overflow:hidden;{font};font-size:14px">
<tr><td style="background:linear-gradient(120deg,#2a78d6,#5b5bd6);background-color:#2a78d6;padding:22px 28px;color:#ffffff">
  <div style="font-size:13px;opacity:.85;">AdPulse weekly report</div>
  <div style="font-size:22px;font-weight:700;margin-top:4px">{r.period_start:%b %d} – {r.period_end:%b %d, %Y}</div></td></tr>
<tr><td style="padding:20px 28px 0"><table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eef0f3;border-radius:12px;font-size:14px">
  <tr style="background:#f8f9fb"><th align="left" style="padding:9px 12px;color:#667085;font-size:12px;">&nbsp;</th>
  <th align="right" style="padding:9px 12px;color:#667085;font-size:12px">This week</th>
  <th align="right" style="padding:9px 12px;color:#667085;font-size:12px">Week before</th>
  <th align="right" style="padding:9px 12px;color:#667085;font-size:12px">Change</th></tr>{kpi_rows}</table></td></tr>
{"".join(parts)}
<tr><td style="padding:24px 28px">
  <div style="background:#fffaeb;border:1px solid #fedf89;border-radius:12px;padding:12px 14px;color:#7a2e0e">
  <b>{len(r.pending)} suggestion(s) waiting for your approval.</b> Nothing changes in your ad accounts until someone approves.</div>
  <div style="margin-top:16px">{cta}</div></td></tr>
<tr><td style="padding:14px 28px;border-top:1px solid #eef0f3;color:#98a2b3;font-size:12px">
  {source}. Sent by AdPulse.</td></tr>
</table></td></tr></table></body></html>"""


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
    sent = [k for k, v in results.items() if v.startswith("sent")]
    failed = [k for k, v in results.items() if v.startswith("error")]
    save(r, sent, "failed" if failed and not sent else ("sent" if sent else "generated"))
    return results
