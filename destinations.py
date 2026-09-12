"""Candidate destination airports for Cork and Shannon UK-only searches."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Destination:
    iata: str
    city: str
    country: str  # ISO alpha-2


# Airport code lookup dictionary
AIRPORT_NAMES = {
    "ORK": "Cork",
    "SNN": "Shannon",
    "LHR": "London Heathrow",
    "LGW": "London Gatwick",
    "LTN": "London Luton",
    "STN": "London Stansted",
    "MAN": "Manchester",
    "BHX": "Birmingham",
    "LPL": "Liverpool",
    "BRS": "Bristol",
    "EDI": "Edinburgh",
    "GLA": "Glasgow",
}

# All Irish airports (always excluded from candidates)
IRISH_AIRPORTS = {
    "DUB": Destination("DUB", "Dublin", "IE"),
    "ORK": Destination("ORK", "Cork", "IE"),
    "SNN": Destination("SNN", "Shannon", "IE"),
    "NOC": Destination("NOC", "Knock", "IE"),
    "KIR": Destination("KIR", "Kerry", "IE"),
    "GWY": Destination("GWY", "Galway", "IE"),
    "BFS": Destination("BFS", "Belfast (Intl)", "IE"),
    "BHD": Destination("BHD", "Belfast (City)", "IE"),
    "LDY": Destination("LDY", "Derry", "IE"),
}

# Specified UK direct destinations from Shannon (SNN)
SHANNON_DESTINATIONS: list[Destination] = [
    Destination("LHR", "London Heathrow", "GB"),
    Destination("LGW", "London Gatwick", "GB"),
    Destination("STN", "London Stansted", "GB"),
    Destination("MAN", "Manchester", "GB"),
    Destination("BHX", "Birmingham", "GB"),
    Destination("LPL", "Liverpool", "GB"),
    Destination("EDI", "Edinburgh", "GB"),
]

# Specified UK direct destinations from Cork (ORK)
CORK_DESTINATIONS: list[Destination] = [
    Destination("LHR", "London Heathrow", "GB"),
    Destination("LGW", "London Gatwick", "GB"),
    Destination("LTN", "London Luton", "GB"),
    Destination("STN", "London Stansted", "GB"),
    Destination("MAN", "Manchester", "GB"),
    Destination("BHX", "Birmingham", "GB"),
    Destination("LPL", "Liverpool", "GB"),
    Destination("BRS", "Bristol", "GB"),
    Destination("EDI", "Edinburgh", "GB"),
    Destination("GLA", "Glasgow", "GB"),
]

CANDIDATES_BY_ORIGIN: dict[str, list[Destination]] = {
    "ORK": CORK_DESTINATIONS,
    "SNN": SHANNON_DESTINATIONS,
}


def get_candidates(origin: str, exclude_countries: set[str]) -> list[Destination]:
    """Candidate destinations for `origin`, with Irish airports filtered out."""
    origin = origin.upper()
    pool = CANDIDATES_BY_ORIGIN.get(origin, [])
    exclude = {c.upper() for c in exclude_countries} | {"IE"}
    return [
        d for d in pool
        if d.iata not in IRISH_AIRPORTS and d.country not in exclude
    ]