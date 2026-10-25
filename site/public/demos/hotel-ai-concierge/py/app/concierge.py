"""Core logic: answer from the knowledge base or hand the question to staff.

Nothing here knows about Telegram, so the same code runs in the bot, in the
terminal demo and in the tests.
"""

import logging
from dataclasses import dataclass

from app.config import Settings
from app.db import Kind, Repository, Role, Stats
from app.knowledge import KnowledgeBase
from app.language import Language, detect_language, resolve_language
from app.llm import ConciergeAnswer, LLMClient, LLMError
from app.texts import ESCALATED, STAFF_REPLY_HEADER, TRANSLATED_NOTE, WELCOME

logger = logging.getLogger(__name__)

ROLE_LABELS = {Role.GUEST: "Guest", Role.BOT: "Concierge", Role.STAFF: "Reception"}


@dataclass(frozen=True)
class Guest:
    chat_id: int
    name: str
    username: str | None = None
    telegram_language: str | None = None


@dataclass(frozen=True)
class GuestReply:
    language: Language
    text: str
    escalation_id: int | None = None
    staff_text: str | None = None  # what to post in the staff chat


@dataclass(frozen=True)
class StaffReply:
    guest_chat_id: int
    guest_text: str
    confirmation: str  # shown to staff after the answer is delivered


def format_history(messages: list[tuple[Role, str]]) -> str:
    return "\n".join(f"{ROLE_LABELS[role]}: {text}" for role, text in messages)


def format_staff_message(
    escalation_id: int,
    guest: Guest,
    language: Language,
    question: str,
    question_en: str,
    reason: str,
) -> str:
    who = guest.name + (f" (@{guest.username})" if guest.username else "")
    lines = [
        f"❓ Question #{escalation_id} from {who} · {language.english_name}",
        f"Reason: {reason}",
        "",
        question,
    ]
    if language is not Language.EN and question_en.strip() != question.strip():
        lines += ["", f"In English: {question_en}"]
    lines += ["", "↩️ Reply to this message and I will send your answer to the guest."]
    return "\n".join(lines)


class Concierge:
    def __init__(
        self, llm: LLMClient, knowledge: KnowledgeBase, repo: Repository, settings: Settings
    ) -> None:
        self._llm = llm
        self._knowledge = knowledge
        self._repo = repo
        self._settings = settings

    async def welcome(self, guest: Guest) -> GuestReply:
        language = resolve_language("", None, guest.telegram_language)
        return GuestReply(language, WELCOME[language].format(hotel=self._settings.hotel_name))

    async def guest_language(self, guest: Guest, text: str = "") -> Language:
        previous = await self._repo.guest_language(guest.chat_id)
        return resolve_language(text, previous, guest.telegram_language)

    async def handle_guest_message(self, guest: Guest, text: str) -> GuestReply:
        language = await self.guest_language(guest, text)
        history = format_history(
            await self._repo.recent_messages(guest.chat_id, self._settings.history_messages)
        )
        await self._repo.upsert_guest(guest.chat_id, guest.name, guest.username, language)
        await self._repo.log(guest.chat_id, Role.GUEST, Kind.QUESTION, text, language)

        result: ConciergeAnswer | None = None
        try:
            result = await self._llm.answer(text, language, self._knowledge.text, history)
        except LLMError as exc:
            logger.warning("LLM failed, escalating to staff: %s", exc)

        if result and result.found_in_knowledge_base and result.answer.strip():
            answer = result.answer.strip()
            await self._repo.log(guest.chat_id, Role.BOT, Kind.ANSWER, answer, language)
            return GuestReply(language, answer)

        # Not in the knowledge base, or the AI is unavailable: never guess, ask a human.
        reason = "not in the knowledge base" if result else "AI assistant unavailable"
        question_en = result.question_in_english if result else text
        escalation_id = await self._repo.create_escalation(
            guest.chat_id, language, text, question_en, reason
        )
        notice = ESCALATED[language]
        await self._repo.log(
            guest.chat_id, Role.BOT, Kind.ESCALATED, notice, language, escalation_id
        )
        staff_text = format_staff_message(escalation_id, guest, language, text, question_en, reason)
        return GuestReply(language, notice, escalation_id, staff_text)

    async def attach_staff_message(self, escalation_id: int, staff_message_id: int) -> None:
        await self._repo.set_staff_message(escalation_id, staff_message_id)

    async def stats(self) -> Stats:
        return await self._repo.stats()

    async def handle_staff_reply(self, staff_message_id: int, text: str) -> StaffReply | None:
        """Route a staff reply back to the guest. None if it answers no escalation."""
        escalation = await self._repo.escalation_by_staff_message(staff_message_id)
        if escalation is None:
            return None
        language = escalation.language

        body, translated = text.strip(), False
        if self._settings.translate_staff_replies and detect_language(text) is not language:
            try:
                translation = (await self._llm.translate(text, language)).strip()
            except LLMError as exc:
                logger.warning("Translation failed, sending the original: %s", exc)
            else:
                if translation and translation != body:
                    body, translated = translation, True

        guest_text = f"{STAFF_REPLY_HEADER[language]}\n{body}"
        if translated:
            guest_text += f"\n\n{TRANSLATED_NOTE[language]}\n{text.strip()}"

        await self._repo.mark_answered(escalation.id)
        await self._repo.log(
            escalation.guest_chat_id, Role.STAFF, Kind.STAFF_REPLY, body, language, escalation.id
        )
        confirmation = f"✅ Sent to the guest (question #{escalation.id})"
        if translated:
            confirmation += f", translated to {language.english_name}"
        return StaffReply(escalation.guest_chat_id, guest_text, confirmation)
