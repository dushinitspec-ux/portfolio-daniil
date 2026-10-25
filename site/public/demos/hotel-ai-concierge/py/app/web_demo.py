"""In-browser demo for the portfolio site: the real concierge, run by Pyodide (WebAssembly).

It is the terminal demo (`python -m app.demo`) behind a JSON interface: the same Concierge,
knowledge base and offline MockLLM, the same guests and the same staff answer. Nothing leaves
the browser: there is no API key and no Telegram, so the guest and staff chats are drawn by
the page, and every text in them comes from the functions below.

Storage is the real SQLite schema of app/db.py in memory. aiosqlite needs a thread, which
WebAssembly does not have, so `SQLiteConnection` gives `Repository` the same async interface
on top of the standard sqlite3 module.

Every function takes and returns JSON-compatible values.
"""

import itertools
import sqlite3
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.concierge import Concierge, Guest
from app.config import Provider, Settings
from app.db import SCHEMA, Repository
from app.demo import SCRIPT, STAFF_ANSWER
from app.knowledge import KnowledgeBase
from app.language import detect_language
from app.llm import create_llm
from app.texts import STAFF_REPLY_HEADER

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_LENGTH = 1000  # characters of a message the demo accepts

# More questions to try, two per language. Some are not in the knowledge base on purpose:
# those go to the staff chat.
SUGGESTIONS: list[tuple[str, str]] = [
    ("en", "Is there free parking?"),
    ("en", "Is there a hairdresser in the hotel?"),
    ("ru", "Где можно курить?"),
    ("ru", "Во сколько работает спа?"),
    ("tr", "Havalimanı transferi var mı?"),
    ("tr", "Odada kasa var mı?"),
    ("de", "Darf ich meinen Hund mitbringen?"),
    ("de", "Kann ich ein Zimmer mit Meerblick bekommen?"),
]


class _Cursor:
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor
        self.lastrowid = cursor.lastrowid
        self.rowcount = cursor.rowcount

    async def fetchone(self) -> Any:
        return self._cursor.fetchone()

    async def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()


class _Result:
    """Like aiosqlite's execute(): awaitable, and usable with `async with`."""

    def __init__(self, run: Callable[[], sqlite3.Cursor]) -> None:
        self._run = run

    async def _cursor(self) -> _Cursor:
        return _Cursor(self._run())

    def __await__(self) -> Generator[Any, None, _Cursor]:
        return self._cursor().__await__()

    async def __aenter__(self) -> _Cursor:
        return await self._cursor()

    async def __aexit__(self, *exc: object) -> None:
        return None


class SQLiteConnection:
    """The part of aiosqlite.Connection that Repository uses, without a thread."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql: str, parameters: Any = ()) -> _Result:
        return _Result(lambda: self._conn.execute(sql, parameters))

    async def executescript(self, sql: str) -> None:
        self._conn.executescript(sql)

    async def commit(self) -> None:
        self._conn.commit()

    async def close(self) -> None:
        self._conn.close()


async def memory_repository() -> Repository:
    """Repository.connect(":memory:") with the browser-safe connection."""
    conn = SQLiteConnection()
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.executescript(SCHEMA)
    await conn.commit()
    return Repository(conn)  # type: ignore[arg-type]  # same interface as aiosqlite's


def demo_settings() -> Settings:
    # The offline provider, whatever the environment says; .env is never read.
    return Settings(_env_file=None, llm_provider=Provider.MOCK)  # type: ignore[call-arg]


@dataclass
class _Session:
    settings: Settings
    repo: Repository
    knowledge: KnowledgeBase
    concierge: Concierge
    guests: dict[int, Guest]
    # Stand in for the ids Telegram gives the messages the bot posts in the staff group.
    staff_ids: Iterator[int] = field(default_factory=lambda: itertools.count(1000))


_session: _Session | None = None


async def _current() -> _Session:
    global _session
    if _session is None:
        settings = demo_settings()
        knowledge = KnowledgeBase(PROJECT_ROOT / settings.knowledge_path)
        repo = await memory_repository()
        concierge = Concierge(create_llm(settings), knowledge, repo, settings)
        guests = {guest.chat_id: guest for guest, _ in SCRIPT}
        _session = _Session(settings, repo, knowledge, concierge, guests)
    return _session


def _clean(text: str) -> str:
    text = text.strip()[:MAX_LENGTH]
    if not text:
        raise ValueError("empty message")
    return text


async def start() -> dict[str, Any]:
    """A fresh conversation (empty database) and everything the page needs to draw it."""
    global _session
    if _session is not None:
        await _session.repo.close()
        _session = None
    session = await _current()
    return {
        "hotel": session.settings.hotel_name,
        "provider": session.settings.llm_provider.value,
        "sections": [section.title for section in session.knowledge.sections],
        "guests": [
            {
                "id": guest.chat_id,
                "name": guest.name,
                "username": guest.username,
                "telegram_language": guest.telegram_language,
            }
            for guest in session.guests.values()
        ],
        "script": [{"guest": guest.chat_id, "text": text} for guest, text in SCRIPT],
        "staff_answer": STAFF_ANSWER,
        "suggestions": [{"lang": lang, "text": text} for lang, text in SUGGESTIONS],
    }


async def welcome(guest_id: int) -> dict[str, Any]:
    """What the bot says on /start, in the language of the guest's Telegram app."""
    session = await _current()
    reply = await session.concierge.welcome(session.guests[guest_id])
    return {"language": reply.language.value, "text": reply.text}


async def ask(guest_id: int, text: str) -> dict[str, Any]:
    """A guest message: the bot's answer, or the question as it is posted in the staff chat."""
    session = await _current()
    text = _clean(text)
    detected = detect_language(text)
    reply = await session.concierge.handle_guest_message(session.guests[guest_id], text)
    staff_message_id = None
    if reply.escalation_id is not None:
        staff_message_id = next(session.staff_ids)
        await session.concierge.attach_staff_message(reply.escalation_id, staff_message_id)
    return {
        "language": reply.language.value,
        "detected": detected.value if detected else None,
        "text": reply.text,
        "escalated": reply.escalation_id is not None,
        "escalation_id": reply.escalation_id,
        "staff_message_id": staff_message_id,
        "staff_text": reply.staff_text,
    }


async def staff_reply(staff_message_id: int, text: str) -> dict[str, Any]:
    """Reception replies to a question in the staff chat; the bot delivers it to the guest."""
    session = await _current()
    text = _clean(text)
    escalation = await session.repo.escalation_by_staff_message(staff_message_id)
    reply = await session.concierge.handle_staff_reply(staff_message_id, text)
    if reply is None or escalation is None:
        return {"delivered": False}
    language = escalation.language
    # The concierge translates a reply that is not in the guest's language. The offline
    # MockLLM cannot translate (it returns the text unchanged), so the reply goes as written.
    needs_translation = (
        session.settings.translate_staff_replies and detect_language(text) is not language
    )
    return {
        "delivered": True,
        "guest": reply.guest_chat_id,
        "guest_text": reply.guest_text,
        "confirmation": reply.confirmation,
        "language": language.value,
        "needs_translation": needs_translation,
        "translated": reply.guest_text != f"{STAFF_REPLY_HEADER[language]}\n{text}",
    }


async def stats() -> dict[str, int]:
    session = await _current()
    s = await session.concierge.stats()
    return {
        "guests": s.guests,
        "questions": s.questions,
        "answered_by_bot": s.answered_by_bot,
        "escalated": s.escalated,
        "open_escalations": s.open_escalations,
    }
