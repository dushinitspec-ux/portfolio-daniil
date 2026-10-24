"""Audit log in SQLite: when, from where, which types and how many, and what was decided.

There is deliberately no column that could hold a value or a prompt. The only text
stored is chosen by the gateway itself (decision, source, model name, entity type names).
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id         INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    source     TEXT NOT NULL,     -- api | web
    decision   TEXT NOT NULL,     -- masked | passed | blocked | error
    entities   TEXT NOT NULL,     -- {"EMAIL": {"count": 2, "distinct": 1, "action": "mask"}}
    messages   INTEGER NOT NULL,
    model      TEXT NOT NULL,
    latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit (ts);
"""


@dataclass(frozen=True)
class AuditEntry:
    ts: datetime
    source: str
    decision: str
    entities: dict[str, dict[str, int | str]]
    messages: int
    model: str
    latency_ms: int | None

    @property
    def summary(self) -> str:
        """Entity counts for the web page, for example "EMAIL ×2, IBAN ×1"."""
        return ", ".join(f"{t} ×{info['count']}" for t, info in self.entities.items()) or "none"


class AuditLog:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._db = conn

    @classmethod
    async def connect(cls, path: Path | str) -> "AuditLog":
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._db.close()

    async def record(
        self,
        *,
        source: str,
        decision: str,
        entities: dict[str, dict[str, int | str]],
        messages: int,
        model: str,
        latency_ms: int | None,
        at: datetime | None = None,
    ) -> None:
        ts = (at or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds")
        await self._db.execute(
            "INSERT INTO audit (ts, source, decision, entities, messages, model, latency_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                source,
                decision,
                json.dumps(entities, sort_keys=True),
                messages,
                model,
                latency_ms,
            ),
        )
        await self._db.commit()

    async def recent(self, limit: int = 20) -> list[AuditEntry]:
        cursor = await self._db.execute(
            "SELECT ts, source, decision, entities, messages, model, latency_ms"
            " FROM audit ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            AuditEntry(datetime.fromisoformat(r[0]), r[1], r[2], json.loads(r[3]), r[4], r[5], r[6])
            for r in rows
        ]
