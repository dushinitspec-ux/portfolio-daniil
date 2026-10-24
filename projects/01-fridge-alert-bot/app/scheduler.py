"""Sends the daily report at a fixed local time."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def parse_hhmm(value: str) -> time | None:
    """'09:00' -> time(9, 0); an empty string disables the report."""
    if not value.strip():
        return None
    hours, minutes = value.strip().split(":")
    return time(int(hours), int(minutes))


def seconds_until(now: datetime, at: time, tz: ZoneInfo) -> float:
    """Seconds from `now` until the next `at` o'clock in timezone `tz`."""
    local_now = now.astimezone(tz)
    target = datetime.combine(local_now.date(), at, tzinfo=tz)
    if target <= local_now:
        target = datetime.combine(local_now.date() + timedelta(days=1), at, tzinfo=tz)
    # Subtract in UTC: Python subtracts two datetimes with the *same* tzinfo as wall-clock
    # times, which is off by an hour across a daylight-saving change.
    return (target.astimezone(UTC) - now.astimezone(UTC)).total_seconds()


async def run_daily(
    job: Callable[[], Awaitable[None]],
    at: time,
    tz: ZoneInfo,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    while True:
        delay = seconds_until(clock(), at, tz)
        logger.info("Next daily report in %.0f s", delay)
        await asyncio.sleep(delay)
        await job()
        # asyncio timers can fire a fraction of a second early; without this pause the
        # next calculation could land on the same 09:00 and send the report twice.
        await asyncio.sleep(61)
