from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest

from app.api import create_app
from app.config import Settings
from app.service import FridgeService
from tests.conftest import T0

KEY = {"X-API-Key": "secret"}


def body(minutes: float, temperature: float, sensor_id: str = "fridge-1") -> dict[str, object]:
    ts = (T0 + timedelta(minutes=minutes)).isoformat()
    return {"sensor_id": sensor_id, "temperature": temperature, "timestamp": ts}


@pytest.fixture
async def client(service: FridgeService, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(service, settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_post_reading_requires_api_key(client: httpx.AsyncClient) -> None:
    resp = await client.post("/readings", json=body(0, 3.0))
    assert resp.status_code == 401
    resp = await client.post("/readings", json=body(0, 3.0), headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


async def test_post_reading(client: httpx.AsyncClient) -> None:
    resp = await client.post("/readings", json=body(0, 3.0), headers=KEY)
    assert resp.status_code == 201
    assert resp.json() == {"sensor_id": "fridge-1", "state": "ok", "stored": True, "event": None}


async def test_alert_event_is_reported(client: httpx.AsyncClient) -> None:
    await client.post("/readings", json=body(0, 8.0), headers=KEY)
    resp = await client.post("/readings", json=body(5, 8.0), headers=KEY)
    assert resp.json()["state"] == "alert"
    assert resp.json()["event"] == "alert"


@pytest.mark.parametrize(
    "payload",
    [
        body(0, 85.0),  # DS18B20 power-on value, not a real temperature
        body(0, -127.0),  # disconnected probe
        body(0, 3.0, sensor_id="bad id with spaces"),
        {"sensor_id": "fridge-1", "temperature": 3.0},  # no timestamp
    ],
)
async def test_invalid_readings_are_rejected(
    client: httpx.AsyncClient, payload: dict[str, object]
) -> None:
    resp = await client.post("/readings", json=payload, headers=KEY)
    assert resp.status_code == 422


async def test_future_timestamp_is_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post("/readings", json=body(60, 3.0), headers=KEY)  # clock is T0+30
    assert resp.status_code == 422
    assert "in the future" in resp.json()["detail"]


async def test_naive_timestamp_is_treated_as_utc(client: httpx.AsyncClient) -> None:
    payload = {"sensor_id": "fridge-1", "temperature": 3.0, "timestamp": "2026-10-24T09:00:00"}
    resp = await client.post("/readings", json=payload, headers=KEY)
    assert resp.status_code == 201
    sensors = (await client.get("/sensors")).json()
    assert sensors[0]["last_seen_at"] == "2026-10-24T09:00:00Z"


async def test_batch(client: httpx.AsyncClient) -> None:
    readings = [body(m, 9.0) for m in range(10)]
    resp = await client.post("/readings/batch", json=readings, headers=KEY)
    assert resp.status_code == 201
    assert resp.json() == {"received": 10, "stored": 10, "events": 1}


async def test_set_limit_and_list_sensors(client: httpx.AsyncClient) -> None:
    resp = await client.put("/sensors/freezer-1/limit", json={"limit": -15}, headers=KEY)
    assert resp.status_code == 200
    sensors = (await client.get("/sensors")).json()
    assert sensors[0]["sensor_id"] == "freezer-1"
    assert sensors[0]["limit"] == -15


async def test_history_and_chart(client: httpx.AsyncClient) -> None:
    await client.post(
        "/readings/batch", json=[body(m, 3.0 + m / 10) for m in range(20)], headers=KEY
    )

    history = (await client.get("/sensors/fridge-1/history", params={"hours": 1})).json()
    assert len(history["points"]) == 20

    chart = await client.get("/sensors/fridge-1/chart.png")
    assert chart.status_code == 200
    assert chart.headers["content-type"] == "image/png"
    assert chart.content.startswith(b"\x89PNG")


async def test_unknown_sensor_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/sensors/nope/history")).status_code == 404
    assert (await client.get("/sensors/nope/chart.png")).status_code == 404


async def test_report(client: httpx.AsyncClient) -> None:
    await client.post("/readings/batch", json=[body(m, 3.0) for m in range(10)], headers=KEY)
    report = (await client.get("/report")).json()
    assert report["sensors"][0]["readings"] == 10
    assert report["sensors"][0]["minutes_above_limit"] == 0
