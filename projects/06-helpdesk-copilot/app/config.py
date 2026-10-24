"""Application settings, loaded from environment variables or a `.env` file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    # env_ignore_empty: "IT_CHAT_ID=" in .env means "not set", not "parse '' as a number".
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    # Demo mode: extractive answers and rule-based triage, no API key, sample tickets.
    demo_mode: bool = Field(default=False, validation_alias=AliasChoices("DEMO_MODE", "DEMO"))

    # Claude. Needed unless DEMO_MODE is on.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Effort = "medium"
    # Triage is a short classification: low effort is enough and cheaper.
    anthropic_triage_effort: Effort = "low"

    # Telegram. Without a token only the web page runs.
    bot_token: str = ""
    # Chat that receives new tickets (the IT person or an IT group; groups start with -100).
    it_chat_id: int | None = None

    # Knowledge base and retrieval
    company_name: str = "Sample Office"
    knowledge_dir: Path = Path("knowledge")
    top_k: int = Field(default=4, ge=1, le=10)
    # Below these the question goes to a ticket without asking the LLM (see README).
    min_score: float = Field(default=2.0, ge=0)
    min_coverage: float = Field(default=0.3, ge=0, le=1)

    # Storage and web page
    database_path: Path = Path("data/helpdesk.db")
    host: str = "0.0.0.0"
    port: int = 8106
    timezone: str = "Europe/Berlin"

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
