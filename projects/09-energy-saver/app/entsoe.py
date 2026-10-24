"""Optional second source: the ENTSO-E Transparency Platform (needs a free API token).

GET https://web-api.tp.entsoe.eu/api?documentType=A44&in_Domain=<EIC>&out_Domain=<EIC>
&periodStart=yyyyMMddHHmm&periodEnd=yyyyMMddHHmm&securityToken=<token>
returns an XML Publication_MarketDocument: TimeSeries > Period (start, resolution PT15M or
PT60M) > Point (position, price.amount). With curveType A03 a point is left out when its
price equals the previous one, so missing positions repeat the last price.

The token travels in the query string, so the httpx request log is switched off in main.py:
at INFO level httpx would print the full URL, token included.
"""

import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from app.energy_charts import PriceResponse, PriceSourceError
from app.prices import RESOLUTIONS, PricePoint

API_URL = "https://web-api.tp.entsoe.eu/api"
SOURCE_NAME = "ENTSO-E Transparency Platform"
LICENSE_INFO = "ENTSO-E Transparency Platform, see transparency.entsoe.eu terms of use"

# EIC codes of common bidding zones (from the ENTSO-E area list).
EIC_CODES = {
    "AT": "10YAT-APG------L",
    "BE": "10YBE----------2",
    "CH": "10YCH-SWISSGRIDZ",
    "CZ": "10YCZ-CEPS-----N",
    "DE-LU": "10Y1001A1001A82H",
    "DK1": "10YDK-1--------W",
    "DK2": "10YDK-2--------M",
    "ES": "10YES-REE------0",
    "FI": "10YFI-1--------U",
    "FR": "10YFR-RTE------C",
    "HU": "10YHU-MAVIR----U",
    "NL": "10YNL----------L",
    "PL": "10YPL-AREA-----S",
    "PT": "10YPT-REN------W",
    "SE4": "10Y1001A1001A47J",
    "SI": "10YSI-ELES-----O",
}

_RESOLUTION_MINUTES = {"PT15M": 15, "PT60M": 60, "PT1H": 60}


def _local(tag: str) -> str:
    """Tag name without the XML namespace: '{urn:...}Period' -> 'Period'."""
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in element if _local(c.tag) == name), None)


def _text(element: ET.Element, name: str) -> str:
    child = _child(element, name)
    if child is None or child.text is None:
        raise PriceSourceError(f"<{_local(element.tag)}> has no <{name}>")
    return child.text.strip()


def _parse_time(value: str) -> datetime:
    # "2026-10-19T22:00Z"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def parse_entsoe_xml(raw: bytes | str) -> list[PricePoint]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise PriceSourceError(f"response is not XML: {exc}") from exc

    if _local(root.tag) == "Acknowledgement_MarketDocument":
        reason = root.find(".//{*}Reason/{*}text")
        message = reason.text if reason is not None and reason.text else "no reason given"
        if "No matching data" in message:
            return []
        raise PriceSourceError(f"ENTSO-E: {message}")

    points: dict[datetime, PricePoint] = {}
    for series in root.iter():
        if _local(series.tag) != "TimeSeries":
            continue
        # Day-ahead only; intraday auction series (other contract types) are skipped.
        contract = _child(series, "contract_MarketAgreement.type")
        if contract is not None and contract.text not in (None, "A01"):
            continue
        curve_type = _child(series, "curveType")
        fill_gaps = curve_type is not None and curve_type.text == "A03"
        for period in (c for c in series if _local(c.tag) == "Period"):
            interval = _child(period, "timeInterval")
            if interval is None:
                raise PriceSourceError("<Period> has no <timeInterval>")
            start = _parse_time(_text(interval, "start"))
            end = _parse_time(_text(interval, "end"))
            resolution = _text(period, "resolution")
            minutes = _RESOLUTION_MINUTES.get(resolution)
            if minutes not in RESOLUTIONS:
                raise PriceSourceError(f"unsupported resolution {resolution}")
            step = timedelta(minutes=minutes)
            by_position: dict[int, Decimal] = {}
            for point in (c for c in period if _local(c.tag) == "Point"):
                try:
                    by_position[int(_text(point, "position"))] = Decimal(
                        _text(point, "price.amount")
                    )
                except (ValueError, InvalidOperation) as exc:
                    raise PriceSourceError(f"bad <Point>: {exc}") from exc
            count = (end - start) // step
            last: Decimal | None = None
            for position in range(1, count + 1):
                price = by_position.get(position)
                if price is None and fill_gaps:
                    price = last
                if price is None:
                    continue
                at = start + (position - 1) * step
                points[at] = PricePoint(at, minutes, price)
                last = price
    return [points[key] for key in sorted(points)]


class EntsoeClient:
    def __init__(self, http: httpx.AsyncClient, token: str, url: str = API_URL) -> None:
        if not token:
            raise ValueError("ENTSOE_TOKEN is empty")
        self._http = http
        self._token = token
        self._url = url

    async def fetch(self, bzn: str, start: datetime, end: datetime) -> PriceResponse:
        eic = EIC_CODES.get(bzn)
        if eic is None:
            raise PriceSourceError(f"no EIC code for bidding zone {bzn}; add it to EIC_CODES")
        params = {
            "securityToken": self._token,
            "documentType": "A44",
            "in_Domain": eic,
            "out_Domain": eic,
            "contract_MarketAgreement.type": "A01",
            "periodStart": start.astimezone(UTC).strftime("%Y%m%d%H%M"),
            "periodEnd": end.astimezone(UTC).strftime("%Y%m%d%H%M"),
        }
        response = await self._http.get(self._url, params=params, timeout=60)
        if response.status_code == 401:
            raise PriceSourceError("ENTSO-E rejected the token (HTTP 401)")
        if response.status_code not in (200, 400):
            # 400 carries an Acknowledgement document, e.g. "No matching data found".
            raise PriceSourceError(f"ENTSO-E answered HTTP {response.status_code}")
        points = [p for p in parse_entsoe_xml(response.content) if start <= p.start < end]
        return PriceResponse(points, LICENSE_INFO, SOURCE_NAME)
