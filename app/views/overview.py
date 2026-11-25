import html

import pandas as pd
import streamlit as st
import ui

from adpulse import plain
from adpulse.audit import search_terms
from adpulse.config import get_settings

if not ui.require_warehouse():
    st.stop()

# own row, so all three choices always fit (they were clipped when squeezed into a column)
window = st.segmented_control("Period", [7, 30, 90], default=30, format_func=lambda d: f"Last {d} days",
                              label_visibility="collapsed", key="period") or 30

k = ui.q(
    """
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
    """, (("w", window),)).iloc[0].astype(float, errors="ignore").rename({"spend_cur": "spend", "clicks_cur": "clicks",
                                                                         "impressions_cur": "impressions"})


def chg(a, b):
    a, b = float(a or 0), float(b or 0)  # counts arrive as UInt64: subtracting would wrap around
    return (a - b) / b if b else None


roas, roas_p = (k.rev / k.spend if k.spend else 0), (k.rev_p / k.spend_p if k.spend_p else 0)
cac, cac_p = (k.spend / k.cust if k.cust else 0), (k.spend_p / k.cust_p if k.cust_p else 0)
end = pd.Timestamp(k.end_date)
period = f"previous {window} days"
target = get_settings().target_cac

# ---- The stage: the answer, a verdict, and this period's trend drawing itself --------------------------
if roas >= 1.5:
    pill = ("good", "Healthy return")
elif roas >= 1:
    pill = ("ok", "Ads are paying for themselves")
else:
    pill = ("bad", "Ads cost more than they bring back")
daily = ui.q("""
    WITH (SELECT max(date) FROM fct_ad_daily) AS e
    SELECT d.day AS day, d.spend AS spend, ifNull(r.revenue, 0) AS revenue
    FROM (SELECT date AS day, round(sum(spend), 2) AS spend FROM fct_ad_daily
          WHERE date > e - {w:UInt32} GROUP BY day) d
    LEFT JOIN (SELECT order_date AS day, round(sum(revenue), 2) AS revenue FROM fct_orders
               WHERE platform != 'unpaid' AND order_date > e - {w:UInt32} GROUP BY day) r ON r.day = d.day
    ORDER BY day
    SETTINGS join_use_nulls = 1
""", (("w", window),))
ui.stage(
    eyebrow=f"Last {window} days, up to {end:%B %-d, %Y}",
    lead="Your ads brought back", big=plain.per_dollar(roas), after="for every $1 you spent",
    pill=pill,
    detail_html=f"Sales from ads {ui.change_text(chg(k.rev, k.rev_p), 'up', period)}",
    spark_svg=ui.sparkline(daily.revenue.astype(float).tolist(), daily.spend.astype(float).tolist()),
    legend=[("Sales from ads", "linear-gradient(90deg,#2DD4BF,#F4B400,#FF8A5B)"),
            ("Ad spend", "rgba(255,255,255,.45)")],
    caption=f"Day by day, last {window} days",
)

# ---- Numbers at a glance (short labels, so every tile lines up) ---------------------------------------
ui.kpi_row([
    ui.kpi("Ad spend", ui.money(k.spend), chg(k.spend, k.spend_p), "neutral", help=plain.explain("spend"),
           period="before"),
    ui.kpi("Sales from ads", ui.money(k.rev), chg(k.rev, k.rev_p), help=plain.explain("paid_revenue"),
           period="before"),
    ui.kpi("New customers", f"{k.cust:,.0f}", chg(k.cust, k.cust_p), help=plain.explain("new_customers"),
           period="before"),
    ui.kpi("Cost per customer", ui.money(cac, 2), chg(cac, cac_p), "down", help=plain.explain("cac"),
           period="before"),
    ui.kpi("Customer value", ui.money(k.ltv90, 2), note="first 90 days", help=plain.explain("ltv90")),
    ui.kpi("Value vs cost", plain.times(k.ltv90 / cac) if cac and k.ltv90 else "–", note="per customer won",
           help=plain.explain("ltv_to_cac")),
])


# ---- What to do: worked out for the selected period ----------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def wasted(days: int) -> dict:
    return search_terms.summary(search_terms.audit(days, llm=None))


