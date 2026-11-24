-- Daily delivery + spend per ad, in dollars, both platforms.
CREATE OR REPLACE TABLE fct_ad_daily
ENGINE = MergeTree ORDER BY (date, platform, ad_id) AS
SELECT date, 'meta' AS platform, ad_id, campaign_id, impressions, clicks,
       round(spend, 2) AS spend, toFloat64(purchases) AS platform_conversions
FROM raw_meta_ads_insights FINAL
UNION ALL
SELECT date, 'google', ad_id, campaign_id, impressions, clicks,
       round(cost_micros / 1e6, 2), conversions
FROM raw_google_ads_ad_performance FINAL
