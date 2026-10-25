"""Alert rules as a pure state machine.

Every reading moves a sensor between three states:

    OK ──(temp > limit)──> PENDING ──(still above after `delay`)──> ALERT
    ^                         │                                       │
    └──(temp <= limit)────────┘                                       │
    └──────────────(temp <= limit - hysteresis)───────────────────────┘

PENDING absorbs short spikes (a door opened for a minute) so they never alert.
ALERT is sent once per incident; the hysteresis stops "back to normal" / "alert"
spam when the temperature hovers right at the limit.

No I/O happens here, which keeps the rules easy to test.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum


class SensorState(StrEnum):
    OK = "ok"
    PENDING = "pending"
    ALERT = "alert"


class EventKind(StrEnum):
    ALERT = "alert"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class AlertRules:
    delay: timedelta = timedelta(minutes=5)
    hysteresis: float = 0.5


@dataclass(frozen=True)
class AlertState:
    state: SensorState = SensorState.OK
    breach_started_at: datetime | None = None
    peak_temperature: float | None = None


@dataclass(frozen=True)
class AlertEvent:
    kind: EventKind
    sensor_id: str
    temperature: float
    limit: float
    breach_started_at: datetime
    peak_temperature: float
    at: datetime

    @property
    def duration(self) -> timedelta:
        return self.at - self.breach_started_at


def evaluate(
    current: AlertState,
    *,
    sensor_id: str,
    temperature: float,
    at: datetime,
    limit: float,
    rules: AlertRules,
) -> tuple[AlertState, AlertEvent | None]:
    """Return the next state and, if something worth telling people happened, an event."""
    above = temperature > limit

    if current.state is SensorState.OK:
        if above:
            return AlertState(SensorState.PENDING, at, temperature), None
        return current, None

    started = current.breach_started_at
    assert started is not None, "PENDING and ALERT states always have a start time"
    peak = (
        temperature
        if current.peak_temperature is None
        else max(current.peak_temperature, temperature)
    )

    if current.state is SensorState.PENDING:
        if not above:
            return AlertState(), None
        if at - started >= rules.delay:
            event = AlertEvent(EventKind.ALERT, sensor_id, temperature, limit, started, peak, at)
            return AlertState(SensorState.ALERT, started, peak), event
        return replace(current, peak_temperature=peak), None

    # ALERT
    if temperature <= limit - rules.hysteresis:
        event = AlertEvent(EventKind.RECOVERED, sensor_id, temperature, limit, started, peak, at)
        return AlertState(), event
    return replace(current, peak_temperature=peak), None
