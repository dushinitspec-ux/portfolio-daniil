"""The Anthropic client against a fake HTTP server: what we send and how we parse it."""

import json

import anthropic
import httpx2
import pytest

from app.allergens import ALLERGEN_IDS
from app.config import Settings
from app.llm import LLMError, OfflineSuggester, create_suggester
from app.llm.anthropic_client import FALLBACK_BETA, AnthropicSuggester


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


def make(server: FakeServer) -> AnthropicSuggester:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server)),
    )
    return AnthropicSuggester(client, "claude-opus-5-5", "medium")


ANSWER = {
    "items": [
        {"ingredient": "guanciale", "allergens": [], "reason": "Cured pork cheek, salt, pepper."},
        {"ingredient": "fıstık", "allergens": ["nuts"], "reason": "In baklava: pistachios."},
    ]
}


async def test_request_shape_and_parsed_answer() -> None:
    server = FakeServer(200, message(json.dumps(ANSWER)))
    result = await make(server).suggest("Baklava", ["guanciale", "fıstık"])

    assert [s.allergens for s in result] == [[], ["nuts"]]
    body = server.last_json
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert FALLBACK_BETA in server.requests[-1].headers["anthropic-beta"]
    output = body["output_config"]
    assert output["effort"] == "medium"  # type: ignore[index]
    schema = output["format"]["schema"]  # type: ignore[index]
    item = schema["properties"]["items"]["items"]
    assert item["properties"]["allergens"]["items"]["enum"] == list(ALLERGEN_IDS)
    assert "Annex II" in str(body["system"])
    assert "pine nuts" in str(body["system"])  # tells the model what is NOT in Annex II
    user = body["messages"][0]["content"]  # type: ignore[index]
    assert "<dish>Baklava</dish>" in user
    assert "- fıstık" in user


async def test_refusal_becomes_llm_error() -> None:
    server = FakeServer(200, message("", stop_reason="refusal"))
    with pytest.raises(LLMError, match="declined"):
        await make(server).suggest("", ["x"])


async def test_server_error_becomes_llm_error() -> None:
    server = FakeServer(500, {"type": "error", "error": {"type": "api_error", "message": "x"}})
    with pytest.raises(LLMError):
        await make(server).suggest("", ["x"])


async def test_bad_json_becomes_llm_error() -> None:
    server = FakeServer(200, message('{"items": [{"ingredient": "x"}]}'))
    with pytest.raises(LLMError, match="format"):
        await make(server).suggest("", ["x"])


async def test_no_call_for_an_empty_list() -> None:
    server = FakeServer(200, message(json.dumps(ANSWER)))
    assert await make(server).suggest("", []) == []
    assert server.requests == []


def test_no_key_means_offline() -> None:
    assert isinstance(create_suggester(Settings(anthropic_api_key="")), OfflineSuggester)
    off = Settings(anthropic_api_key="sk-test", ai_suggestions=False)
    assert isinstance(create_suggester(off), OfflineSuggester)
    on = create_suggester(Settings(anthropic_api_key="sk-test"))
    assert isinstance(on, AnthropicSuggester)
    assert on.model == "claude-opus-5-5"
