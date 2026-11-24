#!/usr/bin/env bash
# One-time AdPulse install on an Ubuntu server (e.g. Oracle Cloud Always Free).
#   cd adpulse && scripts/server_install.sh
# Installs Docker if missing, writes .env with strong generated passwords (keys are asked for, never
# echoed), then starts ClickHouse + app + weekly scheduler. Safe to re-run: existing .env values are kept.
set -euo pipefail
cd "$(dirname "$0")/.."

say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

# ---- Docker --------------------------------------------------------------------------------------
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  say "Installing Docker + Compose (Ubuntu packages)"
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-v2
  sudo systemctl enable --now docker
fi
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  sudo usermod -aG docker "$USER" || true
  DOCKER="sudo docker"   # group membership applies from the next login
fi

# ---- .env ----------------------------------------------------------------------------------------
[ -f .env ] || { cp .env.example .env; say "Created .env from .env.example"; }

getv() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
setv() {
  local key="$1" val="$2" esc
  esc="${val//\\/\\\\}"; esc="${esc//|/\\|}"; esc="${esc//&/\\&}"
  if grep -qE "^${key}=" .env; then sed -i "s|^${key}=.*|${key}=${esc}|" .env; else printf '%s=%s\n' "$key" "$val" >> .env; fi
}
weak() { case "$1" in ""|adpulse|change-me*|reader-local-dev) return 0;; *) return 1;; esac; }
rand() { openssl rand -hex 24; }

say "Securing database passwords"
weak "$(getv CLICKHOUSE_PASSWORD)" && setv CLICKHOUSE_PASSWORD "$(rand)" && echo "  generated CLICKHOUSE_PASSWORD"
weak "$(getv CLICKHOUSE_READER_PASSWORD)" && setv CLICKHOUSE_READER_PASSWORD "$(rand)" && echo "  generated CLICKHOUSE_READER_PASSWORD"
chmod 600 .env

ask_secret() {  # ask_secret KEY "prompt"  (skip with Enter keeps the current value)
  local cur; cur="$(getv "$1")"
  local hint="Enter to skip"; [ -n "$cur" ] && hint="Enter to keep current"
  read -rsp "  $2 ($hint): " v; echo
  [ -n "$v" ] && setv "$1" "$v"
  return 0
}
ask_plain() {
  local cur; cur="$(getv "$1")"
  read -rp "  $2 [${cur:-$3}]: " v
  setv "$1" "${v:-${cur:-$3}}"
}

say "Settings (press Enter to keep the value shown in [brackets])"
ask_plain LLM_PROVIDER "LLM provider: groq | anthropic | openrouter" "groq"
case "$(getv LLM_PROVIDER)" in
  groq) ask_secret GROQ_API_KEY "Groq API key" ;;
  anthropic) ask_secret ANTHROPIC_API_KEY "Anthropic API key" ;;
  openrouter) ask_secret OPENROUTER_API_KEY "OpenRouter API key" ;;
esac
ask_secret SLACK_WEBHOOK_URL "Slack Incoming Webhook URL"
ask_plain REPORT_TIMEZONE "Time zone for the weekly report" "Asia/Karachi"
IP="$(curl -fsS --max-time 5 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
ask_plain APP_BASE_URL "Public URL of the app (used in report links)" "http://${IP:-YOUR_SERVER_IP}:8501"
echo "  (email: run scripts/setup_email.sh any time, then: docker compose up -d)"

# ---- Start ---------------------------------------------------------------------------------------
say "Building and starting AdPulse (first build takes a few minutes)"
$DOCKER compose up -d --build

say "Waiting for the app"
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
    say "AdPulse is running: $(getv APP_BASE_URL)"
    $DOCKER compose ps
    $DOCKER compose logs --tail 3 scheduler
    echo
    echo "If the page doesn't open from your browser, open port 8501 in the cloud firewall (see docs/deploy-server.md)."
    exit 0
  fi
  sleep 5
done
echo "The app did not come up in time. Check: $DOCKER compose logs init app"
exit 1
