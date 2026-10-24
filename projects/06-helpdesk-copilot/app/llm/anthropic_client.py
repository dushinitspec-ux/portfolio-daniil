"""Claude via the official Anthropic SDK, with structured (JSON schema) output."""

import logging

import anthropic
from pydantic import BaseModel, ValidationError

from app.citations import Source
from app.llm.base import (
    AnswerDraft,
    LLMError,
    TriageDraft,
    answer_messages,
    triage_messages,
)
from app.triage import Category, Priority, Triage

logger = logging.getLogger(__name__)

# The API guarantees replies that match these schemas.
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answered": {"type": "boolean"},
        "answer": {"type": "string"},
    },
    "required": ["answered", "answer"],
    "additionalProperties": False,
}

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": [c.value for c in Category]},
        "priority": {"type": "string", "enum": [p.value for p in Priority]},
        "summary": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["category", "priority", "summary", "reason"],
    "additionalProperties": False,
}

# If the model declines for policy reasons, let the API retry on its recommended
# fallback model instead of returning the refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeLLM:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        model: str,
        effort: str,
        triage_effort: str,
        company: str,
    ) -> None:
        self._client = client
        self._model = model
        self._effort = effort
        self._triage_effort = triage_effort
        self._company = company
        self.name = f"Anthropic {model}"

    async def _json(self, system: str, prompt: str, schema: dict[str, object], effort: str) -> str:
        try:
            response = await self._client.beta.messages.create(
                model=self._model,
                max_tokens=16000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                output_config={  # type: ignore[arg-type]
                    "effort": effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                system=system,
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

    @staticmethod
    def _parse[T: BaseModel](model: type[T], text: str) -> T:
        try:
            return model.model_validate_json(text)
        except ValidationError as exc:
            raise LLMError(f"unexpected reply format: {exc}") from exc

    async def answer(self, question: str, sources: list[Source]) -> AnswerDraft:
        system, prompt = answer_messages(self._company, question, sources)
        text = await self._json(system, prompt, ANSWER_SCHEMA, self._effort)
        return self._parse(AnswerDraft, text)

    async def triage(self, text: str) -> Triage:
        system, prompt = triage_messages(self._company, text)
        reply = await self._json(system, prompt, TRIAGE_SCHEMA, self._triage_effort)
        draft = self._parse(TriageDraft, reply)
        summary = " ".join(draft.summary.split())[:120]
        return Triage(draft.category, draft.priority, summary, draft.reason, by="llm")
