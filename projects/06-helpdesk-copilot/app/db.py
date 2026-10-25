"""SQLite storage: every question with its outcome, and the tickets for the IT team.

Timestamps are stored as ISO 8601 strings in UTC, so string order is time order.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from app.triage import Category, Priority, Triage

if TYPE_CHECKING:
    import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id             INTEGER PRIMARY KEY,
    created_at     TEXT NOT NULL,
    requester_id   INTEGER,
    requester_name TEXT NOT NULL,
    channel        TEXT NOT NULL,
    question       TEXT NOT NULL,
    category       TEXT NOT NULL,
    priority       TEXT NOT NULL,
    summary        TEXT NOT NULL,
    triage_reason  TEXT NOT NULL,
    triaged_by     TEXT NOT NULL,
    route_reason   TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'open',
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status, priority);

CREATE TABLE IF NOT EXISTS questions (
    id             INTEGER PRIMARY KEY,
    asked_at       TEXT NOT NULL,
    requester_id   INTEGER,
    requester_name TEXT NOT NULL,
    channel        TEXT NOT NULL,
    question       TEXT NOT NULL,
    answered       INTEGER NOT NULL,
    answer         TEXT NOT NULL DEFAULT '',
    sources        TEXT NOT NULL DEFAULT '[]',
    coverage       REAL NOT NULL,
    resolution     TEXT,
    ticket_id      INTEGER REFERENCES tickets(id)
);
"""


class Status(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


class Resolution(StrEnum):
    SOLVED = "solved"  # the employee pressed "Solved"
    TICKET = "ticket"  # a ticket was created for this question


@dataclass(frozen=True)
class Requester:
    name: str
    channel: str  # "telegram", "web", "api"
    user_id: int | None = None


@dataclass(frozen=True)
class Ticket:
    id: int
    created_at: datetime
    requester: Requester
    question: str
    triage: Triage
    route_reason: str
    status: Status


@dataclass(frozen=True)
class QuestionRecord:
    id: int
    requester: Requester
    question: str
    answered: bool
    resolution: Resolution | None
    ticket_id: int | None


@dataclass(frozen=True)
class Stats:
    questions: int
    answered: int
    solved: int
    tickets: int
    open_tickets: int
    open_by_priority: dict[Priority, int]


def to_db(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ticket(row: "aiosqlite.Row") -> Ticket:
    return Ticket(
        id=row["id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        requester=Requester(row["requester_name"], row["channel"], row["requester_id"]),
        question=row["question"],
        triage=Triage(
            Category(row["category"]),
            Priority(row["priority"]),
            row["summary"],
            row["triage_reason"],
            row["triaged_by"],
        ),
        route_reason=row["route_reason"],
        status=Status(row["status"]),
    )


class Repository:
    def __init__(self, conn: "aiosqlite.Connection") -> None:
        self._db = conn

    @classmethod
    async def connect(cls, path: Path | str) -> "Repository":
        # Imported here, not at the top: aiosqlite runs SQLite in a thread, and the in-browser
        # demo (WebAssembly, no threads) passes its own connection to __init__ instead.
        import aiosqlite

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

    # Questions

    async def log_question(
        self,
        requester: Requester,
        question: str,
        *,
        answered: bool,
        coverage: float,
        answer: str = "",
        sources: list[str] | None = None,
        at: datetime | None = None,
    ) -> int:
        cur = await self._db.execute(
            """
            INSERT INTO questions (asked_at, requester_id, requester_name, channel, question,
                                   answered, answer, sources, coverage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                to_db(at or utcnow()),
                requester.user_id,
                requester.name,
                requester.channel,
                question,
                int(answered),
                answer,
                json.dumps(sources or [], ensure_ascii=False),
                round(coverage, 3),
            ),
        )
        await self._db.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    async def get_question(self, question_id: int) -> QuestionRecord | None:
        async with self._db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return QuestionRecord(
            id=row["id"],
            requester=Requester(row["requester_name"], row["channel"], row["requester_id"]),
            question=row["question"],
            answered=bool(row["answered"]),
            resolution=Resolution(row["resolution"]) if row["resolution"] else None,
            ticket_id=row["ticket_id"],
        )

    async def resolve_question(
        self, question_id: int, resolution: Resolution, ticket_id: int | None = None
    ) -> None:
        await self._db.execute(
            "UPDATE questions SET resolution = ?, ticket_id = ? WHERE id = ?",
            (resolution.value, ticket_id, question_id),
        )
        await self._db.commit()

    # Tickets

    async def create_ticket(
        self,
        requester: Requester,
        question: str,
        triage: Triage,
        route_reason: str,
        at: datetime | None = None,
    ) -> Ticket:
        now = to_db(at or utcnow())
        cur = await self._db.execute(
            """
            INSERT INTO tickets (created_at, requester_id, requester_name, channel, question,
                                 category, priority, summary, triage_reason, triaged_by,
                                 route_reason, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                requester.user_id,
                requester.name,
                requester.channel,
                question,
                triage.category.value,
                triage.priority.value,
                triage.summary,
                triage.reason,
                triage.by,
                route_reason,
                now,
            ),
        )
        await self._db.commit()
        assert cur.lastrowid is not None
        ticket = await self.get_ticket(cur.lastrowid)
        assert ticket is not None
        return ticket

    async def get_ticket(self, ticket_id: int) -> Ticket | None:
        async with self._db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)) as cur:
            row = await cur.fetchone()
        return _ticket(row) if row else None

    async def list_tickets(self, status: Status | None = None, limit: int = 200) -> list[Ticket]:
        """Open work first (by priority, newest first), closed tickets at the end."""
        where, params = ("WHERE status = ?", [status.value]) if status else ("", [])
        async with self._db.execute(
            f"""
            SELECT * FROM tickets {where}
            ORDER BY status = 'closed', priority, created_at DESC, id DESC
            LIMIT ?
            """,
            [*params, limit],
        ) as cur:
            return [_ticket(row) for row in await cur.fetchall()]

    async def set_ticket_status(self, ticket_id: int, status: Status) -> bool:
        cur = await self._db.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, to_db(utcnow()), ticket_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def has_tickets(self) -> bool:
        async with self._db.execute("SELECT 1 FROM tickets LIMIT 1") as cur:
            return await cur.fetchone() is not None

    async def stats(self) -> Stats:
        async with self._db.execute(
            """
            SELECT COUNT(*) AS questions,
                   COALESCE(SUM(answered), 0) AS answered,
                   COALESCE(SUM(resolution = 'solved'), 0) AS solved
            FROM questions
            """
        ) as cur:
            q = await cur.fetchone()
        async with self._db.execute(
            "SELECT status, priority, COUNT(*) AS n FROM tickets GROUP BY status, priority"
        ) as cur:
            rows = await cur.fetchall()
        assert q is not None
        open_by_priority = {p: 0 for p in Priority}
        total = open_total = 0
        for row in rows:
            total += row["n"]
            if row["status"] != Status.CLOSED:
                open_total += row["n"]
                open_by_priority[Priority(row["priority"])] += row["n"]
        return Stats(
            q["questions"], q["answered"], q["solved"], total, open_total, open_by_priority
        )
