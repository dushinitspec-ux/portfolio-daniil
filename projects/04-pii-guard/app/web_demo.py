"""Adapter for the in-browser demo on the portfolio site (Pyodide, JSON in and out).

It runs the real pipeline: Detector -> Guard (policy, masking, leak check) -> Gateway ->
the offline DemoLLM -> restore -> AuditLog. Only the plumbing differs from the server:

- the audit log is the real AuditLog on an in-memory SQLite database, reached through a
  small synchronous stand-in for aiosqlite (no threads in the browser);
- the model is DemoLLM wrapped so the page can show exactly what it was given.

The page shows the visitor's own text back to them with the detections marked. What the
"model" receives, its answer and the audit log hold placeholders, types and counts only.
"""

import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import phonenumbers

from app.audit import SCHEMA, AuditEntry, AuditLog
from app.detectors import Detector, load_names
from app.entities import Entity, EntityType
from app.gateway import BlockedError, Gateway
from app.guard import Guard, LeakCheckError, Message, Prepared
from app.llm import SYSTEM_PROMPT
from app.llm.demo import DISCLAIMER, DemoLLM
from app.masking import Segment, contains_value, placeholder_segments
from app.policy import Action, Policy, PolicyError, load_policy, parse_policy
from app.samples import SAMPLES
from app.validators import (
    IBAN_LENGTHS,
    card_brand,
    compact,
    email_is_valid,
    iban_is_valid,
    ipv4_is_valid,
    luhn_is_valid,
    vat_is_well_formed,
)

ROOT = Path(__file__).resolve().parent.parent
NAMES_FILE = ROOT / "names.demo.txt"
POLICY_FILE = ROOT / "policy.yaml"
PHONE_REGIONS = ("DE",)  # Settings.phone_regions default
MAX_INPUT_CHARS = 20000  # Settings.max_input_chars default
SOURCE = "web"


# --- aiosqlite stand-in --------------------------------------------------------------


class _Cursor:
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    @property
    def lastrowid(self) -> int | None:
        return self._cursor.lastrowid

    async def fetchone(self) -> Any:
        return self._cursor.fetchone()

    async def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()


class _Result:
    """What aiosqlite's execute() returns: awaitable, and an async context manager."""

    def __init__(self, run: Callable[[], sqlite3.Cursor]) -> None:
        self._run = run

    async def _cursor(self) -> _Cursor:
        return _Cursor(self._run())

    def __await__(self):  # type: ignore[no-untyped-def]
        return self._cursor().__await__()

    async def __aenter__(self) -> _Cursor:
        return await self._cursor()

    async def __aexit__(self, *exc: object) -> None:
        return None


class SyncConnection:
    """The part of aiosqlite.Connection that AuditLog uses, on plain sqlite3."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> _Result:
        return _Result(lambda: self._conn.execute(sql, parameters))

    async def executescript(self, script: str) -> None:
        self._conn.executescript(script)

    async def commit(self) -> None:
        self._conn.commit()

    async def close(self) -> None:
        self._conn.close()


async def open_audit_log() -> tuple[AuditLog, sqlite3.Connection]:
    """AuditLog.connect(":memory:") without aiosqlite."""
    conn = sqlite3.connect(":memory:")
    db = SyncConnection(conn)
    await db.executescript(SCHEMA)
    await db.commit()
    return AuditLog(db), conn  # type: ignore[arg-type]


# --- The model, as the page sees it --------------------------------------------------


class RecordingDemoLLM:
    """DemoLLM that remembers what it received, so the page shows exactly that."""

    name = DemoLLM.name

    def __init__(self) -> None:
        self._llm = DemoLLM()
        self.system: str | None = None
        self.received: list[Message] | None = None

    async def complete(self, system: str, messages: Sequence[Message]) -> str:
        self.system = system
        self.received = list(messages)
        return await self._llm.complete(system, messages)


# --- State of one page ---------------------------------------------------------------


class _State:
    def __init__(self) -> None:
        self.detector = Detector(PHONE_REGIONS, load_names(NAMES_FILE))
        self.audit: AuditLog | None = None
        self.conn: sqlite3.Connection | None = None

    async def audit_log(self) -> AuditLog:
        if self.audit is None:
            self.audit, self.conn = await open_audit_log()
        return self.audit


_state = _State()


def _policy_dict(policy: Policy) -> dict[str, str]:
    return {t.value: a.value for t, a in policy.summary()}


def _policy(rules: dict[str, str] | None) -> Policy:
    """The visitor's toggles go through the same parser as policy.yaml."""
    if rules is None:
        return load_policy(POLICY_FILE)
    return parse_policy({"default": "mask", "entities": dict(rules)})


