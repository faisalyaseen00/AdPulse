-- Paid orders with last-click attribution (the session that placed the order).
CREATE OR REPLACE TABLE fct_orders
ENGINE = MergeTree ORDER BY (order_date, order_id) AS
SELECT
    o.order_id                                   AS order_id,
    o.customer_id                                AS customer_id,
    o.created_at                                 AS created_at,
    toDate(o.created_at)                         AS order_date,
    o.total                                      AS revenue,
    o.discount                                   AS discount,
    row_number() OVER (PARTITION BY o.customer_id ORDER BY o.created_at, o.order_id) AS customer_order_number,
    customer_order_number = 1                    AS is_first_order,
    if(s.session_id = '', 'unpaid', s.platform)  AS platform,
    s.ad_id                                      AS ad_id,
    if(s.session_id = '', 'direct', s.channel)   AS channel
FROM (SELECT * FROM raw_shop_orders FINAL WHERE status = 'paid') AS o
LEFT JOIN fct_sessions AS s ON s.session_id = o.session_id
SETTINGS join_use_nulls = 0
