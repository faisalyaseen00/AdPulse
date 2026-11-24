# Loom demo (3 minutes)

**0:00 – Data flowing in (30s)** · *Data pipeline* page
- Show the flow strip: Sources → Airbyte → raw → models → agent.
- Click **Sync now** (mode `airbyte`): the log streams each connector → table with row counts.
- *Sync runs* tab: every stream load is recorded.

**0:30 – Overview (20s)**
- KPIs vs. the prior period, and the funnel: impressions → clicks → sessions → customers → revenue → LTV.
- Ad scorecard: LTV:CAC per ad.

**0:50 – Ask an LTV question (60s)** · *Ask AdPulse*
- Click "Which ads brought customers with the highest LTV last month?"
- Point out the badges: **Verified · Critic passed · N/N numbers traced to data**.
- Open **SQL**: the agent wrote it, ClickHouse ran it as a read-only user.
- Open **How I got this**: write SQL → guard → run → critic → answer → number check.
- Open **Number check**: each figure ✅ with where it came from (cell / computed: 125.75 / 34.81).
- Click **Queue for approval** on a suggested action.

**1:50 – Search term audit (35s)** · *Search term audit*
- ~40% of generic search spend went to jobs / free / DIY queries.
- Tick the terms, **Queue negative keywords**.

**2:25 – Approvals (15s)**
- Pending cards with evidence. Approve one and show the exact Google Ads / Meta API change.
- "Nothing changes spend without a human yes."

**2:40 – Weekly report in Slack (20s)** · *Weekly report*
- KPI tiles, summary, **Send now** → switch to Slack and show the Block Kit message.
