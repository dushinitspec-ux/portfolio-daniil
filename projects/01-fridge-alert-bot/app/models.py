"""Data shapes shared by the API, the bot and the storage layer."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, field_validator

from app.alerts import AlertState

SENSOR_ID_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"
# Anything outside this range is a broken sensor, not a fridge
# (DS18B20 probes report 85 °C on a power glitch and -127 °C when disconnected).
TEMPERATURE_RANGE = (-60.0, 60.0)
LIMIT_RANGE = (-40.0, 20.0)


class ReadingIn(BaseModel):
    sensor_id: str = Field(pattern=SENSOR_ID_PATTERN, examples=["kitchen-fridge-1"])
    temperature: float = Field(
        ge=TEMPERATURE_RANGE[0], le=TEMPERATURE_RANGE[1], description="Degrees Celsius"
    )
    timestamp: datetime = Field(description="ISO 8601. Without a timezone it is treated as UTC.")

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(microsecond=0)


class LimitIn(BaseModel):
    limit: float = Field(ge=LIMIT_RANGE[0], le=LIMIT_RANGE[1], description="Degrees Celsius")


@dataclass(frozen=True)
class Sensor:
    sensor_id: str
    limit: float
    alert: AlertState
    last_temperature: float | None = None
    last_seen_at: datetime | None = None


@dataclass(frozen=True)
class SensorStatus:
    sensor: Sensor
    stale: bool
    age: timedelta | None


@dataclass(frozen=True)
class Point:
    ts: datetime
    temperature: float


@dataclass(frozen=True)
class Incident:
    sensor_id: str
    started_at: datetime
    alerted_at: datetime
    resolved_at: datetime | None
    peak_temperature: float
    limit: float
