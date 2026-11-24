-- Monthly ad scorecard: spend -> clicks -> new customers -> revenue -> LTV.
CREATE OR REPLACE TABLE mart_ad_monthly
ENGINE = MergeTree ORDER BY (month, platform, ad_id) AS
WITH
spend AS (
    SELECT toStartOfMonth(date) AS month, platform, ad_id,
           sum(impressions) AS impressions, sum(clicks) AS clicks, round(sum(spend), 2) AS spend,
           sum(platform_conversions) AS platform_conversions
    FROM fct_ad_daily GROUP BY month, platform, ad_id
),
acq AS (
    SELECT acquisition_month AS month, acquisition_platform AS platform, acquisition_ad_id AS ad_id,
           count() AS new_customers, round(sum(first_order_value), 2) AS first_order_revenue,
           round(sum(ltv), 2) AS cohort_ltv, round(sum(ltv_90d), 2) AS cohort_ltv_90d
    FROM dim_customers WHERE acquisition_platform != 'unpaid'
    GROUP BY month, platform, ad_id
),
rev AS (
    SELECT toStartOfMonth(order_date) AS month, platform, ad_id,
           count() AS attributed_orders, round(sum(revenue), 2) AS attributed_revenue
    FROM fct_orders WHERE platform != 'unpaid'
    GROUP BY month, platform, ad_id
)
SELECT
    s.month AS month, s.platform AS platform, s.ad_id AS ad_id,
    d.ad_name AS ad_name, d.campaign_name AS campaign_name,
    s.impressions AS impressions, s.clicks AS clicks, s.spend AS spend,
    s.platform_conversions AS platform_conversions,
    r.attributed_orders AS attributed_orders, r.attributed_revenue AS attributed_revenue,
    a.new_customers AS new_customers, a.first_order_revenue AS first_order_revenue,
    a.cohort_ltv AS cohort_ltv, a.cohort_ltv_90d AS cohort_ltv_90d,
    if(a.new_customers > 0, round(a.cohort_ltv / a.new_customers, 2), 0) AS avg_ltv,
    if(a.new_customers > 0, round(s.spend / a.new_customers, 2), 0) AS cac,
    if(s.spend > 0, round(r.attributed_revenue / s.spend, 3), 0) AS roas,
    if(s.spend > 0, round(a.cohort_ltv / s.spend, 3), 0) AS ltv_roas
FROM spend s
LEFT JOIN acq a ON a.month = s.month AND a.platform = s.platform AND a.ad_id = s.ad_id
LEFT JOIN rev r ON r.month = s.month AND r.platform = s.platform AND r.ad_id = s.ad_id
LEFT JOIN dim_ads d ON d.platform = s.platform AND d.ad_id = s.ad_id
SETTINGS join_use_nulls = 0
