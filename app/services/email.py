"""Minimal email delivery: SMTP when configured, console log otherwise."""

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from flask import current_app

logger = logging.getLogger(__name__)


def _config(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        import os

        return os.getenv(key, default)


def send_email(to: str, subject: str, text_body: str, html_body: Optional[str] = None) -> None:
    """Send an email, or log it to the console in dev mode."""
    host = _config("SMTP_HOST")
    sender = _config("SMTP_FROM") or _config("SMTP_USER") or "noreply@brainstormer.local"

    if not host:
        # Dev mode: no SMTP configured. Log the message so the reset link
        # is still reachable during local development and tests.
        logger.warning("EMAIL (dev, no SMTP_HOST): to=%s subject=%s", to, subject)
        logger.warning("EMAIL BODY:\n%s", text_body)
        return

    port = int(_config("SMTP_PORT", "587") or 587)
    user = _config("SMTP_USER")
    password = _config("SMTP_PASSWORD")
    use_tls = (_config("SMTP_USE_TLS", "true") or "true").lower() in ("1", "true", "yes")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_tls:
            smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)