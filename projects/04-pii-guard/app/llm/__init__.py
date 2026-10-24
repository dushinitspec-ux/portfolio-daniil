"""LLM backends. The gateway only depends on the LLMClient protocol."""

from app.config import Settings
from app.llm.base import SYSTEM_PROMPT, LLMClient, LLMError

__all__ = ["SYSTEM_PROMPT", "LLMClient", "LLMError", "create_llm"]


def create_llm(settings: Settings) -> LLMClient:
    if settings.demo_mode:
        from app.llm.demo import DemoLLM

        return DemoLLM()

    import anthropic

    from app.llm.anthropic_client import AnthropicLLM

    return AnthropicLLM(
        anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None),
        settings.anthropic_model,
        settings.anthropic_effort,
        settings.anthropic_max_tokens,
    )
