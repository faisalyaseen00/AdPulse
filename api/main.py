"""AdPulse HTTP API for the React frontend.

A thin layer only: every endpoint calls the existing `adpulse` package (src/adpulse) unchanged. The SQL that used
to live inside the Streamlit pages (overview, data status) is moved here as-is, so the numbers match.

Run locally:  .venv/bin/uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import math
import os
import threading
import time
import uuid
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from adpulse import plain, warehouse
from adpulse.actions import recommendations as recs
from adpulse.agent.core import AdPulseAgent, AgentAnswer, Turn
from adpulse.audit import search_terms
from adpulse.config import get_settings
from adpulse.llm import LLMError, get_llm
from adpulse.pipeline import demo_data, ingest, transform
from adpulse.reports import weekly
from adpulse.scheduler import Schedule

load_dotenv()  # local runs: pick up ADPULSE_CORS_* from .env (hosts set real environment variables)
app = FastAPI(title="AdPulse API", version="1.0")

# The web app runs on another origin (Vite in development, Vercel in production).
#   ADPULSE_CORS_ORIGINS  comma-separated exact origins, e.g. https://adpulse.example.com
#   ADPULSE_CORS_REGEX    pattern for preview deployments; defaults to this project's *.vercel.app URLs
_origins = [o.strip() for o in os.environ.get(
    "ADPULSE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins,
                   allow_origin_regex=os.environ.get("ADPULSE_CORS_REGEX", r"https://adpulse[a-z0-9-]*\.vercel\.app"),
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.get("/healthz", include_in_schema=False)
def healthz():
    """Liveness for the host's health check: the process is up. Does not touch the database."""
    return {"ok": True}


# ------------------------------------------------------------------------------------------- helpers
def clean(v: Any) -> Any:
    """Make pandas / numpy values JSON-safe (NaN -> None, dates -> ISO strings)."""
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, pd.DataFrame):
        return [clean(r) for r in v.to_dict(orient="records")]
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return None if pd.isna(v) else v.isoformat()
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if v is pd.NaT:
        return None
    return v


def q(sql: str, **params) -> pd.DataFrame:
    return warehouse.query_df(sql, params)


class _TTL:
    """Tiny in-process cache, like st.cache_data(ttl=...) in the old pages."""

    def __init__(self):
        self._d: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key, ttl: float, fn):
        now = time.time()
        with self._lock:
            hit = self._d.get(key)
            if hit and now - hit[0] < ttl:
                return hit[1]
        val = fn()
        with self._lock:
            self._d[key] = (now, val)
        return val

    def clear(self):
        with self._lock:
            self._d.clear()


cache = _TTL()


def econ(window: int) -> pd.DataFrame:
    return cache.get(("econ", window), 300, lambda: recs.ad_economics(window))


def llm_or_none():
    try:
        return get_llm() if get_settings().llm_configured else None
    except LLMError:
        return None


@lru_cache(maxsize=1)
def agent() -> AdPulseAgent:
    return AdPulseAgent(get_llm())


def money(x: float, decimals: int = 0) -> str:
    return f"${x:,.{decimals}f}"


# ------------------------------------------------------------------------------------------- status
@app.get("/api/health")
def health():
    s = get_settings()
    h = cache.get("health", 30, warehouse.health)
    if not h.ok:
        cache._d.pop("health", None)  # never cache an outage
    out = {"warehouse": h.ok, "warehouse_error": "" if h.ok else "Can't reach the database",
           "ai": s.llm_configured, "slack": s.slack_configured, "email": s.email_configured,
           "data_until": None, "pending": 0}
    if h.ok:
        try:
            out["data_until"] = clean(q("SELECT max(date) AS d FROM fct_ad_daily").iloc[0]["d"])
            out["pending"] = int((recs.latest().status == "pending").sum())
        except Exception:  # noqa: BLE001, S110  (empty warehouse: the pages explain it)
            pass
    return out


@app.get("/api/glossary")
def glossary():
    keys = ["spend", "paid_revenue", "roas", "new_customers", "cac", "ltv", "ltv90", "ltv_to_cac",
            "impressions", "clicks", "ctr", "sessions"]
    return [{"key": k, "label": plain.label(k), "explain": plain.explain(k)} for k in keys]


# ------------------------------------------------------------------------------------------- overview
def _chg(a, b):
    a, b = float(a or 0), float(b or 0)
    return (a - b) / b if b else None


@app.get("/api/overview")
def overview(days: int = Query(30, ge=1, le=365)):
    return cache.get(("overview", days), 300, lambda: _overview(days))


