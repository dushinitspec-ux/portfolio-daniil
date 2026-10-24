from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.db import PriceCache
from app.devices import Device, SiteConfig
from app.fixtures import load_fixture
from app.prices import SLOT, PricePoint, to_grid

TZ = ZoneInfo("Europe/Berlin")
ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
DEMO_FIXTURE = ROOT / "fixtures" / "energy-charts-de-lu.json"

# Real Energy-Charts answers for DE-LU, downloaded on 24 Oct 2026 (see each file's header).
SPRING_15MIN = FIXTURES / "de-lu-2026-03-28_29-spring-15min.json"
SPRING_HOURLY = FIXTURES / "de-lu-2025-03-29_30-spring-hourly.json"
AUTUMN_HOURLY = FIXTURES / "de-lu-2024-10-26_27-autumn-hourly.json"
SWITCH_TO_15MIN = FIXTURES / "de-lu-2025-09-30_10-01-switch-to-15min.json"


def make_device(**fields: Any) -> Device:
    values: dict[str, Any] = {
        "name": "Load",
        "power_kw": "1",
        "run_time": "1h",
        "window": "00:00-24:00",
    }
    values.update(fields)
    return Device.model_validate(values)


def grid_from(start: datetime, prices: Sequence[int | str | Decimal]) -> list[PricePoint]:
    """15-minute slots from `start` (UTC) with the given EUR/MWh prices."""
    return [PricePoint(start + i * SLOT, 15, Decimal(p)) for i, p in enumerate(prices)]


def flat_grid(start: datetime, end: datetime, price: int = 100) -> list[PricePoint]:
    return grid_from(start, [price] * ((end - start) // SLOT))


def real_grid(path: Path) -> list[PricePoint]:
    return to_grid(load_fixture(path).prices.points)


def site_with(*devices: Device, cap: str | None = None) -> SiteConfig:
    return SiteConfig(site="Test site", power_cap_kw=cap, devices=list(devices))


def hours(value: float) -> timedelta:
    return timedelta(hours=value)


@pytest.fixture
async def cache() -> AsyncIterator[PriceCache]:
    price_cache = await PriceCache.connect(":memory:")
    yield price_cache
    await price_cache.close()
