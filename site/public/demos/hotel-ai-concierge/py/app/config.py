"""Application settings, loaded from environment variables or a `.env` file."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Provider(StrEnum):
    MOCK = "mock"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class Settings(BaseSettings):
    # env_ignore_empty: "STAFF_CHAT_ID=" in .env means "not set", not "parse '' as a number".
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    # Telegram
    bot_token: str = ""
    staff_chat_id: int | None = None
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # LLM: "mock" works offline with no API key.
    llm_provider: Provider = Provider.MOCK
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    # Behaviour
    hotel_name: str = "Lara Breeze Hotel"
    knowledge_path: Path = Path("knowledge/hotel.md")
    database_path: Path = Path("data/concierge.db")
    history_messages: int = 6
    rate_limit_per_minute: int = 10
    translate_staff_replies: bool = True

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        # Accept "123,456" in .env instead of JSON.
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