def _overview(window: int):
    s = get_settings()
    k = q("""
        WITH (SELECT max(date) FROM fct_ad_daily) AS e, toUInt32({w:UInt32}) AS w
        SELECT
          sumIf(spend, date > e - w) AS spend_cur, sumIf(spend, date <= e - w AND date > e - 2*w) AS spend_p,
          sumIf(clicks, date > e - w) AS clicks_cur, sumIf(impressions, date > e - w) AS impressions_cur,
          (SELECT sumIf(revenue, order_date > e - w) FROM fct_orders WHERE platform != 'unpaid') AS rev,
          (SELECT sumIf(revenue, order_date <= e - w AND order_date > e - 2*w) FROM fct_orders WHERE platform != 'unpaid') AS rev_p,
          (SELECT countIf(acquisition_date > e - w) FROM dim_customers WHERE acquisition_platform != 'unpaid') AS cust,
          (SELECT countIf(acquisition_date <= e - w AND acquisition_date > e - 2*w) FROM dim_customers WHERE acquisition_platform != 'unpaid') AS cust_p,
          (SELECT countIf(session_date > e - w) FROM fct_sessions WHERE platform != 'unpaid') AS sessions,
          (SELECT round(avgIf(ltv_90d, customer_age_days >= 90), 2) FROM dim_customers WHERE acquisition_platform != 'unpaid') AS ltv90,
          e AS end_date
        FROM fct_ad_daily
    """, w=window).iloc[0].rename({"spend_cur": "spend", "clicks_cur": "clicks", "impressions_cur": "impressions"})
    f = {c: float(k[c] or 0) for c in ["spend", "spend_p", "clicks", "impressions", "rev", "rev_p", "cust", "cust_p",
                                         "sessions", "ltv90"]}
    roas = f["rev"] / f["spend"] if f["spend"] else 0
    roas_p = f["rev_p"] / f["spend_p"] if f["spend_p"] else 0
    cac = f["spend"] / f["cust"] if f["cust"] else 0
    cac_p = f["spend_p"] / f["cust_p"] if f["cust_p"] else 0

    daily = q("""
        WITH (SELECT max(date) FROM fct_ad_daily) AS e
        SELECT d.day AS day, d.spend AS spend, ifNull(r.revenue, 0) AS revenue, ifNull(c.customers, 0) AS customers
        FROM (SELECT date AS day, round(sum(spend), 2) AS spend FROM fct_ad_daily
              WHERE date > e - {w:UInt32} GROUP BY day) d
        LEFT JOIN (SELECT order_date AS day, round(sum(revenue), 2) AS revenue FROM fct_orders
                   WHERE platform != 'unpaid' AND order_date > e - {w:UInt32} GROUP BY day) r ON r.day = d.day
        LEFT JOIN (SELECT acquisition_date AS day, count() AS customers FROM dim_customers
                   WHERE acquisition_platform != 'unpaid' AND acquisition_date > e - {w:UInt32} GROUP BY day) c
                  ON c.day = d.day
        ORDER BY day
        SETTINGS join_use_nulls = 1
    """, w=window)
    wk = q("""
        SELECT toStartOfWeek(d.date, 1) AS week, round(sum(d.spend), 2) AS spend,
               round(any(r.revenue), 2) AS revenue
        FROM fct_ad_daily d
        LEFT JOIN (SELECT toStartOfWeek(order_date, 1) AS week, sum(revenue) AS revenue FROM fct_orders
                   WHERE platform != 'unpaid' GROUP BY week) r ON r.week = toStartOfWeek(d.date, 1)
        GROUP BY week ORDER BY week
    """)
    wk = wk.iloc[1:-1] if len(wk) > 3 else wk  # drop partial edge weeks
    pl = q("""
        WITH (SELECT max(date) FROM fct_ad_daily) AS e
        SELECT platform, round(sum(spend), 2) AS spend FROM fct_ad_daily WHERE date > e - {w:UInt32}
        GROUP BY platform ORDER BY platform
    """, w=window)
    cu = q("""
        WITH (SELECT max(date) FROM fct_ad_daily) AS e
        SELECT acquisition_platform AS platform, count() AS customers FROM dim_customers
        WHERE acquisition_date > e - {w:UInt32} AND acquisition_platform != 'unpaid' GROUP BY platform
    """, w=window)
    m = pl.merge(cu, on="platform", how="left").fillna(0)
    m["cac"] = (m.spend / m.customers.where(m.customers > 0)).round(2)
    m = m.dropna(subset=["cac"]).sort_values("cac")

    # next steps: same rules as the old Overview page
    target = s.target_cac
    per_month = 30 / window
    e = econ(window)
    steps = []
    if not e.empty:
        good = e[(e.ltv_to_cac >= 2.5) & (e.cac_window <= target) & (e.new_customers_window > 0)]
        if not good.empty:
            r = good.sort_values("ltv_to_cac", ascending=False).iloc[0]
            extra = r.spend_window * 0.2 * per_month
            gain = extra / r.cac_window * r.ltv_estimate - extra
            steps.append({"tone": "good", "title": f"Give “{r.ad_name}” more budget",
                          "detail": f"Each new customer costs {money(r.cac_window, 2)} and is worth "
                                    f"{money(r.ltv_estimate, 2)}.",
                          "value": f"+{money(gain)}", "value_note": "per month with 20% more budget"})
        bad = e[(e.new_customers_window == 0) | (e.ltv_to_cac < 1)]
        if not bad.empty:
            r = bad.sort_values("spend_window", ascending=False).iloc[0]
            why = (f"Each new customer costs {money(r.cac_window, 2)} but spends only {money(r.ltv_estimate, 2)}."
                   if r.new_customers_window else f"It spent {money(r.spend_window)} and won no customers.")
            steps.append({"tone": "bad", "title": f"Pause “{r.ad_name}”", "detail": why,
                          "value": money(r.spend_window * per_month), "value_note": "saved per month"})
    w = cache.get(("waste_rules", window), 300,
                  lambda: search_terms.summary(search_terms.audit(window, llm=None)))
    if w["flagged"]:
        steps.append({"tone": "warn", "title": f"Block {w['flagged']} searches that never sell",
                      "detail": "Job seekers, freebie hunters and people looking for store hours.",
                      "value": money(w["wasted_spend"]), "value_note": f"wasted in {window} days"})

    def verdict(r) -> str:
        ratio, n = r.ltv_to_cac, r.new_customers_window or 0
        if n == 0 or (pd.notna(ratio) and ratio < 1):
            return "losing"
        if pd.notna(ratio) and ratio >= 2.5 and (r.cac_window or 0) <= target:
            return "scale"
        return "ok"

    ads = e.assign(verdict=e.apply(verdict, axis=1)) if not e.empty else e
    cols = ["ad_id", "ad_name", "verdict", "platform", "campaign_name", "spend_window", "new_customers_window",
            "cac_window", "ltv_estimate", "ltv_to_cac", "roas_window"]
    ads = ads[[c for c in cols if c in ads.columns]] if not ads.empty else ads

    return clean({
        "days": window,
        "end_date": k["end_date"],
        "roas": roas, "roas_prev": roas_p,
        "kpis": {
            "spend": f["spend"], "spend_change": _chg(f["spend"], f["spend_p"]),
            "revenue": f["rev"], "revenue_change": _chg(f["rev"], f["rev_p"]),
            "customers": f["cust"], "customers_change": _chg(f["cust"], f["cust_p"]),
            "cac": cac, "cac_change": _chg(cac, cac_p),
            "ltv90": f["ltv90"],
            "ltv_to_cac": (f["ltv90"] / cac) if cac and f["ltv90"] else None,
        },
        "journey": {"impressions": f["impressions"], "clicks": f["clicks"], "sessions": f["sessions"],
                    "customers": f["cust"], "revenue": f["rev"], "ltv90": f["ltv90"]},
        "daily": daily, "weekly": wk, "platform_cac": m,
        "next_steps": steps, "ads": ads, "target_cac": target,
    })


