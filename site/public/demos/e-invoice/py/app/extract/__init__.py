"""Extractors turn the text of a PDF into the typed invoice. The pipeline only depends on the
Extractor protocol, so the offline rules and Claude are interchangeable."""

from typing import TYPE_CHECKING, Protocol

from app.model import Extraction
from app.pdf_text import PdfText

if TYPE_CHECKING:
    from app.config import Settings


class ExtractionError(Exception):
    """The extractor could not produce an invoice (API error, refusal, bad output)."""


class Extractor(Protocol):
    name: str

    async def extract(self, pdf: PdfText) -> Extraction: ...


def create_extractor(settings: "Settings") -> Extractor:
    # Imports are local so the offline demo does not need the Anthropic SDK configured, and
    # the rule-based extractor also runs where pydantic-settings is not installed (the
    # in-browser demo).
    from app.config import ExtractorChoice

    if settings.effective_extractor is ExtractorChoice.CLAUDE:
        import anthropic

        from app.extract.claude import ClaudeExtractor

        return ClaudeExtractor(
            anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None),
            settings.anthropic_model,
            settings.anthropic_effort,
        )

    from app.extract.rules import RuleBasedExtractor

    return RuleBasedExtractor()
