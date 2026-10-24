"""Day-ahead prices and the 15-minute grid the planner works on.

The EU day-ahead market switched from hourly to 15-minute products on 1 October 2025, so a
history can contain both. Every price is expanded to 15-minute slots (an hourly price becomes
four equal slots); after that the planner never has to care which resolution it came from.

All times are UTC. Money is `Decimal`: prices arrive with two decimals in EUR/MWh and are
never converted to float, so a sum of 100 slots is exact.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

SLOT = timedelta(minutes=15)
SLOT_MINUTES = 15
RESOLUTIONS = (15, 60)  # minutes per published price


@dataclass(frozen=True, order=True)
class PricePoint:
    """One price: start (UTC), length in minutes, EUR/MWh."""

    start: datetime
    minutes: int
    price: Decimal

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.minutes)


def infer_minutes(starts: Sequence[int]) -> list[int]:
    """Length of each price in minutes, from the gaps between unix timestamps.

    The API gives only start times. A gap of 15 or 60 minutes is the length. A longer gap
    means missing data, so the price keeps the length of the one before it. A 60-minute gap
    right after a 15-minute price is also missing data: the market never went back from
    15-minute to hourly prices. The last price gets the length of the one before it; when
    there is nothing to compare with, it is assumed to be 15 minutes, which never claims
    more coverage than the data has.
    """
    minutes: list[int] = []
    for i, start in enumerate(starts):
        gap = (starts[i + 1] - start) // 60 if i + 1 < len(starts) else None
        previous = minutes[-1] if minutes else None
        if gap == 15 or (gap == 60 and previous != 15):
            minutes.append(gap)
        else:
            minutes.append(previous or 15)
    return minutes


def to_grid(points: Iterable[PricePoint]) -> list[PricePoint]:
    """Expand prices to 15-minute slots, sorted, one per start time."""
    slots: dict[datetime, PricePoint] = {}
    for point in points:
        for i in range(point.minutes // SLOT_MINUTES):
            start = point.start + i * SLOT
            slots[start] = PricePoint(start, SLOT_MINUTES, point.price)
    return [slots[key] for key in sorted(slots)]


def between(slots: Iterable[PricePoint], start: datetime, end: datetime) -> list[PricePoint]:
    return [s for s in slots if start <= s.start and s.end <= end]


def is_complete(slots: Sequence[PricePoint], start: datetime, end: datetime) -> bool:
    """True when the grid has a price for every 15 minutes of [start, end)."""
    inside = {s.start for s in slots if start <= s.start < end}
    return len(inside) == (end - start) // SLOT


def local_midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time(0), tzinfo=tz).astimezone(UTC)


def day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[00:00, next 00:00) of a local day, in UTC. 23, 24 or 25 hours long."""
    return local_midnight(day, tz), local_midnight(day + timedelta(days=1), tz)


def day_hours(day: date, tz: ZoneInfo) -> float:
    start, end = day_bounds(day, tz)
    return (end - start) / timedelta(hours=1)


def resolution_label(points: Iterable[PricePoint]) -> str:
    kinds = sorted({p.minutes for p in points})
    if not kinds:
        return "no data"
    return " + ".join("hourly" if m == 60 else f"{m}-minute" for m in kinds)
