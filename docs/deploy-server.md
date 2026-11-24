# Deploy AdPulse on a free server (Oracle Cloud Always Free)

What you get: a server with 4 CPUs and 24 GB RAM, free for good, running ClickHouse, the web app and the Monday
report scheduler. Data persists across restarts. Any Ubuntu VPS works the same way from step 3.

```
Internet ──► :8501  AdPulse web app ─┐
                                     ├─► ClickHouse (localhost only, never public)
            weekly scheduler ────────┘──► Slack / email every Monday
```

## 1. Create the server (Oracle Cloud console)
1. Sign up at <https://www.oracle.com/cloud/free/>. A card is required for identity verification. Always Free
   resources are not charged.
2. **Menu → Compute → Instances → Create instance**
   - **Image:** Canonical **Ubuntu 24.04** (or 22.04)
   - **Shape:** *Change shape* → **Ampere** → **VM.Standard.A1.Flex** → **4 OCPU, 24 GB memory**
     (shows "Always Free-eligible")
   - **Networking:** keep the default VCN; **Assign a public IPv4 address: Yes**
   - **SSH keys:** *Generate a key pair for me* → **Save private key** (keep this file safe)
3. Click **Create**. When it shows **Running**, copy the **Public IP address**.

> "Out of capacity" for A1? Try another *Availability domain* in the same form, or retry later. It's common.

## 2. Open port 8501
**a) Oracle firewall:** Instance page → **Subnet** link → **Security Lists** → *Default Security List* →
**Add Ingress Rules**: Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination Port **8501** → Add.

**b) Server firewall** (Oracle's Ubuntu images block ports by default). Run this after step 3's SSH login:
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8501 -j ACCEPT && sudo netfilter-persistent save
```

## 3. Log in to the server
From your laptop (replace the key path and IP):
```bash
chmod 600 ~/Downloads/ssh-key-*.key
```
```bash
ssh -i ~/Downloads/ssh-key-*.key ubuntu@YOUR_SERVER_IP
```

## 4. Get the code onto the server
Commit and push from GitHub Desktop first, then on the server:
```bash
git clone https://github.com/faisalyaseen00/AdPulse.git adpulse && cd adpulse
```
If the repo is private, Git asks for your GitHub username and a **personal access token** as the password
(GitHub → Settings → Developer settings → Personal access tokens → *Fine-grained*, read access to this repo).

## 5. Install and start
```bash
scripts/server_install.sh
```
It installs Docker, generates strong database passwords, asks for your Groq key and Slack webhook
(hidden as you paste), then builds and starts everything. The first run takes about 5–10 minutes and loads
the demo data. At the end it prints your link: `http://YOUR_SERVER_IP:8501`.

Optional, email reports: `scripts/setup_email.sh`, then `docker compose up -d`.

## Day-to-day
| Task | Command (in `~/adpulse` on the server) |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f app` · `docker compose logs -f scheduler` |
| Next weekly report | `docker compose exec scheduler adpulse scheduler --next` |
| Send the report now | `docker compose exec scheduler adpulse report --send` |
| Update to the latest code | `git pull && docker compose up -d --build` |
| After editing `.env` | `docker compose up -d` |
| Stop / start | `docker compose stop` · `docker compose start` |
| Backup ClickHouse data | `docker run --rm -v adpulse_ch_data:/d -v "$PWD":/b alpine tar czf /b/ch_backup.tgz -C /d .` |

## Security notes
- ClickHouse listens on `127.0.0.1` only. Port 8123/9000 are never reachable from the internet.
- The agent queries as a separate read-only user. Its password and the admin password are random, in `.env` (mode 600).
- There is no login screen by design. Anyone with the link can use the app, spend LLM credits and trigger
  report sends. Share the link only with the client. For a login, put it behind a reverse proxy with auth
  or ask to add one back.
- Plain HTTP. For HTTPS, point a domain at the server and add Caddy (`reverse_proxy localhost:8501`).
