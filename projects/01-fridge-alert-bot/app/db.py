"""SQLite storage.

Timestamps are stored as ISO 8601 strings in UTC with a fixed format
("2026-10-24T09:30:00+00:00"), so plain string comparison sorts them correctly.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from app.alerts import AlertState, SensorState
from app.models import Incident, Point, Sensor

SCHEMA = """
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id         TEXT PRIMARY KEY,
    limit_c           REAL NOT NULL,
    state             TEXT NOT NULL DEFAULT 'ok',
    breach_started_at TEXT,
    peak_temperature  REAL,
    last_temperature  REAL,
    last_seen_at      TEXT
);

CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY,
    sensor_id   TEXT NOT NULL REFERENCES sensors(sensor_id),
    temperature REAL NOT NULL,
    ts          TEXT NOT NULL,
    UNIQUE (sensor_id, ts)
);

CREATE TABLE IF NOT EXISTS incidents (
    id               INTEGER PRIMARY KEY,
    sensor_id        TEXT NOT NULL REFERENCES sensors(sensor_id),
    started_at       TEXT NOT NULL,
    alerted_at       TEXT NOT NULL,
    resolved_at      TEXT,
    peak_temperature REAL NOT NULL,
    limit_c          REAL NOT NULL
);
"""


def to_db(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def from_db(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _sensor(row: aiosqlite.Row) -> Sensor:
    return Sensor(
        sensor_id=row["sensor_id"],
        limit=row["limit_c"],
        alert=AlertState(
            state=SensorState(row["state"]),
            breach_started_at=from_db(row["breach_started_at"]),
            peak_temperature=row["peak_temperature"],
        ),
        last_temperature=row["last_temperature"],
        last_seen_at=from_db(row["last_seen_at"]),
    )


def _incident(row: aiosqlite.Row) -> Incident:
    started, alerted = from_db(row["started_at"]), from_db(row["alerted_at"])
    assert started is not None and alerted is not None
    return Incident(
        sensor_id=row["sensor_id"],
        started_at=started,
        alerted_at=alerted,
        resolved_at=from_db(row["resolved_at"]),
        peak_temperature=row["peak_temperature"],
        limit=row["limit_c"],
    )


class Repository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._db = conn

    @classmethod
    async def connect(cls, path: Path | str) -> "Repository":
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._db.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Commit everything inside the block, or nothing if it raises."""
        try:
            yield
            await self._db.commit()
        except BaseException:
            await self._db.rollback()
            raise

    # Sensors

    async def get_sensor(self, sensor_id: str) -> Sensor | None:
        async with self._db.execute(
            "SELECT * FROM sensors WHERE sensor_id = ?", (sensor_id,)
        ) as cur:
            row = await cur.fetchone()
        return _sensor(row) if row else None

    async def list_sensors(self) -> list[Sensor]:
        async with self._db.execute("SELECT * FROM sensors ORDER BY sensor_id") as cur:
            return [_sensor(row) for row in await cur.fetchall()]

    async def create_sensor(self, sensor_id: str, limit: float) -> Sensor:
        await self._db.execute(
            "INSERT INTO sensors (sensor_id, limit_c) VALUES (?, ?)", (sensor_id, limit)
        )
        return Sensor(sensor_id=sensor_id, limit=limit, alert=AlertState())

    async def save_sensor(self, sensor: Sensor) -> None:
        alert = sensor.alert
        await self._db.execute(
            """
            UPDATE sensors
               SET limit_c = ?, state = ?, breach_started_at = ?, peak_temperature = ?,
                   last_temperature = ?, last_seen_at = ?
             WHERE sensor_id = ?
            """,
            (
                sensor.limit,
                alert.state.value,
                to_db(alert.breach_started_at) if alert.breach_started_at else None,
                alert.peak_temperature,
                sensor.last_temperature,
                to_db(sensor.last_seen_at) if sensor.last_seen_at else None,
                sensor.sensor_id,
            ),
        )

    # Readings

    async def add_reading(self, sensor_id: str, temperature: float, ts: datetime) -> bool:
        """Store a reading. Returns False if the same reading was already stored."""
        cur = await self._db.execute(
            "INSERT OR IGNORE INTO readings (sensor_id, temperature, ts) VALUES (?, ?, ?)",
            (sensor_id, temperature, to_db(ts)),
        )
        return cur.rowcount == 1

    async def readings(self, sensor_id: str, since: datetime, until: datetime) -> list[Point]:
        async with self._db.execute(
            """
            SELECT ts, temperature FROM readings
             WHERE sensor_id = ? AND ts >= ? AND ts < ?
             ORDER BY ts
            """,
            (sensor_id, to_db(since), to_db(until)),
        ) as cur:
            rows = await cur.fetchall()
        return [Point(datetime.fromisoformat(row["ts"]), row["temperature"]) for row in rows]

    # Incidents

    async def open_incident(
        self,
        sensor_id: str,
        started_at: datetime,
        alerted_at: datetime,
        peak_temperature: float,
        limit: float,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO incidents (sensor_id, started_at, alerted_at, peak_temperature, limit_c)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sensor_id, to_db(started_at), to_db(alerted_at), peak_temperature, limit),
        )

    async def close_incident(
        self, sensor_id: str, resolved_at: datetime, peak_temperature: float
    ) -> None:
        await self._db.execute(
            """
            UPDATE incidents SET resolved_at = ?, peak_temperature = ?
             WHERE sensor_id = ? AND resolved_at IS NULL
            """,
            (to_db(resolved_at), peak_temperature, sensor_id),
        )

    async def incidents(self, since: datetime, until: datetime) -> list[Incident]:
        """Incidents that overlap the [since, until) period."""
        async with self._db.execute(
            """
            SELECT * FROM incidents
             WHERE started_at < ? AND (resolved_at IS NULL OR resolved_at >= ?)
             ORDER BY started_at
            """,
            (to_db(until), to_db(since)),
        ) as cur:
            return [_incident(row) for row in await cur.fetchall()]