per_month = 30 / window
econ = ui.ad_economics(window)
items = []
if not econ.empty:
    good = econ[(econ.ltv_to_cac >= 2.5) & (econ.cac_window <= target) & (econ.new_customers_window > 0)]
    if not good.empty:
        r = good.sort_values("ltv_to_cac", ascending=False).iloc[0]
        extra = r.spend_window * 0.2 * per_month
        gain = extra / r.cac_window * r.ltv_estimate - extra
        items.append(("good", f"Give “{r.ad_name}” more budget",
                      f"Each new customer costs {ui.money(r.cac_window, 2)} and is worth {ui.money(r.ltv_estimate, 2)}.",
                      f"+{ui.money(gain)}", "per month with 20% more budget"))
    bad = econ[(econ.new_customers_window == 0) | (econ.ltv_to_cac < 1)]
    if not bad.empty:
        r = bad.sort_values("spend_window", ascending=False).iloc[0]
        why = (f"Each new customer costs {ui.money(r.cac_window, 2)} but spends only {ui.money(r.ltv_estimate, 2)}."
               if r.new_customers_window else f"It spent {ui.money(r.spend_window)} and won no customers.")
        items.append(("bad", f"Pause “{r.ad_name}”", why, ui.money(r.spend_window * per_month), "saved per month"))
w = wasted(window)
if w["flagged"]:
    items.append(("warn", f"Block {w['flagged']} searches that never sell",
                  "Job seekers, freebie hunters and people looking for store hours.",
                  ui.money(w["wasted_spend"]), f"wasted in {window} days"))

ui.section("Next steps", f"based on the last {window} days")
if items:
    ui.todo(items)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.page_link("views/recommendations.py", label="Review suggestions", icon=":material/task_alt:")
    b2.page_link("views/audit.py", label="See wasted searches", icon=":material/money_off:")
else:
    st.success("Nothing needs your attention in this period.")

# ---- From ad to customer --------------------------------------------------------------------------------
ui.section("Customer journey", f"last {window} days")
flow = [
    (plain.label("impressions"), f"{k.impressions:,.0f}", "times your ads were shown"),
    (plain.label("clicks"), f"{k.clicks:,.0f}",
     f"{k.clicks / k.impressions:.1%} of views" if k.impressions else ""),
    (plain.label("sessions"), f"{k.sessions:,.0f}", "visits to your website"),
    ("New customers", f"{k.cust:,.0f}", f"{k.cust / k.sessions:.1%} of visits bought" if k.sessions else ""),
    (plain.label("paid_revenue"), ui.money(k.rev), f"{plain.per_dollar(roas)} back per $1"),
    (plain.label("ltv90"), ui.money(k.ltv90, 2), "per customer"),
]
st.html('<div class="ap-flow">' + "".join(
    f'<div class="node"><div class="t">{html.escape(t)}</div><div class="v">{v}</div><div class="s">{html.escape(s)}</div></div>'
    for t, v, s in flow) + "</div>")

# ---- Charts -----------------------------------------------------------------------------------------------
c1, c2 = st.columns([1.75, 1], gap="medium")
with c1:
    wk = ui.q("""
        SELECT toStartOfWeek(d.date, 1) AS week, round(sum(d.spend), 2) AS spend,
               round(any(r.revenue), 2) AS revenue
        FROM fct_ad_daily d
        LEFT JOIN (SELECT toStartOfWeek(order_date, 1) AS week, sum(revenue) AS revenue FROM fct_orders
                   WHERE platform != 'unpaid' GROUP BY week) r ON r.week = toStartOfWeek(d.date, 1)
        GROUP BY week ORDER BY week
    """)
    wk = wk.iloc[1:-1] if len(wk) > 3 else wk  # drop partial edge weeks
    dates = [pd.Timestamp(d) for d in wk.week]
    svg = ui.area_chart(dates, [("Sales from ads", wk.revenue.astype(float).tolist(), "#EB6834"),
                                ("Ad spend", wk.spend.astype(float).tolist(), "#2A78D6")])
    ui.chart_card("Sales trend", "Last 6 months, one point per week. Hover for the numbers.", svg,
                  [("Sales from ads", "#EB6834", ui.money(wk.revenue.sum())),
                   ("Ad spend", "#2A78D6", ui.money(wk.spend.sum()))])
