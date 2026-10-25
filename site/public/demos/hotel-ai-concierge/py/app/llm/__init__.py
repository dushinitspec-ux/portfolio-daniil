"""LLM providers. The concierge only depends on the LLMClient protocol."""

from app.config import Provider, Settings
from app.llm.base import ConciergeAnswer, LLMClient, LLMError

__all__ = ["ConciergeAnswer", "LLMClient", "LLMError", "create_llm"]


def create_llm(settings: Settings) -> LLMClient:
    # Imports are local so the offline demo does not need provider SDKs configured.
    if settings.llm_provider is Provider.ANTHROPIC:
        import anthropic

        from app.llm.anthropic_client import AnthropicLLM

        return AnthropicLLM(
            anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None),
            settings.anthropic_model,
            settings.anthropic_effort,
            settings.hotel_name,
        )
    if settings.llm_provider is Provider.OPENAI:
        import openai

        from app.llm.openai_client import OpenAILLM

        return OpenAILLM(
            openai.AsyncOpenAI(api_key=settings.openai_api_key or None),
            settings.openai_model,
            settings.hotel_name,
        )

    from app.llm.mock import MockLLM

    return MockLLM()
