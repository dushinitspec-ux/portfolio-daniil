"""One chat request end to end: mask, ask the LLM, restore, write the audit log."""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

from app.audit import AuditLog
from app.guard import Guard, LeakCheckError, Message, Prepared
from app.llm import SYSTEM_PROMPT, LLMClient, LLMError
from app.masking import Segment, restore_segments, unknown_placeholders

logger = logging.getLogger("pii_guard")


@dataclass
class ChatResult:
    prepared: Prepared
    llm_answer: str  # what the model wrote, with placeholders
    answer: str  # what the user gets, with the real values back
    answer_segments: list[Segment]
    unknown_placeholders: list[str]
    latency_ms: int


class BlockedError(Exception):
    def __init__(self, prepared: Prepared) -> None:
        super().__init__("blocked by policy")
        self.prepared = prepared


def _summary(prepared: Prepared) -> str:
    """'EMAIL:1:mask IBAN:1:mask' - types, counts and actions only, safe to log."""
    return " ".join(f"{f.type}:{f.count}:{f.action}" for f in prepared.findings) or "-"


class Gateway:
    def __init__(self, guard: Guard, llm: LLMClient, audit: AuditLog) -> None:
        self.guard = guard
        self.llm = llm
        self.audit = audit

    async def chat(self, messages: Sequence[Message], source: str) -> ChatResult:
        started = time.perf_counter()
        try:
            prepared = self.guard.prepare(messages)
        except LeakCheckError:
            await self._record(source, "error", {}, len(messages), None)
            logger.error("leak check failed, request refused (source=%s)", source)
            raise

        if prepared.blocked:
            await self._record(source, "blocked", prepared.counts(), len(messages), None)
            logger.info("blocked source=%s entities=%s", source, _summary(prepared))
            raise BlockedError(prepared)

        try:
            llm_answer = await self.llm.complete(SYSTEM_PROMPT, prepared.masked)
        except LLMError:
            latency = round((time.perf_counter() - started) * 1000)
            await self._record(source, "error", prepared.counts(), len(messages), latency)
            logger.warning("LLM failed source=%s entities=%s", source, _summary(prepared))
            raise

        segments = restore_segments(llm_answer, prepared.vault)
        latency = round((time.perf_counter() - started) * 1000)
        await self._record(source, prepared.decision, prepared.counts(), len(messages), latency)
        logger.info(
            "%s source=%s entities=%s latency=%dms",
            prepared.decision,
            source,
            _summary(prepared),
            latency,
        )
        return ChatResult(
            prepared=prepared,
            llm_answer=llm_answer,
            answer="".join(s.text for s in segments),
            answer_segments=segments,
            unknown_placeholders=unknown_placeholders(llm_answer, prepared.vault),
            latency_ms=latency,
        )

    async def _record(
        self,
        source: str,
        decision: str,
        entities: dict[str, dict[str, int | str]],
        messages: int,
        latency_ms: int | None,
    ) -> None:
        await self.audit.record(
            source=source,
            decision=decision,
            entities=entities,
            messages=messages,
            model=self.llm.name,
            latency_ms=latency_ms,
        )
