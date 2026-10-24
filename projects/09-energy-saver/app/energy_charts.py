"""Day-ahead prices from the Energy-Charts API by Fraunhofer ISE (no token needed).

GET https://api.energy-charts.info/price?bzn=DE-LU&start=...&end=...
returns {"license_info", "unix_seconds": [...], "price": [...], "unit": "EUR / MWh",
"deprecated"}. Timestamps mark the start of each price; a price can be null.

Licence: the API's own data is CC BY 4.0 with attribution to Energy-Charts.info. Prices for
DE-LU, AT, BE, CH, CZ, DK1, DK2, FR, HU, IT-North, NL, NO2, PL, SE4 and SI are CC BY 4.0
from Bundesnetzagentur | SMARD.de. Prices for other zones are for private and internal use
only. The response carries its licence in `license_info`; it is stored with the prices and
shown on the page.

The /price endpoint allows 2 requests per minute per IP. A 429 answer has a Retry-After
header; the caller backs off instead of retrying in a loop, and every answer is cached.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.prices import PricePoint, infer_minutes

BASE_URL = "https://api.energy-charts.info"
SOURCE_NAME = "Energy-Charts API (Fraunhofer ISE)"
EXPECTED_UNIT = "EUR / MWh"


class PriceSourceError(Exception):
    """The price source answered with something we cannot use."""


class RateLimitedError(PriceSourceError):
    def __init__(self, retry_after_s: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after_s:g} s")
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class PriceResponse:
    points: list[PricePoint]
    license_info: str
    source: str


def _decimal(value: Any) -> Decimal | None:
    # json.loads(parse_float=Decimal) gives Decimal for 12.5, int for 12, None for null.
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | Decimal):
        raise PriceSourceError(f"price {value!r} is not a number")
    return Decimal(value)


def parse_price_response(raw: bytes | str) -> PriceResponse:
    try:
        payload = json.loads(raw, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise PriceSourceError(f"response is not JSON: {exc}") from exc
    return parse_price_payload(payload)


def parse_price_payload(payload: object) -> PriceResponse:
    """Parse a decoded response. Numbers must be decoded with parse_float=Decimal."""
    if not isinstance(payload, dict):
        raise PriceSourceError("response is not a JSON object")

    starts = payload.get("unix_seconds")
    prices = payload.get("price")
    if not isinstance(starts, list) or not isinstance(prices, list):
        raise PriceSourceError("response has no unix_seconds/price arrays")
    if len(starts) != len(prices):
        raise PriceSourceError(f"{len(starts)} timestamps but {len(prices)} prices")
    unit = payload.get("unit", EXPECTED_UNIT)
    if unit != EXPECTED_UNIT:
        raise PriceSourceError(f"unexpected unit {unit!r}, expected {EXPECTED_UNIT!r}")
    if not all(isinstance(s, int) for s in starts) or starts != sorted(set(starts)):
        raise PriceSourceError("timestamps are not increasing whole seconds")

    points = [
        PricePoint(datetime.fromtimestamp(start, UTC), minutes, value)
        for start, minutes, price in zip(starts, infer_minutes(starts), prices, strict=True)
        if (value := _decimal(price)) is not None
    ]
    return PriceResponse(points, str(payload.get("license_info", "")), SOURCE_NAME)


def retry_after_seconds(response: httpx.Response, default: float = 60.0) -> float:
    value = response.headers.get("Retry-After", "")
    try:
        return max(float(value), 1.0)
    except ValueError:
        return default


class EnergyChartsClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str = BASE_URL) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def get(self, bzn: str, start: datetime, end: datetime) -> httpx.Response:
        """The raw answer for prices that start in [start, end), sent as unix seconds."""
        params = {
            "bzn": bzn,
            "start": str(int(start.timestamp())),
            # `end` is inclusive in this API, so stop one second before the next slot.
            "end": str(int(end.timestamp()) - 1),
        }
        return await self._http.get(f"{self._base_url}/price", params=params, timeout=30)

    async def fetch(self, bzn: str, start: datetime, end: datetime) -> PriceResponse:
        response = await self.get(bzn, start, end)
        if response.status_code == 429:
            raise RateLimitedError(retry_after_seconds(response))
        if response.status_code == 404:
            # No data for the range, e.g. tomorrow's prices before the auction results.
            return PriceResponse([], "", SOURCE_NAME)
        if response.status_code != 200:
            raise PriceSourceError(f"Energy-Charts answered HTTP {response.status_code}")
        parsed = parse_price_response(response.content)
        inside = [p for p in parsed.points if start <= p.start < end]
        return PriceResponse(inside, parsed.license_info, parsed.source)
