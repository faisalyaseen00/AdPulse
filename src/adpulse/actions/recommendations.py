"""Pause / scale / negative-keyword recommendations with a human approval gate.

AdPulse never changes spend on its own. Rules (and the agent / audit) create *pending*
recommendations; a person approves or rejects each one in the UI. Approving one produces the
exact change payload to apply in Meta / Google Ads. Marking it *applied* is a separate, explicit step.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from .. import warehouse
from ..config import get_settings

STATUSES = ("pending", "approved", "rejected", "applied")
SCALE_STEP = 0.20  # suggested budget increase


@dataclass
class Rec:
    kind: str
    platform: str
    entity_id: str
    entity_name: str
    campaign_name: str
    reason: str
    metrics: dict
    est_impact: float
    source: str = "rules"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def ad_economics(window_days: int = 30) -> pd.DataFrame:
    """Recent spend/CAC per ad vs. the LTV its customers historically reach."""
    return warehouse.query_df(
        """
        WITH (SELECT max(date) FROM fct_ad_daily) AS end_date,
        recent AS (
            SELECT platform, ad_id, round(sum(spend), 2) AS spend_window, sum(clicks) AS clicks_window
            FROM fct_ad_daily WHERE date > end_date - {w:UInt32}
            GROUP BY platform, ad_id
        ),
        acq AS (
            SELECT acquisition_platform AS platform, acquisition_ad_id AS ad_id,
                   countIf(acquisition_date > end_date - {w:UInt32}) AS new_customers_window,
                   count() AS customers_all,
                   round(avg(ltv), 2) AS avg_ltv_all,
                   round(avgIf(ltv_90d, customer_age_days >= 90), 2) AS avg_ltv_90d_mature
            FROM dim_customers WHERE acquisition_platform != 'unpaid'
            GROUP BY platform, ad_id
        ),
        rev AS (
            SELECT platform, ad_id, round(sum(revenue), 2) AS revenue_window
            FROM fct_orders WHERE order_date > end_date - {w:UInt32} AND platform != 'unpaid'
            GROUP BY platform, ad_id
        )
        SELECT d.platform AS platform, d.ad_id AS ad_id, d.ad_name AS ad_name, d.campaign_name AS campaign_name,
               r.spend_window AS spend_window, r.clicks_window AS clicks_window,
               a.new_customers_window AS new_customers_window, a.customers_all AS customers_all,
               a.avg_ltv_all AS avg_ltv_all,
               if(a.avg_ltv_90d_mature > 0, a.avg_ltv_90d_mature, a.avg_ltv_all) AS ltv_estimate,
               v.revenue_window AS revenue_window,
               round(r.spend_window / nullIf(a.new_customers_window, 0), 2) AS cac_window,
               round(v.revenue_window / nullIf(r.spend_window, 0), 3) AS roas_window,
               round(ltv_estimate / nullIf(cac_window, 0), 2) AS ltv_to_cac
        FROM recent r
        JOIN dim_ads d ON d.platform = r.platform AND d.ad_id = r.ad_id
        LEFT JOIN acq a ON a.platform = r.platform AND a.ad_id = r.ad_id
        LEFT JOIN rev v ON v.platform = r.platform AND v.ad_id = r.ad_id
        WHERE r.spend_window > 0
        ORDER BY spend_window DESC
        SETTINGS join_use_nulls = 1
        """,
        {"w": window_days},
    )


def rule_recommendations(window_days: int = 30) -> list[Rec]:
    s = get_settings()
    recs: list[Rec] = []
    for r in ad_economics(window_days).to_dict("records"):
        spend = float(r["spend_window"] or 0)
        if spend < s.min_spend_for_decision:
            continue
        new_c = int(r["new_customers_window"] or 0)
        cac = r["cac_window"]
        ratio = r["ltv_to_cac"]
        roas = r["roas_window"]
        metrics = {k: (None if pd.isna(v) else (float(v) if isinstance(v, (int, float)) else v))
                   for k, v in r.items() if k not in ("platform", "ad_id", "ad_name", "campaign_name")}
        metrics["window_days"] = window_days
        if new_c == 0:
            recs.append(Rec("pause_ad", r["platform"], r["ad_id"], r["ad_name"], r["campaign_name"],
                            f"Spent ${spend:,.2f} in the last {window_days} days without winning a single new "
                            "customer.", metrics, spend))
        elif ratio is not None and not pd.isna(ratio) and ratio < 1.0 and cac > s.target_cac:
            recs.append(Rec("pause_ad", r["platform"], r["ad_id"], r["ad_name"], r["campaign_name"],
                            f"Each new customer costs ${cac:,.2f} to win (your target is ${s.target_cac:,.0f}) "
                            f"but only spends about ${r['ltv_estimate']:,.2f}. You lose money on every customer "
                            "this ad brings in.",
                            metrics, spend))
        elif (ratio is not None and not pd.isna(ratio) and ratio >= 2.5 and cac <= s.target_cac
              and roas is not None and not pd.isna(roas) and roas >= s.target_roas * 0.5):
            extra = spend * SCALE_STEP
            value = extra / cac * float(r["ltv_estimate"]) - extra
            recs.append(Rec("scale_ad", r["platform"], r["ad_id"], r["ad_name"], r["campaign_name"],
                            f"Each new customer costs only ${cac:,.2f} and is worth about "
                            f"${r['ltv_estimate']:,.2f}, {ratio:.1f}× what they cost. Try "
                            f"{int(SCALE_STEP * 100)}% more budget and keep an eye on the cost per customer.",
                            metrics, round(value, 2)))
    return recs


def audit_recommendations(audit_df: pd.DataFrame, terms: list[str] | None = None) -> list[Rec]:
    flagged = audit_df[audit_df["flagged"]]
    if terms is not None:
        flagged = flagged[flagged["search_term"].isin(terms)]
    recs = []
    for r in flagged.to_dict("records"):
        recs.append(Rec("negative_keyword", "google", f"{r['ad_group_name']}|{r['search_term']}",
                        r["search_term"], r["campaign_name"],
                        f"{r['reason']}. These clicks cost ${r['cost']:,.2f} and led to {r['conversions']:.0f} "
                        f"sales. Stop showing ads for {r['suggested_negative']} in '{r['ad_group_name']}'.",
                        {"clicks": int(r["clicks"]), "cost": float(r["cost"]), "conversions": float(r["conversions"]),
                         "intent": r["intent"], "suggested_negative": r["suggested_negative"],
                         "ad_group_name": r["ad_group_name"]},
                        float(r["cost"]), source="audit"))
    return recs


def latest(status: str | None = None) -> pd.DataFrame:
    sql = "SELECT * FROM app_recommendations FINAL"
    params = {}
    if status:
        sql += " WHERE status = {st:String}"
        params["st"] = status
    df = warehouse.query_df(sql + " ORDER BY created_at DESC, est_impact DESC", params)
    if not df.empty:
        df["metrics"] = df["metrics"].map(json.loads)
    return df


def save(recs: list[Rec]) -> int:
    """Insert new pending recommendations, skipping ones already pending for the same entity."""
    if not recs:
        return 0
    pending = latest("pending")
    open_keys = set(zip(pending["kind"], pending["entity_id"])) if not pending.empty else set()
    rows = []
    now = _now()
    for r in recs:
        if (r.kind, r.entity_id) in open_keys:
            continue
        open_keys.add((r.kind, r.entity_id))
        rows.append([uuid.uuid4().hex[:12], now, r.kind, r.platform, r.entity_id, r.entity_name, r.campaign_name,
                     r.reason, json.dumps(r.metrics, default=str), float(r.est_impact), "pending", "", None, "",
                     r.source, 1])
    if rows:
        warehouse.admin().insert("app_recommendations", rows, column_names=[
            "id", "created_at", "kind", "platform", "entity_id", "entity_name", "campaign_name", "reason",
            "metrics", "est_impact", "status", "decided_by", "decided_at", "note", "source", "version"])
    return len(rows)


def refresh_pending(window_days: int = 30) -> int:
    """Rebuild suggestions still waiting for a decision (rule and audit ones) so their wording and numbers are
    current. Decided suggestions and ones added from chat are left alone. Returns how many are pending after."""
    from ..audit import search_terms

    pending = latest("pending")
    if not pending.empty:
        stale = pending[pending.source.isin(["rules", "audit"])]
        terms = stale[stale.source == "audit"].entity_name.tolist()
        if not stale.empty:
            ids = ", ".join(f"'{i}'" for i in stale.id if str(i).isalnum())
            warehouse.command(f"ALTER TABLE app_recommendations DELETE WHERE id IN ({ids}) "
                              "SETTINGS mutations_sync = 2")
        if terms:
            save(audit_recommendations(search_terms.audit(window_days, llm=None), terms))
    save(rule_recommendations(window_days))
    return len(latest("pending"))


def decide(rec_id: str, status: str, by: str, note: str = "") -> None:
    if status not in STATUSES[1:]:
        raise ValueError(f"invalid status {status}")
    if not by.strip():
        raise ValueError("a reviewer name is required to approve or reject")
    cur = warehouse.query_df("SELECT * FROM app_recommendations FINAL WHERE id = {id:String}", {"id": rec_id})
    if cur.empty:
        raise KeyError(rec_id)
    row = cur.iloc[0].to_dict()
    allowed = {"pending": {"approved", "rejected"}, "approved": {"applied", "rejected"}}
    if status not in allowed.get(row["status"], set()):
        raise ValueError(f"cannot move a {row['status']} recommendation to {status}")
    row.update(status=status, decided_by=by.strip(), decided_at=_now(), note=note, version=int(row["version"]) + 1)
    cols = list(cur.columns)
    warehouse.admin().insert("app_recommendations", [[row[c] for c in cols]], column_names=cols)


def change_payload(rec: dict) -> dict:
    """The exact change a human applies in the ad platform (or a future executor would send)."""
    m = rec["metrics"] if isinstance(rec["metrics"], dict) else json.loads(rec["metrics"])
    if rec["kind"] == "pause_ad" and rec["platform"] == "meta":
        return {"api": "Meta Marketing API", "method": "POST", "endpoint": f"/{rec['entity_id']}",
                "body": {"status": "PAUSED"}}
    if rec["kind"] == "pause_ad":
        return {"api": "Google Ads API", "operation": "AdGroupAdOperation.update",
                "resource": f"customers/{{customer_id}}/adGroupAds/{{ad_group_id}}~{rec['entity_id']}",
                "update": {"status": "PAUSED"}, "update_mask": "status"}
    if rec["kind"] == "scale_ad":
        return {"api": "Meta Marketing API" if rec["platform"] == "meta" else "Google Ads API",
                "change": f"increase daily budget by {int(SCALE_STEP * 100)}%",
                "current_spend_window": m.get("spend_window"), "window_days": m.get("window_days")}
    if rec["kind"] == "negative_keyword":
        neg = m.get("suggested_negative", "")
        match = "PHRASE" if neg.startswith('"') else "EXACT"
        return {"api": "Google Ads API", "operation": "AdGroupCriterionOperation.create",
                "ad_group": m.get("ad_group_name"), "criterion": {"negative": True,
                                                                  "keyword": {"text": neg.strip('"[]'),
                                                                              "match_type": match}}}
    return {}
