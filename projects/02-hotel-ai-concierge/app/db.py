"""SQLite storage: guests, the conversation log and escalations to staff."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import aiosqlite

from app.language import Language

SCHEMA = """
CREATE TABLE IF NOT EXISTS guests (
    chat_id    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    username   TEXT,
    language   TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS escalations (
    id               INTEGER PRIMARY KEY,
    guest_chat_id    INTEGER NOT NULL,
    language         TEXT NOT NULL,
    question         TEXT NOT NULL,
    question_en      TEXT NOT NULL,
    reason           TEXT NOT NULL,
    staff_message_id INTEGER UNIQUE,
    status           TEXT NOT NULL DEFAULT 'open',
    created_at       TEXT NOT NULL,
    answered_at      TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY,
    chat_id       INTEGER NOT NULL,
    role          TEXT NOT NULL,
    kind          TEXT NOT NULL,
    text          TEXT NOT NULL,
    language      TEXT,
    escalation_id INTEGER REFERENCES escalations(id),
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages (chat_id, id);
"""


class Role(StrEnum):
    GUEST = "guest"
    BOT = "bot"
    STAFF = "staff"


class Kind(StrEnum):
    QUESTION = "question"
    ANSWER = "answer"
    ESCALATED = "escalated"
    STAFF_REPLY = "staff_reply"


@dataclass(frozen=True)
class Escalation:
    id: int
    guest_chat_id: int
    language: Language
    question: str
    question_en: str
    status: str


@dataclass(frozen=True)
class Stats:
    guests: int
    questions: int
    answered_by_bot: int
    escalated: int
    open_escalations: int


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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

    # Guests

    async def upsert_guest(
        self, chat_id: int, name: str, username: str | None, language: Language
    ) -> None:
        now = _now()
        await self._db.execute(
            """
            INSERT INTO guests (chat_id, name, username, language, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (chat_id) DO UPDATE
               SET name = excluded.name, username = excluded.username,
                   language = excluded.language, last_seen = excluded.last_seen
            """,
            (chat_id, name, username, language.value, now, now),
        )
        await self._db.commit()

    async def guest_language(self, chat_id: int) -> Language | None:
        async with self._db.execute(
            "SELECT language FROM guests WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        return Language(row["language"]) if row else None

    # Conversation log

    async def log(
        self,
        chat_id: int,
        role: Role,
        kind: Kind,
        text: str,
        language: Language | None = None,
        escalation_id: int | None = None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO messages (chat_id, role, kind, text, language, escalation_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                role.value,
                kind.value,
                text,
                language.value if language else None,
                escalation_id,
                _now(),
            ),
        )
        await self._db.commit()

    async def recent_messages(self, chat_id: int, limit: int) -> list[tuple[Role, str]]:
        """The last `limit` messages of a chat, oldest first."""
        async with self._db.execute(
            "SELECT role, text FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [(Role(row["role"]), row["text"]) for row in reversed(rows)]

    # Escalations

    async def create_escalation(
        self,
        guest_chat_id: int,
        language: Language,
        question: str,
        question_en: str,
        reason: str,
    ) -> int:
        cur = await self._db.execute(
            """
            INSERT INTO escalations (guest_chat_id, language, question, question_en, reason,
                                     created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guest_chat_id, language.value, question, question_en, reason, _now()),
        )
        await self._db.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    async def set_staff_message(self, escalation_id: int, staff_message_id: int) -> None:
        await self._db.execute(
            "UPDATE escalations SET staff_message_id = ? WHERE id = ?",
            (staff_message_id, escalation_id),
        )
        await self._db.commit()

    async def escalation_by_staff_message(self, staff_message_id: int) -> Escalation | None:
        async with self._db.execute(
            "SELECT * FROM escalations WHERE staff_message_id = ?", (staff_message_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return Escalation(
            id=row["id"],
            guest_chat_id=row["guest_chat_id"],
            language=Language(row["language"]),
            question=row["question"],
            question_en=row["question_en"],
            status=row["status"],
        )

    async def mark_answered(self, escalation_id: int) -> None:
        await self._db.execute(
            """
            UPDATE escalations SET status = 'answered', answered_at = ?
             WHERE id = ? AND status = 'open'
            """,
            (_now(), escalation_id),
        )
        await self._db.commit()

    async def stats(self) -> Stats:
        async with self._db.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM guests) AS guests,
              (SELECT COUNT(*) FROM messages WHERE kind = 'question') AS questions,
              (SELECT COUNT(*) FROM messages WHERE kind = 'answer') AS answered,
              (SELECT COUNT(*) FROM escalations) AS escalated,
              (SELECT COUNT(*) FROM escalations WHERE status = 'open') AS open
            """
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        return Stats(
            row["guests"], row["questions"], row["answered"], row["escalated"], row["open"]
        )
