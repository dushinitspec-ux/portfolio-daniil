import csv
import io
from collections.abc import AsyncIterator
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.changes import ChangeKind
from app.config import DEFAULT_PORTS, Settings
from app.db import Repository
from app.demo import DEMO_SCOPE, OFFICE, DemoScanner, seed
from app.export import asset_rows, safe_cell, to_csv, to_json
from app.inventory import Inventory
from app.oui import OuiDatabase
from app.web import create_app
from tests.conftest import T0, RecordingNotifier


@pytest.fixture
async def demo(repo: Repository, oui: OuiDatabase) -> Inventory:
    scanner = DemoScanner()
    inventory = Inventory(
        repo, scanner, DEMO_SCOPE, oui, RecordingNotifier(), source="demo", clock=lambda: T0
    )
    await seed(repo, oui, scanner, T0)
    await inventory.scan()
    return inventory


@pytest.fixture
async def client(demo: Inventory, repo: Repository) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(demo, repo, ZoneInfo("Europe/Istanbul"), lambda: T0, demo=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_demo_network_has_the_planned_changes(demo: Inventory, repo: Repository) -> None:
    devices = await repo.devices()
    assert len(OFFICE) == len(devices) == 21
    latest = await repo.latest_scan()
    assert latest is not None
    kinds = sorted(c.kind for c in await repo.changes(latest.id))
    assert kinds == sorted(
        [
            ChangeKind.NEW,
            ChangeKind.PORT_OPENED,
            ChangeKind.GONE,
            ChangeKind.GONE,
            ChangeKind.IP_CHANGED,
            ChangeKind.PORT_CLOSED,
        ]
    )
    # Demo MACs use real vendor prefixes, so every vendor device gets a name.
    assert all(d.vendor for d in devices if d.mac_kind == "vendor")
    assert sum(d.mac_kind == "randomised" for d in devices) == 2
    alert = demo.notifier.messages[-1]  # type: ignore[attr-defined]
    assert "Raspberry Pi" in alert and "23 Telnet" in alert


async def test_inventory_page(client: httpx.AsyncClient) -> None:
    html = (await client.get("/")).text
    assert "Network inventory" in html
    assert "Demo · simulated office" in html
    assert "Camera parking" in html
    assert "port opened: 23 Telnet" in html
    assert "IP changed 192.168.10.62 → 192.168.10.65" in html
    assert 'class="badge high"' in html
    assert "randomised MAC" in html


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("status=new", {"192.168.10.99"}),
        ("status=missing", {"192.168.10.61", "192.168.10.81"}),
        ("status=unknown", {"192.168.10.90", "192.168.10.99"}),
        ("risk=high", {"192.168.10.2", "192.168.10.22", "192.168.10.60", "192.168.10.99"}),
        ("q=hikvision", {"192.168.10.21", "192.168.10.30"}),
        ("q=Reception&risk=none", {"192.168.10.70"}),
    ],
)
async def test_filters(client: httpx.AsyncClient, query: str, expected: set[str]) -> None:
    devices = (await client.get(f"/api/devices?{query}")).json()
    assert {d["ip"] for d in devices} == expected
    html = (await client.get(f"/?{query}")).text
    assert f"{len(expected)} shown" in html


async def test_bad_filter_value_is_rejected(client: httpx.AsyncClient) -> None:
    assert (await client.get("/?status=everything")).status_code == 422


async def test_device_page_explains_risks(client: httpx.AsyncClient) -> None:
    devices = (await client.get("/api/devices?q=parking")).json()
    html = (await client.get(f"/devices/{devices[0]['id']}")).text
    assert "Telnet is open" in html
    assert "What to do" in html
    assert "Turn Telnet off" in html
    assert (await client.get("/devices/999")).status_code == 404


async def test_edit_form_and_api(client: httpx.AsyncClient) -> None:
    [pi] = (await client.get("/api/devices?status=new")).json()
    resp = await client.post(
        f"/devices/{pi['id']}",
        data={"name": "Pi in meeting room", "owner": "=HYPERLINK(1)", "known": "true"},
    )
    assert resp.status_code == 303
    data = (await client.get(f"/api/devices/{pi['id']}")).json()
    assert (data["name"], data["known"]) == ("Pi in meeting room", True)
    assert data["risks"][0]["why"]

    resp = await client.patch(f"/api/devices/{pi['id']}", json={"location": "Room 2"})
    assert resp.json()["location"] == "Room 2"
    assert resp.json()["name"] == "Pi in meeting room"  # fields not sent stay as they were
    too_long = await client.patch(f"/api/devices/{pi['id']}", json={"notes": "x" * 1001})
    assert too_long.status_code == 422


async def test_csv_export(client: httpx.AsyncClient) -> None:
    [pi] = (await client.get("/api/devices?status=new")).json()
    await client.patch(f"/api/devices/{pi['id']}", json={"owner": "=HYPERLINK(1)"})
    resp = await client.get("/export/assets.csv")
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.text.startswith("﻿")  # Excel opens it as UTF-8
    rows = list(csv.DictReader(io.StringIO(resp.text.lstrip("﻿"))))
    assert len(rows) == 21
    pi_row = next(r for r in rows if r["ip"] == "192.168.10.99")
    assert pi_row["owner"] == "'=HYPERLINK(1)"  # not run as a formula
    assert pi_row["vendor"] == "Raspberry Pi"
    assert pi_row["risks"] == "vnc"
    assert pi_row["status"] == "present"


async def test_json_export_and_scan_api(client: httpx.AsyncClient) -> None:
    data = (await client.get("/export/assets.json")).json()
    assert data["device_count"] == 21
    macbook = next(d for d in data["devices"] if d["name"] == "Manager MacBook")
    assert macbook["ip_history"] == ["192.168.10.62", "192.168.10.65"]

    latest = (await client.get("/api/scans/latest")).json()
    assert latest["devices_found"] == 19 and len(latest["changes"]) == 6
    rescan = (await client.post("/api/scan")).json()
    assert rescan["changes"] == 0  # the demo office stays as it is after scan 2
    assert (await client.get("/healthz")).json() == {"status": "ok"}


def test_safe_cell() -> None:
    assert safe_cell("=1+1") == "'=1+1"
    assert safe_cell("@SUM(A1)") == "'@SUM(A1)"
    assert safe_cell("Reception") == "Reception"


async def test_export_of_an_empty_register(repo: Repository) -> None:
    rows = asset_rows(await repo.devices(), None, {})
    assert to_csv(rows).splitlines() == [to_csv([]).splitlines()[0]]
    assert to_json(rows, T0)["devices"] == []


def test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO", "1")
    monkeypatch.setenv("SCAN_PORTS", "443, 22,22,80")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.demo_mode
    assert settings.scan_ports == (22, 80, 443)
    monkeypatch.setenv("SCAN_PORTS", "")  # "SCAN_PORTS=" in .env means the default list
    assert Settings(_env_file=None).scan_ports == DEFAULT_PORTS  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="SCAN_PORTS"):
        Settings(_env_file=None, scan_ports="22,ssh")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="between 1 and 65535"):
        Settings(_env_file=None, scan_ports="0")  # type: ignore[call-arg]
