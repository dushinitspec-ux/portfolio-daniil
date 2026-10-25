"""The in-browser demo on the portfolio site (Python running in Pyodide).

Real code: FridgeService with the alert state machine, the fridge model from
app/simulation.py, the bot replies from app/commands.py and the message texts.
Swapped out: SQLite becomes an in-memory store with the same methods as app.db.Repository
(tests check that both give the same results), Telegram becomes a list of sent messages,
and the wall clock becomes simulated time that the page moves forward.

Only browser-safe modules are imported (no aiogram, aiosqlite, FastAPI or matplotlib).
The functions at the bottom take and return JSON-friendly values.
"""

import random
from bisect import bisect_left, insort
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

from app.alerts import AlertState
from app.commands import (
    HELP_TEXT,
    HistoryChart,
    history_reply,
    id_reply,
    report_reply,
    setlimit_reply,
    status_reply,
)
from app.models import Incident, Point, ReadingIn, Sensor
from app.service import FridgeService
from app.simulation import DEFAULT_PROFILES, FridgeModel, Mode

START = datetime(2026, 10, 24, 8, 0, tzinfo=UTC)  # simulated "now" when the demo starts
BACKFILL = timedelta(hours=1)  # history made before START, like simulator.py --backfill-hours
STEP_S = 30  # one reading per sensor every 30 simulated seconds
MAIN_SENSOR = "kitchen-fridge-1"  # the fridge on the chart, driven by the buttons
CHART_HOURS = 1
UNTIL_CHANGED_S = 7 * 24 * 3600  # the door stays open / the compressor broken until undone
DEMO_CHAT_ID = 100200300  # there is no real Telegram chat in the browser


def _db_time(value: datetime) -> datetime:
    """A timestamp as it comes back from app.db: UTC, whole seconds."""
    return value.astimezone(UTC).replace(microsecond=0)


