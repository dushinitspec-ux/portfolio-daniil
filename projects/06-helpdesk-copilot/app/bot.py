"""Telegram layer: employees ask in a private chat; new tickets go to the IT chat."""

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardMarkup, Message, User
from aiogram.utils.chat_action import ChatActionSender
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import messages
from app.config import Settings
from app.copilot import Copilot, Route
from app.db import Requester, Ticket

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="start", description="What this bot does"),
    BotCommand(command="ticket", description="Open a ticket for the IT team"),
]


class Feedback(CallbackData, prefix="fb"):
    action: str  # "solved" or "ticket"
    question_id: int


def feedback_keyboard(question_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Solved", callback_data=Feedback(action="solved", question_id=question_id)
    )
    builder.button(
        text="🎫 Create ticket", callback_data=Feedback(action="ticket", question_id=question_id)
    )
    return builder.as_markup()


def requester_from(user: User | None) -> Requester:
    if user is None:
        return Requester("Unknown", "telegram")
    return Requester(user.full_name, "telegram", user.id)


async def notify_it(bot: Bot, settings: Settings, ticket: Ticket) -> None:
    """Post a new ticket in the IT chat. A Telegram failure never loses the ticket."""
    if settings.it_chat_id is None:
        return
    try:
        await bot.send_message(settings.it_chat_id, messages.it_notification(ticket))
    except TelegramAPIError:
        logger.exception("Could not post ticket #%s to the IT chat", ticket.id)


# Commands


async def cmd_start(message: Message, settings: Settings) -> None:
    name = message.from_user.first_name if message.from_user else "there"
    await message.answer(messages.welcome(settings.company_name, name))


async def cmd_id(message: Message) -> None:
    await message.answer(f"This chat's id: {message.chat.id}")


async def cmd_ticket(
    message: Message, command: CommandObject, bot: Bot, copilot: Copilot, settings: Settings
) -> None:
    text = (command.args or "").strip()
    if not text:
        await message.answer(messages.TICKET_USAGE)
        return
    ticket = await copilot.open_ticket(text, requester_from(message.from_user))
    await message.answer(messages.ticket_text(ticket, Route.DIRECT))
    await notify_it(bot, settings, ticket)


# Questions


async def on_question(message: Message, bot: Bot, copilot: Copilot, settings: Settings) -> None:
    assert message.text is not None
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        reply = await copilot.ask(message.text, requester_from(message.from_user))

    if reply.answered:
        assert reply.question_id is not None
        await message.answer(
            messages.answer_text(reply, settings.company_name),
            reply_markup=None if reply.ticket else feedback_keyboard(reply.question_id),
        )
    else:
        assert reply.ticket is not None
        await message.answer(messages.ticket_text(reply.ticket, reply.decision.route))
    if reply.ticket is not None:
        await notify_it(bot, settings, reply.ticket)


async def on_other(message: Message) -> None:
    await message.answer(messages.TEXT_ONLY)


# Buttons under an answer


async def on_feedback(
    query: CallbackQuery, callback_data: Feedback, bot: Bot, copilot: Copilot, settings: Settings
) -> None:
    user_id = query.from_user.id
    if callback_data.action == "solved":
        ok = await copilot.mark_solved(callback_data.question_id, user_id)
        reply_text = messages.SOLVED if ok else messages.NOT_YOURS
        ticket = None
    else:
        ticket = await copilot.ticket_for_question(callback_data.question_id, user_id)
        reply_text = messages.ticket_text(ticket, Route.ASKED) if ticket else messages.NOT_YOURS

    if reply_text == messages.NOT_YOURS:
        await query.answer(reply_text, show_alert=True)
        return
    await query.answer()
    if isinstance(query.message, Message):
        # Remove the buttons, so the same answer cannot be rated twice.
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.answer(reply_text)
    if ticket is not None:
        await notify_it(bot, settings, ticket)


def create_router() -> Router:
    router = Router(name="helpdesk")
    private = F.chat.type == ChatType.PRIVATE

    router.message.register(cmd_id, Command("id"))
    router.message.register(cmd_start, CommandStart(), private)
    router.message.register(cmd_start, Command("help"), private)
    router.message.register(cmd_ticket, Command("ticket"), private)
    # Any other command: show the welcome text, do not treat it as an IT question.
    router.message.register(cmd_start, private, F.text.startswith("/"))
    router.message.register(on_question, private, F.text)
    router.message.register(on_other, private)
    router.callback_query.register(on_feedback, Feedback.filter())
    return router


def create_dispatcher(copilot: Copilot, settings: Settings) -> Dispatcher:
    # Keyword arguments become "workflow data", injected into handlers by parameter name.
    dispatcher = Dispatcher(copilot=copilot, settings=settings)
    dispatcher.include_router(create_router())
    return dispatcher
