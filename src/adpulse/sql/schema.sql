-- =====================================================================
-- RAW LAYER: exactly what Airbyte lands (one table per source stream).
-- ReplacingMergeTree keyed on the natural key makes re-syncs idempotent.
-- =====================================================================

CREATE TABLE IF NOT EXISTS raw_meta_ads_insights
(
    date              Date,
    account_id        String,
    campaign_id       String,
    campaign_name     String,
    adset_id          String,
    adset_name        String,
    ad_id             String,
    ad_name           String,
    impressions       UInt64,
    clicks            UInt64,
    spend             Float64,
    purchases         UInt32 COMMENT 'Meta-reported purchases (platform attribution, inflated)',
    _airbyte_extracted_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_airbyte_extracted_at)
ORDER BY (ad_id, date);

CREATE TABLE IF NOT EXISTS raw_google_ads_ad_performance
(
    date              Date,
    customer_id       String,
    campaign_id       String,
    campaign_name     String,
    campaign_type     String,
    ad_group_id       String,
    ad_group_name     String,
    ad_id             String,
    ad_name           String,
    impressions       UInt64,
    clicks            UInt64,
    cost_micros       Int64,
    conversions       Float64 COMMENT 'Google-reported conversions (platform attribution)',
    _airbyte_extracted_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_airbyte_extracted_at)
ORDER BY (ad_id, date);

CREATE TABLE IF NOT EXISTS raw_google_ads_search_terms
(
    date              Date,
    campaign_id       String,
    campaign_name     String,
    ad_group_id       String,
    ad_group_name     String,
    search_term       String,
    match_type        String,
    impressions       UInt64,
    clicks            UInt64,
    cost_micros       Int64,
    conversions       Float64,
    conversions_value Float64,
    _airbyte_extracted_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_airbyte_extracted_at)
ORDER BY (ad_group_id, search_term, date);

CREATE TABLE IF NOT EXISTS raw_ga4_sessions
(
    session_id        String,
    user_pseudo_id    String,
    session_start     DateTime,
    source            String,
    medium            String,
    campaign          String,
    ad_content        String COMMENT 'utm_content = platform ad id for paid traffic',
    click_id          String COMMENT 'gclid / fbclid',
    landing_page      String,
    device            String,
    _airbyte_extracted_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_airbyte_extracted_at)
ORDER BY session_id;

CREATE TABLE IF NOT EXISTS raw_shop_orders
(
    order_id          String,
    customer_id       String,
    session_id        String,
    created_at        DateTime,
    subtotal          Float64,
    discount          Float64,
    total             Float64,
    currency          String,
    status            String COMMENT 'paid | refunded',
    _airbyte_extracted_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_airbyte_extracted_at)
ORDER BY order_id;

CREATE TABLE IF NOT EXISTS raw_shop_customers
(
    customer_id       String,
    created_at        DateTime,
    country           String,
    accepts_marketing UInt8,
    _airbyte_extracted_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_airbyte_extracted_at)
ORDER BY customer_id;

-- =====================================================================
-- APP LAYER: operational state (not visible to the agent's read-only user)
-- =====================================================================

CREATE TABLE IF NOT EXISTS app_sync_runs
(
    run_id       String,
    source       String,
    stream       String,
    target_table String,
    mode         String,
    rows         UInt64,
    status       String,
    error        String,
    started_at   DateTime64(3),
    finished_at  DateTime64(3)
)
ENGINE = MergeTree
ORDER BY (started_at, run_id);

CREATE TABLE IF NOT EXISTS app_recommendations
(
    id            String,
    created_at    DateTime,
    kind          LowCardinality(String) COMMENT 'pause_ad | scale_ad | negative_keyword',
    platform      LowCardinality(String),
    entity_id     String,
    entity_name   String,
    campaign_name String,
    reason        String,
    metrics       String COMMENT 'JSON evidence',
    est_impact    Float64 COMMENT 'estimated monthly $ impact',
    status        LowCardinality(String) COMMENT 'pending | approved | rejected | applied',
    decided_by    String,
    decided_at    Nullable(DateTime),
    note          String,
    source        LowCardinality(String) COMMENT 'rules | audit | agent',
    version       UInt64
)
ENGINE = ReplacingMergeTree(version)
ORDER BY id;

CREATE TABLE IF NOT EXISTS app_reports
(
    id           String,
    created_at   DateTime,
    period_start Date,
    period_end   Date,
    payload      String,
    markdown     String,
    channels     String,
    status       String
)
ENGINE = MergeTree
ORDER BY created_at;

CREATE TABLE IF NOT EXISTS app_questions
(
    id             String,
    asked_at       DateTime64(3),
    question       String,
    sql            String,
    answer         String,
    verified       UInt8,
    critic_verdict String,
    numbers_checked UInt16,
    numbers_verified UInt16,
    attempts       UInt8,
    latency_ms     UInt32,
    provider       String,
    error          String
)
ENGINE = MergeTree
ORDER BY asked_at;
