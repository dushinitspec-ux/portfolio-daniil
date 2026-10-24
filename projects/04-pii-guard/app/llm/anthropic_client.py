"""Claude via the official Anthropic SDK. It only ever receives masked text."""

from collections.abc import Sequence

import anthropic

from app.guard import Message
from app.llm.base import LLMError

# If the model declines for policy reasons, let the API retry on its recommended
# fallback model instead of returning the refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicLLM:
    def __init__(
        self, client: anthropic.AsyncAnthropic, model: str, effort: str, max_tokens: int
    ) -> None:
        self._client = client
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens
        self.name = model

    async def complete(self, system: str, messages: Sequence[Message]) -> str:
        try:
            response = await self._client.beta.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                output_config={"effort": self._effort},  # type: ignore[typeddict-item]
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
        except anthropic.APIConnectionError as exc:
            raise LLMError("could not reach the Anthropic API") from exc
        except anthropic.APIStatusError as exc:
            # Only the status and the error type: the message text is not needed here.
            raise LLMError(f"Anthropic API error {exc.status_code}") from exc

        if response.stop_reason == "refusal":
            raise LLMError("the model declined to answer")
        if response.stop_reason == "max_tokens":
            raise LLMError("the answer was cut off by max_tokens")
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text:
            raise LLMError("the answer has no text")
        return text
