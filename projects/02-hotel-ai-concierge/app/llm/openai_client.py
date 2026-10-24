"""OpenAI models via the official OpenAI SDK (Responses API)."""

import openai

from app.language import Language
from app.llm.base import (
    TRANSLATE_PROMPT,
    ConciergeAnswer,
    LLMError,
    build_system_prompt,
    build_user_prompt,
)


class OpenAILLM:
    def __init__(self, client: openai.AsyncOpenAI, model: str, hotel: str) -> None:
        self._client = client
        self._model = model
        self._hotel = hotel

    async def answer(
        self, question: str, language: Language, knowledge: str, history: str
    ) -> ConciergeAnswer:
        try:
            response = await self._client.responses.parse(
                model=self._model,
                instructions=build_system_prompt(self._hotel, knowledge),
                input=build_user_prompt(question, language, history),
                text_format=ConciergeAnswer,
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        if response.output_parsed is None:
            raise LLMError("the model returned no structured answer")
        return response.output_parsed

    async def translate(self, text: str, target: Language) -> str:
        try:
            response = await self._client.responses.create(
                model=self._model,
                input=TRANSLATE_PROMPT.format(language=target.english_name, text=text),
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        return response.output_text.strip()
