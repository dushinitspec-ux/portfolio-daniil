"""Application settings, loaded from environment variables or a `.env` file."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_PORTS = (21, 22, 23, 80, 139, 443, 445, 554, 3389, 5900, 8080, 8291, 8443, 9100)


class Settings(BaseSettings):
    # env_ignore_empty: "ALERT_CHAT_ID=" in .env means "not set", not "parse '' as a number".
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    # Demo mode: a simulated office network with two scans, kept in memory.
    demo_mode: bool = Field(default=False, validation_alias=AliasChoices("DEMO_MODE", "DEMO"))

    # What to scan. Required outside demo mode; see app/scope.py for the rules.
    scan_cidrs: str = ""
    allow_public: bool = False
    subnet_limit: int = Field(default=22, ge=16, le=32)
    scan_ports: Annotated[tuple[int, ...], NoDecode] = DEFAULT_PORTS
    scan_interval_min: float = Field(default=60, ge=0, description="0 = only on request")

    # Probing
    ping_timeout_s: float = Field(default=1.0, gt=0, le=10)
    tcp_timeout_s: float = Field(default=1.0, gt=0, le=10)
    dns_timeout_s: float = Field(default=2.0, gt=0, le=10)
    reverse_dns: bool = True
    max_parallel_pings: int = Field(default=64, ge=1, le=256)
    max_parallel_connects: int = Field(default=128, ge=1, le=512)

    # Telegram. Without a token, alerts are printed to the console.
    bot_token: str = ""
    alert_chat_id: int | None = None

    # Storage and web page
    database_path: Path = Path("data/inventory.db")
    host: str = "127.0.0.1"
    port: int = 8107
    timezone: str = "Europe/Istanbul"

    @field_validator("scan_ports", mode="before")
    @classmethod
    def _parse_ports(cls, value: object) -> object:
        if isinstance(value, str):
            value = [p for p in value.replace(" ", ",").split(",") if p]
        if isinstance(value, list | tuple):
            try:
                ports = tuple(sorted({int(p) for p in value}))
            except ValueError:
                raise ValueError("SCAN_PORTS must be numbers, e.g. 22,80,443") from None
            if not ports or not all(1 <= p <= 65535 for p in ports):
                raise ValueError("SCAN_PORTS must be between 1 and 65535")
            if len(ports) > 100:
                raise ValueError("SCAN_PORTS: keep the list short (100 ports at most)")
            return ports
        return value

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
