from app.copilot import Copilot, Route
from app.db import Repository, Resolution
from app.llm import AnswerDraft
from app.triage import Category, Priority, Triage
from tests.conftest import EMPLOYEE, FakeLLM

VPN_QUESTION = "How do I connect to the VPN from home?"


async def test_answer_with_sources_is_logged(
    copilot: Copilot, llm: FakeLLM, repo: Repository
) -> None:
    reply = await copilot.ask(VPN_QUESTION, EMPLOYEE)

    assert reply.answered
    assert reply.ticket is None
    assert reply.decision.answer == "Do what the guide says [1]."
    assert [s.section.doc_id for s in reply.decision.sources] == ["vpn"]
    # The LLM saw numbered sections from retrieval, best first.
    _, sources = llm.answer_calls[0]
    assert [s.number for s in sources] == [1, 2, 3, 4]
    assert reply.question_id is not None
    stats = await repo.stats()
    assert (stats.questions, stats.answered, stats.tickets) == (1, 1, 0)


async def test_low_confidence_becomes_a_ticket_without_asking_the_llm(
    copilot: Copilot, llm: FakeLLM, repo: Repository
) -> None:
    reply = await copilot.ask("The coffee machine in the kitchen is leaking", EMPLOYEE)

    assert not reply.answered
    assert llm.answer_calls == []  # no paid call for a question retrieval cannot support
    assert reply.ticket is not None
    assert reply.decision.route is Route.NOT_FOUND
    assert "coverage" in reply.ticket.route_reason
    record = await repo.get_question(reply.question_id or 0)
    assert record is not None and record.resolution is Resolution.TICKET


async def test_model_saying_it_does_not_know_becomes_a_ticket(
    copilot: Copilot, llm: FakeLLM
) -> None:
    llm.answers[VPN_QUESTION] = AnswerDraft(answered=False, answer="")
    reply = await copilot.ask(VPN_QUESTION, EMPLOYEE)
    assert reply.ticket is not None
    assert reply.decision.route is Route.NO_ANSWER


async def test_answer_without_a_valid_citation_is_never_shown(
    copilot: Copilot, llm: FakeLLM
) -> None:
    llm.answers[VPN_QUESTION] = AnswerDraft(answered=True, answer="Restart the router [9].")
    reply = await copilot.ask(VPN_QUESTION, EMPLOYEE)
    assert not reply.answered
    assert reply.decision.route is Route.NO_CITATION


async def test_unknown_citation_is_dropped_from_a_grounded_answer(
    copilot: Copilot, llm: FakeLLM
) -> None:
    llm.answers[VPN_QUESTION] = AnswerDraft(answered=True, answer="Open WireGuard [1][9].")
    reply = await copilot.ask(VPN_QUESTION, EMPLOYEE)
    assert reply.decision.answer == "Open WireGuard [1]."


async def test_llm_failure_falls_back_to_the_extractive_answer(
    copilot: Copilot, llm: FakeLLM
) -> None:
    llm.fail = True
    reply = await copilot.ask(VPN_QUESTION, EMPLOYEE)
    assert reply.answered
    assert reply.decision.answer.endswith("[1]")
    assert "unavailable" in reply.decision.note


async def test_security_incident_is_answered_and_escalated(copilot: Copilot) -> None:
    reply = await copilot.ask(
        "I clicked a link in a fake DHL email and typed my password", EMPLOYEE
    )
    assert reply.answered
    assert reply.decision.route is Route.SECURITY
    assert reply.ticket is not None
    assert (reply.ticket.triage.priority, reply.ticket.triage.category) == (
        Priority.P1,
        Category.SECURITY,
    )


async def test_outage_and_action_request_go_straight_to_it(copilot: Copilot, llm: FakeLLM) -> None:
    outage = await copilot.ask("The whole office has no internet!", EMPLOYEE)
    request = await copilot.ask("Please give Anna access to the Finance folder", EMPLOYEE)

    assert outage.decision.route is Route.OUTAGE
    assert outage.ticket is not None and outage.ticket.triage.priority is Priority.P1
    assert request.decision.route is Route.ACTION
    assert llm.answer_calls == []


async def test_create_ticket_button_is_idempotent_and_owner_only(copilot: Copilot) -> None:
    reply = await copilot.ask(VPN_QUESTION, EMPLOYEE)
    assert reply.question_id is not None

    assert await copilot.ticket_for_question(reply.question_id, requester_id=999) is None
    first = await copilot.ticket_for_question(reply.question_id, EMPLOYEE.user_id)
    second = await copilot.ticket_for_question(reply.question_id, EMPLOYEE.user_id)
    assert first is not None and second is not None
    assert first.id == second.id
    assert first.route_reason == Route.ASKED.value


async def test_mark_solved(copilot: Copilot, repo: Repository) -> None:
    reply = await copilot.ask(VPN_QUESTION, EMPLOYEE)
    assert reply.question_id is not None
    assert not await copilot.mark_solved(reply.question_id, requester_id=999)
    assert await copilot.mark_solved(reply.question_id, EMPLOYEE.user_id)
    assert (await repo.stats()).solved == 1


async def test_llm_triage_is_used_but_cannot_lower_p1(copilot: Copilot, llm: FakeLLM) -> None:
    text = "I typed my password on a strange login page"
    llm.triages[text] = Triage(Category.ACCESS, Priority.P3, "Password on fake page", "x", "llm")
    ticket = await copilot.open_ticket(text, EMPLOYEE)
    assert ticket.triage.priority is Priority.P1
    assert ticket.triage.summary == "Password on fake page"
    assert ticket.triage.by == "llm+rules"


async def test_llm_triage_failure_uses_the_rules(copilot: Copilot, llm: FakeLLM) -> None:
    llm.fail_triage = True
    ticket = await copilot.open_ticket("Printer is jammed", EMPLOYEE)
    assert ticket.triage.by == "rules"
    assert ticket.triage.category is Category.HARDWARE


async def test_preview_saves_nothing(copilot: Copilot, repo: Repository) -> None:
    answered = await copilot.preview(VPN_QUESTION)
    ticket = await copilot.preview("The coffee machine in the kitchen is leaking")

    assert answered.answered and answered.question_id is None
    assert ticket.triage is not None and ticket.ticket is None
    stats = await repo.stats()
    assert (stats.questions, stats.tickets) == (0, 0)