class MemoryRepository:
    """app.db.Repository without SQLite: the same methods and results, kept in memory."""

    def __init__(self) -> None:
        self._sensors: dict[str, Sensor] = {}
        self._readings: dict[str, list[tuple[datetime, float]]] = {}
        self._incidents: list[Incident] = []
        self._undo: list[Callable[[], None]] | None = None

    def _changed(self, undo: Callable[[], None]) -> None:
        if self._undo is not None:
            self._undo.append(undo)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Keep everything inside the block, or nothing if it raises."""
        self._undo = []
        try:
            yield
        except BaseException:
            for undo in reversed(self._undo):
                undo()
            raise
        finally:
            self._undo = None

    # Sensors

    async def get_sensor(self, sensor_id: str) -> Sensor | None:
        return self._sensors.get(sensor_id)

    async def list_sensors(self) -> list[Sensor]:
        return [self._sensors[key] for key in sorted(self._sensors)]

    async def create_sensor(self, sensor_id: str, limit: float) -> Sensor:
        if sensor_id in self._sensors:
            raise ValueError(f"sensor {sensor_id!r} already exists")  # PRIMARY KEY
        sensor = Sensor(sensor_id=sensor_id, limit=limit, alert=AlertState())
        self._sensors[sensor_id] = sensor
        self._changed(lambda: self._sensors.pop(sensor_id))
        return sensor

    async def save_sensor(self, sensor: Sensor) -> None:
        old = self._sensors.get(sensor.sensor_id)
        if old is None:
            return  # an UPDATE of a missing row changes nothing
        started = sensor.alert.breach_started_at
        self._sensors[sensor.sensor_id] = replace(
            sensor,
            alert=replace(sensor.alert, breach_started_at=started and _db_time(started)),
            last_seen_at=sensor.last_seen_at and _db_time(sensor.last_seen_at),
        )
        self._changed(lambda: self._sensors.__setitem__(sensor.sensor_id, old))

    # Readings

    async def add_reading(self, sensor_id: str, temperature: float, ts: datetime) -> bool:
        """Store a reading. Returns False if the same reading was already stored."""
        rows = self._readings.setdefault(sensor_id, [])
        ts = _db_time(ts)
        i = bisect_left(rows, (ts,))
        if i < len(rows) and rows[i][0] == ts:
            return False  # UNIQUE (sensor_id, ts)
        row = (ts, temperature)
        insort(rows, row)
        self._changed(lambda: rows.remove(row))
        return True

    async def readings(self, sensor_id: str, since: datetime, until: datetime) -> list[Point]:
        rows = self._readings.get(sensor_id, [])
        lo = bisect_left(rows, (_db_time(since),))
        hi = bisect_left(rows, (_db_time(until),))
        return [Point(ts, temperature) for ts, temperature in rows[lo:hi]]

    # Incidents

    async def open_incident(
        self,
        sensor_id: str,
        started_at: datetime,
        alerted_at: datetime,
        peak_temperature: float,
        limit: float,
    ) -> None:
        incident = Incident(
            sensor_id, _db_time(started_at), _db_time(alerted_at), None, peak_temperature, limit
        )
        self._incidents.append(incident)
        self._changed(lambda: self._incidents.remove(incident))

    async def close_incident(
        self, sensor_id: str, resolved_at: datetime, peak_temperature: float
    ) -> None:
        before = self._incidents
        self._incidents = [
            replace(i, resolved_at=_db_time(resolved_at), peak_temperature=peak_temperature)
            if i.sensor_id == sensor_id and i.resolved_at is None
            else i
            for i in before
        ]
        self._changed(lambda: setattr(self, "_incidents", before))

    async def incidents(self, since: datetime, until: datetime) -> list[Incident]:
        """Incidents that overlap the [since, until) period."""
        since, until = _db_time(since), _db_time(until)
        found = [
            i
            for i in self._incidents
            if i.started_at < until and (i.resolved_at is None or i.resolved_at >= since)
        ]
        return sorted(found, key=lambda i: i.started_at)


@dataclass(frozen=True)
class DemoSettings:
    """The settings FridgeService reads, with the defaults of app.config.Settings (a test
    compares them). Simulated time is shown in UTC, so no time zone data is needed."""

    default_limit_c: float = 5.0
    alert_delay_minutes: float = 5.0
    recovery_hysteresis_c: float = 0.5
    alert_max_age_minutes: float = 15.0
    stale_after_minutes: float = 10.0

    @property
    def tz(self) -> tzinfo:
        return UTC


class ChatNotifier:
    """Stands in for TelegramNotifier: keeps what would have been sent, with the time."""

    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self.sent: list[tuple[datetime, str]] = []

    async def send(self, text: str) -> None:
        self.sent.append((self._clock(), text))


def _clock(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%H:%M")


def _points(points: list[Point]) -> list[list[float]]:
    """[[unix seconds, °C], ...] for the chart drawn by the page."""
    return [[int(p.ts.timestamp()), p.temperature] for p in points]


def split_command(text: str) -> tuple[str, str | None] | None:
    """("setlimit", "bar-fridge 6") from "/setlimit@FridgeBot bar-fridge 6", like aiogram's
    Command filter; None for text that is not a command."""
    parts = text.strip().split(maxsplit=1)
    if not parts or not parts[0].startswith("/") or len(parts[0]) < 2:
        return None
    command = parts[0][1:].partition("@")[0]
    return command, parts[1] if len(parts) == 2 else None


class FridgeDemo:
    def __init__(self, seed: int) -> None:
        self.now = START
        rng = random.Random(seed)
        # No random door openings or failures: in the demo they happen when the script or
        # the visitor presses a button. The sensor noise stays.
        self.models = {
            p.sensor_id: FridgeModel(p, rng, door_per_hour=0, failures_per_day=0)
            for p in DEFAULT_PROFILES
        }
        self.settings = DemoSettings()
        self.notifier = ChatNotifier(lambda: self.now)
        self.service = FridgeService(
            MemoryRepository(),  # type: ignore[arg-type]  # same methods as app.db.Repository
            self.notifier,
            self.settings,  # type: ignore[arg-type]  # the fields FridgeService reads
            clock=lambda: self.now,
        )
        self.door_open = False
        self.compressor_broken = False
        self._reported = 0

    async def setup(self) -> None:
        """What `simulator.py --backfill-hours 1` does: set the limits, then post the last
        hour of readings as one batch."""
        for model in self.models.values():
            await self.service.set_limit(model.profile.sensor_id, model.profile.limit_c)
        batch = []
        at = START - BACKFILL
        while at < START:
            batch += [self._reading(model, at) for model in self.models.values()]
            at += timedelta(seconds=STEP_S)
        await self.service.ingest_many(batch)

    @staticmethod
    def _reading(model: FridgeModel, at: datetime) -> ReadingIn:
        return ReadingIn(
            sensor_id=model.profile.sensor_id, temperature=model.step(STEP_S), timestamp=at
        )

    async def advance(self, seconds: float) -> None:
        """Move simulated time forward; every sensor posts a reading each STEP_S."""
        for _ in range(max(1, round(seconds / STEP_S))):
            self.now += timedelta(seconds=STEP_S)
            for model in self.models.values():
                await self.service.ingest(self._reading(model, self.now))

    def apply_controls(self) -> None:
        model = self.models[MAIN_SENSOR]
        if self.compressor_broken:
            if model.mode is not Mode.FAILURE:
                model.force_failure(UNTIL_CHANGED_S)
        elif self.door_open:
            if model.mode is not Mode.DOOR_OPEN:
                model.force_door(UNTIL_CHANGED_S)
        else:
            model.mode = Mode.NORMAL

    def new_messages(self) -> list[dict[str, str]]:
        sent = self.notifier.sent[self._reported :]
        self._reported = len(self.notifier.sent)
        return [{"text": text, "clock": _clock(at)} for at, text in sent]

    async def snapshot(self) -> dict[str, Any]:
        sensor, points = await self.service.history(MAIN_SENSOR, CHART_HOURS)
        status = next(s for s in await self.service.statuses() if s.sensor.sensor_id == MAIN_SENSOR)
        alert = status.sensor.alert
        started = alert.breach_started_at
        return {
            "now": int(self.now.timestamp()),
            "clock": _clock(self.now),
            "time": f"{self.now:%H:%M:%S}",
            "sensor": {
                "id": MAIN_SENSOR,
                "limit": sensor.limit,
                "temperature": sensor.last_temperature,
                "state": alert.state.value,
                "above_for_s": int((self.now - started).total_seconds()) if started else None,
                "peak": alert.peak_temperature,
            },
            "fridge": {
                "mode": self.models[MAIN_SENSOR].mode.value,
                "door_open": self.door_open,
                "compressor_broken": self.compressor_broken,
            },
            "rules": {
                "delay_s": int(self.settings.alert_delay_minutes * 60),
                "hysteresis_c": self.settings.recovery_hysteresis_c,
                "step_s": STEP_S,
            },
            "points": _points(points),
            "messages": self.new_messages(),
        }

    async def command(self, text: str) -> dict[str, Any]:
        """What the bot answers to a chat message (see app/bot.py for the command list)."""
        parsed = split_command(text)
        if parsed is None:
            return {"kind": "ignored"}  # the real bot only reacts to commands
        name, args = parsed
        if name in ("start", "help"):
            return {"kind": "text", "text": HELP_TEXT}
        if name == "id":
            return {"kind": "text", "text": id_reply(DEMO_CHAT_ID)}
        if name == "status":
            return {"kind": "text", "text": await status_reply(self.service)}
        if name == "setlimit":
            return {"kind": "text", "text": await setlimit_reply(self.service, args)}
        if name == "report":
            return {"kind": "text", "text": await report_reply(self.service, self.settings.tz)}
        if name == "history":
            reply = await history_reply(self.service, args, self.service.history)
            if isinstance(reply, str):
                return {"kind": "text", "text": reply}
            return self._chart_reply(reply)
        return {"kind": "ignored"}  # unknown commands get no answer either

    @staticmethod
    def _chart_reply(reply: HistoryChart[tuple[Sensor, list[Point]]]) -> dict[str, Any]:
        sensor, points = reply.chart
        return {
            "kind": "chart",
            "caption": reply.caption,
            "sensor": reply.sensor_id,
            "hours": reply.hours,
            "limit": sensor.limit,
            "points": _points(points),
        }


# The page's API. One demo per page; start() begins a new one (Replay calls it again).

_demo: FridgeDemo | None = None


def _current() -> FridgeDemo:
    if _demo is None:
        raise RuntimeError("call start() first")
    return _demo


async def start(seed: int = 7) -> dict[str, Any]:
    global _demo
    _demo = FridgeDemo(seed)
    await _demo.setup()
    return await _demo.snapshot()


async def advance(seconds: float = STEP_S) -> dict[str, Any]:
    demo = _current()
    await demo.advance(seconds)
    return await demo.snapshot()


async def set_door(is_open: bool) -> dict[str, Any]:
    demo = _current()
    demo.door_open = bool(is_open)
    demo.apply_controls()
    return await demo.snapshot()


async def set_compressor(broken: bool) -> dict[str, Any]:
    demo = _current()
    demo.compressor_broken = bool(broken)
    demo.apply_controls()
    return await demo.snapshot()


async def command(text: str) -> dict[str, Any]:
    demo = _current()
    reply = await demo.command(str(text)[:500])
    return {**reply, "clock": _clock(demo.now), "snapshot": await demo.snapshot()}
