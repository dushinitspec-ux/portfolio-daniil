"""Telegram commands: /status, /history, /setlimit, /report.

The reply texts live in app/commands.py; this module only connects them to aiogram.
"""

from aiogram import Dispatcher, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import BotCommand, BufferedInputFile, Message

from app.commands import (
    HELP_TEXT,
    history_reply,
    id_reply,
    report_reply,
    setlimit_reply,
    status_reply,
)

# Re-exported: these used to be defined here.
from app.commands import CommandArgsError as CommandArgsError
from app.commands import parse_history_args as parse_history_args
from app.commands import parse_setlimit_args as parse_setlimit_args
from app.config import Settings
from app.service import FridgeService

BOT_COMMANDS = [
    BotCommand(command="status", description="Current temperature of every fridge"),
    BotCommand(command="history", description="Chart: /history <sensor> [hours]"),
    BotCommand(command="setlimit", description="Change limit: /setlimit <sensor> <°C>"),
    BotCommand(command="report", description="Summary of the last 24 hours"),
    BotCommand(command="help", description="How to use the bot"),
]


class AllowedChat(Filter):
    """Only configured chats may read data or change limits."""

    async def __call__(self, message: Message, settings: Settings) -> bool:
        allowed = settings.command_chat_ids
        return not allowed or message.chat.id in allowed


async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


async def cmd_id(message: Message) -> None:
    await message.answer(id_reply(message.chat.id))


async def cmd_status(message: Message, service: FridgeService) -> None:
    await message.answer(await status_reply(service))


async def cmd_history(message: Message, command: CommandObject, service: FridgeService) -> None:
    reply = await history_reply(service, command.args, service.history_chart)
    if isinstance(reply, str):
        await message.answer(reply)
        return
    await message.answer_photo(
        BufferedInputFile(reply.chart, filename=f"{reply.sensor_id}.png"),
        caption=reply.caption,
    )


async def cmd_setlimit(message: Message, command: CommandObject, service: FridgeService) -> None:
    await message.answer(await setlimit_reply(service, command.args))


async def cmd_report(message: Message, service: FridgeService, settings: Settings) -> None:
    await message.answer(await report_reply(service, settings.tz))


def create_router() -> Router:
    router = Router(name="fridge")
    # Open to everyone so a new chat can find its id during setup.
    router.message.register(cmd_help, Command("start", "help"))
    router.message.register(cmd_id, Command("id"))
    # Everything below needs an allowed chat.
    router.message.register(cmd_status, Command("status"), AllowedChat())
    router.message.register(cmd_history, Command("history"), AllowedChat())
    router.message.register(cmd_setlimit, Command("setlimit"), AllowedChat())
    router.message.register(cmd_report, Command("report"), AllowedChat())
    return router


def create_dispatcher(service: FridgeService, settings: Settings) -> Dispatcher:
    # Keyword arguments become "workflow data", injected into handlers by parameter name.
    dispatcher = Dispatcher(service=service, settings=settings)
    dispatcher.include_router(create_router())
    return dispatcher