def _entry(e: AuditEntry) -> dict[str, Any]:
    return {
        "ts": e.ts.isoformat(),
        "source": e.source,
        "decision": e.decision,
        "entities": e.entities,
        "messages": e.messages,
        "model": e.model,
        "latency_ms": e.latency_ms,
        "summary": e.summary,
    }


async def _recent(limit: int = 8) -> list[dict[str, Any]]:
    log = await _state.audit_log()
    return [_entry(e) for e in await log.recent(limit)]


def _columns() -> list[str]:
    assert _state.conn is not None
    return [row[1] for row in _state.conn.execute("PRAGMA table_info(audit)")]


# --- What confirmed each detection ---------------------------------------------------


def check(entity: Entity) -> dict[str, Any]:
    """The validation that turned a candidate into a detection, re-run on its value."""
    value, kind = entity.value, entity.type
    if kind is EntityType.IBAN:
        iban = compact(value)
        return {
            "rule": "iban_mod97",
            "ok": iban_is_valid(iban),
            "country": iban[:2],
            "length": len(iban),
            "registry_length": IBAN_LENGTHS.get(iban[:2]),
        }
    if kind is EntityType.CARD:
        digits = entity.canonical
        return {
            "rule": "card_luhn",
            "ok": luhn_is_valid(digits) and card_brand(digits) is not None,
            "brand": card_brand(digits),
            "length": len(digits),
        }
    if kind is EntityType.EMAIL:
        return {"rule": "email_rfc5321", "ok": email_is_valid(value)}
    if kind is EntityType.VAT_ID:
        return {
            "rule": "vat_vies_format",
            "ok": vat_is_well_formed(entity.canonical),
            "country": entity.canonical[:2],
        }
    if kind is EntityType.PHONE:
        number = phonenumbers.parse(entity.canonical)
        valid = phonenumbers.is_valid_number(number)
        line = phonenumbers.PhoneNumberType.to_string(phonenumbers.number_type(number))
        return {
            "rule": "phone_numbering_plan",
            "ok": valid or phonenumbers.is_possible_number(number),
            "valid": valid,  # False: possible only (international numbers)
            "region": phonenumbers.region_code_for_number(number),
            "line": line.lower(),
        }
    if kind is EntityType.IPV4:
        return {"rule": "ipv4_octets", "ok": ipv4_is_valid(value)}
    if kind is EntityType.DATE_OF_BIRTH:
        return {"rule": "birth_date", "ok": True, "date": entity.canonical}
    return {"rule": "names_list", "ok": True, "file": NAMES_FILE.name}


# --- Turning a request into what the page shows --------------------------------------


def _segments(segments: Sequence[Segment]) -> list[dict[str, Any]]:
    return [
        {"text": s.text, "kind": s.kind.value if s.kind else None, "token": s.token}
        for s in segments
    ]


def _original(prepared: Prepared) -> list[dict[str, Any]]:
    """The visitor's own text in pieces, each detection with its type and action."""
    text, found = prepared.original[0].content, prepared.entities[0]
    actions = {f.type: f.action.value for f in prepared.findings}
    pieces: list[dict[str, Any]] = []
    last = 0
    for e in found:
        if e.start > last:
            pieces.append({"text": text[last : e.start]})
        pieces.append(
            {
                "text": e.value,
                "kind": e.type.value,
                "action": actions[e.type],
                "token": prepared.vault.token_for(e),
            }
        )
        last = e.end
    if last < len(text):
        pieces.append({"text": text[last:]})
    return pieces


