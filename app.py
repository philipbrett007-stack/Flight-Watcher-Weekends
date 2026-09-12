"""Entry point: load config, build the flight source, launch the GUI."""

from __future__ import annotations

import logging
import tkinter as tk

from config import load_settings
from flight_source import GoogleFlightsSource
from gui import FlightWatcherApp


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = load_settings()
    source = GoogleFlightsSource(
        currency=settings.search.currency,
        adults=settings.search.adults,
        children=settings.search.children,
    )

    root = tk.Tk()
    FlightWatcherApp(root, settings, source)
    root.mainloop()


if __name__ == "__main__":
    main()
