"""Plain-language summaries for a shop owner. The app depends only on the Explainer protocol."""

from app.config import AIProvider, Settings
from app.explain.base import LANGUAGES, LIMITS_NOTE, Explainer, ExplainError
from app.explain.fixed import FixedTextExplainer

__all__ = [
    "LANGUAGES",
    "LIMITS_NOTE",
    "ExplainError",
    "Explainer",
    "FixedTextExplainer",
    "create_explainer",
]


def create_explainer(settings: Settings) -> Explainer:
    if settings.ai_provider is AIProvider.ANTHROPIC and not settings.demo_mode:
        # Imported here so the offline demo never needs the SDK configured.
        import anthropic

        from app.explain.anthropic_client import ClaudeExplainer

        return ClaudeExplainer(
            anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None),
            settings.anthropic_model,
            settings.anthropic_effort,
        )
    return FixedTextExplainer()
