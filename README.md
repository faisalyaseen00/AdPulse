# AdPulse

**A marketing data agent on a ClickHouse warehouse.** AdPulse pulls ad, analytics and sales data into
one warehouse. Ask it questions in plain English, like *"which ads brought customers with the highest
LTV last month?"*, and it answers from real data with every number checked. It suggests which ads to
pause or scale and which searches to block, and a person approves each suggestion. Every Monday it sends
a summary to Slack or email.

```
 Meta Ads ─┐
 Google Ads┤  Airbyte          ClickHouse                                 FastAPI (api/)       React (web/)
 GA4 ──────┼─► (PyAirbyte ─► raw_* tables ─► dim_/fct_/mart_ models ─► agent, audit, ─► JSON ─► Overview · Ask ·
 Shopify ──┘   or OSS)        (idempotent)   (ads→clicks→sales→LTV)    approvals,              Suggestions · Wasted
                                                                       weekly report           searches · Report ·
                                                     read-only DB user + SQL guard              Data · Present
                                                                       │
                                                  GitHub Actions ──────┴─► Monday report ─► Slack / email
```

## What it does

| Feature | How |
|---|---|
| **Data into one warehouse** | Airbyte connectors (PyAirbyte, or Airbyte OSS) land Meta Ads, Google Ads, GA4 and Shopify streams in `raw_*` tables. SQL models build `dim_ads`, `fct_ad_daily`, `fct_sessions`, `fct_orders`, `dim_customers`, `mart_ad_monthly`, `fct_search_terms`. |
| **Ads → clicks → sales → revenue → LTV** | UTM `utm_content` = ad id links each click to a session. The session that places an order gets the credit (last-click). A customer's first order sets their acquisition ad, so lifetime value rolls up to the ad that bought them. |
| **Agent writes SQL, warehouse does the math** | The LLM writes one ClickHouse `SELECT`. A static guard allows only read-only queries on approved tables. The query runs as a `readonly=1` ClickHouse user with server-side time and row limits. Failed queries go back to the model for repair. |
| **Critic step** | A second LLM pass reviews the SQL and result: time window, metric definitions, join fan-out, attribution, plausibility. If it fails the query, the SQL is rewritten with the critic's feedback. |
| **Every number is checked** | Each number in the answer must match a result cell or column total at the precision it was printed. Derived figures ("3.6x", "+42%") must be declared with their arithmetic; the verifier recomputes them. Unverified numbers trigger a rewrite, and the app shows the check for each number. |
| **Wasted searches** | Rules (jobs, free, DIY, support, local, wholesale, competitor…) plus optional AI classification flag Google search terms with no buyer intent and suggest the narrowest negative keyword. |
| **Recommended changes** | Rules compare recent cost per customer with the value each ad's customers reach. Suggestions from rules, the search review and the chat share one queue: approve or reject with a reviewer name, then mark as done. **AdPulse never changes spend itself.** Each approved change shows the exact Meta / Google Ads API change to make. |
| **Weekly report** | Figures come from fixed SQL (no LLM math). Optional AI commentary must pass the same number check. Send to Slack or email from the app, or automatically every Monday. |
| **Client presentation** | `/present` turns the live figures into a nine-slide, full-screen deck (arrow keys, F for full screen, Esc to leave). |
| **Plain English** | Every page, answer and report uses everyday words from one glossary (`adpulse/plain.py`): "back per $1" instead of ROAS, "cost per new customer" instead of CAC. |

## How it is built

| Part | Folder | Runs on | Notes |
|---|---|---|---|
| Web app | `web/` | **Vercel** | React 19, Vite, TypeScript, Tailwind CSS 4, TanStack Query, Recharts, Three.js robot. Talks only to the API; no keys in the browser. |
| HTTP API | `api/` | **Railway** (Docker) | FastAPI. A thin layer over `src/adpulse`; it adds no business logic of its own. |
| Core package | `src/adpulse/` | inside the API, the CLI and GitHub Actions | Pipeline, SQL models, agent, audit, approvals, reports. |
| Warehouse | n/a | **ClickHouse Cloud** | Admin user for loading, separate read-only user for the agent. |
| Monday report | `.github/workflows/weekly-report.yml` | **GitHub Actions** | Secret `ADPULSE_SECRETS`. |
| Previous UI | `app/` | Streamlit Community Cloud | Kept working for comparison and rollback; not needed for the new deployment. |

## Run it locally

