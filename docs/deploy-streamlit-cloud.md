# Deploy free: Streamlit Community Cloud + ClickHouse Cloud trial

```
Browser ──► Streamlit Community Cloud (the app, free)  ──┐
                                                          ├─► ClickHouse Cloud (database, free 30-day trial)
GitHub Actions (free) ── every Monday 08:00 PKT ─────────┘──► Slack / email
```

- **Cost:** Streamlit Cloud and GitHub Actions are free. ClickHouse Cloud is a **30-day free trial**. After
  that, either add billing there or move the database (e.g. to the Oracle setup in [deploy-server.md](deploy-server.md)).
- **Sleeping:** the app sleeps after a long time without visitors. The next visitor clicks "Yes, get this app
  back up" and waits about a minute. The ClickHouse service also idles and wakes on the first query (a few seconds).

## 1. Database: ClickHouse Cloud
1. Sign up at <https://clickhouse.cloud> (Google/GitHub/email). Start the **free trial**.
2. **Create service:** pick a cloud provider and the region closest to you, name it `adpulse`, and use the
   smallest/development tier.
3. A **password for the `default` user** is shown once. Click **Download** or copy it somewhere safe.
4. **Allow connections from anywhere:** service → **Settings → IP Access List → Add entry → "Anywhere"**
   (`0.0.0.0/0`). Streamlit Cloud and GitHub don't have fixed IP addresses.
5. Service → **Connect** → choose **HTTPS**. Copy the **host**, like `abc123.europe-west4.gcp.clickhouse.cloud`
   (without `https://` and `:8443`).

## 2. Load the data (on your laptop, once)
```bash
cd ~/Documents/GitHub/adpulse && .venv/bin/python scripts/cloud_setup.py
```
It asks for the host and password (hidden), creates everything in ClickHouse Cloud, loads the demo data
(1–3 minutes) and writes **`streamlit-secrets.toml`** with all settings and keys. That file is git-ignored.
Never commit or share it.

## 3. Push the code
In GitHub Desktop: **Commit to main**, then **Push origin**.

## 4. The app: Streamlit Community Cloud
1. Go to <https://share.streamlit.io> → **Continue with GitHub** → allow access.
2. **Create app** → **Deploy a public app from GitHub**:
   - **Repository:** `faisalyaseen00/AdPulse` · **Branch:** `main` · **Main file path:** `app/main.py`
   - **App URL:** pick a name, e.g. `adpulse-demo` → `https://adpulse-demo.streamlit.app`
3. **Advanced settings:** **Python 3.11**. In **Secrets**, paste the **whole contents** of `streamlit-secrets.toml`.
   Open it with: `xdg-open ~/Documents/GitHub/adpulse/streamlit-secrets.toml`
4. Click **Deploy**. The first build takes 3–5 minutes. That URL is the link for your boss.

Optional: run `scripts/cloud_setup.py` again and enter the app URL when asked, so report links point to it.
Then update the secrets in Streamlit (app → ⋮ → Settings → Secrets) and in GitHub.

## 5. Weekly report: GitHub Actions
1. GitHub → your repo → **Settings → Secrets and variables → Actions → New repository secret**
   - **Name:** `ADPULSE_SECRETS` · **Secret:** paste the same `streamlit-secrets.toml` contents → **Add secret**
2. Test it: repo → **Actions** → **Weekly report** → **Run workflow** → tick *dry run* → **Run**. It turns
   green in about 2 minutes. Run it again without *dry run* to really send it to Slack.
3. From now on it sends every **Monday 08:00 PKT** automatically.

GitHub pauses scheduled workflows in repos with no activity for 60 days. Any commit re-enables them, as does the
"Enable workflow" button in the Actions tab.

## Changing a setting or key later
Edit `streamlit-secrets.toml` (or rerun `scripts/cloud_setup.py`), then paste it again in **both** places:
Streamlit (app → ⋮ → Settings → Secrets) and GitHub (`ADPULSE_SECRETS` → Update).

## Troubleshooting
| Symptom | Fix |
|---|---|
| App says "Cannot reach ClickHouse" | Check the service is running and the IP Access List allows Anywhere. Check the secrets were pasted. |
| App says "warehouse is empty" | Run step 2 again. |
| Build fails on Streamlit | App → ⋮ → **Manage app** shows the log. Check Python is 3.11. |
| Workflow red | Open the run to see the log. `ADPULSE_SECRETS` missing or wrong is the usual cause. |
