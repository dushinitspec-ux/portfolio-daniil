from app.concierge import Concierge, Guest
from app.db import Repository
from app.language import Language
from app.llm import ConciergeAnswer
from tests.conftest import FakeLLM, found

IVAN = Guest(chat_id=7, name="Иван", username="ivan", telegram_language="ru")
ANNA = Guest(chat_id=8, name="Anna", username=None, telegram_language="en")


async def test_answers_from_knowledge_base(concierge: Concierge, llm: FakeLLM) -> None:
    llm.answers["Во сколько завтрак?"] = found("Завтрак с 07:00 до 10:00.")
    reply = await concierge.handle_guest_message(IVAN, "Во сколько завтрак?")
    assert reply.text == "Завтрак с 07:00 до 10:00."
    assert reply.language is Language.RU
    assert reply.escalation_id is None
    assert llm.calls[0]["language"] is Language.RU


async def test_unknown_question_goes_to_staff(concierge: Concierge, llm: FakeLLM) -> None:
    llm.answers["Можно торт в номер?"] = ConciergeAnswer(
        found_in_knowledge_base=False, answer="", question_in_english="Can I get a cake?"
    )
    reply = await concierge.handle_guest_message(IVAN, "Можно торт в номер?")

    assert reply.escalation_id is not None
    assert "ресепшен" in reply.text  # the guest is told, in Russian, what happens next
    assert reply.staff_text is not None
    assert "Иван (@ivan) · Russian" in reply.staff_text
    assert "Можно торт в номер?" in reply.staff_text
    assert "In English: Can I get a cake?" in reply.staff_text


async def test_found_but_empty_answer_is_escalated(concierge: Concierge, llm: FakeLLM) -> None:
    llm.answers["Hi"] = ConciergeAnswer(
        found_in_knowledge_base=True, answer="  ", question_in_english="Hi"
    )
    reply = await concierge.handle_guest_message(ANNA, "Hi")
    assert reply.escalation_id is not None


async def test_llm_failure_goes_to_staff(concierge: Concierge, llm: FakeLLM) -> None:
    llm.fail = True
    reply = await concierge.handle_guest_message(ANNA, "Is the spa open?")
    assert reply.escalation_id is not None
    assert reply.staff_text is not None
    assert "AI assistant unavailable" in reply.staff_text


async def test_language_sticks_for_short_messages(concierge: Concierge, llm: FakeLLM) -> None:
    # Anna's Telegram app is in English, but she writes in Russian.
    await concierge.handle_guest_message(ANNA, "Где бассейн?")
    reply = await concierge.handle_guest_message(ANNA, "ok")
    assert reply.language is Language.RU


async def test_history_is_passed_to_the_llm(concierge: Concierge, llm: FakeLLM) -> None:
    llm.answers["Where is the pool?"] = found("Behind the main building.")
    await concierge.handle_guest_message(ANNA, "Where is the pool?")
    await concierge.handle_guest_message(ANNA, "Is it heated?")

    history = str(llm.calls[1]["history"])
    assert "Guest: Where is the pool?" in history
    assert "Concierge: Behind the main building." in history
    assert "Is it heated?" not in history  # the current question is sent separately


async def test_staff_reply_is_translated_for_the_guest(
    concierge: Concierge, repo: Repository
) -> None:
    reply = await concierge.handle_guest_message(IVAN, "Можно торт в номер?")
    assert reply.escalation_id is not None
    await concierge.attach_staff_message(reply.escalation_id, staff_message_id=500)

    result = await concierge.handle_staff_reply(500, "Yes, order it a day before.")

    assert result is not None
    assert result.guest_chat_id == IVAN.chat_id
    assert "Ответ ресепшена" in result.guest_text
    assert "[ru] Yes, order it a day before." in result.guest_text
    assert "Оригинал:\nYes, order it a day before." in result.guest_text
    assert "translated to Russian" in result.confirmation
    stats = await repo.stats()
    assert (stats.escalated, stats.open_escalations) == (1, 0)


async def test_staff_reply_in_guest_language_is_not_translated(concierge: Concierge) -> None:
    reply = await concierge.handle_guest_message(IVAN, "Можно торт в номер?")
    assert reply.escalation_id is not None
    await concierge.attach_staff_message(reply.escalation_id, staff_message_id=501)

    result = await concierge.handle_staff_reply(501, "Да, закажите за день.")
    assert result is not None
    assert result.guest_text.endswith("Да, закажите за день.")
    assert "Оригинал" not in result.guest_text


async def test_failed_translation_sends_the_original(concierge: Concierge, llm: FakeLLM) -> None:
    reply = await concierge.handle_guest_message(IVAN, "Можно торт в номер?")
    assert reply.escalation_id is not None
    await concierge.attach_staff_message(reply.escalation_id, staff_message_id=502)
    llm.fail_translation = True

    result = await concierge.handle_staff_reply(502, "Yes, order it a day before.")
    assert result is not None
    assert result.guest_text.endswith("Yes, order it a day before.")


async def test_reply_to_unrelated_message_is_ignored(concierge: Concierge) -> None:
    assert await concierge.handle_staff_reply(999, "hello") is None


async def test_welcome_uses_telegram_language(concierge: Concierge) -> None:
    reply = await concierge.welcome(Guest(1, "Jonas", None, "de"))
    assert reply.language is Language.DE
    assert "Test Hotel" in reply.text


async def test_stats(concierge: Concierge, llm: FakeLLM) -> None:
    llm.answers["Where is the pool?"] = found("Behind the main building.")
    await concierge.handle_guest_message(ANNA, "Where is the pool?")
    await concierge.handle_guest_message(ANNA, "Can I bring my drone?")
    stats = await concierge.stats()
    assert (stats.guests, stats.questions, stats.answered_by_bot, stats.escalated) == (1, 2, 1, 1)
