"""Entry point: load config, build the flight source, launch the Streamlit web app."""

from __future__ import annotations

import logging
import streamlit as st
import pandas as pd

from config import load_settings
from flight_source import GoogleFlightsSource

# Configure page display for mobile & desktop web view
st.set_page_config(
    page_title="Flight Watcher",
    page_icon="✈️",
    layout="wide"
)

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    st.title("✈️ Google Flight Watcher")
    st.write("Track flight prices and updates directly from your browser.")

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

    # Web Dashboard Interface
    st.sidebar.header("Flight Search Settings")
    st.sidebar.write(f"**Currency:** {settings.search.currency}")
    st.sidebar.write(f"**Adults:** {settings.search.adults}")
    st.sidebar.write(f"**Children:** {settings.search.children}")

    if st.button("Search Flights Now", type="primary"):
        with st.spinner("Fetching latest flight data..."):
            try:
                # Replace with your actual search execution call
                st.info("Querying flight search source...")
                # Example display placeholder:
                # flights = source.get_flights()
                # st.dataframe(pd.DataFrame(flights))
            except Exception as err:
                st.error(f"Failed to fetch flight data: {err}")

if __name__ == "__main__":
    main()