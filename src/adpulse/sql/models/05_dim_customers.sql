-- One row per customer: acquisition source (first order's ad) + lifetime value.
CREATE OR REPLACE TABLE dim_customers
ENGINE = MergeTree ORDER BY customer_id AS
WITH firsts AS (
    SELECT customer_id, min(created_at) AS first_at FROM fct_orders GROUP BY customer_id
)
SELECT
    o.customer_id                                           AS customer_id,
    any(f.first_at)                                         AS first_order_at,
    toDate(first_order_at)                                  AS acquisition_date,
    toStartOfMonth(first_order_at)                          AS acquisition_month,
    argMin(o.platform, o.customer_order_number)             AS acquisition_platform,
    argMin(o.ad_id, o.customer_order_number)                AS acquisition_ad_id,
    argMin(o.channel, o.customer_order_number)              AS acquisition_channel,
    argMin(o.revenue, o.customer_order_number)              AS first_order_value,
    count()                                                 AS orders_count,
    round(sum(o.revenue), 2)                                AS ltv,
    round(sumIf(o.revenue, o.created_at < f.first_at + INTERVAL 90 DAY), 2) AS ltv_90d,
    max(o.created_at)                                       AS last_order_at,
    dateDiff('day', first_order_at, (SELECT max(created_at) FROM fct_orders)) AS customer_age_days
FROM fct_orders AS o
INNER JOIN firsts AS f ON f.customer_id = o.customer_id
GROUP BY o.customer_id
