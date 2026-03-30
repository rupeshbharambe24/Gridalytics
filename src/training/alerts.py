"""Drift detection alerts via email or console logging."""

import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import settings

logger = logging.getLogger(__name__)


def check_and_alert_drift(
    rolling_mape: float,
    threshold: float | None = None,
    baseline_mape: float | None = None,
) -> bool:
    """Check if model drift occurred and send alert if needed.

    Returns True if drift was detected.
    """
    threshold = threshold or getattr(settings, "DRIFT_MAPE_THRESHOLD", 5.0)
    alerts: list[str] = []

    if rolling_mape > threshold:
        alerts.append(f"MAPE ({rolling_mape:.2f}%) exceeds threshold ({threshold}%)")

    if baseline_mape and rolling_mape > baseline_mape * 1.3:
        pct_worse = (rolling_mape / baseline_mape - 1) * 100
        alerts.append(f"MAPE is {pct_worse:.0f}% worse than baseline ({baseline_mape:.2f}%)")

    if not alerts:
        logger.info(f"Drift check OK: MAPE {rolling_mape:.2f}% (threshold {threshold}%)")
        return False

    alert_msg = f"DRIFT ALERT {date.today()}: " + "; ".join(alerts)
    logger.warning(alert_msg)

    # Try email if configured
    email_to = getattr(settings, "ALERT_EMAIL", None)
    smtp_host = getattr(settings, "SMTP_HOST", None)
    if email_to and smtp_host:
        try:
            _send_email(email_to, alert_msg, rolling_mape, threshold)
        except Exception as e:
            logger.error(f"Email alert failed: {e}")

    return True


def _send_email(to: str, alert_msg: str, mape: float, threshold: float):
    """Send drift alert email via SMTP."""
    host = settings.SMTP_HOST
    port = getattr(settings, "SMTP_PORT", 587)
    user = getattr(settings, "SMTP_USER", "")
    pw = getattr(settings, "SMTP_PASS", "")
    sender = getattr(settings, "ALERT_FROM_EMAIL", user)

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = f"[Gridalytics] Drift Alert - MAPE {mape:.2f}%"

    body = f"""
Gridalytics Model Drift Alert
==============================

Date: {date.today()}
Current Rolling MAPE: {mape:.2f}%
Threshold: {threshold}%

{alert_msg}

Action Required: Consider retraining the model.
Run: python -m src.training.train hourly

---
Gridalytics - AI-Powered Grid Intelligence
"""
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(host, port) as server:
        if port == 587:
            server.starttls()
        if user and pw:
            server.login(user, pw)
        server.send_message(msg)

    logger.info(f"Drift alert email sent to {to}")
