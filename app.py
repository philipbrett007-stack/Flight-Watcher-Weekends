"""Entry point: query Google Flights via SerpApi to bypass cloud IP blocks."""

from __future__ import annotations

import logging
from datetime import date
import streamlit as st
import pandas as pd
from serpapi import GoogleSearch

from destinations import get_candidates, AIRPORT_NAMES
from trip_dates import next_trip_dates

st.set_page_config(
    page_title="UK Flight Watcher",
    page_icon="✈️",
    layout="wide"
)

def search_serpapi_flights(api_key: str, origin: str, dest_code: str, date_out: date, date_back: date):
    """Query SerpApi Google Flights engine for non-stop round trips."""
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": dest_code,
        "outbound_date": date_out.strftime("%Y-%m-%d"),
        "return_date": date_back.strftime("%Y-%m-%d"),
        "currency": "EUR",
        "hl": "en",
        "type": "1",  # Round trip
        "stops": "1", # Direct flights (1 = non-stop in SerpApi)
        "api_key": api_key,
    }

    search = GoogleSearch(params)
    results = search.get_dict()

    if "error" in results:
        st.warning(f"SerpApi Warning ({origin}->{dest_code}): {results['error']}")
        return None

    # Retrieve best flights list
    best_flights = results.get("best_flights", []) or results.get("other_flights", [])
    if not best_flights:
        return None

    cheapest = best_flights[0]
    price = cheapest.get("price", 0)

    # Outbound & Return flight leg details
    legs = cheapest.get("flights", [])
    outbound_dep = legs[0]["departure_airport"]["time"] if legs else "N/A"
    outbound_arr = legs[0]["arrival_airport"]["time"] if legs else "N/A"
    
    return_dep = legs[-1]["departure_airport"]["time"] if len(legs) > 1 else "N/A"
    return_arr = legs[-1]["arrival_airport"]["time"] if len(legs) > 1 else "N/A"

    return {
        "origin_code": origin,
        "destination_code": dest_code,
        "price": price,
        "outbound": f"{outbound_dep} → {outbound_arr}",
        "return": f"{return_dep} → {return_arr}",
    }

def main() -> None:
    logging.basicConfig(level=logging.INFO)

    st.title("✈️ Google Flight Watcher (SerpApi Powered)")
    st.write("Track low-cost direct flight prices from Cork and Shannon to the UK.")

    # Retrieve Secrets
    api_key = st.secrets.get("SERPAPI_KEY", "")
    if not api_key:
        st.error("Missing `SERPAPI_KEY` in Streamlit Secrets! Please add it under Settings > Secrets.")
        return

    st.sidebar.header("Flight Search Settings")
    st.sidebar.write("**Origins:** ORK, SNN")
    st.sidebar.write("**Currency:** EUR")

    if st.button("Search Flights Now", type="primary"):
        date_out, date_back = next_trip_dates(
            today=date.today(),
            on_friday_means_today=False,
            trip_nights=2,
        )

        st.info(f"Searching weekend flights for **{date_out.strftime('%a %d %b %Y')} → {date_back.strftime('%a %d %b %Y')}**")

        all_results = []
        origins = ["ORK", "SNN"]
        
        # Count total candidate destinations
        total_tasks = sum(len(get_candidates(o, {"IE"})) for o in origins)
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        current_step = 0

        for origin in origins:
            origin_name = AIRPORT_NAMES.get(origin, origin)
            candidates = get_candidates(origin, {"IE"})

            for dest in candidates:
                current_step += 1
                status_text.text(f"Querying {origin_name} ({origin}) → {dest.city} ({dest.iata})... [{current_step}/{total_tasks}]")
                
                res = search_serpapi_flights(api_key, origin, dest.iata, date_out, date_back)
                if res:
                    res["origin_name"] = origin_name
                    res["destination_city"] = dest.city
                    all_results.append(res)

                progress_bar.progress(current_step / total_tasks)

        status_text.success("Search complete!")

        if all_results:
            st.subheader("Cheapest Direct UK Flights Found")
            
            table_data = []
            for r in sorted(all_results, key=lambda x: x["price"]):
                table_data.append({
                    "From": r["origin_name"],
                    "Destination": r["destination_city"],
                    "Total Price": f"€{r['price']}",
                    "Outbound": r["outbound"],
                    "Return": r["return"]
                })
            
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No direct flights found for selected dates.")

if __name__ == "__main__":
    main()