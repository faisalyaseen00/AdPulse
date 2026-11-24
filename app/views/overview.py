import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import ui

ui.hero("Overview", "Ads → clicks → customers → revenue → lifetime value, from the warehouse.", icon="📊")
if not ui.require_warehouse():
    st.stop()

window = st.segmented_control("Window", [7, 30, 90], default=30, format_func=lambda d: f"Last {d} days",
                              label_visibility="collapsed") or 30

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
st.caption(f"Data through **{pd.Timestamp(k.end_date):%b %d, %Y}** · compared with the prior {window} days")
ui.kpi_row([
    ui.kpi("Ad spend", ui.money(k.spend), chg(k.spend, k.spend_p), "down"),
    ui.kpi("Paid revenue", ui.money(k.rev), chg(k.rev, k.rev_p)),
    ui.kpi("ROAS", f"{roas:.2f}x", chg(roas, roas_p)),
    ui.kpi("New paid customers", f"{k.cust:,.0f}", chg(k.cust, k.cust_p)),
    ui.kpi("Blended CAC", ui.money(cac, 2), chg(cac, cac_p), "down"),
    ui.kpi("90-day LTV", ui.money(k.ltv90, 2), note="mature paid customers"),
])

ui.section("Funnel", "paid traffic, same window")
flow = [("Impressions", f"{k.impressions:,.0f}", ""), ("Clicks", f"{k.clicks:,.0f}",
        f"CTR {k.clicks / k.impressions:.2%}" if k.impressions else ""),
        ("Sessions", f"{k.sessions:,.0f}", f"{k.sessions / k.clicks:.0%} of clicks" if k.clicks else ""),
        ("New customers", f"{k.cust:,.0f}", f"CVR {k.cust / k.sessions:.2%}" if k.sessions else ""),
        ("Revenue", ui.money(k.rev), f"ROAS {roas:.2f}x"), ("90-day LTV", ui.money(k.ltv90, 2), "per customer")]
st.html('<div class="ap-flow">' + '<div class="arr">→</div>'.join(
    f'<div class="node"><div class="t">{t}</div><div class="v">{v}</div><div class="s">{s}</div></div>'
    for t, v, s in flow) + "</div>")

c1, c2 = st.columns([3, 2])
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
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=wk.week, y=wk.spend, name="Ad spend", mode="lines",
                             line={"color": ui.SERIES[0], "width": 2}, hovertemplate="$%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=wk.week, y=wk.revenue, name="Attributed revenue", mode="lines",
                             line={"color": ui.SERIES[1], "width": 2}, hovertemplate="$%{y:,.0f}"))
    fig.update_layout(title="Weekly spend vs. attributed revenue", hovermode="x unified")
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
                           hovertemplate="CAC $%{y:,.2f}<br>Spend $%{customdata[0]:,.0f}<br>"
                                         "Customers %{customdata[1]:,.0f}<extra></extra>"))
    fig.update_layout(title="CAC by platform", showlegend=False)
    st.plotly_chart(ui.style_fig(fig, money_axis=True), width="stretch")

ui.section("Ad scorecard", f"spend and CAC over the last {window} days")
st.caption("LTV is the 90-day value of each ad's mature customers (or lifetime value when none are 90 days old yet).")
from adpulse.actions.recommendations import ad_economics

sc = ad_economics(window)
sc = sc[["ad_name", "platform", "campaign_name", "spend_window", "new_customers_window", "cac_window",
         "ltv_estimate", "ltv_to_cac", "roas_window"]]
st.dataframe(
    sc, hide_index=True, width="stretch", height=min(560, 38 + 35 * len(sc)),
    column_config={
        "ad_name": st.column_config.TextColumn("Ad", width="medium"),
        "platform": st.column_config.TextColumn("Platform", width="small"),
        "campaign_name": "Campaign",
        "spend_window": st.column_config.NumberColumn("Spend", format="$%.2f"),
        "new_customers_window": st.column_config.NumberColumn("New customers", format="%d"),
        "cac_window": st.column_config.NumberColumn("CAC", format="$%.2f"),
        "ltv_estimate": st.column_config.NumberColumn("LTV", format="$%.2f"),
        "ltv_to_cac": st.column_config.ProgressColumn("LTV : CAC", format="%.2f", min_value=0,
                                                      max_value=float(max(4.0, sc.ltv_to_cac.max() or 0))),
        "roas_window": st.column_config.NumberColumn("ROAS", format="%.2fx"),
    })