# ------------------------------------------------------------------------------------------- ask
class AskTurn(BaseModel):
    question: str
    sql: str = ""
    headline: str = ""


class AskBody(BaseModel):
    question: str
    history: list[AskTurn] = []


def _answer_json(a: AgentAnswer) -> dict:
    return clean({
        "id": a.id, "question": a.question, "ok": a.ok, "headline": a.headline,
        "answer_markdown": a.answer_markdown, "sql": a.sql, "reasoning": a.reasoning,
        "assumptions": a.assumptions, "caveats": a.caveats,
        "columns": list(a.data.columns), "rows": a.data,
        "chart": a.chart.model_dump() if a.chart else None,
        "critic": a.critic.model_dump() if a.critic else None,
        "number_checks": [{"text": c.text, "verified": c.verified, "source": c.source} for c in a.number_checks],
        "numbers_checked": a.numbers_checked, "numbers_verified": a.numbers_verified, "verified": a.verified,
        "suggested_actions": [s.model_dump() for s in a.suggested_actions],
        "steps": [{"name": s.name, "status": s.status, "detail": s.detail[:400], "ms": s.ms} for s in a.steps],
        "latency_ms": a.latency_ms, "error": a.error,
    })


@app.post("/api/ask")
def ask(body: AskBody):
    if not get_settings().llm_configured:
        raise HTTPException(503, "The AI assistant is switched off: add an AI key (for example GROQ_API_KEY).")
    try:
        a = agent().ask(body.question, [Turn(t.question, t.sql, t.headline) for t in body.history])
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    return _answer_json(a)


