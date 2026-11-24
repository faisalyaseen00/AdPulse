-- Google search terms in dollars.
CREATE OR REPLACE TABLE fct_search_terms
ENGINE = MergeTree ORDER BY (date, campaign_name, search_term) AS
SELECT date, campaign_id, campaign_name, ad_group_id, ad_group_name,
       lower(trim(search_term)) AS search_term, match_type,
       impressions, clicks, round(cost_micros / 1e6, 2) AS cost, conversions, conversions_value
FROM raw_google_ads_search_terms FINAL
