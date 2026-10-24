"""End-to-end through aiogram's Dispatcher with a fake network session (no Telegram)."""

import itertools
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update, User

from app.bot import create_dispatcher
from app.concierge import Concierge
from app.config import Settings
from app.knowledge import KnowledgeBase
from tests.conftest import FakeLLM, found

STAFF_CHAT = -100500
GUEST_ID = 7
ADMIN_ID = 99


class RecordingSession(BaseSession):
    """Answers every Bot API call locally and remembers the messages that were sent."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[SendMessage] = []
        self._ids = itertools.count(1000)

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 - signature defined by aiogram
    ) -> Any:
        if isinstance(method, SendMessage):
            self.sent.append(method)
            return Message(
                message_id=next(self._ids),
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id), type="private"),
                text=method.text,
            )
        return True  # sendChatAction and friends

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError
        yield b""

    async def close(self) -> None:
        pass

    def texts_to(self, chat_id: int) -> list[str]:
        return [m.text for m in self.sent if m.chat_id == chat_id]


_update_ids = itertools.count(1)


def update(
    chat_id: int,
    user_id: int,
    text: str,
    chat_type: str = "private",
    reply_to: int | None = None,
) -> Update:
    user = User(id=user_id, is_bot=False, first_name="Ivan", language_code="ru")
    chat = Chat(id=chat_id, type=chat_type)
    replied = None
    if reply_to is not None:
        replied = Message(message_id=reply_to, date=datetime.now(UTC), chat=chat, text="q")
    return Update(
        update_id=next(_update_ids),
        message=Message(
            message_id=next(_update_ids),
            date=datetime.now(UTC),
            chat=chat,
            from_user=user,
            text=text,
            reply_to_message=replied,
        ),
    )


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(session: RecordingSession) -> Bot:
    return Bot("42:TEST", session=session)


async def test_guest_question_answered(
    bot: Bot,
    session: RecordingSession,
    concierge: Concierge,
    knowledge: KnowledgeBase,
    settings: Settings,
    llm: FakeLLM,
) -> None:
    llm.answers["Во сколько завтрак?"] = found("Завтрак с 07:00 до 10:00.")
    dispatcher = create_dispatcher(concierge, knowledge, settings)

    await dispatcher.feed_update(bot, update(GUEST_ID, GUEST_ID, "Во сколько завтрак?"))

    assert session.texts_to(GUEST_ID) == ["Завтрак с 07:00 до 10:00."]
    assert session.texts_to(STAFF_CHAT) == []


async def test_unknown_question_round_trip_through_staff(
    bot: Bot,
    session: RecordingSession,
    concierge: Concierge,
    knowledge: KnowledgeBase,
    settings: Settings,
) -> None:
    dispatcher = create_dispatcher(concierge, knowledge, settings)

    await dispatcher.feed_update(bot, update(GUEST_ID, GUEST_ID, "Можно торт в номер?"))
    staff_messages = [m for m in session.sent if m.chat_id == STAFF_CHAT]
    assert len(staff_messages) == 1
    assert "Можно торт в номер?" in staff_messages[0].text
    assert "ресепшен" in session.texts_to(GUEST_ID)[0]

    # The posted question got message id 1000 (first sendMessage); staff reply to it.
    await dispatcher.feed_update(
        bot, update(STAFF_CHAT, 555, "Yes, order it a day before.", "supergroup", reply_to=1000)
    )
    guest_texts = session.texts_to(GUEST_ID)
    assert "[ru] Yes, order it a day before." in guest_texts[-1]
    assert "✅ Sent to the guest" in session.texts_to(STAFF_CHAT)[-1]


async def test_reload_is_admin_only(
    bot: Bot,
    session: RecordingSession,
    concierge: Concierge,
    knowledge: KnowledgeBase,
    settings: Settings,
) -> None:
    settings.admin_ids = [ADMIN_ID]
    dispatcher = create_dispatcher(concierge, knowledge, settings)

    await dispatcher.feed_update(bot, update(ADMIN_ID, ADMIN_ID, "/reload"))
    assert "Knowledge base reloaded" in session.texts_to(ADMIN_ID)[-1]

    # A guest gets the welcome text, and nothing is sent to staff or the LLM.
    await dispatcher.feed_update(bot, update(GUEST_ID, GUEST_ID, "/reload"))
    assert "виртуальный консьерж" in session.texts_to(GUEST_ID)[-1]
    assert session.texts_to(STAFF_CHAT) == []


async def test_rate_limit(
    bot: Bot,
    session: RecordingSession,
    concierge: Concierge,
    knowledge: KnowledgeBase,
    settings: Settings,
) -> None:
    settings.rate_limit_per_minute = 2
    dispatcher = create_dispatcher(concierge, knowledge, settings)
    for _ in range(3):
        await dispatcher.feed_update(bot, update(GUEST_ID, GUEST_ID, "Где бассейн?"))
    assert "слишком часто" in session.texts_to(GUEST_ID)[-1]
