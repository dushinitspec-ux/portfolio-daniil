"""Application settings, loaded from environment variables or a `.env` file."""

from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Prices bundled for the offline demo and the backtest (real data, see the file's header).
DEFAULT_FIXTURE = Path(__file__).parent.parent / "fixtures" / "energy-charts-de-lu.json"


class Settings(BaseSettings):
    # env_ignore_empty: "PLAN_CHAT_ID=" in .env means "not set", not "parse '' as a number".
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    # Demo mode: bundled real prices, no network, a fixed clock.
    demo_mode: bool = False
    demo_fixture: Path = DEFAULT_FIXTURE
    devices_file: Path = Path("devices.yaml")

    # Market
    bidding_zone: str = Field(default="DE-LU", pattern=r"^[A-Za-z0-9-]{2,12}$")
    timezone: str = "Europe/Berlin"
    price_source: Literal["energy-charts", "entsoe"] = "energy-charts"
    energy_charts_url: str = "https://api.energy-charts.info"
    entsoe_token: str = ""

    # Telegram. Without a token, the daily plan is printed to the console.
    bot_token: str = ""
    plan_chat_id: int | None = None
    # The auction closes at 12:00 CET, results come out shortly before 13:00 CET.
    send_at: time = time(14, 0)
    send_retry_until: time = time(20, 0)

    # Shelly plugs: only log what would be switched unless this is set to false.
    shelly_dry_run: bool = True

    # Storage and web page
    database_path: Path = Path("data/energy.db")
    host: str = "127.0.0.1"
    port: int = 8109

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown timezone {value!r}, use a name like Europe/Berlin") from None
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