Requirements: Python 3.10+, Node 20+, Docker (for a local ClickHouse; skip if you point `.env` at ClickHouse Cloud).

```bash
git clone https://github.com/faisalyaseen00/AdPulse.git adpulse && cd adpulse
```

```bash
make install            # Python venv + AdPulse + API + dev tools
```

```bash
cp .env.example .env    # add GROQ_API_KEY (or ANTHROPIC_API_KEY / OPENROUTER_API_KEY) and database details
```

```bash
make db                 # local ClickHouse in Docker
```

```bash
make setup              # demo data → load → build models → first recommendations
```

Then, in two terminals:

```bash
make api                # http://localhost:8000  (API docs at /docs)
```

```bash
make web-install && make web    # http://localhost:5173
```

In development Vite forwards `/api` to `localhost:8000`, so no web environment variables are needed.

## Deploy

The production setup is **Vercel (web) + Railway (API) + ClickHouse Cloud (data) + GitHub Actions (Monday report)**.
Step-by-step guide: [docs/deploy-vercel-railway.md](docs/deploy-vercel-railway.md).
(The earlier Render setup still works: [docs/deploy-vercel-render.md](docs/deploy-vercel-render.md).)

In short:

1. **ClickHouse Cloud** is already set up if the Streamlit app or the weekly report runs today. Otherwise follow
   [docs/deploy-streamlit-cloud.md](docs/deploy-streamlit-cloud.md) up to "Load the data".
2. **API on Railway:** New Project → Deploy from GitHub repo → this repository. Railway reads
   [`railway.json`](railway.json) and builds [`Dockerfile.api`](Dockerfile.api) (health check `/healthz`). Paste the
   secret values (ClickHouse, Groq, Slack) under Variables, then Settings → Networking → Generate Domain.
3. **Web on Vercel:** Add New → Project → this repository, **Root Directory `web`**. Set
   `VITE_API_URL` to the Railway address (for example `https://adpulse-api-production.up.railway.app`) and deploy.
4. **Back on Railway:** set `ADPULSE_CORS_ORIGINS` to the Vercel address so the browser may call the API.

Other options: one Ubuntu server with Docker ([docs/deploy-server.md](docs/deploy-server.md)), or the earlier
Streamlit-only setup ([docs/deploy-streamlit-cloud.md](docs/deploy-streamlit-cloud.md)).

## Configuration

All settings are environment variables (locally in `.env`; in production in the Railway dashboard).
[`.env.example`](.env.example) lists every one. The ones that matter most:

| Variable | Where | What |
|---|---|---|
| `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_SECURE` | API | Warehouse address (ClickHouse Cloud: port `8443`, secure `true`). |
| `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD` | API | Admin user: loads data and stores suggestions and reports. |
| `CLICKHOUSE_READER_USER`, `CLICKHOUSE_READER_PASSWORD` | API | Read-only user the AI's queries run as. |
| `LLM_PROVIDER` + `GROQ_API_KEY` / `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` | API | The AI assistant. Without a key, everything except Ask still works. |
| `SLACK_WEBHOOK_URL` or `SLACK_BOT_TOKEN` + `SLACK_CHANNEL` | API, GitHub Actions | Weekly report to Slack. |
| `SMTP_*`, `REPORT_EMAIL_FROM`, `REPORT_EMAIL_TO` | API, GitHub Actions | Weekly report by email (optional). |
| `ADPULSE_CORS_ORIGINS` | API | Web addresses allowed to call the API, comma-separated. |
| `ADPULSE_CORS_REGEX` | API | Pattern for Vercel preview URLs. Default `https://adpulse[a-z0-9-]*\.vercel\.app`. |
| `VITE_API_URL` | Vercel | Public address of the API. Baked in at build time; redeploy after changing it. |

### AI provider

Set `LLM_PROVIDER` to `anthropic` (model `claude-opus-5-5`), `groq` (default model `openai/gpt-oss-120b`)
or `openrouter`, and fill in the matching `*_API_KEY`. Groq and OpenRouter use JSON-schema output when the
model supports it and fall back to JSON mode otherwise. The Claude client uses structured outputs and
prompt caching on the large schema prompt.

### Weekly report

- **Slack:** `SLACK_WEBHOOK_URL` (Incoming Webhook) or `SLACK_BOT_TOKEN` + `SLACK_CHANNEL`. If the bot token
  fails, delivery falls back to the webhook.
- **Email (Gmail):** create an App Password at <https://myaccount.google.com/apppasswords>, then run
  `scripts/setup_email.sh`. Other providers: `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` (`starttls` / `ssl`).
