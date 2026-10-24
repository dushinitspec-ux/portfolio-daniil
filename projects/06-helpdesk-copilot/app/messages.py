"""Texts the bot sends. Plain text (no parse mode), so knowledge-base content is shown as is."""

from app.citations import format_sources
from app.copilot import Reply, Route
from app.db import Ticket

# Shown in /start and under every answer: people must know they are talking to an AI
# (EU AI Act, Article 50(1)); see README, "AI Act transparency".
AI_NOTICE = "🤖 AI-generated answer from the {company} IT knowledge base."


def welcome(company: str, name: str) -> str:
    return (
        f"Hi {name}! I'm the IT assistant of {company}.\n\n"
        "I'm an AI system, not a person. I answer from the company's IT knowledge base and "
        "show the sources I used. AI answers can be wrong: if something looks odd, check the "
        "source.\n\n"
        "If I can't answer, I create a ticket for the IT team and a person takes over.\n\n"
        "Just write your question, for example: How do I connect to the VPN from home?\n"
        "/ticket <text> opens a ticket directly."
    )


TEXT_ONLY = "Please describe the problem in a text message. I can't read photos or voice yet."
TICKET_USAGE = "Write the problem after the command, for example:\n/ticket The scanner is offline"
NOT_YOURS = "This button belongs to another question."
SOLVED = "Great, glad it helped! 👍"

_LEADS = {
    Route.OUTAGE: "This sounds like an outage that affects many people, so I went straight to IT.",
    Route.ACTION: "This needs someone from IT to do it, so I passed it on.",
    Route.ASKED: "Sorry the answer didn't help. I passed your question to IT.",
    Route.DIRECT: "Thanks, I passed it on to IT.",
}
_NOT_ANSWERED = (
    "I couldn't find this in the IT knowledge base, so instead of guessing I passed it to IT."
)


def ticket_line(ticket: Ticket) -> str:
    t = ticket.triage
    return f"Ticket #{ticket.id} · {t.priority} · {t.category}\n{t.summary}"


def answer_text(reply: Reply, company: str) -> str:
    decision = reply.decision
    parts = [decision.answer, "Sources:\n" + format_sources(decision.sources)]
    if decision.note:
        parts.append(f"Note: {decision.note}")
    if reply.ticket is not None:
        parts.append(
            "⚠️ This looks like a security incident, so I also opened a ticket and IT has "
            f"been notified.\n{ticket_line(reply.ticket)}"
        )
    parts.append(AI_NOTICE.format(company=company))
    return "\n\n".join(parts)


def ticket_text(ticket: Ticket, route: Route | None) -> str:
    lead = _LEADS.get(route, _NOT_ANSWERED) if route else _NOT_ANSWERED
    return f"{lead}\n\n🎫 {ticket_line(ticket)}\n\nThe IT team will get back to you."


def it_notification(ticket: Ticket) -> str:
    """The message the IT chat gets for a new ticket."""
    who = ticket.requester.name
    if ticket.requester.user_id is not None:
        who += f" (Telegram id {ticket.requester.user_id})"
    return (
        f"🎫 New {ticket_line(ticket)}\n\n"
        f"From: {who}\n"
        f"Question: {ticket.question}\n"
        f"Why a ticket: {ticket.route_reason}\n"
        f"Priority reason: {ticket.triage.reason} ({ticket.triage.by})"
    )
