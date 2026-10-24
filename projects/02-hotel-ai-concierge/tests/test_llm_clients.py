"""Provider clients against a fake HTTP server: checks what we send and how we parse it."""

import json

import anthropic
import httpx2
import openai
import pytest

from app.language import Language
from app.llm import LLMError
from app.llm.anthropic_client import FALLBACK_BETA, AnthropicLLM
from app.llm.openai_client import OpenAILLM

ANSWER = {
    "found_in_knowledge_base": True,
    "answer": "Завтрак с 07:00 до 10:00.",
    "question_in_english": "When is breakfast?",
}


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


def anthropic_message(text: str, stop_reason: str = "end_turn") -> dict[str, object]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1200, "output_tokens": 40},
    }


def make_anthropic(server: FakeServer) -> AnthropicLLM:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server)),
    )
    return AnthropicLLM(client, "claude-opus-5-5", "medium", "Test Hotel")


async def test_anthropic_request_and_answer() -> None:
    server = FakeServer(200, anthropic_message(json.dumps(ANSWER)))
    result = await make_anthropic(server).answer(
        "Во сколько завтрак?", Language.RU, "## Breakfast\n07:00-10:00", ""
    )

    assert result.answer == "Завтрак с 07:00 до 10:00."
    body = server.last_json
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert FALLBACK_BETA in server.requests[-1].headers["anthropic-beta"]
    assert body["output_config"]["effort"] == "medium"  # type: ignore[index]
    assert body["output_config"]["format"]["type"] == "json_schema"  # type: ignore[index]
    system = body["system"][0]  # type: ignore[index]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "07:00-10:00" in system["text"]  # the knowledge base is in the cached system block
    assert "Answer language: Russian" in body["messages"][0]["content"]  # type: ignore[index]


async def test_anthropic_refusal_becomes_llm_error() -> None:
    server = FakeServer(200, anthropic_message("", stop_reason="refusal"))
    with pytest.raises(LLMError, match="declined"):
        await make_anthropic(server).answer("?", Language.EN, "## A\nb", "")


async def test_anthropic_server_error_becomes_llm_error() -> None:
    server = FakeServer(500, {"type": "error", "error": {"type": "api_error", "message": "boom"}})
    with pytest.raises(LLMError):
        await make_anthropic(server).answer("?", Language.EN, "## A\nb", "")


async def test_anthropic_translate_has_no_schema() -> None:
    server = FakeServer(200, anthropic_message("Да, закажите за день."))
    text = await make_anthropic(server).translate("Yes, order a day before.", Language.RU)
    assert text == "Да, закажите за день."
    assert "format" not in server.last_json["output_config"]  # type: ignore[operator]
    assert "system" not in server.last_json


def openai_response(text: str) -> dict[str, object]:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "model": "gpt-5-mini",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_test",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }


def make_openai(server: FakeServer) -> OpenAILLM:
    client = openai.AsyncOpenAI(
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server)),
    )
    return OpenAILLM(client, "gpt-5-mini", "Test Hotel")


async def test_openai_request_and_answer() -> None:
    server = FakeServer(200, openai_response(json.dumps(ANSWER)))
    result = await make_openai(server).answer("Во сколько завтрак?", Language.RU, "## B\nx", "")

    assert result.found_in_knowledge_base
    assert result.question_in_english == "When is breakfast?"
    body = server.last_json
    assert body["model"] == "gpt-5-mini"
    assert body["text"]["format"]["type"] == "json_schema"  # type: ignore[index]
    assert "## B" in str(body["instructions"])


async def test_openai_error_becomes_llm_error() -> None:
    server = FakeServer(429, {"error": {"message": "rate limited", "type": "rate_limit"}})
    with pytest.raises(LLMError):
        await make_openai(server).answer("?", Language.EN, "## A\nb", "")
