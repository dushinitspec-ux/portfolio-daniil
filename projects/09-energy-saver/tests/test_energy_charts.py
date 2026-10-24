import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.db import PriceCache
from app.energy_charts import (
    EnergyChartsClient,
    PriceSourceError,
    RateLimitedError,
    parse_price_response,
)
from app.prices import day_bounds
from app.service import PlanService
from tests.conftest import DEMO_FIXTURE, TZ, make_device, site_with

START = datetime(2026, 10, 19, 22, tzinfo=UTC)  # 20 Oct 2026, 00:00 in Berlin
END = START + timedelta(days=1)


def answer(starts: list[int], prices: list[object], unit: str = "EUR / MWh") -> bytes:
    return json.dumps(
        {
            "license_info": "CC BY 4.0 (creativecommons.org/licenses/by/4.0) from "
            "Bundesnetzagentur | SMARD.de",
            "unix_seconds": starts,
            "price": prices,
            "unit": unit,
            "deprecated": False,
        }
    ).encode()


def real_day() -> bytes:
    """The real answer for 20 Oct 2026, cut out of the bundled fixture."""
    data = json.loads(DEMO_FIXTURE.read_text(encoding="utf-8"))["response"]
    first, last = int(START.timestamp()), int(END.timestamp())
    pairs = [
        (s, p)
        for s, p in zip(data["unix_seconds"], data["price"], strict=True)
        if first <= s < last
    ]
    return answer([s for s, _ in pairs], [p for _, p in pairs])


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> EnergyChartsClient:
    return EnergyChartsClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_parse_keeps_prices_exact() -> None:
    parsed = parse_price_response(real_day())
    assert len(parsed.points) == 96
    assert parsed.points[0].price == Decimal("172.73")  # not 172.72999999...
    assert "SMARD.de" in parsed.license_info


def test_parse_skips_null_prices_but_keeps_their_slot_length() -> None:
    t = int(START.timestamp())
    parsed = parse_price_response(answer([t, t + 900, t + 1800], [10.5, None, 12]))
    assert [(p.minutes, p.price) for p in parsed.points] == [
        (15, Decimal("10.5")),
        (15, Decimal(12)),
    ]


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[1, 2]",
        answer([1, 2], [1.0]),  # lengths differ
        answer([2, 1], [1.0, 2.0]),  # not increasing
        answer([1], [1.0], unit="EUR / kWh"),
        answer([1], ["cheap"]),
    ],
)
def test_parse_rejects_broken_answers(raw: bytes) -> None:
    with pytest.raises(PriceSourceError):
        parse_price_response(raw)


async def test_client_sends_unix_range_and_filters_the_answer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=real_day())

    client = client_for(handler)
    response = await client.fetch("DE-LU", START, START + timedelta(hours=6))
    params = seen[0].url.params
    assert seen[0].url.path == "/price"
    assert params["bzn"] == "DE-LU"
    assert params["start"] == str(int(START.timestamp()))
    assert params["end"] == str(int(START.timestamp()) + 6 * 3600 - 1)  # end is inclusive
    assert len(response.points) == 24  # 6 hours of quarter-hours, the rest is filtered out


async def test_client_raises_rate_limit_with_retry_after() -> None:
    client = client_for(lambda _: httpx.Response(429, headers={"Retry-After": "42"}))
    with pytest.raises(RateLimitedError) as info:
        await client.fetch("DE-LU", START, END)
    assert info.value.retry_after_s == 42


async def test_client_treats_404_as_not_published_yet() -> None:
    client = client_for(lambda _: httpx.Response(404, json={"detail": "no data"}))
    assert (await client.fetch("DE-LU", START, END)).points == []


async def test_client_raises_on_server_error() -> None:
    client = client_for(lambda _: httpx.Response(503))
    with pytest.raises(PriceSourceError, match="503"):
        await client.fetch("DE-LU", START, END)


def service_for(
    cache: PriceCache, handler: Callable[[httpx.Request], httpx.Response], now: datetime
) -> PlanService:
    site = site_with(make_device(window="00:00-24:00"))
    return PlanService(cache, client_for(handler), site, "DE-LU", TZ, lambda: now)


async def test_service_fetches_once_then_uses_the_cache(cache: PriceCache) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=real_day())

    service = service_for(cache, handler, now=START)
    first = await service.grid(START, END)
    second = await service.grid(START, END)
    assert len(first) == len(second) == 96
    assert len(calls) == 1
    assert await service.attribution() == (
        "Prices: CC BY 4.0 (creativecommons.org/licenses/by/4.0) from Bundesnetzagentur | "
        "SMARD.de — via Energy-Charts API (Fraunhofer ISE)"
    )


async def test_service_does_not_hammer_the_api_for_unpublished_days(cache: PriceCache) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    now = datetime(2026, 10, 20, 9, tzinfo=UTC)  # tomorrow's auction is not done yet
    service = service_for(cache, handler, now)
    tomorrow = date(2026, 10, 21)
    assert not await service.has_day(tomorrow)
    assert not await service.has_day(tomorrow)
    assert len(calls) == 1  # the second ask is answered from memory for 10 minutes

    service.clock = lambda: now + timedelta(minutes=11)
    await service.has_day(tomorrow)
    assert len(calls) == 2


async def test_service_backs_off_after_429(cache: PriceCache) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    service = service_for(cache, handler, now=START)
    start, end = day_bounds(date(2026, 10, 20), TZ)
    assert await service.grid(start, end) == []
    await service.grid(start + timedelta(hours=1), end)  # a different range, still blocked
    assert len(calls) == 1
