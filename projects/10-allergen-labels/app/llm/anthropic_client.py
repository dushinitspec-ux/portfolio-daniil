"""AI suggestions from Claude via the official Anthropic SDK."""

import anthropic
from pydantic import ValidationError

from app.llm.base import (
    SUGGESTION_SCHEMA,
    LLMError,
    Suggestion,
    SuggestionList,
    build_system_prompt,
    build_user_prompt,
)

# If the model declines for policy reasons, let the API retry on its recommended
# fallback model instead of returning the refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicSuggester:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str, effort: str) -> None:
        self._client = client
        self._model = model
        self._effort = effort

    @property
    def enabled(self) -> bool:
        return True

    @property
    def model(self) -> str:
        return self._model

    async def suggest(self, dish: str, ingredients: list[str]) -> list[Suggestion]:
        if not ingredients:
            return []
        try:
            response = await self._client.beta.messages.create(
                model=self._model,
                max_tokens=16000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                output_config={  # type: ignore[arg-type]
                    "effort": self._effort,
                    "format": {"type": "json_schema", "schema": SUGGESTION_SCHEMA},
                },
                system=build_system_prompt(),
                messages=[{"role": "user", "content": build_user_prompt(dish, ingredients)}],
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
        try:
            return SuggestionList.model_validate_json(text).items
        except ValidationError as exc:
            raise LLMError(f"unexpected reply format: {exc}") from exc
