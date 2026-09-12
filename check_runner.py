"""Ties together: work out dates -> query each origin -> (optionally) email.

Used by both the GUI's "Run Now" button and the scheduled 18:00 job, so the
two paths can never drift out of sync with each other.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from config import Settings
from destinations import get_candidates
from email_sender import send_summary_email
from flight_source import FlightResult, FlightSource
from trip_dates import next_trip_dates

log = logging.getLogger("flight_watcher.runner")

AIRPORT_NAMES = {"ORK": "Cork", "SNN": "Shannon"}


@dataclass
class CheckOutcome:
    date_out: date
    date_back: date
    results_by_origin: dict[str, list[FlightResult]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    ran_at: datetime = field(default_factory=datetime.now)

    @property
    def ok(self) -> bool:
        return not self.errors


def run_check(settings: Settings, source: FlightSource, send_email: bool) -> CheckOutcome:
    date_out, date_back = next_trip_dates(
        today=date.today(),
        on_friday_means_today=settings.search.on_friday_means_today,
        trip_nights=settings.search.trip_nights,
    )
    log.info("Checking flights for %s -> %s", date_out, date_back)

    outcome = CheckOutcome(date_out=date_out, date_back=date_back)

    for origin in settings.search.origin_airports:
        origin_name = AIRPORT_NAMES.get(origin, origin)
        candidates = get_candidates(origin, set(settings.search.exclude_countries))
        try:
            results = source.search_cheapest_direct(
                origin=origin,
                origin_name=origin_name,
                date_out=date_out,
                date_back=date_back,
                candidates=candidates,
            )
            outcome.results_by_origin[origin] = results[: settings.search.top_n_results]
        except Exception as exc:  # noqa: BLE001
            log.exception("Check failed for origin %s", origin)
            outcome.errors[origin] = str(exc)
            outcome.results_by_origin[origin] = []

    if send_email and settings.email.enabled:
        try:
            send_summary_email(
                settings.email,
                outcome.results_by_origin,
                date_out,
                date_back,
                outcome.errors,
                adults=settings.search.adults,
                children=settings.search.children,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to send summary email")
            outcome.errors["email"] = str(exc)

    return outcome
