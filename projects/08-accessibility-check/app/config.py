"""Application settings, loaded from environment variables or a `.env` file."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__


class AIProvider(StrEnum):
    # Fixed, hand-written texts per rule: works offline, no key, no cost.
    FIXED = "fixed"
    ANTHROPIC = "anthropic"


class Settings(BaseSettings):
    # env_ignore_empty: "ANTHROPIC_API_KEY=" in .env means "not set", not an empty key.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    # Demo mode: the bundled "Sample Shop" pages are scanned at start-up, so the before/after
    # reports are there without any network access. DEMO=1 works as well as DEMO_MODE=true.
    demo_mode: bool = Field(default=False, validation_alias=AliasChoices("DEMO_MODE", "DEMO"))

    # Crawler
    max_pages: int = Field(default=20, ge=1, le=200)
    concurrency: int = Field(default=2, ge=1, le=8)
    request_delay_s: float = Field(default=0.5, ge=0)
    request_timeout_s: float = Field(default=15, gt=0)
    max_page_bytes: int = Field(default=3_000_000, ge=10_000)
    # robots.txt groups are matched against the first word, "AccessibilityCheckBot".
    user_agent: str = f"AccessibilityCheckBot/{__version__} (static WCAG check; obeys robots.txt)"
    # Refuse URLs that resolve to private, loopback or link-local addresses, so a public
    # deployment cannot be used to probe the network it runs in.
    allow_private_targets: bool = False
    max_parallel_scans: int = Field(default=2, ge=1)

    # Plain-language summary for a shop owner
    ai_provider: AIProvider = AIProvider.FIXED
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # Storage and web UI
    database_path: Path = Path("data/reports.db")
    host: str = "127.0.0.1"
    port: int = 8108

    @property
    def public_base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