def _detections(prepared: Prepared, policy: Policy) -> list[dict[str, Any]]:
    return [
        {
            "type": e.type.value,
            "value": e.value,
            "action": policy.action_for(e.type).value,
            "placeholder": prepared.vault.token_for(e),
            "check": check(e),
        }
        for e in prepared.entities[0]
    ]


def _findings(prepared: Prepared) -> list[dict[str, Any]]:
    return [
        {"type": f.type.value, "action": f.action.value, "count": f.count, "distinct": f.distinct}
        for f in prepared.findings
    ]


# --- Entry points (called from the page) ---------------------------------------------


async def setup() -> dict[str, Any]:
    """Everything the page needs before the first request."""
    await _state.audit_log()
    return {
        "policy": _policy_dict(load_policy(POLICY_FILE)),
        "types": [t.value for t in EntityType],
        "actions": [a.value for a in Action],
        "names": load_names(NAMES_FILE),
        "phone_regions": list(PHONE_REGIONS),
        "samples": [{"id": s.id, "label": s.label, "text": s.text} for s in SAMPLES],
        "model": DemoLLM.name,
        "disclaimer": DISCLAIMER,
        "audit_columns": _columns(),
        "max_chars": MAX_INPUT_CHARS,
    }


async def run(text: str, rules: dict[str, str] | None = None) -> dict[str, Any]:
    """One chat request through the gateway, as POST /v1/chat would run it."""
    if not text.strip():
        return {"decision": "empty", "audit": await _recent()}
    if len(text) > MAX_INPUT_CHARS:
        return {"decision": "too_long", "max_chars": MAX_INPUT_CHARS, "audit": await _recent()}
    try:
        policy = _policy(rules)
    except PolicyError as exc:
        return {"decision": "bad_policy", "error": str(exc), "audit": await _recent()}

    llm = RecordingDemoLLM()
    gateway = Gateway(Guard(_state.detector, policy), llm, await _state.audit_log())
    blocked: Prepared | None = None
    try:
        result = await gateway.chat([Message("user", text)], source=SOURCE)
    except BlockedError as exc:
        blocked = exc.prepared
    except LeakCheckError:
        return {"decision": "error", "llm_called": False, "audit": await _recent()}

    prepared = blocked if blocked is not None else result.prepared
    out: dict[str, Any] = {
        "decision": prepared.decision,
        "policy": _policy_dict(policy),
        "detections": _detections(prepared, policy),
        "original": _original(prepared),
        "findings": _findings(prepared),
        "blocked_types": [f.type.value for f in prepared.findings if f.action is Action.BLOCK],
        "llm_called": llm.received is not None,
        "model": llm.name,
    }
    if blocked is None:
        sent = [m.content for m in llm.received or []]
        out |= {
            "system_prompt_chars": len(llm.system or ""),
            "system_prompt_is_fixed": llm.system == SYSTEM_PROMPT,
            "sent": [_segments(placeholder_segments(content)) for content in sent],
            "llm_answer": result.llm_answer,
            "answer": _segments(result.answer_segments),
            "unknown_placeholders": result.unknown_placeholders,
            "latency_ms": result.latency_ms,
            "placeholders": len(prepared.vault),
            # Recounted here on what the model actually received, independently of the
            # Guard's own leak check: how many masked values are still in it (must be 0).
            "values_in_request": sum(
                contains_value(content, value)
                for content in sent
                for value in prepared.vault.originals
            ),
        }
    out["audit"] = await _recent()
    return out


async def audit(limit: int = 8) -> list[dict[str, Any]]:
    return await _recent(max(1, min(int(limit), 50)))


async def reset() -> list[dict[str, Any]]:
    """A new, empty audit log (the page's Replay button)."""
    if _state.audit is not None:
        await _state.audit.close()
    _state.audit = _state.conn = None
    return await _recent()
