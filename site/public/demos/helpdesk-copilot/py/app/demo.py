"""Demo mode: sample employees ask sample questions through the real pipeline.

Nothing here is invented output: every ticket on the demo page is created by running the
question through the same Copilot.ask() the bot uses (extractive answers, rule triage).
The names are the usual placeholder names of each language.
"""

import logging

from app.copilot import Copilot
from app.db import Requester, Status

logger = logging.getLogger(__name__)

# (name, question, what the employee does next: "solved", "ticket" or None)
SAMPLE_QUESTIONS: list[tuple[str, str, str | None]] = [
    ("Erika Mustermann", "How do I connect to the VPN from home?", "solved"),
    ("Max Mustermann", "I clicked a link in a fake DHL email and typed my password", None),
    ("Jane Doe", "The whole office has no internet!", None),
    ("John Doe", "My monitor shows vertical stripes and flickers", None),
    ("Ivan Ivanov", "Принтер не печатает, документ висит в очереди", "solved"),
    ("Ahmet Yılmaz", "Can you order a new office chair for me?", None),
    ("Erika Mustermann", "Please give Anna access to the Finance folder on the S drive", None),
    ("Max Mustermann", "How do I set an out of office message?", "solved"),
    ("John Doe", "Excel freezes when I open the sales report", None),
    ("Jane Doe", "I need Adobe Photoshop for the new brochure", None),
    ("Max Mustermann", "Laptop zeigt beim Start einen Bluescreen, ich kann nicht arbeiten", None),
    ("Jane Doe", "How do I add the colour printer?", "ticket"),
    ("Ahmet Yılmaz", "Şifremi unuttum, nasıl sıfırlarım?", "solved"),
]

# Some tickets are already being worked on, so the page shows every status.
STATUS_CHANGES = {"Can you order a new office chair for me?": Status.CLOSED}
IN_PROGRESS = {"The whole office has no internet!"}


async def seed(copilot: Copilot) -> int:
    """Run the sample questions once; returns the number of tickets created."""
    created = 0
    for user_id, (name, question, follow_up) in enumerate(SAMPLE_QUESTIONS, start=1001):
        requester = Requester(name, "demo", user_id)
        reply = await copilot.ask(question, requester)
        ticket = reply.ticket
        if reply.question_id is not None and reply.answered and not ticket:
            if follow_up == "solved":
                await copilot.mark_solved(reply.question_id, user_id)
            elif follow_up == "ticket":
                ticket = await copilot.ticket_for_question(reply.question_id, user_id)
        if ticket is None:
            continue
        created += 1
        if question in STATUS_CHANGES:
            await copilot.repo.set_ticket_status(ticket.id, STATUS_CHANGES[question])
        elif question in IN_PROGRESS:
            await copilot.repo.set_ticket_status(ticket.id, Status.IN_PROGRESS)
    logger.info("Demo mode: %d sample questions, %d tickets.", len(SAMPLE_QUESTIONS), created)
    return created
