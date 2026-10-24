from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from app.db import Repository
from app.i18n import Language
from app.llm import LLMError, OfflineSuggester, Suggestion
from app.service import Kitchen

T0 = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)
NAMES = {
    Language.EN: "Test dish",
    Language.RU: "Тестовое блюдо",
    Language.TR: "Deneme yemeği",
    Language.DE: "Testgericht",
}


class Clock:
    """A clock that moves one minute every time it is read."""

    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(minutes=1)
        return self.now


class FakeSuggester:
    """Records what it was asked and answers from a fixed table."""

    def __init__(self, answers: dict[str, list[str]] | None = None, fail: bool = False) -> None:
        self.answers = answers or {}
        self.fail = fail
        self.calls: list[tuple[str, list[str]]] = []

    @property
    def enabled(self) -> bool:
        return True

    @property
    def model(self) -> str:
        return "fake-model"

    async def suggest(self, dish: str, ingredients: list[str]) -> list[Suggestion]:
        self.calls.append((dish, list(ingredients)))
        if self.fail:
            raise LLMError("provider down")
        return [
            Suggestion(ingredient=i, allergens=self.answers.get(i, []), reason="test reason")
            for i in ingredients
        ]


@pytest.fixture
async def repo() -> AsyncIterator[Repository]:
    repository = await Repository.connect(":memory:")
    yield repository
    await repository.close()


@pytest.fixture
def kitchen(repo: Repository) -> Kitchen:
    return Kitchen(repo, OfflineSuggester(), Clock())
