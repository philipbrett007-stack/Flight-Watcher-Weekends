"""Builds and sends the daily summary email over Gmail SMTP (SSL)."""

from __future__ import annotations

import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import EmailSettings
from flight_source import FlightResult

log = logging.getLogger("flight_watcher.email")

AIRPORT_NAMES = {"ORK": "Cork", "SNN": "Shannon"}


def _results_table_html(origin: str, results: list[FlightResult]) -> str:
    origin_name = AIRPORT_NAMES.get(origin, origin)
    if not results:
        return f"<h3>{origin_name} ({origin})</h3><p>No direct-flight results found.</p>"

    rows = "".join(
        f"<tr>"
        f"<td>{r.destination_city} ({r.destination_code})</td>"
        f"<td><b>{r.price_display()}</b></td>"
        f"<td>{r.outbound_departure} → {r.outbound_arrival}</td>"
        f"<td>{r.return_departure} → {r.return_arrival}</td>"
        f"</tr>"
        for r in results
    )
    return f"""
    <h3>{origin_name} ({origin})</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:sans-serif;font-size:14px;">
      <tr style="background:#f0f0f0;">
        <th>Destination</th><th>Price (total)</th><th>Outbound (local)</th><th>Return (local)</th>
      </tr>
      {rows}
    </table>
    """


def _party_label(adults: int, children: int) -> str:
    parts = [f"{adults} adult{'s' if adults != 1 else ''}"]
    if children:
        parts.append(f"{children} child{'ren' if children != 1 else ''}")
    return " + ".join(parts)


def build_email_html(
    results_by_origin: dict[str, list[FlightResult]],
    date_out: date,
    date_back: date,
    errors: dict[str, str] | None = None,
    adults: int = 1,
    children: int = 0,
) -> str:
    errors = errors or {}
    parts = [
        f"<p>Cheapest direct weekend flights for "
        f"<b>{date_out.strftime('%a %d %b %Y')} → {date_back.strftime('%a %d %b %Y')}</b> "
        f"(destinations outside Ireland only, direct flights only). "
        f"Prices are the <b>total</b> for {_party_label(adults, children)}, not per person.</p>"
    ]
    for origin, results in results_by_origin.items():
        if origin in errors:
            origin_name = AIRPORT_NAMES.get(origin, origin)
            parts.append(f"<h3>{origin_name} ({origin})</h3><p><i>Check failed: {errors[origin]}</i></p>")
        else:
            parts.append(_results_table_html(origin, results))
    return "<html><body>" + "".join(parts) + "</body></html>"


def send_summary_email(
    settings: EmailSettings,
    results_by_origin: dict[str, list[FlightResult]],
    date_out: date,
    date_back: date,
    errors: dict[str, str] | None = None,
    adults: int = 1,
    children: int = 0,
) -> None:
    if not settings.enabled:
        log.info("Email sending disabled in config; skipping.")
        return
    if not settings.app_password:
        log.error("EMAIL_APP_PASSWORD not set (see .env.example) - cannot send email.")
        raise RuntimeError("Missing EMAIL_APP_PASSWORD environment variable.")

    html = build_email_html(results_by_origin, date_out, date_back, errors, adults, children)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = settings.subject
    msg["From"] = settings.sender
    msg["To"] = settings.recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL(settings.smtp_server, settings.smtp_port) as server:
        server.login(settings.sender, settings.app_password)
        server.sendmail(settings.sender, [settings.recipient], msg.as_string())

    log.info("Summary email sent to %s", settings.recipient)
