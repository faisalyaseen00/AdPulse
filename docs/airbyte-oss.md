# Running with Airbyte OSS (web UI)

AdPulse's default ingestion uses **PyAirbyte**: the same open-source Airbyte connectors, run as
Python processes. If you want the full Airbyte platform (scheduling, web UI, connection history),
run Airbyte OSS next to ClickHouse. The rest of AdPulse is unchanged because it only reads the `raw_*` tables.

> Airbyte OSS runs a small Kubernetes cluster via `abctl` and needs about 8 GB of free RAM.

## 1. Install and start Airbyte

```bash
curl -LsfS https://get.airbyte.com | bash -
```

```bash
abctl local install
```

```bash
abctl local credentials        # login for http://localhost:8000
```

## 2. Destination: ClickHouse

In Airbyte → **Destinations → ClickHouse**:

| Field | Value |
|---|---|
| Host | `host.docker.internal` (ClickHouse from `docker compose`) |
| Port | `8123` |
| Database | `adpulse` |
| Username / password | `adpulse` / `adpulse` (the admin user from `.env`) |

## 3. Sources

| AdPulse table | Airbyte source | Stream |
|---|---|---|
| `raw_meta_ads_insights` | Facebook Marketing | `ads_insights` |
| `raw_google_ads_ad_performance` | Google Ads | `ad_group_ad_legacy` |
| `raw_google_ads_search_terms` | Google Ads | `search_term_view` |
| `raw_ga4_sessions` | Google Analytics 4 | custom report: sessionId, source, medium, campaign, adContent |
| `raw_shop_orders`, `raw_shop_customers` | Shopify | `orders`, `customers` |

For the demo dataset use the **File** source (`local` storage, CSV) on each file in `data/demo/`.

Set each connection's **stream prefix / table name** to the AdPulse table name, or point a view at
Airbyte's output table, for example:

```sql
CREATE VIEW adpulse.raw_meta_ads_insights AS
SELECT toDate(date_start) AS date, account_id, campaign_id, campaign_name, adset_id, adset_name,
       ad_id, ad_name, toUInt64(impressions) AS impressions, toUInt64(clicks) AS clicks,
       toFloat64(spend) AS spend, 0 AS purchases, _airbyte_extracted_at
FROM airbyte_internal.ads_insights;
```

Column mappings for each stream are listed in `src/adpulse/pipeline/connections.yaml`.

## 4. After each sync

```bash
adpulse transform
```

Or schedule it right after the Airbyte sync. That rebuilds the models the agent reads from.
