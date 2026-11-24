"""Prepare AdPulse for Streamlit Community Cloud + ClickHouse Cloud.

    .venv/bin/python scripts/cloud_setup.py

1. Asks for the ClickHouse Cloud host + password (password is hidden).
2. Creates the database, tables and read-only agent user there, and loads the demo data (`adpulse bootstrap`).
3. Writes `streamlit-secrets.toml` (git-ignored): paste its contents into Streamlit Cloud -> Settings -> Secrets
   and into the GitHub secret ADPULSE_SECRETS (used by the weekly report workflow).
Re-running reuses the saved values; press Enter to keep them.
"""
from __future__ import annotations

import getpass
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "streamlit-secrets.toml"

# Local .env values worth carrying to the cloud (keys, delivery, schedule, rules).
CARRY = ["LLM_PROVIDER", "GROQ_API_KEY", "GROQ_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
         "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "SLACK_WEBHOOK_URL", "SLACK_BOT_TOKEN", "SLACK_CHANNEL",
         "SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USER", "SMTP_PASSWORD", "REPORT_EMAIL_FROM",
         "REPORT_EMAIL_TO", "REPORT_SCHEDULE_DAY", "REPORT_SCHEDULE_TIME", "REPORT_TIMEZONE",
         "TARGET_ROAS", "TARGET_CAC", "MIN_SPEND_FOR_DECISION"]


def read_secrets(path: Path) -> dict[str, str]:
    """Read the `KEY = "json string"` lines this script writes (a TOML subset; no tomllib on 3.10)."""
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = json.loads(v.strip())
    return out


def read_env(path: Path) -> dict[str, str]:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.split(" #", 1)[0].strip()
                if v:
                    out[k.strip()] = v
    return out


def strong_password() -> str:
    """Meets ClickHouse Cloud's policy (length, upper, lower, digit, special); no quotes or backslashes."""
    return "Ap9!" + secrets.token_urlsafe(24)


def policy_ok(pw: str) -> bool:
    return (len(pw) >= 12 and any(c.isupper() for c in pw) and any(c.islower() for c in pw)
            and any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw))


def write_secrets(cfg: dict[str, str]) -> None:
    body = "# AdPulse secrets: paste into Streamlit Cloud (Settings -> Secrets) and GitHub secret ADPULSE_SECRETS.\n"
    body += "".join(f"{k} = {json.dumps(str(v))}\n" for k, v in cfg.items())
    OUT.write_text(body)
    OUT.chmod(0o600)

def ask(prompt: str, current: str = "", secret: bool = False) -> str:
    hint = " (Enter keeps saved value)" if current else ""
    v = (getpass.getpass if secret else input)(f"{prompt}{hint}: ").strip()
    return v or current


def main() -> int:
    saved = read_secrets(OUT)
    local = read_env(ROOT / ".env")

    print("ClickHouse Cloud -> your service -> Connect -> HTTPS. Copy the host (without https:// and :8443).")
    host = ask("ClickHouse Cloud host (e.g. abc123.europe-west4.gcp.clickhouse.cloud)", saved.get("CLICKHOUSE_HOST", ""))
    host = host.removeprefix("https://").removeprefix("http://").split(":")[0].strip("/")
    user = ask("ClickHouse user", saved.get("CLICKHOUSE_USER", "default"))
    pwd = ask("ClickHouse password (hidden)", saved.get("CLICKHOUSE_PASSWORD", ""), secret=True)
    app_url = ask("Streamlit app URL, if you know it yet (for links in reports)", saved.get("APP_BASE_URL", ""))
    if not host or not pwd:
        print("Host and password are required.")
        return 1

    cfg = {k: local[k] for k in CARRY if k in local}
    cfg.update({k: v for k, v in saved.items() if k in CARRY})  # values edited in the file win
    cfg.update({
        "CLICKHOUSE_HOST": host, "CLICKHOUSE_PORT": "8443", "CLICKHOUSE_SECURE": "true",
        "CLICKHOUSE_USER": user, "CLICKHOUSE_PASSWORD": pwd, "CLICKHOUSE_DATABASE": "adpulse",
        "CLICKHOUSE_READER_USER": "adpulse_reader",
        "CLICKHOUSE_READER_PASSWORD": (saved.get("CLICKHOUSE_READER_PASSWORD")
                                       if policy_ok(saved.get("CLICKHOUSE_READER_PASSWORD", ""))
                                       else strong_password()),
    })
    if app_url:
        cfg["APP_BASE_URL"] = app_url.rstrip("/")

    write_secrets(cfg)  # saved first, so a re-run after a failure doesn't ask for everything again
    print("\nCreating tables, the read-only user and loading demo data in ClickHouse Cloud (1-3 minutes)...")
    env = {**os.environ, **cfg}
    adpulse = ROOT / ".venv" / "bin" / "adpulse"
    r = subprocess.run([str(adpulse) if adpulse.exists() else "adpulse", "bootstrap", "--wait", "180"],
                       env=env, cwd=ROOT, check=False)
    if r.returncode != 0:
        print("\nBootstrap failed. Check the host/password, and that the service is running in ClickHouse Cloud.")
        return r.returncode

    print(f"\nDone. Secrets file written: {OUT}")
    print("Next: copy its whole contents into Streamlit Cloud and GitHub (see docs/deploy-streamlit-cloud.md).")
    print("Never commit or share this file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
