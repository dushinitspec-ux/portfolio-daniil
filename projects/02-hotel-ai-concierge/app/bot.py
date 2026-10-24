"""Telegram layer: guests in private chats, staff in a group, admins anywhere."""

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart, Filter
from aiogram.types import BotCommand, Message
from aiogram.utils.chat_action import ChatActionSender

from app.concierge import Concierge, Guest, GuestReply
from app.config import Settings
from app.knowledge import KnowledgeBase, KnowledgeBaseError
from app.ratelimit import SlidingWindowLimiter
from app.texts import ESCALATION_UNAVAILABLE, RATE_LIMITED, TEXT_ONLY

logger = logging.getLogger(__name__)

BOT_COMMANDS = [BotCommand(command="start", description="Start / Начать / Başla / Starten")]


class IsAdmin(Filter):
    async def __call__(self, message: Message, settings: Settings) -> bool:
        return message.from_user is not None and message.from_user.id in settings.admin_ids


class IsStaffChat(Filter):
    async def __call__(self, message: Message, settings: Settings) -> bool:
        return settings.staff_chat_id is not None and message.chat.id == settings.staff_chat_id


def guest_from(message: Message) -> Guest:
    user = message.from_user
    return Guest(
        chat_id=message.chat.id,
        name=user.full_name if user else "Guest",
        username=user.username if user else None,
        telegram_language=user.language_code if user else None,
    )


async def forward_to_staff(
    bot: Bot, settings: Settings, concierge: Concierge, reply: GuestReply
) -> bool:
    """Post the question in the staff chat. False if it could not be delivered."""
    if settings.staff_chat_id is None or reply.escalation_id is None or not reply.staff_text:
        logger.error("STAFF_CHAT_ID is not set: question #%s reached nobody", reply.escalation_id)
        return False
    try:
        sent = await bot.send_message(settings.staff_chat_id, reply.staff_text)
    except TelegramAPIError:
        logger.exception("Could not post question #%s to the staff chat", reply.escalation_id)
        return False
    await concierge.attach_staff_message(reply.escalation_id, sent.message_id)
    return True


# Commands


async def cmd_start(message: Message, concierge: Concierge) -> None:
    reply = await concierge.welcome(guest_from(message))
    await message.answer(reply.text)


async def cmd_id(message: Message) -> None:
    await message.answer(f"This chat's id: {message.chat.id}")


async def cmd_reload(message: Message, knowledge: KnowledgeBase) -> None:
    try:
        snapshot = knowledge.reload()
    except KnowledgeBaseError as exc:
        await message.answer(f"⚠️ Reload failed, the old knowledge base is still in use: {exc}")
        return
    await message.answer(
        f"✅ Knowledge base reloaded: {len(snapshot.sections)} topics, "
        f"{len(snapshot.text):,} characters."
    )


async def cmd_stats(message: Message, concierge: Concierge) -> None:
    s = await concierge.stats()
    share = f" ({s.answered_by_bot / s.questions:.0%})" if s.questions else ""
    await message.answer(
        f"Guests: {s.guests}\nQuestions: {s.questions}\n"
        f"Answered by the bot: {s.answered_by_bot}{share}\n"
        f"Passed to staff: {s.escalated} (still open: {s.open_escalations})"
    )


# Staff


async def on_staff_reply(message: Message, bot: Bot, concierge: Concierge) -> None:
    assert message.reply_to_message is not None and message.text is not None
    result = await concierge.handle_staff_reply(message.reply_to_message.message_id, message.text)
    if result is None:
        return  # a reply to something other than a guest question
    try:
        await bot.send_message(result.guest_chat_id, result.guest_text)
    except TelegramAPIError as exc:
        await message.reply(f"⚠️ Could not deliver to the guest: {exc}")
        return
    await message.reply(result.confirmation)


# Guests


async def on_guest_text(
    message: Message,
    bot: Bot,
    concierge: Concierge,
    settings: Settings,
    limiter: SlidingWindowLimiter,
) -> None:
    assert message.text is not None
    guest = guest_from(message)
    if not limiter.allow(guest.chat_id):
        language = await concierge.guest_language(guest, message.text)
        await message.answer(RATE_LIMITED[language])
        return

    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        reply = await concierge.handle_guest_message(guest, message.text)
        text = reply.text
        if reply.escalation_id is not None and not await forward_to_staff(
            bot, settings, concierge, reply
        ):
            text = ESCALATION_UNAVAILABLE[reply.language]
    await message.answer(text)


async def on_guest_other(message: Message, concierge: Concierge) -> None:
    language = await concierge.guest_language(guest_from(message))
    await message.answer(TEXT_ONLY[language])


def create_router() -> Router:
    router = Router(name="concierge")
    private = F.chat.type == ChatType.PRIVATE

    router.message.register(cmd_start, CommandStart(), private)
    router.message.register(cmd_id, Command("id"))
    router.message.register(cmd_reload, Command("reload"), IsAdmin())
    router.message.register(cmd_stats, Command("stats"), IsAdmin())
    router.message.register(on_staff_reply, IsStaffChat(), F.reply_to_message, F.text)
    # /help or a command the guest may not use: show the welcome text, do not ask the LLM.
    router.message.register(cmd_start, private, F.text.startswith("/"))
    router.message.register(on_guest_text, private, F.text)
    router.message.register(on_guest_other, private)
    return router


def create_dispatcher(
    concierge: Concierge, knowledge: KnowledgeBase, settings: Settings
) -> Dispatcher:
    # Keyword arguments become "workflow data", injected into handlers by parameter name.
    dispatcher = Dispatcher(
        concierge=concierge,
        knowledge=knowledge,
        settings=settings,
        limiter=SlidingWindowLimiter(settings.rate_limit_per_minute),
    )
    dispatcher.include_router(create_router())
    return dispatcher
