"""End-to-end through aiogram's Dispatcher with a fake network session (no Telegram)."""

import itertools
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User

from app.bot import Feedback, create_dispatcher
from app.config import Settings
from app.copilot import Copilot
from app.db import Repository, Resolution

IT_CHAT = -100500
EMPLOYEE_ID = 7
OTHER_ID = 8


class RecordingSession(BaseSession):
    """Answers every Bot API call locally and remembers what was sent."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self._ids = itertools.count(1000)

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 - signature defined by aiogram
    ) -> Any:
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=next(self._ids),
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id), type="private"),
                text=method.text,
            )
        return True  # sendChatAction, answerCallbackQuery, editMessageReplyMarkup

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError
        yield b""

    async def close(self) -> None:
        pass

    def sent(self, chat_id: int) -> list[SendMessage]:
        return [m for m in self.calls if isinstance(m, SendMessage) and m.chat_id == chat_id]

    def texts(self, chat_id: int) -> list[str]:
        return [m.text for m in self.sent(chat_id)]


_ids = itertools.count(1)


def user(user_id: int = EMPLOYEE_ID) -> User:
    return User(id=user_id, is_bot=False, first_name="Erika", last_name="Mustermann")


def text_update(text: str, user_id: int = EMPLOYEE_ID) -> Update:
    return Update(
        update_id=next(_ids),
        message=Message(
            message_id=next(_ids),
            date=datetime.now(UTC),
            chat=Chat(id=user_id, type="private"),
            from_user=user(user_id),
            text=text,
        ),
    )


def button_update(data: Feedback, user_id: int = EMPLOYEE_ID) -> Update:
    answer = Message(
        message_id=1000,
        date=datetime.now(UTC),
        chat=Chat(id=EMPLOYEE_ID, type="private"),
        text="answer",
    )
    return Update(
        update_id=next(_ids),
        callback_query=CallbackQuery(
            id=str(next(_ids)),
            from_user=user(user_id),
            chat_instance="ci",
            message=answer,
            data=data.pack(),
        ),
    )


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(session: RecordingSession) -> Bot:
    return Bot("42:TEST", session=session)


@pytest.fixture
def dispatcher(copilot: Copilot, settings: Settings) -> Dispatcher:
    return create_dispatcher(copilot, settings)


async def test_start_says_it_is_an_ai(
    bot: Bot, session: RecordingSession, dispatcher: Dispatcher
) -> None:
    await dispatcher.feed_update(bot, text_update("/start"))
    text = session.texts(EMPLOYEE_ID)[0]
    assert "I'm an AI system, not a person" in text
    assert "Sample Office" in text


async def test_answer_has_sources_ai_label_and_buttons(
    bot: Bot, session: RecordingSession, dispatcher: Dispatcher
) -> None:
    await dispatcher.feed_update(bot, text_update("How do I connect to the VPN from home?"))

    reply = session.sent(EMPLOYEE_ID)[0]
    assert "Sources:\n[1] VPN for remote work" in reply.text
    assert "AI-generated answer" in reply.text
    buttons = reply.reply_markup.inline_keyboard[0]  # type: ignore[union-attr]
    assert [b.text for b in buttons] == ["✅ Solved", "🎫 Create ticket"]
    assert session.texts(IT_CHAT) == []


async def test_unknown_question_becomes_a_ticket_and_it_is_notified(
    bot: Bot, session: RecordingSession, dispatcher: Dispatcher
) -> None:
    await dispatcher.feed_update(bot, text_update("My monitor shows vertical stripes"))

    assert "instead of guessing" in session.texts(EMPLOYEE_ID)[0]
    assert "🎫 Ticket #1" in session.texts(EMPLOYEE_ID)[0]
    notification = session.texts(IT_CHAT)[0]
    assert "New Ticket #1" in notification
    assert "From: Erika Mustermann (Telegram id 7)" in notification


async def test_solved_button(
    bot: Bot, session: RecordingSession, dispatcher: Dispatcher, repo: Repository
) -> None:
    await dispatcher.feed_update(bot, text_update("How do I connect to the VPN from home?"))
    await dispatcher.feed_update(bot, button_update(Feedback(action="solved", question_id=1)))

    assert any(isinstance(c, EditMessageReplyMarkup) for c in session.calls)
    assert session.texts(EMPLOYEE_ID)[-1].startswith("Great, glad it helped")
    record = await repo.get_question(1)
    assert record is not None and record.resolution is Resolution.SOLVED


async def test_create_ticket_button(
    bot: Bot, session: RecordingSession, dispatcher: Dispatcher
) -> None:
    await dispatcher.feed_update(bot, text_update("How do I connect to the VPN from home?"))
    await dispatcher.feed_update(bot, button_update(Feedback(action="ticket", question_id=1)))

    assert "Sorry the answer didn't help" in session.texts(EMPLOYEE_ID)[-1]
    assert "the answer did not help" in session.texts(IT_CHAT)[0]


async def test_button_of_someone_else_is_refused(
    bot: Bot, session: RecordingSession, dispatcher: Dispatcher, repo: Repository
) -> None:
    await dispatcher.feed_update(bot, text_update("How do I connect to the VPN from home?"))
    await dispatcher.feed_update(
        bot, button_update(Feedback(action="ticket", question_id=1), user_id=OTHER_ID)
    )

    alert = next(c for c in session.calls if isinstance(c, AnswerCallbackQuery))
    assert alert.show_alert
    assert (await repo.stats()).tickets == 0


async def test_ticket_command(bot: Bot, session: RecordingSession, dispatcher: Dispatcher) -> None:
    await dispatcher.feed_update(bot, text_update("/ticket"))
    assert "Write the problem after the command" in session.texts(EMPLOYEE_ID)[-1]

    await dispatcher.feed_update(
        bot, text_update("/ticket The scanner on floor 1 makes a loud noise")
    )
    assert "🎫 Ticket #1 · P3 · hardware" in session.texts(EMPLOYEE_ID)[-1]
    assert len(session.texts(IT_CHAT)) == 1


async def test_other_commands_and_photos_are_not_questions(
    bot: Bot, session: RecordingSession, dispatcher: Dispatcher, repo: Repository
) -> None:
    await dispatcher.feed_update(bot, text_update("/reload"))
    photo = Update(
        update_id=next(_ids),
        message=Message(
            message_id=next(_ids),
            date=datetime.now(UTC),
            chat=Chat(id=EMPLOYEE_ID, type="private"),
            from_user=user(),
            photo=[PhotoSize(file_id="f", file_unique_id="u", width=10, height=10)],
        ),
    )
    await dispatcher.feed_update(bot, photo)

    texts = session.texts(EMPLOYEE_ID)
    assert "I'm the IT assistant" in texts[0]
    assert "text message" in texts[1]
    assert (await repo.stats()).questions == 0
