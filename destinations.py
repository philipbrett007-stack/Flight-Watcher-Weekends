"""Candidate destination airports for the "cheapest anywhere" search.

Google Flights has no public "explore every destination" API. A fully
exhaustive search would mean scraping an unbounded, undocumented set of
routes, which is both unreliable and the fastest way to get IP-blocked.
Instead, this module holds a maintained list of the destinations actually
served *directly* from Cork and Shannon (per the airlines that fly from
each airport), and the tool finds the cheapest fare among those.

This list will drift out of date as airlines add/drop seasonal routes —
review and edit it periodically. IATA "country" here uses "IE" to mean
the island of Ireland (Republic + Northern Ireland), since the user wants
destinations outside Ireland altogether, not just outside the Republic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Destination:
    iata: str
    city: str
    country: str  # ISO alpha-2, or "IE" for the island of Ireland


# All Irish airports (Republic + Northern Ireland) — always excluded from
# candidate destination lists, regardless of what's listed below.
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

# Known direct destinations from Cork (ORK). Edit freely.
CORK_DESTINATIONS: list[Destination] = [
    Destination("LHR", "London", "GB"),
    Destination("LGW", "London", "GB"),
    Destination("STN", "London", "GB"),
    Destination("MAN", "Manchester", "GB"),
    Destination("BHX", "Birmingham", "GB"),
    Destination("EDI", "Edinburgh", "GB"),
    Destination("BRS", "Bristol", "GB"),
    Destination("LPL", "Liverpool", "GB"),
    Destination("AMS", "Amsterdam", "NL"),
    Destination("CDG", "Paris", "FR"),
    Destination("BRU", "Brussels", "BE"),
    Destination("FRA", "Frankfurt", "DE"),
    Destination("MUC", "Munich", "DE"),
    Destination("BER", "Berlin", "DE"),
    Destination("BCN", "Barcelona", "ES"),
    Destination("AGP", "Malaga", "ES"),
    Destination("ALC", "Alicante", "ES"),
    Destination("PMI", "Palma de Mallorca", "ES"),
    Destination("FAO", "Faro", "PT"),
    Destination("LIS", "Lisbon", "PT"),
    Destination("OPO", "Porto", "PT"),
    Destination("BGY", "Milan (Bergamo)", "IT"),
    Destination("MXP", "Milan", "IT"),
    Destination("FCO", "Rome", "IT"),
    Destination("NCE", "Nice", "FR"),
    Destination("KEF", "Reykjavik", "IS"),
    Destination("LPA", "Gran Canaria", "ES"),
    Destination("TFS", "Tenerife", "ES"),
    Destination("ACE", "Lanzarote", "ES"),
    Destination("FUE", "Fuerteventura", "ES"),
]

# Known direct destinations from Shannon (SNN). Edit freely.
SHANNON_DESTINATIONS: list[Destination] = [
    Destination("STN", "London", "GB"),
    Destination("LGW", "London", "GB"),
    Destination("MAN", "Manchester", "GB"),
    Destination("BHX", "Birmingham", "GB"),
    Destination("EDI", "Edinburgh", "GB"),
    Destination("LPL", "Liverpool", "GB"),
    Destination("FAO", "Faro", "PT"),
    Destination("ALC", "Alicante", "ES"),
    Destination("AGP", "Malaga", "ES"),
    Destination("PMI", "Palma de Mallorca", "ES"),
    Destination("LPA", "Gran Canaria", "ES"),
    Destination("TFS", "Tenerife", "ES"),
    Destination("ACE", "Lanzarote", "ES"),
]

CANDIDATES_BY_ORIGIN: dict[str, list[Destination]] = {
    "ORK": CORK_DESTINATIONS,
    "SNN": SHANNON_DESTINATIONS,
}


def get_candidates(origin: str, exclude_countries: set[str]) -> list[Destination]:
    """Candidate destinations for `origin`, with Irish airports and any
    extra excluded countries filtered out."""
    origin = origin.upper()
    pool = CANDIDATES_BY_ORIGIN.get(origin, [])
    exclude = {c.upper() for c in exclude_countries} | {"IE"}
    return [
        d for d in pool
        if d.iata not in IRISH_AIRPORTS and d.country not in exclude
    ]
