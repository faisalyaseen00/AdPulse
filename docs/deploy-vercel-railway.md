# Deploy: Vercel (web) + Railway (API) + ClickHouse Cloud

This puts the client-facing AdPulse online:

```
browser ──► Vercel: web/ (static React app) ──► Railway: api/ (FastAPI, Docker) ──► ClickHouse Cloud
                                                          ▲
                               GitHub Actions (Monday report) uses the same database and Slack settings
```

Time: about 30 minutes. Vercel Hobby is free. Railway gives trial credit, then the Hobby plan costs about
$5 a month (check <https://railway.com/pricing>). Unlike Render's free plan, the API does not fall asleep, so
there is no one-minute wait on the first visit.

The repository already holds Railway's settings in [`railway.json`](../railway.json): build with
`Dockerfile.api` (not the Streamlit `Dockerfile` at the root), health check on `/healthz`, restart on failure,
one replica, and rebuild only when API files change. You set only the secrets.

## Before you start

- The code is pushed to GitHub (both services deploy from the repository).
- ClickHouse Cloud is running with the AdPulse data loaded. If the Streamlit app or the weekly report already
  works, it is. Otherwise follow [deploy-streamlit-cloud.md](deploy-streamlit-cloud.md) up to "Load the data".
- Have these values to hand (from your password manager or the ClickHouse Cloud console, never from chat):
  ClickHouse host, admin user and password, read-only user and password, `GROQ_API_KEY`, and the Slack webhook
  or bot token if you want reports in Slack.

## 1. API on Railway

1. Sign in at <https://railway.com> with GitHub.
2. **New Project → Deploy from GitHub repo**, pick the AdPulse repository (allow Railway access to it if asked).
   Railway reads `railway.json` and starts a build with `Dockerfile.api`.
3. Open the service → **Variables → Raw Editor**, paste this and fill in your values:

   ```
   CLICKHOUSE_HOST=abc123.europe-west4.gcp.clickhouse.cloud
   CLICKHOUSE_PORT=8443
   CLICKHOUSE_SECURE=true
   CLICKHOUSE_DATABASE=adpulse
   CLICKHOUSE_USER=
   CLICKHOUSE_PASSWORD=
   CLICKHOUSE_READER_USER=
   CLICKHOUSE_READER_PASSWORD=
   LLM_PROVIDER=groq
   GROQ_API_KEY=
   REPORT_TIMEZONE=Asia/Karachi
   SLACK_WEBHOOK_URL=
   SLACK_BOT_TOKEN=
   SLACK_CHANNEL=
   APP_BASE_URL=
   ADPULSE_CORS_ORIGINS=
   ```

   - `CLICKHOUSE_HOST` is the host only, without `https://`.
   - Leave `APP_BASE_URL` and `ADPULSE_CORS_ORIGINS` empty for now; you set them in step 3.
   - Do not set `PORT`: Railway sets it and the API listens on it.

   Save (**Deploy** / **Update Variables**). Railway rebuilds with the new values.
4. **Settings → Networking → Generate Domain.** If asked for a port, enter `8000`. You get an address like
   `https://adpulse-api-production.up.railway.app`.
5. **Settings → Region:** pick the one nearest your ClickHouse Cloud region (for example EU West for a
   European service).
6. The first build takes 3 to 5 minutes (**Deployments → View logs**). When it shows **Active**, open
   `https://<your-railway-domain>/healthz`. It should show `{"ok":true}`.
7. Open `https://<your-railway-domain>/api/health`. `"warehouse": true` means the database settings are
   right. If it is `false`, check the host, port `8443` and `CLICKHOUSE_SECURE=true`.

## 2. Web app on Vercel

1. Sign in at <https://vercel.com> with GitHub. **Add New → Project**, import the AdPulse repository.
   (Already have the project? Go straight to step 3.)
2. **Root Directory:** `web`. Vercel detects Vite; `web/vercel.json` already sets the build command, output
   folder, page routing and caching.
3. **Settings → Environment Variables:** `VITE_API_URL` = `https://<your-railway-domain>` (no trailing slash).
4. **Deploy**, or for an existing project **Deployments → … → Redeploy**. Note the address, for example
   `https://adpulse.vercel.app`.

`VITE_API_URL` is built into the app. If you change it later, redeploy.

## 3. Let the browser talk to the API

Back in Railway → the service → **Variables**:

- `ADPULSE_CORS_ORIGINS` = your Vercel address, e.g. `https://adpulse.vercel.app`
  (add a custom domain too, comma-separated, if you use one).
- `APP_BASE_URL` = the same address.

Save; Railway redeploys. Preview deployments (`https://adpulse-git-….vercel.app`) are allowed by default
through `ADPULSE_CORS_REGEX`. If your Vercel project has a different name, set `ADPULSE_CORS_REGEX` to match
it, e.g. `https://myname[a-z0-9-]*\.vercel\.app`.

## 4. Check it

Open the Vercel address and go through:

- **Overview** shows figures and charts (the API and database work).
- **Ask** answers a starter question (the AI key works; 10 to 30 seconds is normal).
- **Weekly report → Send to Slack** posts the report (if Slack is set).
- **Present** opens the full-screen deck.

| Symptom | Cause |
|---|---|
| Page says *"Can't reach the AdPulse server"* | `VITE_API_URL` wrong or missing on Vercel; fix it and redeploy |
| Browser console shows a CORS error | `ADPULSE_CORS_ORIGINS` does not match the address bar exactly |
| Railway logs show Streamlit starting | `railway.json` was not picked up; set the variable `RAILWAY_DOCKERFILE_PATH=Dockerfile.api` |
| Railway deploy fails its health check | Open the deploy logs; usually a missing or mistyped variable |

## 5. The Monday report

Nothing changes: `.github/workflows/weekly-report.yml` keeps sending it with the `ADPULSE_SECRETS` secret.
Update `APP_BASE_URL` inside that secret to the Vercel address so links in the report open the new app.

## Moving from Render

If the API ran on Render before: once Railway passes step 4, change `VITE_API_URL` on Vercel to the Railway
address (and redeploy), then delete the Render service. `render.yaml` can stay in the repository; Railway
ignores it.

## Updating

Push to `main`. Vercel rebuilds the web app; Railway rebuilds the API when `api/`, `src/`, `pyproject.toml`,
`Dockerfile.api` or `railway.json` change. Run `make test` and `make web-build` before pushing.

Keep one replica: the API holds a small cache and the data-refresh job tracker in memory.

## Custom domain (optional)

- Vercel → Project → Settings → Domains → add `app.yourdomain.com`, then add the DNS record it shows.
- Add the same address to `ADPULSE_CORS_ORIGINS` and `APP_BASE_URL` on Railway.
- For the API: Railway → Settings → Networking → Custom Domain, e.g. `api.yourdomain.com`, then point
  `VITE_API_URL` at it and redeploy Vercel.

## Security notes

- The web app holds no secrets. Database, AI and Slack credentials exist only on Railway and in GitHub Actions.
- The AI's SQL runs as the read-only ClickHouse user, behind the SQL guard.
- The app has no login yet: anyone with the address can view it and approve suggestions with any name.
  Share the address only with the client, or add an auth layer before wider use.
