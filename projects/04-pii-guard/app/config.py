"""Application settings, loaded from environment variables or a `.env` file."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import phonenumbers
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # env_ignore_empty: "NAMES_FILE=" in .env means "not set", not "an empty path".
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    # Demo mode: an offline, deterministic fake model instead of Claude. No key needed.
    demo_mode: bool = False

    # Claude. Only masked text is ever sent here.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    anthropic_max_tokens: int = Field(default=16000, ge=256)

    # Detection and policy
    policy_file: Path = Path("policy.yaml")
    names_file: Path | None = None
    phone_regions: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["DE"])

    # Storage and web
    database_path: Path = Path("data/audit.db")
    max_input_chars: int = Field(default=20000, ge=100)
    host: str = "127.0.0.1"
    port: int = 8104

    @field_validator("phone_regions", mode="before")
    @classmethod
    def _split_regions(cls, value: object) -> object:
        # Accept "DE,AT,FR" in .env instead of JSON.
        if isinstance(value, str):
            return [part.strip().upper() for part in value.split(",") if part.strip()]
        return value

    @field_validator("phone_regions")
    @classmethod
    def _check_regions(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("set at least one phone region, e.g. DE")
        for region in value:
            if region not in phonenumbers.SUPPORTED_REGIONS:
                raise ValueError(f"unknown phone region {region!r}, use a code like DE or TR")
        return value

    @property
    def effective_names_file(self) -> Path | None:
        if self.names_file:
            return self.names_file
        return Path("names.demo.txt") if self.demo_mode else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
