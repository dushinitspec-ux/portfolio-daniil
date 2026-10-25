"""The in-browser demo adapter (app/web_demo.py), run here under normal CPython."""

import json
import subprocess
import sys
from dataclasses import fields
from datetime import timedelta
from pathlib import Path

import pytest

from app import web_demo
from app.alerts import SensorState
from app.commands import HistoryChart, history_reply
from app.config import Settings
from app.db import Repository
from app.service import FridgeService, SensorNotFoundError
from app.web_demo import DemoSettings, MemoryRepository, split_command
from tests.conftest import T0, FakeClock, RecordingNotifier, reading

PROJECT = Path(__file__).resolve().parent.parent

# Readings that touch every storage path: an incident with alert and recovery, a short
# spike, a duplicate, a late reading, a second sensor and a limit change.
SCENARIO = [
    *[reading(m, t) for m, t in [(0, 3.0), (1, 6.0), (3, 7.0), (6, 8.5), (9, 6.0), (12, 4.0)]],
    reading(12, 4.0),  # duplicate
    reading(8, 2.0),  # late
    *[reading(m, t, sensor_id="bar-fridge") for m, t in [(0, 4.0), (2, 7.5), (3, 4.0)]],
]


async def run_scenario(service: FridgeService, clock: FakeClock) -> list[object]:
    results: list[object] = []
    await service.set_limit("bar-fridge", 7.0)
    for item in SCENARIO:
        clock.now = item.timestamp + timedelta(seconds=10)
        results.append(await service.ingest(item))
    results += await service.ingest_many([reading(m, 9.0, sensor_id="freezer") for m in range(7)])
    results.append(await service.set_limit("freezer", 10.0))
    clock.now = T0 + timedelta(minutes=20)
    return results


async def test_memory_store_gives_the_same_results_as_sqlite(
    repo: Repository, settings: Settings, clock: FakeClock
) -> None:
    sqlite_notifier, memory_notifier = RecordingNotifier(), RecordingNotifier()
    sqlite = FridgeService(repo, sqlite_notifier, settings, clock=clock)
    memory = FridgeService(MemoryRepository(), memory_notifier, settings, clock=clock)  # type: ignore[arg-type]

    assert await run_scenario(sqlite, clock) == await run_scenario(memory, clock)
    assert sqlite_notifier.messages == memory_notifier.messages
    assert len(memory_notifier.messages) == 3  # alert + recovery, alert for the freezer
    assert await sqlite.statuses() == await memory.statuses()
    assert await sqlite.history("fridge-1", 1) == await memory.history("fridge-1", 1)
    assert await sqlite.report() == await memory.report()


async def test_memory_store_rolls_back_a_failed_transaction() -> None:
    store = MemoryRepository()
    await store.create_sensor("a", 5.0)
    with pytest.raises(RuntimeError):
        async with store.transaction():
            await store.create_sensor("b", 5.0)
            await store.add_reading("a", 3.0, T0)
            await store.open_incident("a", T0, T0, 9.0, 5.0)
            raise RuntimeError("boom")
    assert [s.sensor_id for s in await store.list_sensors()] == ["a"]
    assert await store.readings("a", T0, T0 + timedelta(hours=1)) == []
    assert await store.incidents(T0, T0 + timedelta(hours=1)) == []


def test_demo_settings_match_the_real_defaults() -> None:
    real = Settings(_env_file=None)  # type: ignore[call-arg]
    for field in fields(DemoSettings):
        assert getattr(DemoSettings(), field.name) == getattr(real, field.name), field.name


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/status", ("status", None)),
        ("  /setlimit bar-fridge 6 ", ("setlimit", "bar-fridge 6")),
        ("/history@FridgeBot kitchen-fridge-1 1", ("history", "kitchen-fridge-1 1")),
        ("hello", None),
        ("/", None),
        ("", None),
    ],
)
def test_split_command(text: str, expected: tuple[str, str | None] | None) -> None:
    assert split_command(text) == expected


async def test_history_reply_reports_unknown_sensors(service: FridgeService) -> None:
    await service.ingest(reading(0, 3.0))
    found = await history_reply(service, "fridge-1 2", service.history)
    assert isinstance(found, HistoryChart)
    assert found.caption == "fridge-1 — last 2 h"

    async def missing(sensor_id: str, hours: int) -> None:
        raise SensorNotFoundError(sensor_id)

    assert await history_reply(service, "nope", missing) == (
        "Unknown sensor 'nope'. Sensors: fridge-1"
    )


