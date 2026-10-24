from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import Settings
from app.db import Repository
from app.models import ReadingIn
from app.service import FridgeService

T0 = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


def reading(minutes: float, temperature: float, sensor_id: str = "fridge-1") -> ReadingIn:
    return ReadingIn(
        sensor_id=sensor_id, temperature=temperature, timestamp=T0 + timedelta(minutes=minutes)
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]  # never read a developer's real .env
        bot_token="",
        api_key="secret",
        database_path=tmp_path / "test.db",
        default_limit_c=5.0,
        alert_delay_minutes=5,
        recovery_hysteresis_c=0.5,
        timezone="Europe/Istanbul",
    )


@pytest.fixture
async def repo() -> AsyncIterator[Repository]:
    repository = await Repository.connect(":memory:")
    yield repository
    await repository.close()


@pytest.fixture
def clock() -> FakeClock:
    # "Now" is a little after the readings the tests send, so alerts are fresh.
    return FakeClock(T0 + timedelta(minutes=15))


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def service(
    repo: Repository, notifier: RecordingNotifier, settings: Settings, clock: FakeClock
) -> FridgeService:
    return FridgeService(repo, notifier, settings, clock=clock)
