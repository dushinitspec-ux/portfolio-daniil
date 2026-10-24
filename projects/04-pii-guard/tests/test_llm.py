"""The Claude client against a fake HTTP server, and the offline demo model."""

import json

import anthropic
import httpx2
import pytest

from app.config import Settings
from app.guard import Message
from app.llm import SYSTEM_PROMPT, LLMError, create_llm
from app.llm.anthropic_client import FALLBACK_BETA, AnthropicLLM
from app.llm.demo import DISCLAIMER, DemoLLM, quote_sentence


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
        "usage": {"input_tokens": 300, "output_tokens": 20},
    }


def make_llm(server: FakeServer) -> AnthropicLLM:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server)),
    )
    return AnthropicLLM(client, "claude-opus-5-5", "medium", 16000)


MASKED = [Message("user", "Refund <IBAN_1> and confirm to <EMAIL_1>.")]


async def test_request_contains_only_the_masked_conversation() -> None:
    server = FakeServer(200, message("Done. Confirmation goes to <EMAIL_1>."))
    answer = await make_llm(server).complete(SYSTEM_PROMPT, MASKED)

    assert answer == "Done. Confirmation goes to <EMAIL_1>."
    body = server.last_json
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == 16000
    assert body["system"] == SYSTEM_PROMPT
    assert body["messages"] == [
        {"role": "user", "content": "Refund <IBAN_1> and confirm to <EMAIL_1>."}
    ]
    assert body["output_config"] == {"effort": "medium"}
    assert body["fallbacks"] == "default"
    assert FALLBACK_BETA in server.requests[-1].headers["anthropic-beta"]


async def test_refusal_becomes_llm_error() -> None:
    server = FakeServer(200, message("", stop_reason="refusal"))
    with pytest.raises(LLMError, match="declined"):
        await make_llm(server).complete(SYSTEM_PROMPT, MASKED)


async def test_cut_off_answer_becomes_llm_error() -> None:
    server = FakeServer(200, message("Done. Confir", stop_reason="max_tokens"))
    with pytest.raises(LLMError, match="max_tokens"):
        await make_llm(server).complete(SYSTEM_PROMPT, MASKED)


async def test_server_error_becomes_llm_error() -> None:
    server = FakeServer(500, {"type": "error", "error": {"type": "api_error", "message": "x"}})
    with pytest.raises(LLMError, match="500"):
        await make_llm(server).complete(SYSTEM_PROMPT, MASKED)


def test_demo_mode_needs_no_key() -> None:
    assert isinstance(create_llm(Settings(demo_mode=True, anthropic_api_key="")), DemoLLM)
    assert isinstance(create_llm(Settings(demo_mode=False, anthropic_api_key="k")), AnthropicLLM)


async def test_demo_model_is_deterministic_and_uses_every_placeholder() -> None:
    conversation = [Message("user", "Hi, I am <NAME_1>. Refund <IBAN_1>, mail <EMAIL_1>.")]
    first = await DemoLLM().complete(SYSTEM_PROMPT, conversation)
    second = await DemoLLM().complete(SYSTEM_PROMPT, conversation)

    assert first == second
    assert first.startswith(DISCLAIMER)
    assert 'From your message: "Hi, I am <NAME_1>."' in first
    assert "Dear <NAME_1>," in first  # the same placeholder twice in one answer
    assert "The refund will be paid to the account <IBAN_1>." in first
    assert "We will send the confirmation to <EMAIL_1>." in first


async def test_demo_model_without_placeholders() -> None:
    answer = await DemoLLM().complete(SYSTEM_PROMPT, [Message("user", "What is GDPR?")])
    assert 'From your message: "What is GDPR?"' in answer
    assert "nothing to mask" in answer


def test_quote_prefers_a_sentence_with_a_placeholder_and_is_short() -> None:
    assert quote_sentence("Write a reply. I am <NAME_1>. Thanks.") == "I am <NAME_1>."
    long = quote_sentence("word " * 100)
    assert len(long) == 160 and long.endswith("…")
