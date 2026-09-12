"""Works out which Friday-out / Sunday-back dates a run should check."""

from __future__ import annotations

from datetime import date, timedelta

FRIDAY = 4  # date.weekday(): Monday=0 ... Sunday=6


def next_trip_dates(today: date, on_friday_means_today: bool, trip_nights: int = 2) -> tuple[date, date]:
    """Return (date_out, date_back) for the next Friday->Sunday-style trip.

    If `today` itself is a Friday: `on_friday_means_today=True` uses today
    as the departure date; `False` skips ahead to next week's Friday.
    """
    days_ahead = (FRIDAY - today.weekday()) % 7
    if days_ahead == 0 and not on_friday_means_today:
        days_ahead = 7
    date_out = today + timedelta(days=days_ahead)
    date_back = date_out + timedelta(days=trip_nights)
    return date_out, date_back
