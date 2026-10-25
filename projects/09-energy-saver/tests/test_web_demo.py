"""The in-browser demo adapter (app/web_demo.py), run here under CPython.

The site runs the same module in Pyodide, where only the files in web_demo.json exist and
there is no httpx, aiogram or pydantic-settings; the last test checks that.
"""

import json
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app import web_demo
from app.backtest import run_backtest
from app.config import DEFAULT_FIXTURE, Settings

PROJECT = Path(__file__).parent.parent
DAY = "2026-10-22"
DST_DAY = "2026-10-25"


def test_settings_match_the_app() -> None:
    assert Settings.model_fields["timezone"].default == web_demo.TIMEZONE
    assert web_demo.FIXTURE.resolve() == DEFAULT_FIXTURE.resolve()


def test_init_describes_the_real_prices_and_the_sample_devices() -> None:
    info = web_demo.init()
    assert info["bidding_zone"] == "DE-LU"
    assert info["license"].startswith("CC BY 4.0") and "SMARD.de" in info["license"]
    assert info["attribution"].startswith("Prices: CC BY 4.0")
    assert info["resolution"] == "15-minute"
    days = {d["day"]: d["hours"] for d in info["days"]}
    assert len(days) == 35 and min(days) == "2026-09-21" and max(days) == DST_DAY
    assert days[DST_DAY] == 25.0 and days[DAY] == 24.0
    names = [d["name"] for d in info["site"]["devices"]]
    assert names == [
        "Hot-water boiler",
        "EV charger",
        "Dishwasher pre-heat",
        "Laundry dryer",
        "Pool pump",
    ]
    assert info["site"]["power_cap_kw"] == "18"


def test_plan_matches_the_backtest_for_the_same_day() -> None:
    result = web_demo.plan(DAY)
    assert result["ok"] and result["hours"] == 24.0 and result["dst_note"] is None
    d = web_demo.data()
    replay = run_backtest(d.site, d.grid, d.tz, [date.fromisoformat(DAY)])
    assert Decimal(result["totals"]["cost"]) == replay.cost.quantize(Decimal("0.01"))
    assert Decimal(result["totals"]["baseline"]) == replay.baseline_cost.quantize(Decimal("0.01"))
    assert result["totals"] == {
        "cost": "8.39",
        "baseline": "15.86",
        "saving": "7.47",
        "percent": "47.1",
        "planned": 5,
        "devices": 5,
    }
    assert result["order"][0] == "Dishwasher pre-heat"  # least flexible first
    assert "Saving 7.47 € (47.1 %)." in result["message"]


def test_positions_point_at_the_right_slots() -> None:
    result = web_demo.plan(DAY)
    slots = result["slots"]
    tz = web_demo.data().tz
    start, end = result["day_range"]
    assert datetime.fromisoformat(slots[start]["t"]).astimezone(tz).strftime("%H:%M") == "00:00"
    assert end - start == 96
    for device in result["devices"]:
        w0, w1 = device["window"]
        assert slots[w0]["label"] == device["window_text"][0]
        for block in device["blocks"]:
            assert w0 <= block["from"] < block["to"] <= w1
            assert block["text"].startswith(slots[block["from"]]["label"])
        slots_used = sum(b["to"] - b["from"] for b in device["blocks"])
        assert slots_used * 15 == device["run_time"]
    boiler = result["devices"][0]
    assert boiler["blocks"] == [{"from": 34, "to": 46, "text": "02:30–05:30"}]
    assert (boiler["cost"], boiler["baseline_cost"], boiler["saving"]) == ("1.65", "2.78", "1.13")


def test_dst_day_has_25_hours_and_the_repeated_hour_is_labelled() -> None:
    result = web_demo.plan(DST_DAY)
    assert result["hours"] == 25.0
    assert "25 hours" in result["dst_note"]
    start, end = result["day_range"]
    assert end - start == 100
    labels = [t["label"] for t in result["ticks"]]
    assert "02:00 CEST" in labels and "02:00 CET" in labels
    assert "CEST" in result["message"]


def test_visitor_edits_are_planned_and_checked() -> None:
    site = web_demo.init()["site"]
    ev = site["devices"][1]
    ev["contiguous"] = True
    site["power_cap_kw"] = "12"
    result = web_demo.plan(DAY, site)
    assert result["ok"] and result["power_cap_kw"] == "12"
    assert len(result["devices"][1]["blocks"]) == 1
    assert result["totals"]["cost"] != web_demo.plan(DAY)["totals"]["cost"]

    site["power_cap_kw"] = ""
    assert web_demo.plan(DAY, site)["power_cap_kw"] is None

    site["devices"][2]["window"] = "04:00-05:00"  # latest_finish 06:30 no longer fits
    bad = web_demo.plan(DAY, site)
    assert bad == {
        "ok": False,
        "errors": [
            {
                "device": 2,
                "field": None,
                "message": "Dishwasher pre-heat: latest_finish 06:30 is outside the window "
                "04:00-05:00",
            }
        ],
    }
    site["devices"][2]["window"] = "04:00-07:00"
    site["devices"][0]["power_kw"] = "-1"
    errors = web_demo.plan(DAY, site)["errors"]
    assert errors[0]["device"] == 0 and errors[0]["field"] == "power_kw"


def test_a_cap_too_low_for_a_device_is_reported() -> None:
    site = web_demo.init()["site"]
    site["power_cap_kw"] = "5"
    result = web_demo.plan(DAY, site)
    assert not result["ok"]
    assert "alone use more than power_cap_kw" in result["errors"][0]["message"]


def test_browser_build_needs_only_the_listed_files() -> None:
    """Import the adapter with the server-only libraries blocked and check that every app
    module it loads, and the data it reads, is copied to the browser (web_demo.json)."""
    code = (
        "import sys, json\n"
        "for name in ('httpx', 'aiogram', 'aiosqlite', 'fastapi', 'uvicorn', 'jinja2',"
        " 'pydantic_settings'):\n"
        "    sys.modules[name] = None\n"
        "import app.web_demo\n"
        "app.web_demo.plan('2026-10-22')\n"
        "print(json.dumps(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT, capture_output=True, text=True, check=True
    )
    listed = set(json.loads((PROJECT / "web_demo.json").read_text(encoding="utf-8"))["files"])
    for module in json.loads(result.stdout):
        path = "app/__init__.py" if module == "app" else module.replace(".", "/") + ".py"
        assert path in listed, f"{path} is imported by the demo but not in web_demo.json"
    assert {"devices.yaml", "fixtures/energy-charts-de-lu.json"} <= listed
