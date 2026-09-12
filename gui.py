"""Tkinter GUI: two result tables (Cork, Shannon), a Run Now button, and a
status/log panel. Network calls run on a background thread so the window
never freezes; results come back through a thread-safe queue.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from check_runner import CheckOutcome, run_check
from config import Settings
from email_sender import send_summary_email
from flight_source import FlightResult, FlightSource
from scheduler_service import DailyScheduler

log = logging.getLogger("flight_watcher.gui")

AIRPORT_NAMES = {"ORK": "Cork", "SNN": "Shannon"}
COLUMNS = ("destination", "price", "out_time", "back_time", "route")


class FlightWatcherApp:
    def __init__(self, root: tk.Tk, settings: Settings, source: FlightSource):
        self.root = root
        self.settings = settings
        self.source = source
        self.result_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.trees: dict[str, ttk.Treeview] = {}
        self.last_outcome: CheckOutcome | None = None

        root.title("Flight Watcher — Cork & Shannon Weekend Getaways")
        root.geometry("900x600")

        self._build_widgets()

        self.scheduler = DailyScheduler(settings.schedule, job=self._scheduled_job)
        self.scheduler.start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._poll_queue()
        self._tick_status()

    # ---------- UI construction ----------

    def _build_widgets(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        self.run_button = ttk.Button(top, text="Run Now", command=self.run_now)
        self.run_button.pack(side="left")

        self.send_email_button = ttk.Button(
            top, text="Send Email Now", command=self.send_email_now, state="disabled"
        )
        self.send_email_button.pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="Starting up…")
        ttk.Label(top, textvariable=self.status_var).pack(side="left", padx=12)

        party = self._party_label()
        ttk.Label(top, text=f"Prices shown are TOTAL for {party}", foreground="#555").pack(side="right")

        notebook = ttk.Frame(self.root, padding=(10, 0))
        notebook.pack(fill="both", expand=True)

        for origin in self.settings.search.origin_airports:
            frame = ttk.LabelFrame(notebook, text=f"{AIRPORT_NAMES.get(origin, origin)} ({origin})")
            frame.pack(fill="both", expand=True, pady=6)

            tree = ttk.Treeview(frame, columns=COLUMNS, show="headings", height=6)
            headings = {
                "destination": "Destination",
                "price": "Price (total)",
                "out_time": "Outbound (local)",
                "back_time": "Return (local)",
                "route": "Flight #s",
            }
            widths = {"destination": 220, "price": 90, "out_time": 150, "back_time": 150, "route": 160}
            for col in COLUMNS:
                tree.heading(col, text=headings[col])
                tree.column(col, width=widths[col], anchor="w")
            tree.pack(fill="both", expand=True, padx=4, pady=4)
            self.trees[origin] = tree

        log_frame = ttk.LabelFrame(self.root, text="Log", padding=6)
        log_frame.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log_text = tk.Text(log_frame, height=8, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)

    # ---------- actions ----------

    def run_now(self) -> None:
        self.run_button.config(state="disabled")
        self.status_var.set("Checking flights…")
        self._log(f"[{self._now()}] Manual run started.")
        threading.Thread(
            target=self._background_run,
            args=(self.settings.email.send_on_manual_run,),
            daemon=True,
        ).start()

    def send_email_now(self) -> None:
        """Emails the most recent results shown on screen, on demand —
        for when you ran a check outside the scheduled 18:00 slot (which
        normally doesn't email unless `send_on_manual_run` is set) and
        want to send yourself that result anyway."""
        if self.last_outcome is None:
            self._log(f"[{self._now()}] No results yet — click Run Now first.")
            return
        self.send_email_button.config(state="disabled")
        self._log(f"[{self._now()}] Sending email with the results currently shown…")
        threading.Thread(target=self._background_send_email, args=(self.last_outcome,), daemon=True).start()

    def _background_send_email(self, outcome: CheckOutcome) -> None:
        try:
            send_summary_email(
                self.settings.email,
                outcome.results_by_origin,
                outcome.date_out,
                outcome.date_back,
                outcome.errors,
                adults=self.settings.search.adults,
                children=self.settings.search.children,
            )
            self.result_queue.put(("email_sent", None))
        except Exception as exc:  # noqa: BLE001
            log.exception("Manual email send failed")
            self.result_queue.put(("email_error", str(exc)))

    def _scheduled_job(self) -> None:
        # Runs on APScheduler's own thread.
        self._log(f"[{self._now()}] Scheduled 18:00 run started.")
        self._background_run(send_email=True)

    def _background_run(self, send_email: bool) -> None:
        try:
            outcome = run_check(self.settings, self.source, send_email)
            self.result_queue.put(("done", outcome))
        except Exception as exc:  # noqa: BLE001
            log.exception("Check failed")
            self.result_queue.put(("error", str(exc)))

    # ---------- queue / polling (keeps all Tk calls on the main thread) ----------

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "done":
                    self._apply_outcome(payload)  # type: ignore[arg-type]
                    self.run_button.config(state="normal")
                elif kind == "error":
                    self.status_var.set("Last run failed — see log.")
                    self._log(f"[{self._now()}] ERROR: {payload}")
                    self.run_button.config(state="normal")
                elif kind == "email_sent":
                    self._log(f"[{self._now()}] Email sent to {self.settings.email.recipient}.")
                    self.send_email_button.config(state="normal")
                elif kind == "email_error":
                    self._log(f"[{self._now()}] Email failed: {payload}")
                    self.send_email_button.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    def _tick_status(self) -> None:
        nxt = self.scheduler.next_run_time()
        if nxt is not None and "Checking" not in self.status_var.get():
            self.status_var.set(f"Next scheduled check: {nxt.strftime('%a %d %b %Y %H:%M %Z')}")
        self.root.after(30_000, self._tick_status)

    def _apply_outcome(self, outcome: CheckOutcome) -> None:
        self.last_outcome = outcome
        self.send_email_button.config(state="normal")
        for origin, tree in self.trees.items():
            for row in tree.get_children():
                tree.delete(row)
            for r in outcome.results_by_origin.get(origin, []):
                tree.insert("", "end", values=(
                    r.destination_city,
                    r.price_display(),
                    f"{r.outbound_departure} → {r.outbound_arrival}",
                    f"{r.return_departure} → {r.return_arrival}",
                    f"{r.outbound_flight_number} / {r.return_flight_number}",
                ))
            if origin in outcome.errors:
                self._log(f"[{self._now()}] {origin}: {outcome.errors[origin]}")

        trip = f"{outcome.date_out.strftime('%a %d %b')} → {outcome.date_back.strftime('%a %d %b')}"
        if outcome.ok:
            self.status_var.set(f"Last check OK ({trip}) at {self._now()}")
        else:
            self.status_var.set(f"Last check had errors ({trip}) — see log.")
        self._log(f"[{self._now()}] Run complete for {trip}.")

    # ---------- helpers ----------

    def _log(self, line: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _party_label(self) -> str:
        adults = self.settings.search.adults
        children = self.settings.search.children
        parts = [f"{adults} adult{'s' if adults != 1 else ''}"]
        if children:
            parts.append(f"{children} child{'ren' if children != 1 else ''}")
        return " + ".join(parts)

    def _on_close(self) -> None:
        self.scheduler.shutdown()
        self.root.destroy()
