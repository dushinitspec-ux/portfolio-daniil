"""The ENTSO-E parser, tested with documents in the A44 format built from REAL prices.

I have no ENTSO-E token, so these documents are assembled here in the documented
Publication_MarketDocument layout, filled with the real DE-LU prices from the Energy-Charts
fixtures (both sources publish the same day-ahead auction results).
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime

import httpx
import pytest

from app.energy_charts import PriceSourceError
from app.entsoe import EntsoeClient, parse_entsoe_xml
from app.fixtures import load_fixture
from app.prices import PricePoint, day_bounds
from tests.conftest import AUTUMN_HOURLY, DEMO_FIXTURE, TZ

NS = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"


def document(points: Sequence[PricePoint], resolution: str, curve_type: str = "A03") -> str:
    start, end = points[0].start, points[-1].end
    xml_points = []
    previous = None
    for position, point in enumerate(points, start=1):
        if curve_type == "A03" and point.price == previous:
            continue  # A03: a repeated price is left out
        xml_points.append(
            f"<Point><position>{position}</position>"
            f"<price.amount>{point.price}</price.amount></Point>"
        )
        previous = point.price
    fmt = "%Y-%m-%dT%H:%MZ"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Publication_MarketDocument xmlns="{NS}">
  <type>A44</type>
  <TimeSeries>
    <mRID>1</mRID>
    <auction.type>A01</auction.type>
    <businessType>A62</businessType>
    <in_Domain.mRID codingScheme="A01">10Y1001A1001A82H</in_Domain.mRID>
    <out_Domain.mRID codingScheme="A01">10Y1001A1001A82H</out_Domain.mRID>
    <contract_MarketAgreement.type>A01</contract_MarketAgreement.type>
    <currency_Unit.name>EUR</currency_Unit.name>
    <price_Measure_Unit.name>MWH</price_Measure_Unit.name>
    <curveType>{curve_type}</curveType>
    <Period>
      <timeInterval><start>{start:{fmt}}</start><end>{end:{fmt}}</end></timeInterval>
      <resolution>{resolution}</resolution>
      {"".join(xml_points)}
    </Period>
  </TimeSeries>
</Publication_MarketDocument>"""


def real_points(path, day: date) -> list[PricePoint]:
    start, end = day_bounds(day, TZ)
    return [p for p in load_fixture(path).prices.points if start <= p.start < end]


def test_a03_fills_left_out_positions_with_the_previous_price() -> None:
    # 25 Oct 2026 had long runs of 0.00 and -0.01 EUR/MWh: many positions are left out.
    points = real_points(DEMO_FIXTURE, date(2026, 10, 25))
    xml = document(points, "PT15M")
    assert xml.count("<Point>") < len(points) - 20
    assert parse_entsoe_xml(xml) == points


def test_hourly_document_on_a_25_hour_day() -> None:
    points = real_points(AUTUMN_HOURLY, date(2024, 10, 27))
    parsed = parse_entsoe_xml(document(points, "PT60M", curve_type="A01"))
    assert len(parsed) == 25
    assert parsed == points


def test_no_data_acknowledgement_means_empty() -> None:
    ns = "urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0"
    reason = "No matching data found for Data item Day-ahead Prices"
    xml = f"""<Acknowledgement_MarketDocument xmlns="{ns}">
      <Reason><code>999</code><text>{reason}</text></Reason>
    </Acknowledgement_MarketDocument>"""
    assert parse_entsoe_xml(xml) == []


def test_other_acknowledgements_are_errors() -> None:
    xml = """<Acknowledgement_MarketDocument><Reason><text>Invalid date</text></Reason>
    </Acknowledgement_MarketDocument>"""
    with pytest.raises(PriceSourceError, match="Invalid date"):
        parse_entsoe_xml(xml)


async def test_client_sends_eic_codes_and_utc_period() -> None:
    points = real_points(DEMO_FIXTURE, date(2026, 10, 20))
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=document(points, "PT15M"))

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = EntsoeClient(http, token="test-token")
    start, end = day_bounds(date(2026, 10, 20), TZ)
    response = await client.fetch("DE-LU", start, end)
    params = seen[0].url.params
    assert params["documentType"] == "A44"
    assert params["in_Domain"] == params["out_Domain"] == "10Y1001A1001A82H"
    assert params["periodStart"] == "202610192200"  # UTC, not Berlin time
    assert params["periodEnd"] == "202610202200"
    assert len(response.points) == 96


def test_client_needs_a_token_and_a_known_zone() -> None:
    http = httpx.AsyncClient()
    with pytest.raises(ValueError):
        EntsoeClient(http, token="")


async def test_unknown_zone_is_an_error() -> None:
    client = EntsoeClient(httpx.AsyncClient(), token="x")
    now = datetime(2026, 10, 20, tzinfo=UTC)
    with pytest.raises(PriceSourceError, match="EIC"):
        await client.fetch("XX", now, now)