- **Schedule:** GitHub Actions runs `adpulse report --send` every Monday. To run your own scheduler instead:
  `adpulse scheduler` (`--next` shows the next run, `--once` runs now).

### Real Airbyte connectors

```bash
make install-airbyte
```

```bash
adpulse ingest --mode airbyte
```

To connect real accounts, enable a block under `live:` in
[`src/adpulse/pipeline/connections.yaml`](src/adpulse/pipeline/connections.yaml) and set its env vars
(`META_ACCESS_TOKEN`, `GOOGLE_ADS_*`, `SHOPIFY_*`). For the Airbyte OSS UI with its ClickHouse destination,
see [docs/airbyte-oss.md](docs/airbyte-oss.md).

## CLI

```
adpulse setup                 demo data → warehouse → models → recommendations
adpulse sync --mode airbyte   init-db + ingest + transform
adpulse ask "which ads brought customers with the highest LTV last month?"
adpulse audit --days 30 --save
adpulse recommend
adpulse report --send         Slack + email now (--no-slack / --no-email to pick one)
adpulse scheduler             send the weekly report on schedule (--next, --once, --dry-run)
adpulse ui                    the previous Streamlit interface
```

## Demo data

`adpulse demo-data` generates a reproducible 180-day dataset for a fictional DTC coffee brand: 14 ads,
~485k sessions, ~27k orders. Each ad has its own economics, so there are real findings to make:

- **Static - 20% Off** buys cheap customers who rarely come back (lowest LTV).
- **RSA - Coffee Subscription** and **UGC Video - Morning Routine** bring high-LTV subscribers.
- **Search - Competitor** pays $3+ per click for almost no buyers.
- **Carousel - Bestsellers** fatigues: its conversion rate decays over the period.
- Generic search leaks ~40% of its spend on jobs, free-sample and DIY queries.
- Ad platforms over-report conversions compared with warehouse orders.

## Safety model

1. **SQL guard** (`agent/sql_guard.py`): single `SELECT`/`WITH`, approved tables only, no table functions
   (`url`, `s3`, `remote`, `file`…), no other databases.
2. **Read-only ClickHouse user** with `readonly=1`, `max_execution_time` and `max_result_rows` set on the user,
   so generated SQL cannot raise them. It cannot read the app's own `app_*` tables.
3. **No automatic spend changes:** suggestions are proposals. Pending → approved/rejected (reviewer recorded)
   → done (a separate, explicit step after someone makes the change in Meta or Google).
4. **No secrets in the browser:** the web app only calls the API; database and AI keys live on Railway.
5. Every question is logged in `app_questions` with its SQL, review verdict and number check.

## Tests

```bash
make test
```

```bash
make lint && make web-build
```

101 Python tests: SQL guard, number verifier (including a random-number false-acceptance check), audit rules,
the HTTP API, the full agent loop against the warehouse with a scripted LLM (repair, guard rejection, critic
retry, hallucination rewrite, read-only user), and a headless render of every Streamlit page.
`make web-build` type-checks and builds the web app.

## Project layout

```
web/                 React web app (Vercel)
  src/pages/         Overview · Ask · Suggestions · Wasted · Report · DataStatus · Present
  src/components/    layout, charts, KPI figure, funnel, brand logos, robot launcher
  src/robot/         Three.js robot (React Three Fiber)
  public/            icon, brand logos, robot model
api/main.py          FastAPI layer over src/adpulse (Railway)
src/adpulse/
  pipeline/          demo_data.py · ingest.py (PyAirbyte / direct) · transform.py · connections.yaml
  sql/               schema.sql (raw + app tables) · models/*.sql (dim_/fct_/mart_)
  agent/             core.py (loop) · prompts.py · semantic.yaml · sql_guard.py · verify.py · schemas.py
  llm/               anthropic_llm.py · openai_compat.py (Groq, OpenRouter) · fake.py
  audit/             search_terms.py
  actions/           recommendations.py (rules + approval workflow + change payloads)
  reports/           weekly.py · delivery.py (Slack, SMTP)
  cli.py
app/                 previous Streamlit interface (kept for rollback)
frontend/companion/  robot source used by the Streamlit interface
tests/
docs/                deploy guides · airbyte-oss.md · loom-script.md
Dockerfile.api       API image (Railway)   railway.json  Railway settings   render.yaml  older Render blueprint
Dockerfile           Streamlit image       docker-compose.yml   full stack on one server
```
