"""Flight data source: an abstract interface plus a Google-Flights-backed
implementation, so the scraping backend can be swapped out later without
touching the GUI, scheduler, or email code.
"""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from destinations import Destination, get_candidates

log = logging.getLogger("flight_watcher.source")

DEBUG_HTML_DIR = Path(__file__).resolve().parent / "debug_html"

# Temporary diagnostic aid: always save the raw response for these specific
# (origin, destination) pairs, even when parsing succeeds. Google Flights'
# results list is widely known to show a PER-TRAVELER price (with a "Price
# is per traveler" disclaimer on the real site) rather than a party total
# when multiple passengers are searched - suspected cause of prices not
# reflecting the 2-adults-1-child party size. Need a real multi-passenger
# response to confirm what the underlying `price` field actually contains
# before fixing. Remove once diagnosed.
FORCE_DEBUG_ROUTES = {("SNN", "STN")}


def _parse_flights_response(html: str):
    """A fixed copy of `fast_flights.parser.parse` / `parse_js`.

    Diagnosed from real captured responses (see debug_html/): when Google
    genuinely has zero non-stop itineraries for the exact requested dates,
    it still returns a normal 200 page (with a "nearby dates" price
    calendar elsewhere in the payload), but the slot the upstream library
    expects the itinerary list at (`payload[3][0]`) is `None` at the outer
    level (`payload[3]` itself, not just `payload[3][0]`). The upstream
    `parse_js` only guards the inner case, so it crashes with `'NoneType'
    object is not subscriptable` on what is actually a completely normal
    "no direct flights that day" result. This copy adds the missing check
    so that case comes back as a clean, empty result list instead.
    """
    import json

    from fast_flights.exceptions import FlightsNotFound
    from fast_flights.model import Airline, Airport, Alliance, CarbonEmission, Flights, JsMetadata, SimpleDatetime, SingleFlight
    from fast_flights.parser import _parse_time
    from selectolax.lexbor import LexborHTMLParser

    from fast_flights.parser import ResultList

    parser = LexborHTMLParser(html)
    script = parser.css_first(r"script.ds\:1")
    if script is None:
        raise RuntimeError("expected script.ds:1 tag not found in response")
    js = script.text()

    data = js.split("data:", 1)[1].rsplit(",", 1)[0]
    if data.endswith("errorHasStatus: true"):
        raise FlightsNotFound("no flights found; received error")

    payload = json.loads(data)

    alliances = []
    airlines = []
    (alliances_data, airlines_data) = (payload[7][1][0], payload[7][1][1])
    for code, name in alliances_data:
        alliances.append(Alliance(code=code, name=name))
    for code, name in airlines_data:
        airlines.append(Airline(code=code, name=name))
    meta = JsMetadata(alliances=alliances, airlines=airlines)

    flights = ResultList()
    # The fix: payload[3] can be None outright (no results at all), not
    # just payload[3][0] (results container present but empty).
    if payload[3] is None or payload[3][0] is None:
        flights.metadata = meta
        return flights

    for k in payload[3][0]:
        flight = k[0]
        price = k[1][0][1]
        typ = flight[0]
        flight_airlines = flight[1]

        sg_flights = []
        for single_flight in flight[2]:
            from_airport = Airport(code=single_flight[3], name=single_flight[4])
            to_airport = Airport(code=single_flight[6], name=single_flight[5])
            departure = SimpleDatetime(date=tuple(single_flight[20]), time=_parse_time(single_flight[8]))
            arrival = SimpleDatetime(date=tuple(single_flight[21]), time=_parse_time(single_flight[10]))
            sg_flights.append(
                SingleFlight(
                    from_airport=from_airport,
                    to_airport=to_airport,
                    departure=departure,
                    arrival=arrival,
                    duration=single_flight[11],
                    plane_type=single_flight[17],
                )
            )

        extras = flight[22]
        flights.append(
            Flights(
                type=typ,
                price=price,
                airlines=flight_airlines,
                flights=sg_flights,
                carbon=CarbonEmission(typical_on_route=extras[8], emission=extras[7]),
            )
        )

    flights.metadata = meta
    return flights


@dataclass
class FlightResult:
    origin_code: str
    origin_name: str
    destination_code: str
    destination_city: str
    date_out: date
    date_back: date
    price: float
    currency: str
    outbound_departure: str  # "HH:MM"
    outbound_arrival: str
    return_departure: str
    return_arrival: str
    outbound_flight_number: str = "N/A"
    return_flight_number: str = "N/A"

    def price_display(self) -> str:
        symbol = {"EUR": "€", "GBP": "£", "USD": "$"}.get(self.currency, self.currency + " ")
        return f"{symbol}{self.price:.0f}"


