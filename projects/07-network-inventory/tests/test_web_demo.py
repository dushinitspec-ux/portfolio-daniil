"""The in-browser demo adapter (app/web_demo.py), run here under CPython.

The site runs the same module in Pyodide, where there are no threads and only the files in
web_demo.json exist; the last test checks both.
"""

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app import web_demo
from app.export import CSV_COLUMNS

PROJECT = Path(__file__).parent.parent


@pytest.fixture
async def started() -> dict:
    return await web_demo.start("Europe/Berlin")


def by_label(listing: dict) -> dict[str, dict]:
    return {d["label"]: d for d in listing["devices"]}


async def test_start_gives_an_empty_register(started: dict) -> None:
    assert started["scope"] == "192.168.10.0/24"
    assert started["hosts"] == 254
    assert started["vendors"] > 9000
    listing = await web_demo.devices()
    assert listing["scan"] is None and listing["devices"] == []


async def test_unknown_time_zone_falls_back_to_utc() -> None:
    assert (await web_demo.start("Mars/Olympus_Mons"))["timezone"] == "UTC"


async def test_first_scan_fills_the_register(started: dict) -> None:
    first = await web_demo.scan()
    assert first["scan"]["id"] == 1 and first["scan"]["first"] is True
    assert len(first["devices"]) == 20
    assert first["alert"] is not None and "First scan: 20 devices" in first["alert"]
    router = by_label(first)["Main router"]
    assert router["vendor"] == "MikroTik"
    assert [p["service"] for p in router["ports"]] == ["SSH", "HTTP", "Winbox"]
    assert {r["code"] for r in router["risks"]} == {"winbox", "http-only"}
    assert by_label(first)["Staff phone"]["randomised"] is True


async def test_second_scan_shows_what_changed(started: dict) -> None:
    await web_demo.scan()
    second = await web_demo.scan()
    kinds = [(c["kind"], c["label"]) for c in second["changes"]]
    assert kinds == [
        ("new", "raspberrypi.office.lan"),
        ("port_opened", "Camera parking"),
        ("gone", "Accounting laptop"),
        ("gone", "Staff phone 2"),
        ("ip_changed", "Manager MacBook"),
        ("port_closed", "Samsung"),
    ]
    flagged = {c["kind"] for c in second["changes"] if c["flagged"]}
    assert flagged == {"new", "port_opened"}
    moved = next(c for c in second["changes"] if c["kind"] == "ip_changed")
    assert (moved["old_ip"], moved["new_ip"]) == ("192.168.10.62", "192.168.10.65")
    assert second["summary"] == {
        "total": 21,
        "present": 19,
        "new": 1,
        "gone": 2,
        "unknown": 2,
        "high": 4,
    }
    assert "5900 VNC" in second["alert"] and "23 Telnet" in second["alert"]


async def test_device_detail_explains_each_risk(started: dict) -> None:
    await web_demo.scan()
    second = await web_demo.scan()
    camera = by_label(second)["Camera parking"]
    detail = await web_demo.device(camera["id"])
    assert [(r["code"], r["severity"]) for r in detail["risks"]] == [
        ("telnet", "high"),
        ("http-only", "medium"),
        ("rtsp", "medium"),
    ]
    telnet = detail["risks"][0]
    assert "plain text" in telnet["why"] and "SSH" in telnet["fix"]
    assert [h["kind"] for h in detail["history"]] == ["port_opened", "new"]
    assert [r["ip"] for r in detail["ip_records"]] == ["192.168.10.22"]
    with pytest.raises(ValueError):
        await web_demo.device(999)


async def test_closing_a_port_shows_in_the_next_scan(started: dict) -> None:
    await web_demo.scan()
    camera = by_label(await web_demo.scan())["Camera parking"]
    assert await web_demo.close_port(camera["id"], 23) == {"unplugged": False, "closed": [23]}
    third = await web_demo.scan()
    assert [(c["kind"], [p["port"] for p in c["ports"]]) for c in third["changes"]] == [
        ("port_closed", [23])
    ]
    assert third["alert"] is None  # a closed port is not worth a Telegram message
    after = by_label(third)["Camera parking"]
    assert "telnet" not in {r["code"] for r in after["risks"]}
    with pytest.raises(ValueError):
        await web_demo.close_port(camera["id"], 23)  # already closed


async def test_unplugging_and_plugging_back(started: dict) -> None:
    await web_demo.scan()
    nas = by_label(await web_demo.scan())["File server (NAS)"]
    await web_demo.set_unplugged(nas["id"], True)
    third = await web_demo.scan()
    assert ("gone", "File server (NAS)") in [(c["kind"], c["label"]) for c in third["changes"]]
    assert by_label(third)["File server (NAS)"]["present"] is False
    await web_demo.set_unplugged(nas["id"], False)
    fourth = await web_demo.scan()
    assert [(c["kind"], c["label"]) for c in fourth["changes"]] == [
        ("returned", "File server (NAS)")
    ]


async def test_filters_work_like_the_web_page(started: dict) -> None:
    await web_demo.scan()
    await web_demo.scan()
    high = await web_demo.devices("", "high", "all")
    assert {d["label"] for d in high["devices"]} == {
        "Core switch",
        "Camera parking",
        "Reception PC",
        "raspberrypi.office.lan",
    }
    cams = await web_demo.devices("  CAMERA ", "all", "all")
    assert [d["label"] for d in cams["devices"]] == [
        "Camera entrance",
        "Camera parking",
        "Camera back door",
    ]
    assert [d["label"] for d in (await web_demo.devices("", "all", "new"))["devices"]] == [
        "raspberrypi.office.lan"
    ]
    missing = await web_demo.devices("", "all", "missing")
    assert {d["label"] for d in missing["devices"]} == {"Accounting laptop", "Staff phone 2"}
    with pytest.raises(ValueError):
        await web_demo.devices("", "everything", "all")


async def test_exports_match_the_web_page(started: dict) -> None:
    await web_demo.scan()
    await web_demo.scan()
    exported = await web_demo.export_csv()
    assert exported["filename"].startswith("assets-") and exported["filename"].endswith(".csv")
    assert exported["text"].startswith("﻿")
    rows = list(csv.reader(io.StringIO(exported["text"][1:])))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert len(rows) - 1 == exported["rows"] == 21
    data = json.loads((await web_demo.export_json())["text"])
    assert data["device_count"] == 21 and len(data["devices"]) == 21


def test_browser_build_needs_only_the_listed_files() -> None:
    """Import the adapter with the server-only libraries blocked and check that every
    app module it loads is copied to the browser (web_demo.json)."""
    code = (
        "import sys, json\n"
        "for name in ('aiosqlite', 'aiogram', 'fastapi', 'uvicorn', 'httpx', 'jinja2',"
        " 'pydantic_settings'):\n"
        "    sys.modules[name] = None\n"
        "import app.web_demo\n"
        "print(json.dumps(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT, capture_output=True, text=True, check=True
    )
    modules = json.loads(result.stdout)
    listed = set(json.loads((PROJECT / "web_demo.json").read_text(encoding="utf-8"))["files"])
    for module in modules:
        path = "app/__init__.py" if module == "app" else module.replace(".", "/") + ".py"
        assert path in listed, f"{path} is imported by the demo but not in web_demo.json"
    assert "app/resources/oui.csv" in listed
