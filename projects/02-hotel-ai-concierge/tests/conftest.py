from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.concierge import Concierge
from app.config import Settings
from app.db import Repository
from app.knowledge import KnowledgeBase
from app.language import Language
from app.llm import ConciergeAnswer, LLMError

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class FakeLLM:
    """Answers questions from a dict; records what it was asked."""

    answers: dict[str, ConciergeAnswer] = field(default_factory=dict)
    fail: bool = False
    fail_translation: bool = False
    calls: list[dict[str, object]] = field(default_factory=list)

    async def answer(
        self, question: str, language: Language, knowledge: str, history: str
    ) -> ConciergeAnswer:
        self.calls.append({"question": question, "language": language, "history": history})
        if self.fail:
            raise LLMError("provider is down")
        return self.answers.get(
            question,
            ConciergeAnswer(found_in_knowledge_base=False, answer="", question_in_english=question),
        )

    async def translate(self, text: str, target: Language) -> str:
        if self.fail_translation:
            raise LLMError("provider is down")
        return f"[{target.value}] {text}"


def found(answer: str, question_en: str = "") -> ConciergeAnswer:
    return ConciergeAnswer(
        found_in_knowledge_base=True, answer=answer, question_in_english=question_en
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]  # never read a developer's real .env
        llm_provider="mock",
        knowledge_path=PROJECT_ROOT / "knowledge" / "hotel.md",
        database_path=tmp_path / "test.db",
        staff_chat_id=-100500,
        hotel_name="Test Hotel",
    )


@pytest.fixture
async def repo() -> AsyncIterator[Repository]:
    repository = await Repository.connect(":memory:")
    yield repository
    await repository.close()


@pytest.fixture
def knowledge(settings: Settings) -> KnowledgeBase:
    return KnowledgeBase(settings.knowledge_path)


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def concierge(
    llm: FakeLLM, knowledge: KnowledgeBase, repo: Repository, settings: Settings
) -> Concierge:
    return Concierge(llm, knowledge, repo, settings)
