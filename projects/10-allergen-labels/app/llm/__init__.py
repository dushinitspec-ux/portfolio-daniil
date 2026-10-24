"""AI suggestions. The rest of the app only depends on the Suggester protocol."""

from app.config import Settings
from app.llm.base import LLMError, Suggester, Suggestion

__all__ = ["LLMError", "OfflineSuggester", "Suggester", "Suggestion", "create_suggester"]


class OfflineSuggester:
    """Demo mode and installs without an API key: nothing is guessed, the chef decides."""

    @property
    def enabled(self) -> bool:
        return False

    @property
    def model(self) -> str:
        return "offline"

    async def suggest(self, dish: str, ingredients: list[str]) -> list[Suggestion]:
        return []


def create_suggester(settings: Settings) -> Suggester:
    if not settings.ai_enabled:
        return OfflineSuggester()
    # Imported here so the offline demo never needs the SDK configured.
    import anthropic

    from app.llm.anthropic_client import AnthropicSuggester

    return AnthropicSuggester(
        anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key),
        settings.anthropic_model,
        settings.anthropic_effort,
    )
