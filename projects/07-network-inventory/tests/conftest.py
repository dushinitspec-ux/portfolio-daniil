from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.db import Repository
from app.discovery import Observation
from app.oui import OuiDatabase
from app.scope import Scope

FIXTURES = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class ScriptedScanner:
    """Returns one pre-planned list of observations per scan."""

    def __init__(self, *rounds: list[Observation]) -> None:
        self.rounds = list(rounds)
        self.calls = 0

    async def scan(self, scope: Scope) -> list[Observation]:
        result = self.rounds[min(self.calls, len(self.rounds) - 1)]
        self.calls += 1
        return [o for o in result if scope.contains(o.ip)]


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


class Clock:
    """A clock that moves one hour per call, so every scan gets its own time."""

    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(hours=1)
        return self.now


@pytest.fixture
async def repo() -> AsyncIterator[Repository]:
    repository = await Repository.connect(":memory:")
    yield repository
    await repository.close()


@pytest.fixture(scope="session")
def oui() -> OuiDatabase:
    return OuiDatabase.load()