class FromAnswer(BaseModel):
    action: str
    platform: str
    ad_name: str
    rationale: str
    question: str = ""


@app.post("/api/suggestions/from-answer")
def suggestion_from_answer(body: FromAnswer):
    if body.action not in ("pause_ad", "scale_ad"):
        raise HTTPException(400, "Only pause or scale ideas can be added.")
    e = econ(30).set_index("ad_name")
    row = e.loc[body.ad_name] if body.ad_name in e.index else None
    metrics = {} if row is None else {k: (None if pd.isna(v) else float(v)) for k, v in row.to_dict().items()
                                      if isinstance(v, (int, float, np.number))}
    n = recs.save([recs.Rec(
        body.action, body.platform, "" if row is None else row["ad_id"], body.ad_name,
        "" if row is None else row["campaign_name"], f"From chat: {body.rationale}",
        metrics | {"question": body.question}, float(metrics.get("spend_window") or 0), source="agent")])
    return {"added": n}


# ------------------------------------------------------------------------------------------- suggestions
@app.get("/api/suggestions")
def suggestions():
    df = recs.latest()
    return clean(df)


class CheckBody(BaseModel):
    days: int = 30


@app.post("/api/suggestions/check")
def suggestions_check(body: CheckBody):
    n = recs.save(recs.rule_recommendations(body.days))
    return {"added": n}


class DecideBody(BaseModel):
    status: str  # approved | rejected | applied
    by: str
    note: str = ""


