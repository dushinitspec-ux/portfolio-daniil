"""Claude via the official Anthropic SDK."""

import logging

import anthropic
from pydantic import ValidationError

from app.language import Language
from app.llm.base import (
    TRANSLATE_PROMPT,
    ConciergeAnswer,
    LLMError,
    build_system_prompt,
    build_user_prompt,
)

logger = logging.getLogger(__name__)

# Structured output: the API guarantees the reply is JSON matching this schema.
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "found_in_knowledge_base": {"type": "boolean"},
        "answer": {"type": "string"},
        "question_in_english": {"type": "string"},
    },
    "required": ["found_in_knowledge_base", "answer", "question_in_english"],
    "additionalProperties": False,
}

# If the model declines for policy reasons, let the API retry on its recommended
# fallback model instead of returning the refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicLLM:
    def __init__(
        self, client: anthropic.AsyncAnthropic, model: str, effort: str, hotel: str
    ) -> None:
        self._client = client
        self._model = model
        self._effort = effort
        self._hotel = hotel

    async def _create(
        self,
        system: list[dict[str, object]] | None,
        prompt: str,
        output_format: dict[str, object] | None = None,
    ) -> str:
        output_config: dict[str, object] = {"effort": self._effort}
        if output_format:
            output_config["format"] = output_format
        try:
            response = await self._client.beta.messages.create(
                model=self._model,
                max_tokens=16000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                output_config=output_config,  # type: ignore[arg-type]
                system=system or anthropic.omit,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMError("the model declined to answer")
        if response.stop_reason == "max_tokens":
            raise LLMError("the reply was cut off by max_tokens")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise LLMError("the reply has no text")
        return text

    async def answer(
        self, question: str, language: Language, knowledge: str, history: str
    ) -> ConciergeAnswer:
        # The knowledge base is the large, stable part of every request: cache it.
        system = [
            {
                "type": "text",
                "text": build_system_prompt(self._hotel, knowledge),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        text = await self._create(
            system,
            build_user_prompt(question, language, history),
            {"type": "json_schema", "schema": ANSWER_SCHEMA},
        )
        try:
            return ConciergeAnswer.model_validate_json(text)
        except ValidationError as exc:
            raise LLMError(f"unexpected reply format: {exc}") from exc

    async def translate(self, text: str, target: Language) -> str:
        prompt = TRANSLATE_PROMPT.format(language=target.english_name, text=text)
        return (await self._create(None, prompt)).strip()
