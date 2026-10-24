"""The flexible loads to plan, loaded from devices.yaml."""

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.prices import SLOT_MINUTES

DAY_MINUTES = 24 * 60
_DURATION = re.compile(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*min)?\s*$")
_CLOCK = re.compile(r"^([01]\d|2[0-4]):([0-5]\d)$")
_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:-]*$")


class DeviceConfigError(Exception):
    pass


def parse_duration(value: str | int) -> int:
    """'3h' / '45min' / '1h30min' / 90 -> minutes, a positive multiple of 15."""
    if isinstance(value, int) and not isinstance(value, bool):
        minutes = value
    elif isinstance(value, str) and (match := _DURATION.match(value)) and any(match.groups()):
        hours, mins = match.groups()
        minutes = int(hours or 0) * 60 + int(mins or 0)
    else:
        raise ValueError(f"{value!r} is not a duration; write it like 3h, 45min or 1h30min")
    if minutes <= 0 or minutes % SLOT_MINUTES:
        raise ValueError(f"{value!r}: durations must be whole quarter-hours (15, 30, 45 min...)")
    return minutes


def parse_clock(value: str) -> int:
    """'22:00' -> minutes after midnight. '24:00' is allowed as an end time."""
    match = _CLOCK.match(value.strip()) if isinstance(value, str) else None
    if not match:
        raise ValueError(f"{value!r} is not a time; write it like 06:30")
    minutes = int(match.group(1)) * 60 + int(match.group(2))
    if minutes > DAY_MINUTES:
        raise ValueError(f"{value!r} is after 24:00")
    if minutes % SLOT_MINUTES:
        raise ValueError(f"{value!r}: times must be on a quarter-hour (:00, :15, :30, :45)")
    return minutes


def format_minutes(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} h {mins} min"
    return f"{hours} h" if hours else f"{mins} min"


@dataclass(frozen=True)
class WindowSpec:
    """A window in wall-clock minutes, relative to the day the window starts on.

    `start_day_offset` is -1 when the window crosses midnight: it starts the day before the
    plan day. `end_minute` can be above 1440 (the next day) and already includes the
    latest finish time.
    """

    start_day_offset: int
    start_minute: int
    end_minute: int

    @property
    def minutes(self) -> int:
        return self.end_minute - self.start_minute


def parse_window(window: str, latest_finish: str | None = None) -> WindowSpec:
    parts = window.replace("–", "-").split("-")
    if len(parts) != 2:
        raise ValueError(f"window {window!r} must look like 22:00-07:00")
    start, end = parse_clock(parts[0]), parse_clock(parts[1])
    if start == DAY_MINUTES:
        raise ValueError("a window cannot start at 24:00")
    if end in (0, DAY_MINUTES):  # "...-24:00" or "...-00:00": until the end of the day
        offset, end = 0, DAY_MINUTES
    elif end <= start:  # crosses midnight, so it starts on the previous day
        offset, end = -1, end + DAY_MINUTES
    else:
        offset = 0

    if latest_finish is not None:
        finish = parse_clock(latest_finish)
        if finish <= start:
            finish += DAY_MINUTES
        if finish > end:
            raise ValueError(f"latest_finish {latest_finish} is outside the window {window}")
        end = finish
    return WindowSpec(offset, start, end)


class ShellyPlug(BaseModel):
    """A Shelly smart plug or relay on the local network."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(max_length=253, description="IP address or host name")
    generation: Literal[1, 2] = 2  # 2 = Gen2/Gen3/Gen4 RPC API, 1 = Gen1 /relay API
    channel: int = Field(default=0, ge=0, le=3)

    @field_validator("host")
    @classmethod
    def _check_host(cls, value: str) -> str:
        if not _HOST.match(value):
            raise ValueError(f"{value!r} is not a valid IP address or host name")
        return value


class Device(BaseModel):
    """A load that can run at any time inside its window.

    Times are local wall-clock times. A window whose end is not after its start crosses
    midnight and belongs to the day it ends on: "22:00-07:00" in the plan for Sunday runs
    from Saturday 22:00 to Sunday 07:00, so tonight's run is planned together with
    tomorrow's prices.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=60)
    power_kw: Decimal = Field(gt=0, le=1000)
    run_time: int = Field(description="minutes per day")
    window: str = Field(description="allowed window, local time, e.g. 22:00-07:00")
    latest_finish: str | None = Field(default=None, description="must be done by, e.g. 06:00")
    contiguous: bool = False
    min_block: int = SLOT_MINUTES
    shelly: ShellyPlug | None = None

    @field_validator("run_time", "min_block", mode="before")
    @classmethod
    def _duration(cls, value: str | int) -> int:
        return parse_duration(value)

    @field_validator("power_kw", mode="before")
    @classmethod
    def _power(cls, value: object) -> object:
        # YAML gives 6.5 as a float; go through str so Decimal gets "6.5", not 6.4999...
        return str(value) if isinstance(value, float) else value

    @model_validator(mode="after")
    def _check_window(self) -> "Device":
        try:
            spec = parse_window(self.window, self.latest_finish)
        except ValueError as exc:
            raise ValueError(f"{self.name}: {exc}") from None
        if self.min_block > self.run_time:
            raise ValueError(f"{self.name}: min_block is longer than run_time")
        if spec.minutes < self.run_time:
            raise ValueError(
                f"{self.name}: needs {format_minutes(self.run_time)} but the window "
                f"{self.window_label} is only {format_minutes(spec.minutes)}"
            )
        return self

    @property
    def spec(self) -> WindowSpec:
        return parse_window(self.window, self.latest_finish)

    @property
    def slots_needed(self) -> int:
        return self.run_time // SLOT_MINUTES

    @property
    def min_block_slots(self) -> int:
        return self.slots_needed if self.contiguous else self.min_block // SLOT_MINUTES

    @property
    def energy_kwh(self) -> Decimal:
        return self.power_kw * self.run_time / 60

    @property
    def window_label(self) -> str:
        label = self.window.replace("-", "–")
        return f"{label}, done by {self.latest_finish}" if self.latest_finish else label

    @property
    def mode_label(self) -> str:
        if self.contiguous:
            return "one block"
        if self.min_block_slots > 1:
            return f"split, blocks ≥ {format_minutes(self.min_block)}"
        return "split"


class SiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site: str = Field(default="Sample site", max_length=80)
    power_cap_kw: Decimal | None = Field(default=None, gt=0)
    devices: list[Device] = Field(min_length=1)

    @field_validator("power_cap_kw", mode="before")
    @classmethod
    def _cap(cls, value: object) -> object:
        return str(value) if isinstance(value, float) else value

    @model_validator(mode="after")
    def _check(self) -> "SiteConfig":
        names = [d.name for d in self.devices]
        if len(set(names)) != len(names):
            raise ValueError("device names must be unique")
        if self.power_cap_kw is not None:
            too_big = [d.name for d in self.devices if d.power_kw > self.power_cap_kw]
            if too_big:
                raise ValueError(f"{', '.join(too_big)} alone use more than power_cap_kw")
        return self


def load_site(path: Path) -> SiteConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeviceConfigError(f"cannot read {path}: {exc.strerror}") from exc
    except yaml.YAMLError as exc:
        raise DeviceConfigError(f"{path} is not valid YAML: {exc}") from exc
    try:
        return SiteConfig.model_validate(raw)
    except ValidationError as exc:
        raise DeviceConfigError(f"{path} has errors:\n{exc}") from exc
