-- One row per ad across platforms.
CREATE OR REPLACE TABLE dim_ads
ENGINE = MergeTree ORDER BY (platform, ad_id) AS
SELECT
    'meta'                    AS platform,
    ad_id,
    argMax(ad_name, date)     AS ad_name,
    argMax(campaign_id, date) AS campaign_id,
    argMax(campaign_name, date) AS campaign_name,
    'social'                  AS campaign_type,
    argMax(adset_name, date)  AS ad_group_name,
    min(date)                 AS first_active_date,
    max(date)                 AS last_active_date
FROM raw_meta_ads_insights FINAL
GROUP BY ad_id
UNION ALL
SELECT
    'google', ad_id, argMax(ad_name, date), argMax(campaign_id, date), argMax(campaign_name, date),
    argMax(campaign_type, date), argMax(ad_group_name, date), min(date), max(date)
FROM raw_google_ads_ad_performance FINAL
GROUP BY ad_id
