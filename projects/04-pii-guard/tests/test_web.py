from collections.abc import AsyncIterator

import httpx
import pytest

from app.audit import AuditLog
from app.gateway import Gateway
from app.guard import Guard
from app.web import create_app
from tests.conftest import CARD, EMAIL, IBAN, VAT, RecordingLLM

PROMPT = f"Please refund {IBAN} and write to {EMAIL}. VAT {VAT}."


def make_client(gateway: Gateway, max_chars: int = 20000) -> httpx.AsyncClient:
    app = create_app(gateway, max_chars, demo=True)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(gateway: Gateway) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(gateway) as c:
        yield c


def chat(content: str) -> dict[str, object]:
    return {"messages": [{"role": "user", "content": content}]}


async def test_chat_masks_calls_and_restores(client: httpx.AsyncClient) -> None:
    resp = await client.post("/v1/chat", json=chat(PROMPT))
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "masked"
    assert data["sent_to_llm"] == [
        {"role": "user", "content": f"Please refund <IBAN_1> and write to <EMAIL_1>. VAT {VAT}."}
    ]
    assert IBAN in data["answer"] and EMAIL in data["answer"]
    assert "<IBAN_1>" in data["llm_answer"]
    assert {e["type"]: (e["count"], e["action"]) for e in data["entities"]} == {
        "IBAN": (1, "mask"),
        "EMAIL": (1, "mask"),
        "VAT_ID": (1, "allow"),
    }
    assert data["model"] == "recording"


async def test_chat_blocked_by_policy(client: httpx.AsyncClient, llm: RecordingLLM) -> None:
    resp = await client.post("/v1/chat", json=chat(f"card {CARD}"))
    assert resp.status_code == 422
    assert resp.json()["error"] == "blocked_by_policy"
    assert CARD not in resp.text
    assert llm.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"messages": []},
        {"messages": [{"role": "assistant", "content": "Hi"}]},
        {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Yo"}]},
        {"messages": [{"role": "system", "content": "Hi"}]},
    ],
)
async def test_chat_validation(client: httpx.AsyncClient, body: dict[str, object]) -> None:
    assert (await client.post("/v1/chat", json=body)).status_code == 422


async def test_chat_too_long(gateway: Gateway) -> None:
    async with make_client(gateway, max_chars=100) as client:
        resp = await client.post("/v1/chat", json=chat("x" * 101))
    assert resp.status_code == 413


async def test_chat_llm_error_is_502(guard: Guard, audit: AuditLog) -> None:
    async with make_client(Gateway(guard, RecordingLLM(fail=True), audit)) as client:
        resp = await client.post("/v1/chat", json=chat(PROMPT))
    assert resp.status_code == 502
    assert resp.json()["error"] == "llm_error"


async def test_mask_endpoint_is_a_dry_run(client: httpx.AsyncClient, llm: RecordingLLM) -> None:
    data = (await client.post("/v1/mask", json={"text": f"mail {EMAIL}"})).json()
    assert data == {
        "decision": "masked",
        "masked": "mail <EMAIL_1>",
        "entities": [{"type": "EMAIL", "action": "mask", "count": 1, "distinct": 1}],
    }
    assert llm.calls == []
    assert (await client.get("/v1/audit")).json() == []  # nothing was sent, nothing logged


async def test_audit_endpoint(client: httpx.AsyncClient) -> None:
    await client.post("/v1/chat", json=chat(PROMPT))
    await client.post("/v1/chat", json=chat(f"card {CARD}"))
    entries = (await client.get("/v1/audit")).json()
    assert [e["decision"] for e in entries] == ["blocked", "masked"]  # newest first
    for value in (IBAN, EMAIL, CARD):
        assert value not in str(entries)


async def test_page_without_a_sample_shows_the_form(client: httpx.AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Send through PII Guard" in resp.text
    assert "htmx.org" in resp.text
    assert "demo model" in resp.text
    assert "No requests yet." in resp.text


async def test_page_with_a_sample_shows_three_columns(client: httpx.AsyncClient) -> None:
    html = (await client.get("/?sample=refund")).text
    assert "Original" in html and "Sent to the model" in html and "Answer" in html
    assert '<span class="ph">&lt;IBAN_1&gt;</span>' in html  # placeholders are escaped
    assert 'title="IBAN: mask → &lt;IBAN_1&gt;"' in html


async def test_card_sample_shows_the_block(client: httpx.AsyncClient) -> None:
    html = (await client.get("/?sample=card")).text
    assert "Request refused" in html
    assert "Sent to the model" not in html


async def test_htmx_partial_updates_the_audit_log_too(client: httpx.AsyncClient) -> None:
    resp = await client.post("/ui/run", data={"text": PROMPT})
    assert "<html" not in resp.text
    assert 'id="audit" hx-swap-oob="true"' in resp.text
    assert "IBAN ×1" in resp.text


async def test_form_works_without_javascript(client: httpx.AsyncClient) -> None:
    resp = await client.post("/", data={"text": f"<b>{EMAIL}</b>"})
    assert resp.status_code == 200
    assert "<!doctype html>" in resp.text
    assert "&lt;b&gt;" in resp.text  # user input is escaped, never rendered as HTML
    assert "<b>" not in resp.text


async def test_healthz(client: httpx.AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
