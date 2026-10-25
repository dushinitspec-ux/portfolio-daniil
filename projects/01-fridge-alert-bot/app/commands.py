"""What the bot commands answer, without the Telegram library.

app/bot.py wires these into aiogram handlers; the in-browser demo (app/web_demo.py) calls
them directly, so both give exactly the same replies.
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html import escape
from zoneinfo import ZoneInfo

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


def id_reply(chat_id: int) -> str:
    return f"This chat's id: <code>{chat_id}</code>"


async def known_sensors(service: FridgeService) -> str:
    ids = await service.sensor_ids()
    return ", ".join(escape(i) for i in ids) if ids else "none yet"


async def status_reply(service: FridgeService) -> str:
    return format_status(await service.statuses())


@dataclass(frozen=True)
class HistoryChart[T]:
    sensor_id: str
    hours: int
    caption: str
    chart: T


async def history_reply[T](
    service: FridgeService, args: str | None, render: Callable[[str, int], Awaitable[T]]
) -> str | HistoryChart[T]:
    """The chart drawn by `render(sensor_id, hours)`, or an error text to send instead."""
    try:
        sensor_id, hours = parse_history_args(args)
    except CommandArgsError as exc:
        return f"{exc}\nSensors: {await known_sensors(service)}"
    try:
        chart = await render(sensor_id, hours)
    except SensorNotFoundError:
        return f"Unknown sensor '{escape(sensor_id)}'. Sensors: {await known_sensors(service)}"
    return HistoryChart(sensor_id, hours, f"{escape(sensor_id)} — last {hours} h", chart)


async def setlimit_reply(service: FridgeService, args: str | None) -> str:
    try:
        sensor_id, limit = parse_setlimit_args(args)
    except CommandArgsError as exc:
        return str(exc)
    sensor = await service.set_limit(sensor_id, limit)
    return f"✅ Limit for <b>{escape(sensor.sensor_id)}</b> is now {limit:.1f} °C."


async def report_reply(service: FridgeService, tz: ZoneInfo) -> str:
    return format_report(await service.report(), tz)
