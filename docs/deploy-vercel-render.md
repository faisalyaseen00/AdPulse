# Deploy: Vercel (web) + Render (API) + ClickHouse Cloud

This puts the client-facing AdPulse online:

```
browser ──► Vercel: web/ (static React app) ──► Render: api/ (FastAPI, Docker) ──► ClickHouse Cloud
                                                         ▲
                              GitHub Actions (Monday report) uses the same database and Slack settings
```

Time: about 30 minutes. Cost: free. Vercel Hobby and Render Free cost nothing; Render's free service sleeps
after 15 minutes without visits, and the first visit after that takes about a minute to wake it. Open the
app a minute before a client meeting. ClickHouse Cloud is free during its trial; after that, see
[deploy-server.md](deploy-server.md) for a free Oracle Cloud server.

## Before you start

- The code is pushed to GitHub (both services deploy from the repository).
- ClickHouse Cloud is running with the AdPulse data loaded. If the Streamlit app or the weekly report already
  works, it is. Otherwise follow [deploy-streamlit-cloud.md](deploy-streamlit-cloud.md) up to "Load the data".
- Have these values to hand (from your password manager or the ClickHouse Cloud console, never from chat):
  ClickHouse host, admin user and password, read-only user and password, `GROQ_API_KEY`, and the Slack webhook
  or bot token if you want reports in Slack.

## 1. API on Render

1. Sign in at <https://dashboard.render.com> with GitHub.
2. **New + → Blueprint**, pick the AdPulse repository, branch `main`.
3. Render reads `render.yaml` and shows one service, **adpulse-api**. It asks for every value marked
   `sync: false`:

   | Key | Value |
   |---|---|
   | `CLICKHOUSE_HOST` | your service host, e.g. `abc123.europe-west4.gcp.clickhouse.cloud` (no `https://`) |
   | `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` | admin user |
   | `CLICKHOUSE_READER_USER` / `CLICKHOUSE_READER_PASSWORD` | read-only user |
   | `GROQ_API_KEY` | your Groq key |
   | `SLACK_WEBHOOK_URL` or `SLACK_BOT_TOKEN` + `SLACK_CHANNEL` | optional |
   | `APP_BASE_URL` | the Vercel address once you have it (used for links in the report) |
   | `ADPULSE_CORS_ORIGINS` | leave empty for now; set in step 3 |

4. **Apply.** The first build takes 3 to 5 minutes. When the service shows **Live**, open
   `https://<your-service>.onrender.com/healthz`. It should show `{"ok":true}`.
5. Open `https://<your-service>.onrender.com/api/health`. `"warehouse": true` means the database settings
   are right. If it is `false`, check the host, port `8443` and `CLICKHOUSE_SECURE=true`.

## 2. Web app on Vercel

1. Sign in at <https://vercel.com> with GitHub. **Add New → Project**, import the AdPulse repository.
2. **Root Directory:** `web`. Vercel detects Vite; `web/vercel.json` already sets the build command, output
   folder, page routing and caching.
3. **Environment Variables:** `VITE_API_URL` = `https://<your-service>.onrender.com` (no trailing slash).
4. **Deploy.** Note the address, for example `https://adpulse.vercel.app`.

`VITE_API_URL` is built into the app. If you change it later, redeploy (Deployments → … → Redeploy).

## 3. Let the browser talk to the API

Back in Render → adpulse-api → **Environment**:

- `ADPULSE_CORS_ORIGINS` = your Vercel address, e.g. `https://adpulse.vercel.app`
  (add a custom domain too, comma-separated, if you use one).
- `APP_BASE_URL` = the same address.

Save; Render restarts the service. Preview deployments (`https://adpulse-git-….vercel.app`) are allowed by
default through `ADPULSE_CORS_REGEX`. If your Vercel project has a different name, set
`ADPULSE_CORS_REGEX` to match it, e.g. `https://myname[a-z0-9-]*\.vercel\.app`.

## 4. Check it

Open the Vercel address and go through:

- **Overview** shows figures and charts (the API and database work).
- **Ask** answers a starter question (the AI key works; 10 to 30 seconds is normal).
- **Weekly report → Send to Slack** posts the report (if Slack is set).
- **Present** opens the full-screen deck.

If a page says *"Can't reach the AdPulse server"*, `VITE_API_URL` is wrong or missing. If the browser
console shows a CORS error, `ADPULSE_CORS_ORIGINS` does not match the address in the address bar exactly.

## 5. The Monday report

Nothing changes: `.github/workflows/weekly-report.yml` keeps sending it with the `ADPULSE_SECRETS` secret.
Update `APP_BASE_URL` inside that secret to the Vercel address so links in the report open the new app.

## Updating

Push to `main`. Vercel rebuilds the web app; Render rebuilds the API when `api/`, `src/`, `pyproject.toml`
or `Dockerfile.api` change. Run `make test` and `make web-build` before pushing.

## Custom domain (optional)

- Vercel → Project → Settings → Domains → add `app.yourdomain.com`, then add the DNS record it shows.
- Add the same address to `ADPULSE_CORS_ORIGINS` and `APP_BASE_URL` on Render.

## Security notes

- The web app holds no secrets. Database, AI and Slack credentials exist only on Render and in GitHub Actions.
- The AI's SQL runs as the read-only ClickHouse user, behind the SQL guard.
- The app has no login yet: anyone with the address can view it and approve suggestions with any name.
  Share the address only with the client, or add Vercel password protection (Pro plan) or an auth layer
  before wider use.