@app.post("/api/suggestions/{rec_id}/decide")
def suggestions_decide(rec_id: str, body: DecideBody):
    try:
        recs.decide(rec_id, body.status, body.by, body.note)
    except KeyError as e:
        raise HTTPException(404, "Suggestion not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@app.get("/api/suggestions/{rec_id}/change")
def suggestions_change(rec_id: str):
    df = recs.latest()
    hit = df[df.id == rec_id]
    if hit.empty:
        raise HTTPException(404, "Suggestion not found")
    return clean(recs.change_payload(hit.iloc[0].to_dict()))


# ------------------------------------------------------------------------------------------- wasted searches
def _audit(days: int, min_cost: float, ai: bool) -> pd.DataFrame:
    return cache.get(("audit", days, min_cost, ai), 300,
                     lambda: search_terms.audit(days, llm=llm_or_none() if ai else None, min_cost=min_cost))


@app.get("/api/wasted")
def wasted(days: int = 30, min_cost: float = 5.0, ai: bool = True):
    df = _audit(days, min_cost, ai)
    if df.empty:
        return {"summary": search_terms.summary(df), "terms": [], "reasons": [], "campaigns": []}
    df = df.assign(intent_label=df.intent.map(plain.intent))
    flagged = df[df.flagged]
    reasons = (flagged.groupby("reason", as_index=False).wasted_spend.sum()
               .sort_values("wasted_spend", ascending=False)) if not flagged.empty else flagged
    camp = (flagged.groupby("campaign_name", as_index=False).wasted_spend.sum()
            .sort_values("wasted_spend", ascending=False)) if "campaign_name" in flagged and not flagged.empty \
        else pd.DataFrame()
    return clean({"summary": search_terms.summary(df), "terms": df, "reasons": reasons, "campaigns": camp})


class BlockBody(BaseModel):
    days: int = 30
    min_cost: float = 5.0
    ai: bool = True
    terms: list[str]


@app.post("/api/wasted/block")
def wasted_block(body: BlockBody):
    df = _audit(body.days, body.min_cost, body.ai)
    n = recs.save(recs.audit_recommendations(df, body.terms))
    return {"added": n}


# ------------------------------------------------------------------------------------------- weekly report
def _report(end: date | None, ai: bool) -> weekly.WeeklyReport:
    return cache.get(("report", end, ai), 300, lambda: weekly.build(end=end, llm=llm_or_none() if ai else None))


def _report_json(r: weekly.WeeklyReport) -> dict:
    return clean({
        "id": r.id, "period_start": r.period_start, "period_end": r.period_end,
        "kpis": [{"label": k.label, "value": k.value, "previous": k.prior, "text": k.text(),
                  "previous_text": k.text(k.prior), "change": k.change, "good": k.good, "better": k.better}
                 for k in r.kpis],
        "top_ads": r.top_ads, "worst_ads": r.worst_ads, "platform": r.platform, "waste": r.waste,
        "top_waste_terms": r.top_waste_terms, "pending": len(r.pending),
        "commentary": r.commentary, "commentary_source": r.commentary_source,
    })


@app.get("/api/report")
def report(end: date | None = None, ai: bool = True):
    return _report_json(_report(end, ai))


@app.get("/api/report/markdown")
def report_markdown(end: date | None = None, ai: bool = True):
    return {"markdown": weekly.to_markdown(_report(end, ai))}


class SendBody(BaseModel):
    end: date | None = None
    ai: bool = True
    slack: bool = True
    email: bool = False


@app.post("/api/report/send")
def report_send(body: SendBody):
    return weekly.deliver(_report(body.end, body.ai), slack=body.slack, email=body.email)


@app.get("/api/report/history")
def report_history():
    return clean(weekly.history())


@app.get("/api/report/schedule")
def report_schedule():
    sch = Schedule.from_settings()
    return {"describe": sch.describe(),
            "next_run": clean(sch.next_run(pd.Timestamp.now(tz="UTC").to_pydatetime()))}


# ------------------------------------------------------------------------------------------- data status
@app.get("/api/data/status")
def data_status():
    try:
        fresh = q("""
            SELECT 'Meta ads' AS source, toString(max(date)) AS latest FROM raw_meta_ads_insights
            UNION ALL SELECT 'Google ads', toString(max(date)) FROM raw_google_ads_ad_performance
            UNION ALL SELECT 'Google searches', toString(max(date)) FROM raw_google_ads_search_terms
            UNION ALL SELECT 'Website visits (Google Analytics)', toString(max(session_start)) FROM raw_ga4_sessions
            UNION ALL SELECT 'Shop orders (Shopify)', toString(max(created_at)) FROM raw_shop_orders
        """)
        fresh["latest"] = pd.to_datetime(fresh.latest, format="mixed")
        fresh["age_days"] = (pd.Timestamp.now() - fresh.latest).dt.days
    except Exception:  # noqa: BLE001  (tables not created yet)
        fresh = pd.DataFrame()
    counts = cache.get("counts", 60, warehouse.table_counts)
    raw_rows = int(counts[counts.table.str.startswith("raw_")].rows.sum()) if not counts.empty else 0
    try:
        hist = ingest.sync_history()
    except Exception:  # noqa: BLE001
        hist = pd.DataFrame()
    return clean({"sources": fresh, "tables": counts, "raw_rows": raw_rows, "history": hist,
                  "version": cache.get("health", 30, warehouse.health).version})


_jobs: dict[str, dict] = {}


class RefreshBody(BaseModel):
    kind: str = "full"  # full | models
    mode: str = "auto"  # auto | airbyte | direct


@app.post("/api/data/refresh")
def data_refresh(body: RefreshBody):
    """Starts the refresh in the background; poll /api/data/jobs/{id} for its real progress."""
    if any(j["state"] == "running" for j in _jobs.values()):
        raise HTTPException(409, "A refresh is already running.")
    job = {"id": uuid.uuid4().hex[:10], "state": "running", "log": [], "error": "", "kind": body.kind}
    _jobs[job["id"]] = job
    s = get_settings()

    def progress(msg: str):
        job["log"].append(str(msg))

    def work():
        try:
            if body.kind == "models":
                transform.run_models(progress=progress)
            else:
                warehouse.init_db()
                if not (s.demo_dir / "meta_ads_insights.csv").exists():
                    progress("sample data not found, creating it…")
                    demo_data.generate(s.demo_dir)
                ingest.ingest(body.mode, progress=progress)
                transform.run_models(progress=progress)
            cache.clear()
            job["state"] = "done"
        except Exception as e:  # noqa: BLE001
            job["state"], job["error"] = "failed", str(e)

    threading.Thread(target=work, daemon=True).start()
    return job


@app.get("/api/data/jobs/{job_id}")
def data_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    return {**job, "log": job["log"][-40:]}
