"""Report delivery: Slack (bot token or incoming webhook) and SMTP email."""
from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

from ..config import Settings
from .weekly import WeeklyReport, to_html, to_markdown, to_slack_blocks


def send_slack(r: WeeklyReport, s: Settings) -> str:
    """Post via bot token if set; fall back to the incoming webhook if the bot fails."""
    blocks = to_slack_blocks(r, s.app_base_url)
    fallback = f"AdPulse weekly report {r.period_start} – {r.period_end}"
    errors: list[str] = []
    if s.slack_bot_token:
        try:
            from slack_sdk import WebClient
            WebClient(token=s.slack_bot_token).chat_postMessage(channel=s.slack_channel, text=fallback, blocks=blocks)
            return "sent"
        except Exception as e:  # noqa: BLE001
            err = getattr(getattr(e, "response", None), "data", {}) or {}
            errors.append(f"bot: {err.get('error') or e}")
    if s.slack_webhook_url:
        try:
            from slack_sdk.webhook import WebhookClient
            resp = WebhookClient(s.slack_webhook_url).send(text=fallback, blocks=blocks)
            if resp.status_code == 200:
                return "sent (webhook)" if errors else "sent"
            errors.append(f"webhook: {resp.status_code} {resp.body}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"webhook: {e}")
    return "error: " + "; ".join(errors or ["Slack not configured"])


def build_email(r: WeeklyReport, s: Settings) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"AdPulse weekly report · {r.period_start:%b %d} – {r.period_end:%b %d}"
    msg["From"] = formataddr(("AdPulse", s.report_email_from))
    msg["To"] = ", ".join(recipients(s))
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=s.report_email_from.split("@")[-1] or "adpulse.local")
    msg.attach(MIMEText(to_markdown(r), "plain", "utf-8"))
    msg.attach(MIMEText(to_html(r, s.app_base_url), "html", "utf-8"))
    return msg


def recipients(s: Settings) -> list[str]:
    return [a.strip() for a in s.report_email_to.replace(";", ",").split(",") if a.strip()]


def send_email(r: WeeklyReport, s: Settings) -> str:
    """Send via SMTP. Gmail: smtp.gmail.com, port 587, starttls, an App Password (not your login password)."""
    to = recipients(s)
    if not to:
        return "error: REPORT_EMAIL_TO is empty"
    msg = build_email(r, s)
    security = (s.smtp_security or "starttls").lower()
    if s.smtp_port == 465:
        security = "ssl"
    try:
        ctx = ssl.create_default_context()
        if security == "ssl":
            smtp = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=30, context=ctx)
        else:
            smtp = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30)
        with smtp:
            smtp.ehlo()
            if security == "starttls":
                smtp.starttls(context=ctx)
                smtp.ehlo()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            refused = smtp.sendmail(s.report_email_from, to, msg.as_string())
        if refused:
            return f"error: refused recipients {', '.join(refused)}"
        return "sent"
    except smtplib.SMTPAuthenticationError:
        return ("error: SMTP login failed. For Gmail use an App Password "
                "(myaccount.google.com/apppasswords), not your normal password")
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"
