"""Application settings, loaded from environment variables or a `.env` file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_ignore_empty: "ANTHROPIC_API_KEY=" in .env means "not set".
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    # Demo mode: a sample menu in four languages, no API key needed.
    demo_mode: bool = False

    # AI suggestions for unknown or ambiguous ingredients. Off when there is no key.
    ai_suggestions: bool = True
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # Menu and storage
    restaurant_name: str = ""
    # Empty = data/demo.db in demo mode, data/allergens.db otherwise, so the sample menu
    # never mixes with real dishes.
    database_path: Path | None = None
    timezone: str = "Europe/Istanbul"
    host: str = "0.0.0.0"
    port: int = 8110

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
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
    def db_path(self) -> Path:
        if self.database_path:
            return self.database_path
        return Path("data/demo.db" if self.demo_mode else "data/allergens.db")

    @property
    def ai_enabled(self) -> bool:
        return self.ai_suggestions and bool(self.anthropic_api_key)

    @property
    def menu_title(self) -> str:
        if self.restaurant_name:
            return self.restaurant_name
        return "Sample Kitchen" if self.demo_mode else "Our menu"


@lru_cache
def get_settings() -> Settings:
    return Settings()
