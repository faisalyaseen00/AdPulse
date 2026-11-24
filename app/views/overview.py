import html

import pandas as pd
import plotly.graph_objects as go
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
period = "before"

# ---- The stage: the answer in three seconds, with the trend drawing itself beside it ------------------
if roas >= 1.5:
    after = "back for every $1 you spent. A healthy return."
elif roas >= 1:
    after = "back for every $1 you spent. Ads are paying for themselves."
else:
    after = "back for every $1 you spent. Less than they cost."
rev_change = chg(k.rev, k.rev_p)
detail = (f"You spent <b>{ui.money(k.spend)}</b> and won <b>{k.cust:,.0f} new customers</b> at "
          f"<b>{ui.money(cac, 2)}</b> each. ")
if k.ltv90 and not pd.isna(k.ltv90) and cac:
    detail += (f"Each is worth about <b>{ui.money(k.ltv90, 2)}</b> in their first 90 days, "
               f"<b>{plain.times(k.ltv90 / cac)}</b> what it cost to win them. ")
if rev_change is not None:
    detail += f"Sales from ads {ui.change_text(rev_change, 'up', 'the ' + str(window) + ' days before')}."

wk = ui.q("""
    SELECT toStartOfWeek(d.date, 1) AS week, round(sum(d.spend), 2) AS spend,
           round(any(r.revenue), 2) AS revenue
    FROM fct_ad_daily d
    LEFT JOIN (SELECT toStartOfWeek(order_date, 1) AS week, sum(revenue) AS revenue FROM fct_orders
               WHERE platform != 'unpaid' GROUP BY week) r ON r.week = toStartOfWeek(d.date, 1)
    GROUP BY week ORDER BY week
""")
wk = wk.iloc[1:-1] if len(wk) > 3 else wk  # drop partial edge weeks
recent = wk.tail(26)
ui.stage(
    eyebrow=f"Last {window} days, up to {end:%B %-d, %Y}",
    lead="Your ads brought back", big=plain.per_dollar(roas), after=after, detail_html=detail,
    spark_svg=ui.sparkline(recent.revenue.astype(float).tolist(), recent.spend.astype(float).tolist()),
    legend=[("Sales from ads, weekly", "linear-gradient(90deg,#2DD4BF,#F4B400,#FF8A5B)"),
            ("Ad spend", "rgba(255,255,255,.45)")],
    mini=[(ui.money(recent.revenue.iloc[-1]), "sales last full week"),
          (ui.money(recent.spend.iloc[-1]), "spent last full week"),
          (f"{len(recent)} weeks", "shown in the line")],
)

# ---- Numbers at a glance --------------------------------------------------------------------------------
ui.kpi_row([
    ui.kpi(plain.label("spend"), ui.money(k.spend), chg(k.spend, k.spend_p), "neutral", help=plain.explain("spend"),
           period=period),
    ui.kpi(plain.label("paid_revenue"), ui.money(k.rev), chg(k.rev, k.rev_p), help=plain.explain("paid_revenue"),
           period=period),
    ui.kpi(plain.label("roas"), plain.per_dollar(roas), chg(roas, roas_p), help=plain.explain("roas"), period=period),
    ui.kpi(plain.label("new_customers"), f"{k.cust:,.0f}", chg(k.cust, k.cust_p), help=plain.explain("new_customers"),
           period=period),
    ui.kpi(plain.label("cac"), ui.money(cac, 2), chg(cac, cac_p), "down", help=plain.explain("cac"), period=period),
    ui.kpi(plain.label("ltv90"), ui.money(k.ltv90, 2), note="per customer, first 90 days", help=plain.explain("ltv90")),
])


# ---- What to do this week -------------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def wasted(days: int) -> dict:
    return search_terms.summary(search_terms.audit(days, llm=None))


pending = ui.suggestions()
pending = pending[pending.status == "pending"] if not pending.empty else pending
items = []
if not pending.empty:
    scale = pending[pending.kind == "scale_ad"].sort_values("est_impact", ascending=False)
    pause = pending[pending.kind == "pause_ad"].sort_values("est_impact", ascending=False)
    if not scale.empty:
        r = scale.iloc[0]
        m = r.metrics
        items.append(("good", f"Give “{r.entity_name}” more budget",
                      (f"Each new customer from this ad costs {ui.money(m.get('cac_window'), 2)} and is worth "
                       f"about {ui.money(m.get('ltv_estimate'), 2)}."),
                      f"+{ui.money(r.est_impact)}", "extra customer value / month"))
    if not pause.empty:
        r = pause.iloc[0]
        m = r.metrics
        detail = (f"Each new customer costs {ui.money(m.get('cac_window'), 2)} but only spends "
                  f"{ui.money(m.get('ltv_estimate'), 2)}." if m.get("new_customers_window")
                  else f"It spent {ui.money(m.get('spend_window'))} without winning a single new customer.")
        items.append(("bad", f"Pause “{r.entity_name}”", detail, ui.money(r.est_impact), "saved / month"))
w = wasted(30)
if w["flagged"]:
    items.append(("warn", f"Block {w['flagged']} searches that never turn into sales",
                  "People searching for jobs, free samples or store hours are clicking your ads.",
                  ui.money(w["wasted_spend"]), "wasted in 30 days"))

ui.section("What to do this week", "nothing changes until you approve it")
if items:
    ui.todo(items)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.page_link("views/recommendations.py", label="Review suggestions", icon=":material/task_alt:")
    b2.page_link("views/audit.py", label="See wasted searches", icon=":material/money_off:")
else:
    st.success("Nothing needs your attention right now.")

# ---- From ad to customer --------------------------------------------------------------------------------
ui.section("From ad to customer", f"last {window} days")
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

# ---- Charts ---------------------------------------------------------------------------------------------
c1, c2 = st.columns([3, 2])
with c1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=wk.week, y=wk.revenue, name="Sales from ads", mode="lines",
                             line={"color": ui.SERIES[1], "width": 2.5}, hovertemplate="$%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=wk.week, y=wk.spend, name="Ad spend", mode="lines",
                             line={"color": ui.SERIES[0], "width": 2.5}, hovertemplate="$%{y:,.0f}"))
    fig.update_layout(title="Ad spend and the sales it brought in, by week", hovermode="x unified")
    st.plotly_chart(ui.style_fig(fig, money_axis=True), width="stretch")
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
    fig = go.Figure(go.Bar(x=m.platform.str.title(), y=m.cac, marker_color=[ui.PLATFORM_COLORS[p] for p in m.platform],
                           text=[ui.money(v, 2) for v in m.cac], textposition="outside",
                           customdata=m[["spend", "customers"]],
                           hovertemplate="Cost per new customer $%{y:,.2f}<br>Ad spend $%{customdata[0]:,.0f}<br>"
                                         "New customers %{customdata[1]:,.0f}<extra></extra>"))
    fig.update_layout(title="Cost to win one new customer", showlegend=False)
    st.plotly_chart(ui.style_fig(fig, money_axis=True), width="stretch")

# ---- Every ad, judged -----------------------------------------------------------------------------------
ui.section("How each ad is doing", f"last {window} days")
target = get_settings().target_cac
sc = ui.ad_economics(window)


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