class FlightSource(ABC):
    """Interface every flight-data backend must implement."""

    @abstractmethod
    def search_cheapest_direct(
        self,
        origin: str,
        origin_name: str,
        date_out: date,
        date_back: date,
        candidates: list[Destination],
    ) -> list[FlightResult]:
        """Return direct-flight results for `origin`, one attempt per
        candidate destination, sorted cheapest first. Destinations with no
        direct flight (or a lookup failure) are simply omitted."""
        raise NotImplementedError


class GoogleFlightsSource(FlightSource):
    """Uses the `fast-flights` library, which queries Google Flights'
    internal (undocumented) endpoints without full browser automation.

    Caveats (see README "Limitations"):
      - Google Flights has no public API and can change its internal
        format at any time, breaking this without warning.
      - Scraping Google Flights is against its Terms of Service — this is
        a personal/hobby tool, not something to deploy at scale.
      - The results-list view Google returns does not include the actual
        flight number, so `outbound_flight_number` / `return_flight_number`
        stay "N/A" here. Getting real flight numbers would require opening
        each itinerary's detail view individually, which multiplies the
        number of requests (and the chance of getting blocked).
      - For any request that looks like it's coming from the EU/EEA/UK
        (which includes Ireland), Google inserts a cookie-consent
        interstitial ("Before you continue to Google...") instead of
        returning flight results directly. This class pre-sets the
        cookies Google's own "reject/accept" button would set, to skip
        that page — see `_CONSENT_COOKIES` / `_fetch()` below. Google has
        two overlapping consent mechanisms (the older `CONSENT` cookie and
        the newer Consent-Mode-v2 `SOCS` cookie); both are set, and passed
        directly on every request rather than relying only on the client's
        cookie jar, since the jar alone wasn't reliably enough to stop the
        redirect in testing.
      - A single "round-trip" query to this endpoint only returns the
        OUTBOUND leg's options (each tagged with an estimated round-trip
        price) — getting the matching return-leg options back requires a
        second, follow-up request carrying a "selected outbound flight"
        token, mirroring the two-step flow the real google.com/travel
        UI uses (pick your outbound, then it shows you return options).
        Confirmed against a real captured response: a 2-leg round-trip
        query for a route with real, verified availability came back with
        3 results that each had only 1 leg (the outbound), not 2.
        Reproducing that full token handshake is significant extra
        complexity for a personal tool, so instead this class runs the
        outbound and return as two independent one-way searches and adds
        their cheapest direct fares together. For the low-cost carriers
        that dominate Cork/Shannon's network (Ryanair etc.), this is
        actually a good match for reality — those fares are priced
        per-direction anyway, with no real combined round-trip discount
        to miss.
    """

    _CONSENT_COOKIES = {
        "CONSENT": "YES+",
        # A pre-accepted Consent-Mode-v2 blob. Google doesn't appear to
        # validate its embedded timestamp/region for this purpose — it
        # just checks that a plausibly-shaped SOCS cookie is present.
        "SOCS": "CAESHwgBEhJnd3NfMjAyNTAyMjctMF9SQzIaBXpoLUNOIAEaBgiAy6O-Bg",
    }

    def __init__(self, currency: str = "EUR", adults: int = 1, children: int = 0):
        self.currency = currency
        self.adults = adults
        self.children = children
        self._client = self._make_client()

    def _make_client(self):
        from primp import Client

        client = Client(
            impersonate="chrome_145",  # matches the profile fast_flights itself uses
            impersonate_os="macos",
            referer=True,
            cookie_store=True,
        )
        client.set_cookies("https://www.google.com", self._CONSENT_COOKIES)
        return client

    def search_cheapest_direct(
        self,
        origin: str,
        origin_name: str,
        date_out: date,
        date_back: date,
        candidates: list[Destination],
    ) -> list[FlightResult]:
        results: list[FlightResult] = []
        first_request = True

        for dest in candidates:
            def paced_fetch(from_ap: str, to_ap: str, on_date: date):
                nonlocal first_request
                if not first_request:
                    # A short, randomised pause between requests. Firing
                    # ~40-60 requests back-to-back with no gap is a classic
                    # trigger for Google's automated-traffic detection.
                    time.sleep(random.uniform(1.5, 3.5))
                first_request = False
                query = self._build_one_way_query(from_ap, to_ap, on_date)
                return self._fetch(query, origin=from_ap, dest=to_ap)

            try:
                outbound_flights = paced_fetch(origin, dest.iata, date_out)
                outbound_leg = self._cheapest_direct_leg(outbound_flights)
                if outbound_leg is None:
                    log.info("No non-stop %s->%s outbound for %s", origin, dest.iata, date_out)
                    continue

                return_flights = paced_fetch(dest.iata, origin, date_back)
                return_leg = self._cheapest_direct_leg(return_flights)
                if return_leg is None:
                    log.info("No non-stop %s->%s return for %s", dest.iata, origin, date_back)
                    continue
            except Exception as exc:  # noqa: BLE001 - one bad destination shouldn't kill the run
                log.warning("No direct itinerary from %s to %s: %s", origin, dest.iata, exc)
                continue

            out_price, out_leg = outbound_leg
            back_price, back_leg = return_leg
            results.append(
                FlightResult(
                    origin_code=origin,
                    origin_name=origin_name,
                    destination_code=dest.iata,
                    destination_city=f"{dest.city}, {dest.country}",
                    date_out=date_out,
                    date_back=date_back,
                    price=out_price + back_price,
                    currency=self.currency,
                    outbound_departure=self._fmt_time(out_leg.departure.time),
                    outbound_arrival=self._fmt_time(out_leg.arrival.time),
                    return_departure=self._fmt_time(back_leg.departure.time),
                    return_arrival=self._fmt_time(back_leg.arrival.time),
                )
            )

        results.sort(key=lambda r: r.price)
        return results

    def _build_one_way_query(self, from_ap: str, to_ap: str, on_date: date):
        import fast_flights as ff

        return ff.create_query(
            flights=[ff.FlightQuery(date=on_date.isoformat(), from_airport=from_ap, to_airport=to_ap)],
            trip="one-way",
            seat="economy",
            passengers=ff.Passengers(adults=self.adults, children=self.children),
            currency=self.currency,
            max_stops=0,  # direct flights only
        )

    def _fetch(self, query, *, origin: str = "", dest: str = ""):
        """Fetch + parse one query's HTML ourselves (instead of calling
        `fast_flights.get_flights` directly), so we can use our own
        consent-cookie-primed client. Raises if Google still serves the
        consent interstitial or the page can't be parsed.

        The consent cookies are sent three redundant ways (client-level
        jar, per-request `cookies=`, and a raw `Cookie` header) because in
        testing the jar alone wasn't consistently enough to stop the
        redirect - if one mechanism is silently ignored, the others still
        get the cookies onto the wire.
        """
        from fast_flights.exceptions import FlightsNotFound

        cookie_header = "; ".join(f"{k}={v}" for k, v in self._CONSENT_COOKIES.items())
        res = self._client.get(
            "https://www.google.com/travel/flights",
            params=query.params(),
            cookies=self._CONSENT_COOKIES,
            headers={"Cookie": cookie_header},
        )
        if (origin, dest) in FORCE_DEBUG_ROUTES:
            path = self._save_debug_html(res.text, origin, dest)
            log.info("Diagnostic capture for %s->%s saved to %s", origin, dest, path)
        if "consent.google.com" in res.url:
            raise RuntimeError(
                "Google served a cookie-consent page instead of flight results "
                "(consent-cookie bypass didn't take effect this time)"
            )
        try:
            # Our own parser (see `_parse_flights_response` above), not
            # `fast_flights.parser.parse` - it has a fix for a crash on a
            # perfectly normal "no non-stop itinerary for these exact
            # dates" response (confirmed against real captured responses).
            return _parse_flights_response(res.text)
        except FlightsNotFound:
            # A clean, expected outcome: Google genuinely has no itinerary
            # for this route/date combo. Nothing to debug - just no result.
            raise
        except Exception as exc:  # noqa: BLE001 - unexpected page shape; capture it for diagnosis
            path = self._save_debug_html(res.text, origin, dest)
            raise RuntimeError(
                f"couldn't parse Google's response ({exc}); raw page saved to {path} for inspection"
            ) from exc

    @staticmethod
    def _save_debug_html(html: str, origin: str, dest: str) -> Path:
        DEBUG_HTML_DIR.mkdir(exist_ok=True)
        filename = f"{origin}_{dest}_{time.strftime('%Y%m%d_%H%M%S')}.html"
        path = DEBUG_HTML_DIR / filename
        path.write_text(html, encoding="utf-8", errors="replace")
        return path

    @staticmethod
    def _cheapest_direct_leg(flights):
        """From a `fast_flights` ResultList for a ONE-WAY search, pick the
        cheapest itinerary that is genuinely a single non-stop segment, and
        return (price, leg). None if nothing qualifies."""
        candidates = []
        for itinerary in flights:
            if itinerary.type == "multi":
                continue  # separate-ticket / self-transfer, not a clean direct flight
            legs = itinerary.flights
            if len(legs) != 1:
                continue  # a real non-stop one-way is exactly one segment
            candidates.append((itinerary.price, legs[0]))

        if not candidates:
            return None
        return min(candidates, key=lambda c: c[0])

    @staticmethod
    def _fmt_time(hm: tuple[int, int]) -> str:
        h, m = hm
        return f"{h:02d}:{m:02d}"