async def advance_until_message(limit: int = 60) -> dict:
    for _ in range(limit):
        snapshot = await web_demo.advance(30)
        if snapshot["messages"]:
            return snapshot
    raise AssertionError("no message")


async def test_demo_scenario_door_spike_then_compressor_failure() -> None:
    start = await web_demo.start(7)
    assert start["sensor"] | {"temperature": None} == {
        "id": "kitchen-fridge-1",
        "limit": 5.0,
        "temperature": None,
        "state": "ok",
        "above_for_s": None,
        "peak": None,
    }
    assert len(start["points"]) == 120  # one hour of history, a reading every 30 s

    # The door stays open for 3 minutes: above the limit for a while, but no alert.
    await web_demo.set_door(True)
    states = [(await web_demo.advance(30))["sensor"]["state"] for _ in range(6)]
    await web_demo.set_door(False)
    for _ in range(10):
        snapshot = await web_demo.advance(30)
        assert snapshot["messages"] == []
        states.append(snapshot["sensor"]["state"])
    assert SensorState.PENDING in states
    assert states[-1] == SensorState.OK

    # The compressor stops: an alert once the fridge has been too warm for 5 minutes.
    broken = await web_demo.set_compressor(True)
    assert broken["fridge"]["mode"] == "failure"
    alert = await advance_until_message()
    assert alert["sensor"]["state"] == "alert"
    assert alert["sensor"]["above_for_s"] == 300
    [message] = alert["messages"]
    assert message["text"].startswith("🚨 <b>Fridge alert: kitchen-fridge-1</b>")
    assert "Above the limit for 5 min" in message["text"]

    await web_demo.set_compressor(False)
    recovered = await advance_until_message()
    assert recovered["sensor"]["state"] == "ok"
    assert recovered["messages"][0]["text"].startswith("✅ <b>Back to normal: kitchen-fridge-1")


async def test_demo_commands_use_the_bot_replies() -> None:
    await web_demo.start(7)
    status = await web_demo.command("/status")
    assert status["kind"] == "text"
    assert "🟢 kitchen-fridge-1 — " in status["text"]

    usage = await web_demo.command("/setlimit 6")
    assert usage["text"].startswith("Usage: /setlimit &lt;sensor&gt;")

    changed = await web_demo.command("/setlimit kitchen-fridge-1 6")
    assert changed["text"] == "✅ Limit for <b>kitchen-fridge-1</b> is now 6.0 °C."
    assert changed["snapshot"]["sensor"]["limit"] == 6.0

    chart = await web_demo.command("/history kitchen-fridge-1 1")
    assert chart["kind"] == "chart"
    assert chart["caption"] == "kitchen-fridge-1 — last 1 h"
    assert chart["limit"] == 6.0
    assert len(chart["points"]) == 120

    assert (await web_demo.command("/history"))["text"].startswith("Usage: /history")
    assert (await web_demo.command("/report"))["text"].startswith("📋 <b>Daily report</b>")
    assert (await web_demo.command("/help"))["text"].startswith("🧊 <b>Fridge Alert Bot</b>")
    assert (await web_demo.command("hello"))["kind"] == "ignored"
    assert (await web_demo.command("/unknown"))["kind"] == "ignored"


def test_demo_imports_only_browser_safe_modules() -> None:
    code = (
        "import sys, app.web_demo; "
        "bad = ('aiogram', 'aiosqlite', 'fastapi', 'uvicorn', 'httpx', 'matplotlib', "
        "'pydantic_settings', 'sqlite3'); "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT, capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"


def test_web_demo_json_lists_every_module_the_demo_imports() -> None:
    code = (
        "import json, sys, app.web_demo; "
        "print(json.dumps(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.'))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT, capture_output=True, text=True, check=True
    )
    imported = {
        "app/__init__.py" if m == "app" else m.replace(".", "/") + ".py"
        for m in json.loads(result.stdout)
    }
    config = json.loads((PROJECT / "web_demo.json").read_text(encoding="utf-8"))
    assert imported == set(config["files"])
