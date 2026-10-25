"""In-browser demo for the portfolio site: the real copilot, run by Pyodide (WebAssembly).

An employee chats with the bot. Each question goes through the same Copilot.ask() as in the
Telegram bot, in demo mode: BM25 retrieval over knowledge/, extractive answers with numbered
sources (DemoLLM), rule-based triage. The page draws the chat and the copilot's working
(top sources, confidence, ticket queue) from what these functions return; the bot's texts
are the bot's own (app/messages.py).

Storage is the real SQLite schema of app/db.py in memory. aiosqlite needs a thread, which
WebAssembly does not have, so `SQLiteConnection` gives `Repository` the same async interface
on top of the standard sqlite3 module.

Every function takes and returns JSON-compatible values.
"""

import sqlite3
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import messages
from app.config import Settings
from app.copilot import Copilot, Reply, Route
from app.db import SCHEMA, Repository, Requester, Ticket
from app.demo import SAMPLE_QUESTIONS
from app.knowledge import load_documents
from app.llm import create_llm
from app.retrieval import Retriever

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_LENGTH = 2000  # characters of a question, as on the project's web page
EMPLOYEE = Requester("Erika Mustermann", "telegram", 1001)

# The autoplay: (question, what the employee does next). The questions are the project's
# sample questions (app/demo.py) plus one that the knowledge base does not cover.
SCRIPT: list[tuple[str, str | None]] = [
    ("How do I connect to the VPN from home?", "solved"),
    ("Принтер не печатает, документ висит в очереди", None),
    ("The coffee machine in the kitchen is leaking", None),
    ("I clicked a link in a fake DHL email and typed my password", None),
]
# Messages to try: the rest of the sample questions, and the /ticket command.
SUGGESTIONS = [q for _, q, _ in SAMPLE_QUESTIONS if q not in {q for q, _ in SCRIPT}] + [
    "/ticket The scanner is offline"
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
    """The project's default settings in demo mode; the environment and .env are not read.

    Built without validation: the only validator checks the timezone, which needs tz data
    the browser would have to download, and only the web page uses the timezone. A test
    checks that these settings equal the validated ones.
    """
    return Settings.model_construct(demo_mode=True)


@dataclass
class _Session:
    settings: Settings
    repo: Repository
    copilot: Copilot


_session: _Session | None = None


async def _current() -> _Session:
    global _session
    if _session is None:
        settings = demo_settings()
        retriever = Retriever(
            load_documents(PROJECT_ROOT / settings.knowledge_dir),
            min_score=settings.min_score,
            min_coverage=settings.min_coverage,
        )
        repo = await memory_repository()
        copilot = Copilot(retriever, create_llm(settings), repo, top_k=settings.top_k)
        _session = _Session(settings, repo, copilot)
    return _session


def _ticket_json(ticket: Ticket) -> dict[str, Any]:
    return {
        "id": ticket.id,
        "priority": ticket.triage.priority.value,
        "category": ticket.triage.category.value,
        "summary": ticket.triage.summary,
        "reason": ticket.triage.reason,
        "by": ticket.triage.by,
        "route_reason": ticket.route_reason,
        "status": ticket.status.value,
        "requester": ticket.requester.name,
        "question": ticket.question,
    }


def _reply_json(reply: Reply, company: str) -> dict[str, Any]:
    decision = reply.decision
    retrieval = decision.retrieval
    if reply.answered:
        text = messages.answer_text(reply, company)
    else:
        assert reply.ticket is not None
        text = messages.ticket_text(reply.ticket, decision.route)
    return {
        "question": reply.question,
        "question_id": reply.question_id,
        "answered": reply.answered,
        "text": text,  # what the bot sends in Telegram
        # Telegram shows "Solved" / "Create ticket" under an answer without a ticket.
        "buttons": reply.answered and reply.ticket is None,
        "answer": decision.answer,
        "sources": [
            {"number": s.number, "label": s.label, "file": f"knowledge/{s.section.doc_id}.md"}
            for s in decision.sources
        ],
        "note": decision.note,
        "route": decision.route.name if decision.route else None,
        "ticket_reason": decision.ticket_reason,
        "ticket": _ticket_json(reply.ticket) if reply.ticket else None,
        "it_notification": messages.it_notification(reply.ticket) if reply.ticket else None,
        "retrieval": {
            "terms": list(retrieval.terms),
            "hits": [
                {
                    "label": hit.section.label,
                    "file": f"knowledge/{hit.section.doc_id}.md",
                    "score": round(hit.score, 2),
                    "matched": list(hit.matched),
                }
                for hit in retrieval.hits
            ],
            "coverage": round(retrieval.coverage, 3),
            "coverage_label": retrieval.coverage_label,
            "confident": retrieval.confident,
        },
    }


def _clean(text: str) -> str:
    text = text.strip()[:MAX_LENGTH]
    if not text:
        raise ValueError("empty message")
    return text


async def start() -> dict[str, Any]:
    """A fresh chat (empty database) and everything the page needs to draw it."""
    global _session
    if _session is not None:
        await _session.repo.close()
        _session = None
    session = await _current()
    settings, retriever = session.settings, session.copilot.retriever
    return {
        "company": settings.company_name,
        "employee": EMPLOYEE.name,
        "answers_by": session.copilot.llm.name,
        "min_score": retriever.min_score,
        "min_coverage": retriever.min_coverage,
        "top_k": session.copilot.top_k,
        "documents": len(retriever.documents),
        "sections": len(retriever.sections),
        "script": [{"question": q, "then": then} for q, then in SCRIPT],
        "suggestions": SUGGESTIONS,
    }


async def send(text: str) -> dict[str, Any]:
    """A chat message, routed like the bot does it (app/bot.py, create_router).

    "/ticket <text>" opens a ticket directly, any other command shows the welcome text with
    the AI notice, everything else is a question.
    """
    session = await _current()
    text = _clean(text)
    if not text.startswith("/"):
        return {"kind": "answer", **await ask(text)}
    command, _, rest = text.partition(" ")
    if command.split("@")[0] == "/ticket":
        if not rest.strip():
            return {"kind": "text", "text": messages.TICKET_USAGE}
        return {"kind": "ticket", **await open_ticket(rest)}
    company = session.settings.company_name
    return {"kind": "text", "text": messages.welcome(company, EMPLOYEE.name.split()[0])}


async def ask(text: str) -> dict[str, Any]:
    """An employee's question: answered with sources, or a ticket (or both, for security)."""
    session = await _current()
    reply = await session.copilot.ask(_clean(text), EMPLOYEE)
    return _reply_json(reply, session.settings.company_name)


async def solved(question_id: int) -> dict[str, Any]:
    """The "Solved" button under an answer."""
    session = await _current()
    ok = await session.copilot.mark_solved(question_id, EMPLOYEE.user_id)
    return {"ok": ok, "text": messages.SOLVED if ok else messages.NOT_YOURS}


async def create_ticket(question_id: int) -> dict[str, Any]:
    """The "Create ticket" button: the answer did not help."""
    session = await _current()
    ticket = await session.copilot.ticket_for_question(question_id, EMPLOYEE.user_id)
    if ticket is None:
        return {"ok": False, "text": messages.NOT_YOURS, "ticket": None}
    return {
        "ok": True,
        "text": messages.ticket_text(ticket, Route.ASKED),
        "ticket": _ticket_json(ticket),
        "it_notification": messages.it_notification(ticket),
    }


async def open_ticket(text: str) -> dict[str, Any]:
    """The /ticket command: a ticket written directly, triaged by the rules."""
    session = await _current()
    ticket = await session.copilot.open_ticket(_clean(text), EMPLOYEE)
    return {
        "text": messages.ticket_text(ticket, Route.DIRECT),
        "ticket": _ticket_json(ticket),
        "it_notification": messages.it_notification(ticket),
    }


async def tickets() -> list[dict[str, Any]]:
    """The IT queue: open work first, by priority, newest first (as on the tickets page)."""
    session = await _current()
    return [_ticket_json(t) for t in await session.repo.list_tickets()]


async def stats() -> dict[str, Any]:
    session = await _current()
    s = await session.repo.stats()
    return {
        "questions": s.questions,
        "answered": s.answered,
        "solved": s.solved,
        "tickets": s.tickets,
        "open_tickets": s.open_tickets,
        "open_by_priority": {p.value: n for p, n in s.open_by_priority.items()},
    }
