"""Entry point: load config, build the flight source, launch the Streamlit web app."""

from __future__ import annotations

import logging
from datetime import date
import streamlit as st
import pandas as pd

from config import load_settings
from flight_source import GoogleFlightsSource
from destinations import get_candidates, AIRPORT_NAMES
from trip_dates import next_trip_dates

# Configure page display for mobile & desktop web view
st.set_page_config(
    page_title="UK Flight Watcher",
    page_icon="✈️",
    layout="wide"
)

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    st.title("✈️ Google Flight Watcher (UK Routes)")
    st.write("Track low-cost direct flight prices from Cork and Shannon to the UK.")

    # Load configuration settings
    try:
        settings = load_settings()
        source = GoogleFlightsSource(
            currency=settings.search.currency,
            adults=settings.search.adults,
            children=settings.search.children,
        )
        st.success("Configuration loaded successfully!")
    except Exception as e:
        st.error(f"Error loading configuration: {e}")
        return

    # Web Dashboard Sidebar Controls
    st.sidebar.header("Flight Search Settings")
    st.sidebar.write(f"**Origins:** {', '.join(settings.search.origin_airports)}")
    st.sidebar.write(f"**Currency:** {settings.search.currency}")
    st.sidebar.write(f"**Adults:** {settings.search.adults}")
    st.sidebar.write(f"**Children:** {settings.search.children}")

    if st.button("Search Flights Now", type="primary"):
        date_out, date_back = next_trip_dates(
            today=date.today(),
            on_friday_means_today=settings.search.on_friday_means_today,
            trip_nights=settings.search.trip_nights,
        )

        st.info(f"Searching weekend flights for **{date_out.strftime('%a %d %b %Y')} → {date_back.strftime('%a %d %b %Y')}**")

        all_results = []
        
        # Calculate total candidates for progress bar tracking
        total_tasks = sum(
            len(get_candidates(origin, set(settings.search.exclude_countries)))
            for origin in settings.search.origin_airports
        )
        
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        current_step = 0

        for origin in settings.search.origin_airports:
            origin_name = AIRPORT_NAMES.get(origin, origin)
            candidates = get_candidates(origin, set(settings.search.exclude_countries))

            for dest in candidates:
                current_step += 1
                progress = current_step / max(total_tasks, 1)
                status_text.text(f"Checking {origin_name} ({origin}) → {dest.city} ({dest.iata})... [{current_step}/{total_tasks}]")
                
                # Fetch route
                try:
                    res = source.search_cheapest_direct(
                        origin=origin,
                        origin_name=origin_name,
                        date_out=date_out,
                        date_back=date_back,
                        candidates=[dest]
                    )
                    if res:
                        all_results.extend(res)
                except Exception as err:
                    st.warning(f"Could not check {origin} to {dest.iata}: {err}")

                progress_bar.progress(progress)

        status_text.success("Search complete!")

        # Display Output Table
        if all_results:
            st.subheader("Cheapest Direct UK Flights Found")
            
            table_data = []
            for r in sorted(all_results, key=lambda x: x.price):
                table_data.append({
                    "From": r.origin_name,
                    "Destination": r.destination_city,
                    "Total Price": r.price_display(),
                    "Outbound": f"{r.outbound_departure} → {r.outbound_arrival}",
                    "Return": f"{r.return_departure} → {r.return_arrival}"
                })
            
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No direct flights found for the selected dates.")

if __name__ == "__main__":
    main()