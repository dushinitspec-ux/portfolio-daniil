"""Telegram commands: /status, /history, /setlimit, /report."""

import re
from html import escape

from aiogram import Dispatcher, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import BotCommand, BufferedInputFile, Message

from app.config import Settings
from app.messages import format_report, format_status
from app.models import LIMIT_RANGE, SENSOR_ID_PATTERN
from app.service import FridgeService, SensorNotFoundError

_SENSOR_ID = re.compile(SENSOR_ID_PATTERN)
MAX_HISTORY_HOURS = 168

HELP_TEXT = (
    "🧊 <b>Fridge Alert Bot</b>\n\n"
    "/status — current temperature of every fridge\n"
    "/history &lt;sensor&gt; [hours] — temperature chart (default 24 h)\n"
    "/setlimit &lt;sensor&gt; &lt;°C&gt; — change the alert limit\n"
    "/report — summary of the last 24 hours\n"
    "/id — show this chat's id (needed for setup)"
)

BOT_COMMANDS = [
    BotCommand(command="status", description="Current temperature of every fridge"),
    BotCommand(command="history", description="Chart: /history <sensor> [hours]"),
    BotCommand(command="setlimit", description="Change limit: /setlimit <sensor> <°C>"),
    BotCommand(command="report", description="Summary of the last 24 hours"),
    BotCommand(command="help", description="How to use the bot"),
]


class CommandArgsError(ValueError):
    """Bad command arguments; the message is shown to the user."""


def parse_history_args(args: str | None) -> tuple[str, int]:
    parts = (args or "").split()
    if not parts or len(parts) > 2:
        raise CommandArgsError("Usage: /history &lt;sensor&gt; [hours]")
    sensor_id = parts[0]
    if not _SENSOR_ID.match(sensor_id):
        raise CommandArgsError("Sensor names use letters, digits, dot, dash and underscore.")
    hours = 24
    if len(parts) == 2:
        if not parts[1].isdigit() or not 1 <= int(parts[1]) <= MAX_HISTORY_HOURS:
            raise CommandArgsError(f"Hours must be a whole number from 1 to {MAX_HISTORY_HOURS}.")
        hours = int(parts[1])
    return sensor_id, hours


def parse_setlimit_args(args: str | None) -> tuple[str, float]:
    parts = (args or "").split()
    if len(parts) != 2:
        raise CommandArgsError(
            "Usage: /setlimit &lt;sensor&gt; &lt;°C&gt;, e.g. /setlimit bar-fridge 6"
        )
    sensor_id, raw = parts
    if not _SENSOR_ID.match(sensor_id):
        raise CommandArgsError("Sensor names use letters, digits, dot, dash and underscore.")
    try:
        limit = float(raw.replace(",", "."))  # "4,5" is how many people type decimals
    except ValueError:
        raise CommandArgsError(f"'{escape(raw)}' is not a number.") from None
    low, high = LIMIT_RANGE
    if not low <= limit <= high:
        raise CommandArgsError(f"The limit must be between {low:.0f} and {high:.0f} °C.")
    return sensor_id, limit


class AllowedChat(Filter):
    """Only configured chats may read data or change limits."""

    async def __call__(self, message: Message, settings: Settings) -> bool:
        allowed = settings.command_chat_ids
        return not allowed or message.chat.id in allowed


async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


async def cmd_id(message: Message) -> None:
    await message.answer(f"This chat's id: <code>{message.chat.id}</code>")


async def cmd_status(message: Message, service: FridgeService) -> None:
    await message.answer(format_status(await service.statuses()))


async def _known_sensors(service: FridgeService) -> str:
    ids = await service.sensor_ids()
    return ", ".join(escape(i) for i in ids) if ids else "none yet"


async def cmd_history(message: Message, command: CommandObject, service: FridgeService) -> None:
    try:
        sensor_id, hours = parse_history_args(command.args)
    except CommandArgsError as exc:
        await message.answer(f"{exc}\nSensors: {await _known_sensors(service)}")
        return
    try:
        png = await service.history_chart(sensor_id, hours)
    except SensorNotFoundError:
        await message.answer(
            f"Unknown sensor '{escape(sensor_id)}'. Sensors: {await _known_sensors(service)}"
        )
        return
    await message.answer_photo(
        BufferedInputFile(png, filename=f"{sensor_id}.png"),
        caption=f"{escape(sensor_id)} — last {hours} h",
    )


async def cmd_setlimit(message: Message, command: CommandObject, service: FridgeService) -> None:
    try:
        sensor_id, limit = parse_setlimit_args(command.args)
    except CommandArgsError as exc:
        await message.answer(str(exc))
        return
    sensor = await service.set_limit(sensor_id, limit)
    await message.answer(f"✅ Limit for <b>{escape(sensor.sensor_id)}</b> is now {limit:.1f} °C.")


async def cmd_report(message: Message, service: FridgeService, settings: Settings) -> None:
    await message.answer(format_report(await service.report(), settings.tz))


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
