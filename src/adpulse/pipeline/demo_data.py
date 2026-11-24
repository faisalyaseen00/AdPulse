"""Deterministic demo dataset for a fictional DTC coffee brand ("Ember & Oak").

It writes one CSV per Airbyte stream into ``data/demo/`` in the shape the real
connectors emit (Meta Ads insights, Google Ads ad performance + search terms,
GA4 sessions, Shopify orders + customers).

Each ad has its own economics, so the data holds real stories for the agent to find:
* "Static - 20% Off" buys cheap customers who rarely come back (low LTV).
* "RSA - Coffee Subscription" and "UGC Video - Morning Routine" bring high-LTV subscribers.
* "Search - Competitor" pays high CPCs for almost no buyers -> pause candidate.
* "Carousel - Bestsellers" fatigues: its conversion rate decays over time.
* Generic search wastes money on job / DIY / free-sample queries (search term audit).
* Platform-reported conversions are inflated vs. warehouse truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AdSpec:
    platform: str
    campaign_id: str
    campaign_name: str
    campaign_type: str
    group_id: str
    group_name: str
    ad_id: str
    ad_name: str
    daily_spend: float
    cpc: float
    ctr: float
    cvr: float             # session -> first order
    aov: float
    repeat_mean: float     # expected repeat orders per customer over ~6 months
    first_discount: float = 0.0
    fatigue: float = 0.0   # fractional cvr loss over the full period
    start_offset: int = 0  # days after period start the ad launched
    stop_offset: int | None = None


ADS: list[AdSpec] = [
    # ---- Meta ----
    AdSpec("meta", "120201", "Prospecting - Broad", "social", "2301", "Broad 25-54", "6101",
           "UGC Video - Morning Routine", 320, 1.35, 0.018, 0.026, 42, 3.4),
    AdSpec("meta", "120201", "Prospecting - Broad", "social", "2301", "Broad 25-54", "6102",
           "Carousel - Bestsellers", 260, 1.10, 0.021, 0.034, 38, 1.2, fatigue=0.75),
    AdSpec("meta", "120201", "Prospecting - Broad", "social", "2302", "Interests - Coffee", "6103",
           "Static - 20% Off", 300, 0.85, 0.024, 0.045, 34, 0.25, first_discount=0.20),
    AdSpec("meta", "120201", "Prospecting - Broad", "social", "2302", "Interests - Coffee", "6104",
           "Reels - Founder Story", 140, 1.60, 0.012, 0.017, 45, 2.1, start_offset=60),
    AdSpec("meta", "120202", "Retargeting - Cart Abandoners", "social", "2303", "ATC 14d", "6105",
           "Dynamic Product Ads", 120, 0.95, 0.031, 0.070, 40, 1.6),
    AdSpec("meta", "120202", "Retargeting - Cart Abandoners", "social", "2303", "ATC 14d", "6106",
           "Testimonial Video", 70, 1.05, 0.026, 0.055, 41, 1.9),
    AdSpec("meta", "120203", "Lookalike - Top Buyers 1%", "social", "2304", "LAL 1% Purchasers", "6107",
           "UGC Video - Unboxing", 180, 1.25, 0.019, 0.030, 44, 2.6),
    AdSpec("meta", "120203", "Lookalike - Top Buyers 1%", "social", "2304", "LAL 1% Purchasers", "6108",
           "Static - Free Shipping", 110, 0.90, 0.022, 0.024, 36, 0.6, stop_offset=150),
    # ---- Google ----
    AdSpec("google", "9001", "Search - Brand", "search", "7001", "Brand Exact", "8101",
           "RSA - Brand", 90, 0.55, 0.12, 0.090, 46, 2.4),
    AdSpec("google", "9002", "Search - Generic Coffee", "search", "7002", "Specialty Beans", "8102",
           "RSA - Specialty Coffee Beans", 240, 1.90, 0.045, 0.028, 43, 1.8),
    AdSpec("google", "9002", "Search - Generic Coffee", "search", "7003", "Subscription", "8103",
           "RSA - Coffee Subscription", 180, 2.30, 0.040, 0.032, 48, 4.2),
    AdSpec("google", "9003", "Search - Competitor", "search", "7004", "Competitor Terms", "8104",
           "RSA - Better Than The Big Chains", 150, 3.40, 0.030, 0.006, 39, 0.8),
    AdSpec("google", "9004", "Shopping - All Products", "shopping", "7005", "All Products", "8105",
           "Shopping - Catalog", 210, 0.75, 0.011, 0.022, 37, 1.3),
    AdSpec("google", "9005", "PMax - Prospecting", "performance_max", "7006", "Asset Group A", "8106",
           "PMax - Asset Group A", 260, 1.15, 0.009, 0.015, 39, 1.0, start_offset=30),
]

# (term, intent, weight) per Google search ad group. Intent drives conversions.
SEARCH_TERMS: dict[str, list[tuple[str, str, float]]] = {
    "7001": [("ember and oak coffee", "buyer", 6), ("ember oak coffee discount code", "buyer", 2),
             ("ember and oak coffee reviews", "research", 1.5), ("ember oak login", "navigational", 1)],
    "7002": [("buy specialty coffee beans online", "buyer", 5), ("single origin coffee beans", "buyer", 4),
             ("best whole bean coffee", "buyer", 3), ("ethiopian coffee beans", "buyer", 2),
             ("how to roast coffee beans at home", "research", 2.5), ("what is single origin coffee", "research", 2),
             ("coffee beans calories", "research", 1.2), ("coffee shop jobs near me", "irrelevant", 2.2),
             ("barista salary", "irrelevant", 1.4), ("free coffee samples", "irrelevant", 2.0),
             ("coffee bean tattoo", "irrelevant", 0.8), ("diy cold brew without beans", "irrelevant", 1.0),
             ("coffee beans wholesale 50 lb", "irrelevant", 0.9)],
    "7003": [("coffee subscription", "buyer", 6), ("monthly coffee subscription gift", "buyer", 3),
             ("best coffee subscription 2026", "buyer", 2.5), ("coffee subscription cancel", "irrelevant", 1.3),
             ("free coffee subscription trial", "irrelevant", 1.6), ("coffee subscription box reddit", "research", 1.2)],
    "7004": [("big chain coffee beans", "research", 3), ("big chain coffee menu prices", "irrelevant", 3.5),
             ("big chain coffee hours", "irrelevant", 2.5), ("big chain coffee jobs", "irrelevant", 2),
             ("alternative to big chain coffee", "buyer", 1.2)],
}
INTENT_CVR_MULT = {"buyer": 1.9, "research": 0.35, "navigational": 0.8, "irrelevant": 0.0}


def generate(out_dir: Path, days: int = 180, end: date | None = None, seed: int = 42) -> dict[str, int]:
    """Generate the demo dataset. Returns row counts per stream file."""
    rng = np.random.default_rng(seed)
    end = end or (date.today() - timedelta(days=1))
    start = end - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]
    end_dt = datetime.combine(end, datetime.max.time()).replace(microsecond=0)

    meta_rows, gads_rows, term_rows = [], [], []
    sess_cols: dict[str, list] = {k: [] for k in
                                  ("session_id", "user_pseudo_id", "session_start", "source", "medium",
                                   "campaign", "ad_content", "click_id", "landing_page", "device")}
    orders: list[dict] = []
    customers: list[dict] = []
    session_seq = 0
    order_seq = 0
    cust_seq = 0

    def add_sessions(n: int, day: date, source: str, medium: str, campaign: str, ad_id: str,
                     landing: str) -> np.ndarray:
        nonlocal session_seq
        ids = np.arange(session_seq, session_seq + n)
        session_seq += n
        secs = rng.integers(0, 86400, n)
        base = datetime.combine(day, datetime.min.time())
        sess_cols["session_id"].extend(f"s{i:09d}" for i in ids)
        sess_cols["user_pseudo_id"].extend(f"u{x:010d}" for x in rng.integers(0, 10**10, n))
        sess_cols["session_start"].extend(base + timedelta(seconds=int(s)) for s in secs)
        sess_cols["source"].extend([source] * n)
        sess_cols["medium"].extend([medium] * n)
        sess_cols["campaign"].extend([campaign] * n)
        sess_cols["ad_content"].extend([ad_id] * n)
        click_prefix = "gclid_" if source == "google" else ("fbclid_" if source == "facebook" else "")
        sess_cols["click_id"].extend(
            [f"{click_prefix}{i}" for i in ids] if click_prefix else [""] * n)
        sess_cols["landing_page"].extend([landing] * n)
        sess_cols["device"].extend(rng.choice(["mobile", "desktop", "tablet"], n, p=[0.68, 0.28, 0.04]))
        return ids

    def new_customer(first_at: datetime, ad: AdSpec | None, session_id: str, aov: float,
                     discount_rate: float, repeat_mean: float) -> None:
        nonlocal order_seq, cust_seq
        cust_seq += 1
        cid = f"c{cust_seq:07d}"
        customers.append({"customer_id": cid, "created_at": first_at,
                          "country": rng.choice(["US", "CA", "GB", "AU"], p=[0.78, 0.1, 0.08, 0.04]),
                          "accepts_marketing": int(rng.random() < 0.62)})
        subtotal = round(float(aov * rng.lognormal(0, 0.25)), 2)
        disc = round(subtotal * discount_rate, 2)
        order_seq += 1
        orders.append({"order_id": f"o{order_seq:08d}", "customer_id": cid, "session_id": session_id,
                       "created_at": first_at, "subtotal": subtotal, "discount": disc,
                       "total": round(subtotal - disc, 2), "currency": "USD",
                       "status": "refunded" if rng.random() < 0.03 else "paid"})
        # Repeat purchases: geometric-ish chain; subscribers re-order roughly monthly.
        retention = repeat_mean / (1.0 + repeat_mean)
        t = first_at
        while rng.random() < retention:
            t = t + timedelta(days=float(rng.gamma(4.0, 30.0 / 4.0)))
            if t > end_dt:
                break
            src, med = [("klaviyo", "email"), ("(direct)", "(none)"), ("google", "organic")][
                int(rng.choice(3, p=[0.5, 0.35, 0.15]))]
            sid = add_sessions(1, t.date(), src, med, "retention" if med == "email" else "", "", "/account")[0]
            sub = round(float(aov * 0.95 * rng.lognormal(0, 0.2)), 2)
            order_seq += 1
            orders.append({"order_id": f"o{order_seq:08d}", "customer_id": cid, "session_id": f"s{sid:09d}",
                           "created_at": t, "subtotal": sub, "discount": 0.0, "total": sub,
                           "currency": "USD", "status": "refunded" if rng.random() < 0.02 else "paid"})

    for di, day in enumerate(dates):
        dow = day.weekday()
        season = 1.0 + 0.12 * np.sin(2 * np.pi * di / 365 * 2) + (0.08 if dow in (5, 6) else 0.0)
        for ad in ADS:
            if di < ad.start_offset or (ad.stop_offset is not None and di >= ad.stop_offset):
                continue
            spend = max(0.0, ad.daily_spend * season * rng.lognormal(0, 0.18))
            cpc = ad.cpc * rng.lognormal(0, 0.1)
            clicks = int(spend / cpc)
            spend = round(clicks * cpc, 2)
            impressions = int(clicks / max(ad.ctr * rng.lognormal(0, 0.1), 1e-4))
            progress = di / max(days - 1, 1)
            cvr = ad.cvr * (1 - ad.fatigue * progress)

            # sessions (~92% of clicks land a tracked session)
            n_sess = int(rng.binomial(clicks, 0.92))
            source = "facebook" if ad.platform == "meta" else "google"
            medium = "paid_social" if ad.platform == "meta" else "cpc"
            sids = add_sessions(n_sess, day, source, medium, ad.campaign_name, ad.ad_id,
                                "/subscribe" if "Subscription" in ad.ad_name else "/shop")
            n_first = int(rng.binomial(n_sess, min(cvr, 0.5))) if n_sess else 0
            for idx in rng.choice(sids, n_first, replace=False) if n_first else []:
                ts = sess_cols["session_start"][idx] + timedelta(minutes=int(rng.integers(2, 40)))
                new_customer(ts, ad, f"s{idx:09d}", ad.aov, ad.first_discount, ad.repeat_mean)

            inflation = rng.uniform(1.15, 1.6)
            if ad.platform == "meta":
                meta_rows.append({"date": day, "account_id": "act_5550001", "campaign_id": ad.campaign_id,
                                  "campaign_name": ad.campaign_name, "adset_id": ad.group_id,
                                  "adset_name": ad.group_name, "ad_id": ad.ad_id, "ad_name": ad.ad_name,
                                  "impressions": impressions, "clicks": clicks, "spend": spend,
                                  "purchases": round(n_first * inflation)})
            else:
                gads_rows.append({"date": day, "customer_id": "123-456-7890", "campaign_id": ad.campaign_id,
                                  "campaign_name": ad.campaign_name, "campaign_type": ad.campaign_type,
                                  "ad_group_id": ad.group_id, "ad_group_name": ad.group_name,
                                  "ad_id": ad.ad_id, "ad_name": ad.ad_name, "impressions": impressions,
                                  "clicks": clicks, "cost_micros": int(spend * 1e6),
                                  "conversions": round(n_first * inflation, 1)})
                terms = SEARCH_TERMS.get(ad.group_id)
                if terms and clicks:
                    w = np.array([t[2] for t in terms]) * rng.lognormal(0, 0.3, len(terms))
                    split = rng.multinomial(clicks, w / w.sum())
                    for (term, intent, _), c in zip(terms, split):
                        if c == 0:
                            continue
                        cost = round(spend * c / clicks, 2)
                        conv = float(rng.binomial(c, min(ad.cvr * INTENT_CVR_MULT[intent], 0.5)))
                        term_rows.append({"date": day, "campaign_id": ad.campaign_id,
                                          "campaign_name": ad.campaign_name, "ad_group_id": ad.group_id,
                                          "ad_group_name": ad.group_name, "search_term": term,
                                          "match_type": "EXACT" if ad.group_id == "7001" else
                                          rng.choice(["PHRASE", "BROAD"], p=[0.4, 0.6]),
                                          "impressions": int(c / max(ad.ctr * rng.lognormal(0, 0.15), 1e-4)),
                                          "clicks": int(c), "cost_micros": int(cost * 1e6),
                                          "conversions": conv, "conversions_value": round(conv * ad.aov, 2)})

        # unpaid traffic: organic / direct / email sessions and the customers they bring
        for src, med, n_mean, cvr in (("google", "organic", 260, 0.012), ("(direct)", "(none)", 150, 0.015),
                                      ("klaviyo", "email", 90, 0.01)):
            n = int(rng.poisson(n_mean * season))
            sids = add_sessions(n, day, src, med, "newsletter" if med == "email" else "", "", "/")
            k = int(rng.binomial(n, cvr))
            for idx in rng.choice(sids, k, replace=False) if k else []:
                ts = sess_cols["session_start"][idx] + timedelta(minutes=int(rng.integers(2, 40)))
                new_customer(ts, None, f"s{idx:09d}", 40, 0.0, 1.5)

    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {
        "meta_ads_insights": pd.DataFrame(meta_rows),
        "google_ads_ad_performance": pd.DataFrame(gads_rows),
        "google_ads_search_terms": pd.DataFrame(term_rows),
        "ga4_sessions": pd.DataFrame(sess_cols),
        "shop_orders": pd.DataFrame(orders).sort_values("created_at"),
        "shop_customers": pd.DataFrame(customers),
    }
    counts = {}
    for name, df in frames.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
        counts[name] = len(df)
    return counts
