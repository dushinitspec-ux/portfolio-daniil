"""Application settings, loaded from environment variables or a `.env` file."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # env_ignore_empty: "ALERT_CHAT_ID=" in .env means "not set", not "parse '' as a number".
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    # Telegram. Without a token the app runs in demo mode and prints alerts to the console.
    bot_token: str = ""
    alert_chat_id: int | None = None
    allowed_chat_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # HTTP API
    host: str = "0.0.0.0"
    port: int = 8000
    api_key: str = ""

    # Storage
    database_path: Path = Path("data/fridge.db")

    # Alert rules
    default_limit_c: float = 5.0
    alert_delay_minutes: float = 5.0
    recovery_hysteresis_c: float = 0.5
    alert_max_age_minutes: float = 15.0
    stale_after_minutes: float = 10.0

    # Reports
    timezone: str = "Europe/Istanbul"
    daily_report_time: str = "09:00"

    @field_validator("allowed_chat_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        # Accept "123,-100456" in .env instead of JSON.
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        # ZoneInfoNotFoundError is a KeyError, which pydantic does not turn into a
        # readable validation error, so convert it.
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(
                f"unknown timezone {value!r}, use a name like Europe/Istanbul"
            ) from None
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.bot_token)

    @property
    def command_chat_ids(self) -> set[int]:
        """Chats allowed to use bot commands. Empty means everyone (fine for a demo only)."""
        ids = set(self.allowed_chat_ids)
        if self.alert_chat_id is not None:
            ids.add(self.alert_chat_id)
        return ids


@lru_cache
def get_settings() -> Settings:
    return Settings()
