"""Terminal demo: the whole guest -> bot -> staff -> guest flow, no Telegram needed.

    uv run python -m app.demo       # scripted conversation in four languages
    uv run python -m app.demo -i    # type as a guest; "/staff <text>" answers as reception

Uses the LLM from .env (LLM_PROVIDER=mock works offline with no API key).
"""

import argparse
import asyncio
import io
import itertools
import sys

from app.concierge import Concierge, Guest
from app.config import get_settings
from app.db import Repository
from app.knowledge import KnowledgeBase
from app.llm import create_llm

SCRIPT = [
    (Guest(1, "Anna Smith", "anna", "en"), "What time is breakfast?"),
    (Guest(2, "Иван Петров", "ivan", "ru"), "Какой пароль от вайфая?"),
    (Guest(3, "Mehmet Yılmaz", None, "tr"), "Havuz saat kaçta açılıyor?"),
    (Guest(4, "Jonas Weber", None, "de"), "Wann gibt es Frühstück?"),
    (Guest(2, "Иван Петров", "ivan", "ru"), "Можно заказать торт на день рождения в номер?"),
]
STAFF_ANSWER = (
    "Yes, our pastry chef can make a cake. Please order it at the reception a day before."
)

_staff_ids = itertools.count(1000)  # stands in for Telegram message ids


def show(speaker: str, text: str) -> None:
    print(f"\n[{speaker}]\n{text}")


async def ask(concierge: Concierge, guest: Guest, text: str) -> int | None:
    """Send a guest question. Returns the staff-chat message id if it went to staff."""
    show(f"guest {guest.name}", text)
    reply = await concierge.handle_guest_message(guest, text)
    show(f"bot -> {guest.name} ({reply.language.english_name})", reply.text)
    if reply.escalation_id is None or not reply.staff_text:
        return None
    staff_message_id = next(_staff_ids)
    await concierge.attach_staff_message(reply.escalation_id, staff_message_id)
    show("bot -> staff chat", reply.staff_text)
    return staff_message_id


async def answer_as_staff(concierge: Concierge, staff_message_id: int, text: str) -> None:
    show("reception (reply in the staff chat)", text)
    result = await concierge.handle_staff_reply(staff_message_id, text)
    if result is None:
        print("(no open question to answer)")
        return
    show("bot -> guest", result.guest_text)
    show("bot -> staff chat", result.confirmation)


async def run(interactive: bool) -> None:
    settings = get_settings()
    repo = await Repository.connect(":memory:")
    concierge = Concierge(
        create_llm(settings), KnowledgeBase(settings.knowledge_path), repo, settings
    )
    print(f"LLM provider: {settings.llm_provider}. Knowledge base: {settings.knowledge_path}")
    try:
        if interactive:
            await interactive_loop(concierge)
            return
        last = None
        for guest, text in SCRIPT:
            last = await ask(concierge, guest, text) or last
        if last is not None:
            await answer_as_staff(concierge, last, STAFF_ANSWER)
        stats = await concierge.stats()
        print(
            f"\nAnswered by the bot: {stats.answered_by_bot} of {stats.questions}, "
            f"passed to staff: {stats.escalated}"
        )
    finally:
        await repo.close()


async def interactive_loop(concierge: Concierge) -> None:
    guest = Guest(1, "Demo Guest", None, None)
    last_staff_message: int | None = None
    print('Type a question as a guest. "/staff <answer>" replies as reception. Ctrl+C quits.')
    while True:
        try:
            line = (await asyncio.to_thread(input, "\nguest> ")).strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not line:
            continue
        if line.startswith("/staff "):
            if last_staff_message is None:
                print("(no question has been passed to staff yet)")
            else:
                await answer_as_staff(concierge, last_staff_message, line.removeprefix("/staff "))
            continue
        last_staff_message = await ask(concierge, guest, line) or last_staff_message


def main() -> None:
    # When output goes to a pipe or a file, Windows Python encodes it with the ANSI code
    # page (cp1251 on a Russian system), which has no Turkish "ı" - force UTF-8.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Hotel concierge terminal demo")
    parser.add_argument("-i", "--interactive", action="store_true")
    asyncio.run(run(parser.parse_args().interactive))


if __name__ == "__main__":
    main()
