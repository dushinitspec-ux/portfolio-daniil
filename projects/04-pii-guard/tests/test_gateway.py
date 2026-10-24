import logging
from pathlib import Path

import pytest

from app.audit import AuditLog
from app.gateway import BlockedError, Gateway
from app.guard import Guard, Message
from app.llm import SYSTEM_PROMPT, LLMError
from tests.conftest import CARD, EMAIL, IBAN, PHONE, RecordingLLM

SECRETS = (IBAN, EMAIL, PHONE)
PROMPT = f"Refund to {IBAN}, confirm to {EMAIL}, or call {PHONE}."


async def test_the_llm_only_ever_sees_placeholders(gateway: Gateway, llm: RecordingLLM) -> None:
    result = await gateway.chat([Message("user", PROMPT)], source="api")

    system, sent = llm.calls[0]
    assert system == SYSTEM_PROMPT
    assert sent[0].content == "Refund to <IBAN_1>, confirm to <EMAIL_1>, or call <PHONE_1>."
    for value in SECRETS:
        assert value not in sent[0].content
        assert value not in result.llm_answer
        assert value in result.answer  # restored for the user
    assert result.unknown_placeholders == []


async def test_blocked_request_never_reaches_the_llm(
    gateway: Gateway, llm: RecordingLLM, audit: AuditLog
) -> None:
    with pytest.raises(BlockedError):
        await gateway.chat([Message("user", f"card {CARD}")], source="api")
    assert llm.calls == []
    [entry] = await audit.recent()
    assert entry.decision == "blocked"
    assert entry.entities == {"CARD": {"count": 1, "distinct": 1, "action": "block"}}


async def test_llm_failure_is_audited_and_raised(guard: Guard, audit: AuditLog) -> None:
    gateway = Gateway(guard, RecordingLLM(fail=True), audit)
    with pytest.raises(LLMError):
        await gateway.chat([Message("user", PROMPT)], source="web")
    [entry] = await audit.recent()
    assert (entry.decision, entry.source) == ("error", "web")


async def test_audit_log_has_counts_but_no_values(gateway: Gateway, audit: AuditLog) -> None:
    await gateway.chat([Message("user", PROMPT)], source="api")
    [entry] = await audit.recent()
    assert entry.decision == "masked"
    assert entry.model == "recording"
    assert entry.entities == {
        "EMAIL": {"count": 1, "distinct": 1, "action": "mask"},
        "IBAN": {"count": 1, "distinct": 1, "action": "mask"},
        "PHONE": {"count": 1, "distinct": 1, "action": "mask"},
    }


def read_all_files(folder: Path) -> bytes:
    """The database plus any journal file SQLite left next to it."""
    return b"".join(p.read_bytes() for p in folder.iterdir())


async def test_database_file_never_contains_a_value(guard: Guard, tmp_path: Path) -> None:
    audit = await AuditLog.connect(tmp_path / "audit.db")
    gateway = Gateway(guard, RecordingLLM(), audit)
    await gateway.chat([Message("user", PROMPT)], source="api")
    with pytest.raises(BlockedError):
        await gateway.chat([Message("user", f"{PROMPT} {CARD}")], source="api")
    await audit.close()

    raw = read_all_files(tmp_path)
    for value in (*SECRETS, CARD, "Refund to"):
        assert value.encode() not in raw


async def test_logs_never_contain_a_value(
    gateway: Gateway, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await gateway.chat([Message("user", PROMPT)], source="api")
        with pytest.raises(BlockedError):
            await gateway.chat([Message("user", f"card {CARD}")], source="api")
    assert "EMAIL:1:mask" in caplog.text  # types and counts are logged ...
    for value in (*SECRETS, CARD):
        assert value not in caplog.text  # ... values are not
