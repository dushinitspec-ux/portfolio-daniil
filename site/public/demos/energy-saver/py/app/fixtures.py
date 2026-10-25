"""Bundled price files: a real API response plus where and when it was downloaded.

{
  "source": "...", "request": "https://api.energy-charts.info/price?...",
  "downloaded_at": "2026-10-24T15:27:17Z", "bidding_zone": "DE-LU",
  "license": "...", "note": "...",
  "response": { ...the API response, unchanged... }
}

The response is kept exactly as the API sent it and goes through the same parser as a live
answer, so the demo and the backtest exercise the real code path.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.energy_charts import PriceResponse, parse_price_payload

NOTE = (
    "Real day-ahead prices, unchanged, downloaded once for the offline demo and the backtest. "
    "Timestamps are UTC (unix seconds) and mark the start of each price."
)


@dataclass(frozen=True)
class Fixture:
    bidding_zone: str
    request: str
    downloaded_at: datetime
    prices: PriceResponse


def load_fixture(path: Path) -> Fixture:
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    return Fixture(
        bidding_zone=data["bidding_zone"],
        request=data["request"],
        downloaded_at=datetime.fromisoformat(data["downloaded_at"].replace("Z", "+00:00")),
        prices=parse_price_payload(data["response"]),
    )


def write_fixture(
    path: Path, raw_response: bytes, request: str, bidding_zone: str, downloaded_at: datetime
) -> None:
    response = json.loads(raw_response)  # numbers stay as written: 172.73 -> 172.73
    data = {
        "source": "Energy-Charts API by Fraunhofer ISE, https://api.energy-charts.info",
        "request": request,
        "downloaded_at": downloaded_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bidding_zone": bidding_zone,
        "license": response.get("license_info", ""),
        "note": NOTE,
        "response": response,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
