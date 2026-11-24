# AdPulse

**A marketing data agent on a ClickHouse warehouse.** AdPulse pulls ad, analytics and sales data into
one warehouse. Ask it questions in plain English, like *"which ads brought customers with the highest
LTV last month?"*, and it answers from real data with every number checked. It then suggests which
ads to pause or scale, and a human approves each suggestion.

```
 Meta Ads ─┐
 Google Ads┤   Airbyte        ClickHouse                                    Streamlit
 GA4 ──────┼─► (PyAirbyte ─► raw_* tables ─► dim_/fct_/mart_ models ─► agent ─► chat · audit · approvals
 Shopify ──┘    or OSS)       (idempotent)    (ads→clicks→sales→LTV)     │       weekly report ─► Slack / email
                                                                         └─ read-only DB user + SQL guard
```

## What it does

| Feature | How |
|---|---|
| **Data into one warehouse** | Airbyte connectors (PyAirbyte, or Airbyte OSS) land Meta Ads, Google Ads, GA4 and Shopify streams in `raw_*` tables. SQL models build `dim_ads`, `fct_ad_daily`, `fct_sessions`, `fct_orders`, `dim_customers`, `mart_ad_monthly`, `fct_search_terms`. |
| **Ads → clicks → sales → revenue → LTV** | UTM `utm_content` = ad id links each click to a session. The session that places an order gets the credit (last-click). A customer's first order sets their acquisition ad, so lifetime value rolls up to the ad that bought them. |
| **Agent writes SQL, warehouse does the math** | The LLM writes one ClickHouse `SELECT`. A static guard allows only read-only queries on approved tables. The query runs as a `readonly=1` ClickHouse user with server-side time and row limits. Failed queries go back to the model for repair. |
| **Critic step** | A second LLM pass reviews the SQL and result: time window, metric definitions, join fan-out, attribution, plausibility. If it fails the query, the SQL is rewritten with the critic's feedback. |
| **Every number is checked** | Each number in the answer must match a result cell or column total at the precision it was printed. Derived figures ("3.6x", "+42%") must be declared with their arithmetic. The verifier checks the operands are real values and recomputes the result. Unverified numbers trigger a rewrite. The UI shows the check per number. |
| **Search term audit** | Rules (jobs, free, DIY, support, local, wholesale, competitor…) plus optional LLM classification flag Google search terms with no buyer intent and suggest the narrowest negative keyword. |
| **Pause / scale suggestions** | Rules compare recent CAC with the LTV each ad's customers historically reach. Suggestions from rules, the audit and the chat all go to one **approval queue**: approve or reject with a reviewer name, then "mark applied". **AdPulse never changes spend itself.** Each approval shows the exact Meta / Google Ads API change to make. |
| **Weekly report** | KPIs come from fixed SQL (no LLM math). Optional AI commentary must pass the same number check. Delivered to Slack (Block Kit) and/or email, with history. |

## Quick start

Requirements: Python 3.10+ and Docker.

```bash
git clone https://github.com/faisalyaseen00/AdPulse.git adpulse && cd adpulse
```

```bash
make install            # venv + dependencies
```

```bash
cp .env.example .env    # then add ANTHROPIC_API_KEY, GROQ_API_KEY or OPENROUTER_API_KEY
```

```bash
make db                 # ClickHouse in Docker (docker compose up -d clickhouse)
```

```bash
make setup              # generate demo data → load → build models → first recommendations
```

```bash
make ui                 # http://localhost:8501
```

The whole stack in Docker: `docker compose up -d --build`, then run `adpulse setup` inside the `app` container.

### LLM

Set `LLM_PROVIDER` to `anthropic` (model `claude-opus-5-5`), `groq` (default model `openai/gpt-oss-120b`)
or `openrouter`, and fill in the matching `*_API_KEY`. Groq and OpenRouter use JSON-schema output when the
model supports it, fall back to JSON mode otherwise, and get one repair round if the reply fails validation.
The Claude client uses structured outputs, prompt caching on the large schema prompt, and the
server-side refusal fallback (`ANTHROPIC_FALLBACKS=true`). Without a key, every page except chat
still works: dashboards, the audit (rules only), approvals and reports (template commentary).

### Real Airbyte connectors

```bash
make install-airbyte                 # PyAirbyte
```

```bash
adpulse ingest --mode airbyte        # demo CSVs through the official source-file connector
```

To connect real accounts, enable a block under `live:` in
[`src/adpulse/pipeline/connections.yaml`](src/adpulse/pipeline/connections.yaml) and set its env vars
(`META_ACCESS_TOKEN`, `GOOGLE_ADS_*`, `SHOPIFY_*`). For the full Airbyte OSS UI with its ClickHouse
destination, see [docs/airbyte-oss.md](docs/airbyte-oss.md).

## CLI

```
adpulse setup                 demo data → warehouse → models → recommendations
adpulse sync --mode airbyte   init-db + ingest + transform
adpulse ask "which ads brought customers with the highest LTV last month?"
adpulse audit --days 30 --save
adpulse recommend
adpulse report --send         schedule with cron: 0 8 * * MON
adpulse ui
```

## Demo data

`adpulse demo-data` generates a reproducible 180-day dataset for a fictional DTC coffee brand: 14 ads,
~485k sessions, ~27k orders. Each ad has its own economics, so there are real findings to make:

- **Static - 20% Off** buys cheap customers who rarely come back (lowest LTV).
- **RSA - Coffee Subscription** and **UGC Video - Morning Routine** bring high-LTV subscribers.
- **Search - Competitor** pays $3+ CPCs for almost no buyers.
- **Carousel - Bestsellers** fatigues: its conversion rate decays over the period.
- Generic search leaks ~40% of its spend on jobs / free-sample / DIY queries.
- Ad platforms over-report conversions compared with warehouse orders.

## Safety model

1. **SQL guard** (`agent/sql_guard.py`): single `SELECT`/`WITH`, approved tables only, no table
   functions (`url`, `s3`, `remote`, `file`…), no other databases.
2. **Read-only ClickHouse user** with `readonly=1`, `max_execution_time` and `max_result_rows` set
   on the user, so generated SQL cannot raise them. The user cannot read the app's own `app_*` tables.
3. **No auto-spend**: recommendations are proposals. Pending → approved/rejected (reviewer recorded) →
   applied (separate, explicit step).
4. Every question is logged in `app_questions` with its SQL, verdict and number check.

## Tests

```bash
make test
```

50 tests: SQL guard, number verifier (including a random-number false-acceptance check), audit rules,
the full agent loop against the live warehouse with a scripted LLM (repair, guard rejection, critic
retry, hallucination rewrite, read-only user), and a headless render of every UI page.

## Project layout

```
src/adpulse/
  pipeline/   demo_data.py · ingest.py (PyAirbyte / direct) · transform.py · connections.yaml
  sql/        schema.sql (raw + app tables) · models/*.sql (dim_/fct_/mart_)
  agent/      core.py (loop) · prompts.py · semantic.yaml · sql_guard.py · verify.py · schemas.py
  llm/        anthropic_llm.py · openai_compat.py (Groq, OpenRouter) · fake.py
  audit/      search_terms.py
  actions/    recommendations.py (rules + approval workflow + change payloads)
  reports/    weekly.py · delivery.py (Slack, SMTP)
  cli.py
app/          Streamlit: main.py + views/ (overview, ask, audit, approvals, report, pipeline)
tests/
docs/         airbyte-oss.md · loom-script.md
```
