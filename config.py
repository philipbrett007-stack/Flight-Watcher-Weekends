"""Loads config.ini + the .env file into a single typed Settings object."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.ini"
ENV_PATH = BASE_DIR / ".env"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency required)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class EmailSettings:
    enabled: bool
    subject: str
    sender: str
    recipient: str
    smtp_server: str
    smtp_port: int
    send_on_manual_run: bool
    app_password: str = field(repr=False, default="")


@dataclass
class ScheduleSettings:
    time_str: str  # "HH:MM"
    timezone: str

    @property
    def hour(self) -> int:
        return int(self.time_str.split(":")[0])

    @property
    def minute(self) -> int:
        return int(self.time_str.split(":")[1])


@dataclass
class SearchSettings:
    origin_airports: list[str]
    exclude_countries: list[str]
    top_n_results: int
    on_friday_means_today: bool
    trip_nights: int
    currency: str
    adults: int
    children: int


@dataclass
class Settings:
    search: SearchSettings
    schedule: ScheduleSettings
    email: EmailSettings


def load_settings(config_path: Path = CONFIG_PATH, env_path: Path = ENV_PATH) -> Settings:
    _load_dotenv(env_path)

    parser = configparser.ConfigParser()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing config file: {config_path}. Copy config.ini.example if needed."
        )
    parser.read(config_path, encoding="utf-8")

    origins = [a.strip().upper() for a in parser.get("origins", "airports").split(",") if a.strip()]
    exclude = [c.strip().upper() for c in parser.get("search", "exclude_countries").split(",") if c.strip()]

    search = SearchSettings(
        origin_airports=origins,
        exclude_countries=exclude,
        top_n_results=parser.getint("search", "top_n_results", fallback=1),
        on_friday_means_today=parser.getboolean("search", "on_friday_means_today", fallback=False),
        trip_nights=parser.getint("search", "trip_nights", fallback=2),
        currency=parser.get("search", "currency", fallback="EUR"),
        adults=parser.getint("search", "adults", fallback=1),
        children=parser.getint("search", "children", fallback=0),
    )

    schedule = ScheduleSettings(
        time_str=parser.get("schedule", "time", fallback="18:00"),
        timezone=parser.get("schedule", "timezone", fallback="Europe/Dublin"),
    )

    email = EmailSettings(
        enabled=parser.getboolean("email", "enabled", fallback=True),
        subject=parser.get("email", "subject", fallback="Phil's Low Cost Flight Analysis"),
        sender=parser.get("email", "sender", fallback=""),
        recipient=parser.get("email", "recipient", fallback=""),
        smtp_server=parser.get("email", "smtp_server", fallback="smtp.gmail.com"),
        smtp_port=parser.getint("email", "smtp_port", fallback=465),
        send_on_manual_run=parser.getboolean("email", "send_on_manual_run", fallback=False),
        app_password=os.environ.get("EMAIL_APP_PASSWORD", ""),
    )

    return Settings(search=search, schedule=schedule, email=email)
