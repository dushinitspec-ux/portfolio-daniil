from dataclasses import dataclass, field

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage

from app.bot import forward_to_staff
from app.concierge import Concierge, Guest
from app.config import Settings

GUEST = Guest(chat_id=7, name="Ivan", username=None, telegram_language="ru")


@dataclass
class SentMessage:
    message_id: int


@dataclass
class FakeBot:
    fail: bool = False
    sent: list[tuple[int, str]] = field(default_factory=list)

    async def send_message(self, chat_id: int, text: str) -> SentMessage:
        if self.fail:
            raise TelegramBadRequest(SendMessage(chat_id=chat_id, text=text), "chat not found")
        self.sent.append((chat_id, text))
        return SentMessage(message_id=900 + len(self.sent))


async def test_question_is_posted_and_linked(concierge: Concierge, settings: Settings) -> None:
    bot = FakeBot()
    reply = await concierge.handle_guest_message(GUEST, "Можно торт в номер?")

    assert await forward_to_staff(bot, settings, concierge, reply)  # type: ignore[arg-type]
    assert bot.sent[0][0] == settings.staff_chat_id
    # A staff reply to that message now reaches the guest.
    assert await concierge.handle_staff_reply(901, "Да") is not None


async def test_no_staff_chat_means_not_delivered(concierge: Concierge, settings: Settings) -> None:
    settings.staff_chat_id = None
    reply = await concierge.handle_guest_message(GUEST, "Можно торт в номер?")
    assert not await forward_to_staff(FakeBot(), settings, concierge, reply)  # type: ignore[arg-type]


async def test_telegram_error_means_not_delivered(concierge: Concierge, settings: Settings) -> None:
    reply = await concierge.handle_guest_message(GUEST, "Можно торт в номер?")
    bot = FakeBot(fail=True)
    assert not await forward_to_staff(bot, settings, concierge, reply)  # type: ignore[arg-type]
