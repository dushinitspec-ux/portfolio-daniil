"""The helpdesk logic: answer from the knowledge base with sources, or open a ticket.

The order of checks, cheapest first:

1. An outage affecting many people, or a request for IT to do something -> ticket at once.
2. Retrieval: if the best section does not cover the question -> ticket, no LLM call.
3. The LLM answers from the numbered sections, or says it cannot -> ticket.
4. The citations are checked: an answer without a valid source is never shown -> ticket.
5. A security incident is answered (the how-to has the first steps) *and* gets a P1 ticket.

Nothing here knows about Telegram or HTTP, so the bot, the web page, the evaluation and the
tests all run the same code.
"""

import logging
from dataclasses import dataclass, field
from enum import StrEnum

from app.citations import Source, check_citations, number_sources
from app.db import Repository, Requester, Resolution, Ticket
from app.llm import LLMClient, LLMError
from app.llm.demo import DemoLLM
from app.retrieval import Retrieval, Retriever
from app.triage import Triage, Urgency, apply_floor, is_action_request, triage_by_rules, urgency

logger = logging.getLogger(__name__)


class Route(StrEnum):
    """Why a question became a ticket."""

    OUTAGE = "outage affecting many people"
    ACTION = "the employee asks IT to do something"
    NOT_FOUND = "not found in the knowledge base"
    NO_ANSWER = "the sources do not answer it"
    NO_CITATION = "the answer cited no valid source"
    SECURITY = "security incident: answered and escalated"
    ASKED = "the answer did not help (employee asked)"
    DIRECT = "written as a ticket"


@dataclass(frozen=True)
class Decision:
    retrieval: Retrieval
    answer: str = ""  # empty if not answered
    sources: list[Source] = field(default_factory=list)  # the sources the answer cites
    route: Route | None = None  # set when a ticket is needed
    detail: str = ""
    note: str = ""  # e.g. that the LLM was unavailable

    @property
    def answered(self) -> bool:
        return bool(self.answer)

    @property
    def ticket_reason(self) -> str:
        if self.route is None:
            return ""
        return f"{self.route.value} ({self.detail})" if self.detail else self.route.value


@dataclass(frozen=True)
class Reply:
    question: str
    decision: Decision
    question_id: int | None = None  # None for a preview
    ticket: Ticket | None = None
    triage: Triage | None = None  # also filled in a preview, where no ticket is saved

    @property
    def answered(self) -> bool:
        return self.decision.answered


class Copilot:
    def __init__(
        self,
        retriever: Retriever,
        llm: LLMClient,
        repo: Repository,
        *,
        top_k: int = 4,
        fallback: LLMClient | None = None,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.repo = repo
        self.top_k = top_k
        # Used when the LLM fails: an extractive answer is still grounded in the sources.
        self.fallback = fallback or DemoLLM()

    async def decide(self, question: str) -> Decision:
        retrieval = self.retriever.search(question, self.top_k)
        urgent = urgency(question)

        if urgent is Urgency.OUTAGE:
            return Decision(retrieval, route=Route.OUTAGE)
        if is_action_request(question):
            return Decision(retrieval, route=Route.ACTION)
        if not retrieval.confident:
            detail = (
                f"coverage {retrieval.coverage_label}, needed {self.retriever.min_coverage:.2f}"
            )
            return Decision(retrieval, route=Route.NOT_FOUND, detail=detail)

        sources = number_sources([hit.section for hit in retrieval.hits])
        note = ""
        try:
            draft = await self.llm.answer(question, sources)
        except LLMError as exc:
            logger.warning("LLM answer failed, using the extractive answer: %s", exc)
            draft = await self.fallback.answer(question, sources)
            note = "The language model was unavailable, so this is the best matching section."

        if not draft.answered or not draft.answer.strip():
            return Decision(retrieval, route=Route.NO_ANSWER)
        check = check_citations(draft.answer, sources)
        if check.unknown:
            logger.warning("Removed citations of unknown sources: %s", check.unknown)
        if not check.grounded:
            return Decision(retrieval, route=Route.NO_CITATION)

        route = Route.SECURITY if urgent is Urgency.SECURITY else None
        return Decision(retrieval, check.text, check.cited, route=route, note=note)

    async def triage(self, text: str) -> Triage:
        """LLM triage, with the rules as a fallback and as a floor for P1."""
        rules = triage_by_rules(text)
        try:
            return apply_floor(await self.llm.triage(text), rules)
        except LLMError as exc:
            logger.warning("LLM triage failed, using the rules: %s", exc)
            return rules

    async def ask(self, question: str, requester: Requester) -> Reply:
        """Answer or open a ticket, and record what happened."""
        decision = await self.decide(question)
        question_id = await self.repo.log_question(
            requester,
            question,
            answered=decision.answered,
            coverage=decision.retrieval.coverage,
            answer=decision.answer,
            sources=[s.section.id for s in decision.sources],
        )
        if decision.route is None:
            return Reply(question, decision, question_id)

        triage = await self.triage(question)
        ticket = await self.repo.create_ticket(requester, question, triage, decision.ticket_reason)
        await self.repo.resolve_question(question_id, Resolution.TICKET, ticket.id)
        return Reply(question, decision, question_id, ticket, triage)

    async def preview(self, question: str) -> Reply:
        """What the copilot would do, without saving anything (the "Try a question" page)."""
        decision = await self.decide(question)
        triage = await self.triage(question) if decision.route else None
        return Reply(question, decision, triage=triage)

    async def ticket_for_question(
        self, question_id: int, requester_id: int | None
    ) -> Ticket | None:
        """The "Create ticket" button: the answer did not help.

        Only the person who asked can do this. Pressing it twice (or after a ticket was
        already opened) returns the same ticket.
        """
        record = await self.repo.get_question(question_id)
        if record is None or record.requester.user_id != requester_id:
            return None
        if record.ticket_id is not None:
            return await self.repo.get_ticket(record.ticket_id)
        triage = await self.triage(record.question)
        ticket = await self.repo.create_ticket(
            record.requester, record.question, triage, Route.ASKED.value
        )
        await self.repo.resolve_question(question_id, Resolution.TICKET, ticket.id)
        return ticket

    async def mark_solved(self, question_id: int, requester_id: int | None) -> bool:
        record = await self.repo.get_question(question_id)
        if record is None or record.requester.user_id != requester_id:
            return False
        if record.resolution is None:
            await self.repo.resolve_question(question_id, Resolution.SOLVED)
        return True

    async def open_ticket(self, text: str, requester: Requester) -> Ticket:
        """A ticket written directly (the /ticket command, the API)."""
        triage = await self.triage(text)
        return await self.repo.create_ticket(requester, text, triage, Route.DIRECT.value)
