"""Application settings, loaded from environment variables or a `.env` file."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExtractorChoice(StrEnum):
    AUTO = "auto"  # Claude when an API key is set (and not in demo mode), else rules
    RULES = "rules"  # offline, rule-based: works on the bundled sample layouts
    CLAUDE = "claude"  # Anthropic API with structured output


class Settings(BaseSettings):
    # env_ignore_empty: "ANTHROPIC_API_KEY=" in .env means "not set".
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    # Demo mode: rule-based extraction only, sample PDFs one click away, no key needed.
    demo_mode: bool = False
    extractor: ExtractorChoice = ExtractorChoice.AUTO

    # Claude
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # Storage and web
    database_path: Path = Path("data/invoices.db")
    samples_dir: Path = Path("samples")
    max_upload_mb: float = Field(default=10, gt=0)
    max_pages: int = Field(default=20, ge=1)
    host: str = "127.0.0.1"
    port: int = 8105

    @property
    def effective_extractor(self) -> ExtractorChoice:
        if self.demo_mode:
            return ExtractorChoice.RULES
        if self.extractor is ExtractorChoice.AUTO:
            return ExtractorChoice.CLAUDE if self.anthropic_api_key else ExtractorChoice.RULES
        return self.extractor


@lru_cache
def get_settings() -> Settings:
    return Settings()
