"""The adapter behind the in-browser demo (app/web_demo.py), run here on CPython."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app import web_demo
from tests.conftest import CARD, EMAIL, IBAN, PHONE, ROOT, VAT

NAME = "Anna Schmidt"
MESSAGE = (
    f"Hello, this is {NAME} from Muster GmbH. We were charged twice for invoice 2026-114 on "
    f"the card {CARD}. Please refund the extra payment to our account {IBAN} and send the "
    f"corrected invoice with our VAT ID {VAT} to {EMAIL}. If you have questions, call me at "
    f"{PHONE}."
)
MASKED_VALUES = (NAME, CARD, IBAN, EMAIL, PHONE)
ALL_MASK = {
    "EMAIL": "mask",
    "PHONE": "mask",
    "IBAN": "mask",
    "CARD": "mask",
    "VAT_ID": "allow",
    "IPV4": "mask",
    "DATE_OF_BIRTH": "mask",
    "NAME": "mask",
}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets its own detector and an empty in-memory audit log."""
    monkeypatch.setattr(web_demo, "_state", web_demo._State())


def text_of(segments: list[dict[str, object]]) -> str:
    return "".join(str(s["text"]) for s in segments)


async def test_setup_reads_the_real_policy_and_names() -> None:
    setup = await web_demo.setup()
    assert setup["policy"]["CARD"] == "block"
    assert setup["policy"]["VAT_ID"] == "allow"
    assert setup["policy"]["IBAN"] == "mask"
    assert "Anna Schmidt" in setup["names"]
    assert [s["id"] for s in setup["samples"]] == ["refund", "onboarding", "server-log", "card"]
    # The audit table has no column that could hold a value or a prompt.
    assert setup["audit_columns"] == [
        "id",
        "ts",
        "source",
        "decision",
        "entities",
        "messages",
        "model",
        "latency_ms",
    ]
    json.dumps(setup)


async def test_masked_round_trip_never_shows_the_model_a_value() -> None:
    result = await web_demo.run(MESSAGE, ALL_MASK)

    assert result["decision"] == "masked"
    assert result["llm_called"] is True
    assert result["system_prompt_is_fixed"] is True
    sent = text_of(result["sent"][0])
    for value in MASKED_VALUES:
        assert value not in sent
        assert value not in result["llm_answer"]
        assert value in text_of(result["answer"])  # restored for the user
    assert VAT in sent  # the policy allows VAT IDs
    assert result["values_in_request"] == 0
    assert result["placeholders"] == 5
    assert result["unknown_placeholders"] == []
    assert {s["token"] for s in result["sent"][0] if s["token"]} == {
        "<NAME_1>",
        "<CARD_1>",
        "<IBAN_1>",
        "<EMAIL_1>",
        "<PHONE_1>",
    }
    json.dumps(result)


async def test_each_detection_says_which_check_confirmed_it() -> None:
    result = await web_demo.run(MESSAGE, ALL_MASK)
    checks = {d["type"]: d["check"] for d in result["detections"]}

    assert set(checks) == {"NAME", "CARD", "IBAN", "VAT_ID", "EMAIL", "PHONE"}
    assert all(c["ok"] for c in checks.values())
    assert checks["IBAN"] == {
        "rule": "iban_mod97",
        "ok": True,
        "country": "DE",
        "length": 22,
        "registry_length": 22,
    }
    assert checks["CARD"] == {"rule": "card_luhn", "ok": True, "brand": "visa", "length": 16}
    assert checks["PHONE"]["region"] == "DE"
    assert checks["PHONE"]["valid"] is True
    assert checks["VAT_ID"]["rule"] == "vat_vies_format"
    assert checks["NAME"] == {"rule": "names_list", "ok": True, "file": "names.demo.txt"}
    placeholders = {d["type"]: d["placeholder"] for d in result["detections"]}
    assert placeholders["IBAN"] == "<IBAN_1>"
    assert placeholders["VAT_ID"] is None  # allowed: sent as it is


async def test_original_pieces_rebuild_the_text_with_actions() -> None:
    result = await web_demo.run(MESSAGE, ALL_MASK)
    assert text_of(result["original"]) == MESSAGE
    marked = {p["kind"]: p["action"] for p in result["original"] if p.get("kind")}
    assert marked["VAT_ID"] == "allow"
    assert marked["CARD"] == "mask"


async def test_blocked_card_never_reaches_the_model_and_audit_has_no_values() -> None:
    await web_demo.run(MESSAGE, ALL_MASK)
    result = await web_demo.run(MESSAGE, {**ALL_MASK, "CARD": "block"})

    assert result["decision"] == "blocked"
    assert result["blocked_types"] == ["CARD"]
    assert result["llm_called"] is False
    assert "sent" not in result
    assert "answer" not in result

    blocked, masked = result["audit"]  # newest first
    assert blocked["decision"] == "blocked"
    assert masked["decision"] == "masked"
    assert blocked["entities"]["CARD"] == {"count": 1, "distinct": 1, "action": "block"}
    assert blocked["latency_ms"] is None
    stored = json.dumps(result["audit"])
    for value in (*MASKED_VALUES, VAT, "4111", "Muster"):
        assert value not in stored


async def test_the_default_policy_comes_from_policy_yaml() -> None:
    result = await web_demo.run(MESSAGE)  # no toggles: policy.yaml blocks cards
    assert result["decision"] == "blocked"


async def test_rejected_input_is_reported_not_raised() -> None:
    assert (await web_demo.run("   ", ALL_MASK))["decision"] == "empty"
    too_long = await web_demo.run("x" * (web_demo.MAX_INPUT_CHARS + 1), ALL_MASK)
    assert too_long["decision"] == "too_long"
    bad = await web_demo.run("hello", {"CARD": "shred"})
    assert bad["decision"] == "bad_policy"
    assert "shred" in bad["error"]
    assert await web_demo.audit() == []  # none of them was audited


async def test_text_without_personal_data_passes() -> None:
    result = await web_demo.run("What is the capital of Austria?", ALL_MASK)
    assert result["decision"] == "passed"
    assert result["detections"] == []
    assert text_of(result["sent"][0]) == "What is the capital of Austria?"
    [entry] = await web_demo.audit()
    assert entry["decision"] == "passed"
    assert entry["summary"] == "none"


def test_the_adapter_imports_nothing_the_browser_lacks() -> None:
    code = (
        "import sys, app.web_demo\n"
        "bad = {'fastapi', 'uvicorn', 'aiosqlite', 'anthropic', 'pydantic_settings', 'httpx'}\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in bad))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"


def test_web_demo_json_lists_every_module_the_adapter_needs() -> None:
    config = json.loads((ROOT / "web_demo.json").read_text("utf-8"))
    code = (
        "import sys, app.web_demo\n"
        "print('\\n'.join(sorted(m.__file__ for m in list(sys.modules.values())"
        " if getattr(m, '__file__', None) and m.__name__.startswith('app'))))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    loaded = {Path(line).resolve().relative_to(ROOT).as_posix() for line in out.stdout.splitlines()}
    assert loaded <= set(config["files"])
    assert config["entry"] == "app.web_demo"


async def test_reset_starts_an_empty_audit_log() -> None:
    await web_demo.run(MESSAGE, ALL_MASK)
    assert len(await web_demo.audit()) == 1
    assert await web_demo.reset() == []
    assert await web_demo.audit() == []
    await web_demo.run(MESSAGE, ALL_MASK)
    assert len(await web_demo.audit()) == 1
