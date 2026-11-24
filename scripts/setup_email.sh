#!/usr/bin/env bash
# Save Gmail settings for the AdPulse email report into .env (the app password is never echoed).
set -euo pipefail
ENV="$(cd "$(dirname "$0")/.." && pwd)/.env"
[ -f "$ENV" ] || { echo "no .env at $ENV (copy .env.example first)"; exit 1; }

setv() {  # replace KEY=... in .env, or append it
  local key="$1" val="$2" esc
  esc="${val//\\/\\\\}"; esc="${esc//|/\\|}"; esc="${esc//&/\\&}"   # escaped for sed only
  if grep -q "^${key}=" "$ENV"; then sed -i "s|^${key}=.*|${key}=${esc}|" "$ENV"; else printf '%s=%s\n' "$key" "$val" >> "$ENV"; fi
}

read -rp  "Gmail address that sends the report: " from
read -rsp "Gmail App Password (16 letters, hidden): " pw; echo
read -rp  "Send the report to (comma-separated emails) [$from]: " to
to="${to:-$from}"
pw="${pw// /}"   # Google shows it in groups of 4; spaces are not part of it

setv SMTP_HOST smtp.gmail.com
setv SMTP_PORT 587
setv SMTP_SECURITY starttls
setv SMTP_USER "$from"
setv SMTP_PASSWORD "$pw"
setv REPORT_EMAIL_FROM "$from"
setv REPORT_EMAIL_TO "$to"
unset pw
echo "saved. Test it with:  .venv/bin/adpulse report --send --no-slack"
