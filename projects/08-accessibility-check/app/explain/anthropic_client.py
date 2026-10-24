"""Claude writes the shop-owner summary, via the official Anthropic SDK."""

import logging

import anthropic
from pydantic import BaseModel, ValidationError

from app.explain.base import (
    LANGUAGES,
    LIMITS_NOTE,
    SYSTEM_PROMPT,
    ExplainError,
    build_user_prompt,
)
from app.models import Action, Explanation, ScanReport

logger = logging.getLogger(__name__)

# Structured output: the API guarantees the reply is JSON matching this schema.
EXPLANATION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "why": {"type": "string"},
                    "how": {"type": "string"},
                },
                "required": ["title", "why", "how"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "actions"],
    "additionalProperties": False,
}

# If the model declines for policy reasons, the API retries on its recommended fallback
# model inside the same call instead of returning the refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_ACTIONS = 6


class _Reply(BaseModel):
    summary: str
    actions: list[Action]


class ClaudeExplainer:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str, effort: str) -> None:
        self._client = client
        self._model = model
        self._effort = effort

    async def explain(self, report: ScanReport, language: str = "en") -> Explanation:
        try:
            response = await self._client.beta.messages.create(
                model=self._model,
                max_tokens=16000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                output_config={  # type: ignore[arg-type]
                    "effort": self._effort,
                    "format": {"type": "json_schema", "schema": EXPLANATION_SCHEMA},
                },
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(report, language)}],
            )
        except anthropic.APIError as exc:
            raise ExplainError(f"Anthropic API error: {exc}") from exc

        if response.stop_reason == "refusal":
            raise ExplainError("the model declined to write the summary")
        if response.stop_reason == "max_tokens":
            raise ExplainError("the reply was cut off by max_tokens")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise ExplainError("the reply has no text")
        try:
            reply = _Reply.model_validate_json(text)
        except ValidationError as exc:
            raise ExplainError(f"unexpected reply format: {exc}") from exc
        logger.info("Explanation written by %s", response.model)
        return Explanation(
            summary=reply.summary,
            actions=reply.actions[:MAX_ACTIONS],
            language=LANGUAGES.get(language, "English"),
            source=f"Claude ({response.model})",
            note=LIMITS_NOTE,
        )
