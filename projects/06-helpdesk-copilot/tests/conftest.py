from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.citations import Source
from app.config import Settings
from app.copilot import Copilot
from app.db import Repository, Requester
from app.knowledge import Document, load_documents
from app.llm import AnswerDraft, LLMError
from app.retrieval import Retriever
from app.triage import Triage, triage_by_rules

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = load_documents(PROJECT_ROOT / "knowledge")
EMPLOYEE = Requester("Erika Mustermann", "telegram", 7)


@dataclass
class FakeLLM:
    """Answers with a scripted draft (default: cite source 1); records every call."""

    name: str = "fake"
    answers: dict[str, AnswerDraft] = field(default_factory=dict)
    triages: dict[str, Triage] = field(default_factory=dict)
    fail: bool = False
    fail_triage: bool = False
    answer_calls: list[tuple[str, list[Source]]] = field(default_factory=list)
    triage_calls: list[str] = field(default_factory=list)

    async def answer(self, question: str, sources: list[Source]) -> AnswerDraft:
        self.answer_calls.append((question, sources))
        if self.fail:
            raise LLMError("provider is down")
        return self.answers.get(
            question, AnswerDraft(answered=True, answer="Do what the guide says [1].")
        )

    async def triage(self, text: str) -> Triage:
        self.triage_calls.append(text)
        if self.fail_triage:
            raise LLMError("provider is down")
        return self.triages.get(text) or triage_by_rules(text)


@pytest.fixture
def documents() -> list[Document]:
    return DOCUMENTS


@pytest.fixture
def retriever(documents: list[Document]) -> Retriever:
    return Retriever(documents, min_score=2.0, min_coverage=0.3)


@pytest.fixture
async def repo() -> AsyncIterator[Repository]:
    repository = await Repository.connect(":memory:")
    yield repository
    await repository.close()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def copilot(retriever: Retriever, llm: FakeLLM, repo: Repository) -> Copilot:
    return Copilot(retriever, llm, repo, top_k=4)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]  # never read a developer's real .env
        demo_mode=True,
        knowledge_dir=PROJECT_ROOT / "knowledge",
        database_path=tmp_path / "test.db",
        it_chat_id=-100500,
        company_name="Sample Office",
    )
