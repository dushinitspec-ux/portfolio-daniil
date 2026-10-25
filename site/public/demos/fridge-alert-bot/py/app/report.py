"""Daily summary: min / avg / max temperature and time spent above the limit."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from app.models import Incident, Point

# A gap longer than this means the sensor was offline; we do not count it as "above limit".
MAX_GAP = timedelta(minutes=10)


@dataclass(frozen=True)
class SensorSummary:
    sensor_id: str
    limit: float
    readings: int
    min_c: float | None
    avg_c: float | None
    max_c: float | None
    time_above: timedelta
    incidents: int


@dataclass(frozen=True)
class Report:
    since: datetime
    until: datetime
    sensors: list[SensorSummary]


def time_above_limit(
    points: list[Point], limit: float, until: datetime, max_gap: timedelta = MAX_GAP
) -> timedelta:
    """Sum the intervals that start with a reading above the limit.

    Each reading is assumed to hold until the next one, but never longer than `max_gap`.
    """
    total = timedelta()
    for current, following in pairwise(points):
        if current.temperature > limit:
            total += min(following.ts - current.ts, max_gap)
    if points and points[-1].temperature > limit:
        total += min(until - points[-1].ts, max_gap)
    return total


def summarize(
    sensor_id: str,
    limit: float,
    points: list[Point],
    incidents: list[Incident],
    until: datetime,
) -> SensorSummary:
    temps = [p.temperature for p in points]
    return SensorSummary(
        sensor_id=sensor_id,
        limit=limit,
        readings=len(points),
        min_c=min(temps) if temps else None,
        avg_c=sum(temps) / len(temps) if temps else None,
        max_c=max(temps) if temps else None,
        time_above=time_above_limit(points, limit, until),
        incidents=sum(1 for i in incidents if i.sensor_id == sensor_id),
    )
