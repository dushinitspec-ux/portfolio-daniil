"""Answer and triage providers. The copilot only depends on the LLMClient protocol."""

from app.config import Settings
from app.llm.base import AnswerDraft, LLMClient, LLMError

__all__ = ["AnswerDraft", "LLMClient", "LLMError", "create_llm"]


def create_llm(settings: Settings) -> LLMClient:
    if settings.demo_mode:
        from app.llm.demo import DemoLLM

        return DemoLLM()

    # Imported here so demo mode works without the SDK being configured.
    import anthropic

    from app.llm.anthropic_client import ClaudeLLM

    return ClaudeLLM(
        anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None),
        settings.anthropic_model,
        settings.anthropic_effort,
        settings.anthropic_triage_effort,
        settings.company_name,
    )
