"""Background daily scheduler, timezone-aware (so it doesn't drift with DST)."""

from __future__ import annotations

import logging
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import ScheduleSettings

log = logging.getLogger("flight_watcher.scheduler")


class DailyScheduler:
    def __init__(self, settings: ScheduleSettings, job: Callable[[], None]):
        self._settings = settings
        self._job = job
        self._scheduler = BackgroundScheduler()

    def start(self) -> None:
        trigger = CronTrigger(
            hour=self._settings.hour,
            minute=self._settings.minute,
            timezone=self._settings.timezone,
        )
        self._scheduler.add_job(self._job, trigger, id="daily_flight_check", replace_existing=True)
        self._scheduler.start()
        log.info(
            "Scheduled daily check at %02d:%02d %s",
            self._settings.hour,
            self._settings.minute,
            self._settings.timezone,
        )

    def next_run_time(self):
        job = self._scheduler.get_job("daily_flight_check")
        return job.next_run_time if job else None

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
