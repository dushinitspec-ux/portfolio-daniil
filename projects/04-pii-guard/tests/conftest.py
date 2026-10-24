from collections.abc import AsyncIterator, Sequence
from datetime import date
from pathlib import Path

import pytest

from app.audit import AuditLog
from app.detectors import Detector, load_names
from app.gateway import Gateway
from app.guard import Guard, Message
from app.llm import LLMError
from app.llm.demo import DemoLLM
from app.policy import Policy, load_policy

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 10, 24)

# Sample values used across the tests. All of them are published examples or made up.
IBAN = "DE89 3704 0044 0532 0130 00"
EMAIL = "anna.schmidt@muster-gmbh.example"
PHONE = "+49 30 12345678"
CARD = "4111 1111 1111 1111"
VAT = "DE123456789"
IP = "203.0.113.42"


class RecordingLLM:
    """Remembers exactly what it was sent; answers like the demo model or fails on demand."""

    name = "recording"

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, list[Message]]] = []
        self.fail = fail
        self._demo = DemoLLM()

    async def complete(self, system: str, messages: Sequence[Message]) -> str:
        self.calls.append((system, list(messages)))
        if self.fail:
            raise LLMError("provider is down")
        return await self._demo.complete(system, messages)


@pytest.fixture
def detector() -> Detector:
    return Detector(["DE"], load_names(ROOT / "names.demo.txt"), today=TODAY)


@pytest.fixture
def policy() -> Policy:
    return load_policy(ROOT / "policy.yaml")


@pytest.fixture
def guard(detector: Detector, policy: Policy) -> Guard:
    return Guard(detector, policy)


@pytest.fixture
async def audit() -> AsyncIterator[AuditLog]:
    log = await AuditLog.connect(":memory:")
    yield log
    await log.close()


@pytest.fixture
def llm() -> RecordingLLM:
    return RecordingLLM()


@pytest.fixture
def gateway(guard: Guard, llm: RecordingLLM, audit: AuditLog) -> Gateway:
    return Gateway(guard, llm, audit)