with c2:
    pl = ui.q("""
        WITH (SELECT max(date) FROM fct_ad_daily) AS e
        SELECT platform, round(sum(spend), 2) AS spend FROM fct_ad_daily WHERE date > e - {w:UInt32}
        GROUP BY platform ORDER BY platform
    """, (("w", window),))
    cu = ui.q("""
        WITH (SELECT max(date) FROM fct_ad_daily) AS e
        SELECT acquisition_platform AS platform, count() AS customers FROM dim_customers
        WHERE acquisition_date > e - {w:UInt32} AND acquisition_platform != 'unpaid' GROUP BY platform
    """, (("w", window),))
    m = pl.merge(cu, on="platform", how="left").fillna(0)
    m["cac"] = (m.spend / m.customers.where(m.customers > 0)).round(2)
    m = m.dropna(subset=["cac"]).sort_values("cac")
    verdict = ""
    if len(m) >= 2:
        cheap, dear = m.iloc[0], m.iloc[-1]
        verdict = (f"{cheap.platform.title()} wins customers {ui.money(dear.cac - cheap.cac, 2)} cheaper "
                   f"than {dear.platform.title()}.")
    ui.compare_card("Customer cost", f"Cost to win one customer, last {window} days. Lower is better.",
                    [(f"{r.platform.title()}, {int(r.customers):,} customers", r.cac, ui.money(r.cac, 2),
                      ui.PLATFORM_COLORS.get(r.platform, ui.INK)) for r in m.itertuples()], verdict)

# ---- Every ad, judged -----------------------------------------------------------------------------------
ui.section("Ad performance", f"last {window} days")
sc = econ


def verdict_for(r) -> str:
    ratio, n = r.ltv_to_cac, r.new_customers_window or 0
    if n == 0 or (pd.notna(ratio) and ratio < 1):
        return "🔴 Losing money"
    if pd.notna(ratio) and ratio >= 2.5 and (r.cac_window or 0) <= target:
        return "🟢 Worth more budget"
    return "⚪ Doing OK"


sc = sc.assign(verdict=sc.apply(verdict_for, axis=1), platform=sc.platform.str.title())
sc = sc[["ad_name", "verdict", "platform", "spend_window", "new_customers_window", "cac_window", "ltv_estimate",
         "ltv_to_cac", "roas_window"]]
st.dataframe(
    sc, hide_index=True, width="stretch", height=min(600, 38 + 35 * len(sc)),
    column_config={
        "ad_name": st.column_config.TextColumn("Ad", width="medium"),
        "verdict": st.column_config.TextColumn("Verdict", width="medium",
                                               help="Worth more budget: customers are worth at least 2.5× what they "
                                                    "cost. Losing money: customers are worth less than they cost."),
        "platform": st.column_config.TextColumn("Where", width="small"),
        "spend_window": st.column_config.NumberColumn(plain.label("spend"), format="$%.0f"),
        "new_customers_window": st.column_config.NumberColumn("New customers", format="%d"),
        "cac_window": st.column_config.NumberColumn(plain.label("cac"), format="$%.2f", help=plain.explain("cac")),
        "ltv_estimate": st.column_config.NumberColumn(plain.label("ltv"), format="$%.2f", help=plain.explain("ltv")),
        "ltv_to_cac": st.column_config.ProgressColumn(plain.label("ltv_to_cac"), format="%.1f×", min_value=0,
                                                      max_value=float(max(4.0, sc.ltv_to_cac.max() or 0)),
                                                      help=plain.explain("ltv_to_cac")),
        "roas_window": st.column_config.NumberColumn(plain.label("roas"), format="$%.2f", help=plain.explain("roas")),
    })

ui.glossary(["spend", "paid_revenue", "roas", "new_customers", "cac", "ltv", "ltv90", "ltv_to_cac",
             "impressions", "ctr", "sessions"])
