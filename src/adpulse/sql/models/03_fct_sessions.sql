-- Web sessions with the paid channel resolved from UTM parameters.
CREATE OR REPLACE TABLE fct_sessions
ENGINE = MergeTree ORDER BY (session_start, session_id) AS
SELECT
    session_id,
    user_pseudo_id,
    session_start,
    toDate(session_start) AS session_date,
    multiIf(source IN ('facebook', 'instagram', 'meta') AND medium IN ('paid_social', 'cpc'), 'meta',
            source = 'google' AND medium = 'cpc', 'google',
            'unpaid') AS platform,
    if(platform = 'unpaid', '', ad_content) AS ad_id,
    multiIf(platform != 'unpaid', 'paid', medium = 'email', 'email', medium = 'organic', 'organic', 'direct') AS channel,
    source, medium, campaign, landing_page, device
FROM raw_ga4_sessions FINAL
