"""SQLite cache of day-ahead prices, plus a note of which daily plans were already sent.

Prices are stored as published (15 or 60 minutes) and keyed by bidding zone and unix start
time. The price is TEXT so the Decimal survives the round trip exactly.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import aiosqlite

from app.prices import PricePoint

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    bzn        TEXT    NOT NULL,
    start      INTEGER NOT NULL,  -- unix seconds, UTC
    minutes    INTEGER NOT NULL,  -- 15 or 60, as published
    price      TEXT    NOT NULL,  -- EUR/MWh, exact decimal
    source     TEXT    NOT NULL,
    fetched_at TEXT    NOT NULL,
    PRIMARY KEY (bzn, start)
);

CREATE TABLE IF NOT EXISTS licenses (
    bzn          TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    license_info TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sent_plans (
    day     TEXT PRIMARY KEY,  -- local date the plan is for
    sent_at TEXT NOT NULL
);
"""


class PriceCache:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._db = conn

    @classmethod
    async def connect(cls, path: Path | str) -> "PriceCache":
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._db.close()

    async def save(
        self,
        bzn: str,
        points: list[PricePoint],
        source: str,
        license_info: str,
        fetched_at: datetime,
    ) -> None:
        await self._db.executemany(
            "INSERT OR REPLACE INTO prices (bzn, start, minutes, price, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    bzn,
                    int(p.start.timestamp()),
                    p.minutes,
                    str(p.price),
                    source,
                    fetched_at.astimezone(UTC).isoformat(timespec="seconds"),
                )
                for p in points
            ],
        )
        if license_info:
            await self._db.execute(
                "INSERT OR REPLACE INTO licenses (bzn, source, license_info) VALUES (?, ?, ?)",
                (bzn, source, license_info),
            )
        await self._db.commit()

    async def load(self, bzn: str, start: datetime, end: datetime) -> list[PricePoint]:
        """Prices that overlap [start, end). An hourly price starting 45 min before `start`
        still covers its first quarter-hour, so look back one hour."""
        async with self._db.execute(
            "SELECT start, minutes, price FROM prices WHERE bzn = ? AND start >= ? AND start < ? "
            "ORDER BY start",
            (bzn, int(start.timestamp()) - 3600, int(end.timestamp())),
        ) as cur:
            rows = await cur.fetchall()
        return [
            PricePoint(datetime.fromtimestamp(r["start"], UTC), r["minutes"], Decimal(r["price"]))
            for r in rows
        ]

    async def span(self, bzn: str) -> tuple[datetime, datetime] | None:
        """First start and last end of the cached prices."""
        async with self._db.execute(
            "SELECT MIN(start) AS first, MAX(start + minutes * 60) AS last FROM prices "
            "WHERE bzn = ?",
            (bzn,),
        ) as cur:
            row = await cur.fetchone()
        if row is None or row["first"] is None:
            return None
        return datetime.fromtimestamp(row["first"], UTC), datetime.fromtimestamp(row["last"], UTC)

    async def license(self, bzn: str) -> tuple[str, str] | None:
        async with self._db.execute(
            "SELECT source, license_info FROM licenses WHERE bzn = ?", (bzn,)
        ) as cur:
            row = await cur.fetchone()
        return (row["source"], row["license_info"]) if row else None

    async def was_sent(self, day: date) -> bool:
        async with self._db.execute(
            "SELECT 1 FROM sent_plans WHERE day = ?", (day.isoformat(),)
        ) as cur:
            return await cur.fetchone() is not None

    async def mark_sent(self, day: date, at: datetime) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO sent_plans (day, sent_at) VALUES (?, ?)",
            (day.isoformat(), at.astimezone(UTC).isoformat(timespec="seconds")),
        )
        await self._db.commit()
