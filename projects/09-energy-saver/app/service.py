"""Prices from the cache first, the API only for what is missing; plans built on top."""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx

from app.db import PriceCache
from app.devices import SiteConfig
from app.energy_charts import PriceResponse, PriceSourceError, RateLimitedError
from app.planner import DayPlan, horizon, plan_day
from app.prices import PricePoint, between, day_bounds, is_complete, local_midnight, to_grid

logger = logging.getLogger("energy.prices")


class PriceSource(Protocol):
    async def fetch(self, bzn: str, start: datetime, end: datetime) -> PriceResponse: ...


class PlanService:
    def __init__(
        self,
        cache: PriceCache,
        source: PriceSource | None,
        site: SiteConfig,
        bzn: str,
        tz: ZoneInfo,
        clock: Callable[[], datetime],
        retry_after: timedelta = timedelta(minutes=10),
    ) -> None:
        self.cache = cache
        self.source = source
        self.site = site
        self.bzn = bzn
        self.tz = tz
        self.clock = clock
        self._retry_after = retry_after
        self._failed: dict[tuple[datetime, datetime], datetime] = {}
        self._blocked_until: datetime | None = None
        self.fetches = 0  # API calls made, for tests and logs

    def today(self) -> date:
        return self.clock().astimezone(self.tz).date()

    async def grid(self, start: datetime, end: datetime) -> list[PricePoint]:
        """15-minute prices for [start, end): from the cache, fetching what is missing."""
        slots = between(to_grid(await self.cache.load(self.bzn, start, end)), start, end)
        if is_complete(slots, start, end) or self.source is None:
            return slots

        now = self.clock()
        if self._blocked_until and now < self._blocked_until:
            return slots
        failed_at = self._failed.get((start, end))
        if failed_at and now - failed_at < self._retry_after:
            return slots  # e.g. tomorrow before the auction results; do not hammer the API

        # Whole local days, one day before too, so the previous day's plan is covered.
        first = start.astimezone(self.tz).date() - timedelta(days=1)
        last = (end - timedelta(seconds=1)).astimezone(self.tz).date()
        fetch_start, fetch_end = local_midnight(first, self.tz), day_bounds(last, self.tz)[1]
        self.fetches += 1
        try:
            response = await self.source.fetch(self.bzn, fetch_start, fetch_end)
        except RateLimitedError as exc:
            logger.warning("Price API rate limit; waiting %g s", exc.retry_after_s)
            self._blocked_until = now + timedelta(seconds=exc.retry_after_s)
            return slots
        except (PriceSourceError, httpx.HTTPError) as exc:
            logger.warning("Could not fetch prices for %s: %s", self.bzn, exc)
            self._failed[(start, end)] = now
            return slots

        if response.points:
            await self.cache.save(
                self.bzn, response.points, response.source, response.license_info, now
            )
            logger.info(
                "Fetched %d prices for %s, %s to %s",
                len(response.points),
                self.bzn,
                first,
                last,
            )
        slots = between(to_grid(await self.cache.load(self.bzn, start, end)), start, end)
        if not is_complete(slots, start, end):
            self._failed[(start, end)] = now
        return slots

    async def has_day(self, day: date) -> bool:
        start, end = day_bounds(day, self.tz)
        return is_complete(await self.grid(start, end), start, end)

    async def plan(self, day: date) -> DayPlan:
        """Plan `day`, counting what the previous day's plan already uses (power cap)."""
        devices = self.site.devices
        prev_start, _ = horizon(devices, day - timedelta(days=1), self.tz)
        start, end = horizon(devices, day, self.tz)
        slots = await self.grid(min(prev_start, start), end)
        cap = self.site.power_cap_kw
        previous = plan_day(devices, slots, day - timedelta(days=1), self.tz, cap)
        return plan_day(
            devices,
            slots,
            day,
            self.tz,
            cap,
            existing_load=previous.load,
            existing_baseline_load=previous.baseline_load,
        )

    async def default_day(self) -> date:
        """Tomorrow once its prices are out (early afternoon), today before that."""
        tomorrow = self.today() + timedelta(days=1)
        return tomorrow if await self.has_day(tomorrow) else self.today()

    async def cached_days(self) -> tuple[date, date] | None:
        span = await self.cache.span(self.bzn)
        if span is None:
            return None
        first, last = span
        return first.astimezone(self.tz).date(), (last - timedelta(seconds=1)).astimezone(
            self.tz
        ).date()

    async def attribution(self) -> str:
        stored = await self.cache.license(self.bzn)
        if stored is None:
            return ""
        source, license_info = stored
        return f"Prices: {license_info} — via {source}" if license_info else f"Prices: {source}"
