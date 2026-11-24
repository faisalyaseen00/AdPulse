"""Report delivery: Slack (bot token or incoming webhook) and SMTP email."""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import Settings
from .weekly import WeeklyReport, to_html, to_markdown, to_slack_blocks


def send_slack(r: WeeklyReport, s: Settings) -> str:
    blocks = to_slack_blocks(r, s.app_base_url)
    fallback = f"AdPulse weekly report {r.period_start} – {r.period_end}"
    try:
        if s.slack_bot_token:
            from slack_sdk import WebClient
            WebClient(token=s.slack_bot_token).chat_postMessage(channel=s.slack_channel, text=fallback, blocks=blocks)
        else:
            from slack_sdk.webhook import WebhookClient
            resp = WebhookClient(s.slack_webhook_url).send(text=fallback, blocks=blocks)
            if resp.status_code != 200:
                return f"error: Slack webhook returned {resp.status_code} {resp.body}"
        return "sent"
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


def send_email(r: WeeklyReport, s: Settings) -> str:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"AdPulse weekly report · {r.period_start:%b %d} – {r.period_end:%b %d}"
    msg["From"] = s.report_email_from
    msg["To"] = s.report_email_to
    msg.attach(MIMEText(to_markdown(r), "plain"))
    msg.attach(MIMEText(to_html(r), "html"))
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.sendmail(s.report_email_from, [a.strip() for a in s.report_email_to.split(",")], msg.as_string())
        return "sent"
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"
