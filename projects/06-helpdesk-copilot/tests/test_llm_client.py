"""The Claude client against a fake HTTP server: what we send and how we parse the reply."""

import json
from typing import Any

import anthropic
import httpx2
import pytest

from app.citations import number_sources
from app.knowledge import Document
from app.llm import LLMError
from app.llm.anthropic_client import FALLBACK_BETA, ClaudeLLM
from app.triage import Category, Priority


class FakeServer:
    def __init__(self, status: int, body: dict[str, object]) -> None:
        self.status = status
        self.body = body
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(self.status, json=self.body)

    @property
    def last_json(self) -> dict[str, object]:
        return json.loads(self.requests[-1].content)


def message(text: str, stop_reason: str = "end_turn") -> dict[str, object]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 900, "output_tokens": 60},
    }


def make_client(server: FakeServer) -> ClaudeLLM:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server)),
    )
    return ClaudeLLM(client, "claude-opus-5-5", "medium", "low", "Sample Office")


async def test_answer_request_and_reply(documents: list[Document]) -> None:
    vpn = next(d for d in documents if d.id == "vpn")
    sources = number_sources(list(vpn.sections[:2]))
    reply = {"answered": True, "answer": "Öffnen Sie WireGuard [2]."}
    server = FakeServer(200, message(json.dumps(reply)))

    draft = await make_client(server).answer("Wie verbinde ich das VPN?", sources)

    assert draft.answered and draft.answer == "Öffnen Sie WireGuard [2]."
    body = server.last_json
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert FALLBACK_BETA in server.requests[-1].headers["anthropic-beta"]
    output_config: dict[str, Any] = body["output_config"]  # type: ignore[assignment]
    assert output_config["effort"] == "medium"
    assert output_config["format"]["type"] == "json_schema"
    assert output_config["format"]["schema"]["required"] == ["answered", "answer"]
    assert "thinking" not in body  # Opus 5.5 always thinks; effort is the only control
    assert "Sample Office" in str(body["system"])
    prompt = body["messages"][0]["content"]  # type: ignore[index]
    assert "[1] VPN for remote work" in prompt
    assert "[2] VPN for remote work › Install the VPN client" in prompt
    assert "<question>\nWie verbinde ich das VPN?\n</question>" in prompt


async def test_triage_uses_low_effort_and_an_enum_schema() -> None:
    reply = {"category": "security", "priority": "P1", "summary": "Phishing link", "reason": "x"}
    server = FakeServer(200, message(json.dumps(reply)))

    triage = await make_client(server).triage("I clicked a phishing link")

    assert (triage.category, triage.priority, triage.by) == (
        Category.SECURITY,
        Priority.P1,
        "llm",
    )
    output_config = server.last_json["output_config"]
    assert output_config["effort"] == "low"  # type: ignore[index]
    schema = output_config["format"]["schema"]  # type: ignore[index]
    assert schema["properties"]["priority"]["enum"] == ["P1", "P2", "P3", "P4"]


@pytest.mark.parametrize(
    ("status", "body", "match"),
    [
        (200, message("", stop_reason="refusal"), "declined"),
        (200, message('{"answered": tr', stop_reason="max_tokens"), "max_tokens"),
        (200, message("not json"), "unexpected reply"),
        (500, {"type": "error", "error": {"type": "api_error", "message": "boom"}}, "API error"),
    ],
)
async def test_failures_become_llm_errors(
    status: int, body: dict[str, object], match: str, documents: list[Document]
) -> None:
    sources = number_sources([documents[0].sections[0]])
    with pytest.raises(LLMError, match=match):
        await make_client(FakeServer(status, body)).answer("?", sources)
