"""Telegram commands: /today and /tomorrow show a plan, /start explains the bot.

The daily message is sent by scheduler.DailyPlanSender; these commands are for asking
again later. Only the configured chat gets answers (if PLAN_CHAT_ID is set).
"""

from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command, Filter
from aiogram.types import BotCommand, Message

from app.messages import format_plan
from app.service import PlanService

HELP_TEXT = (
    "⚡ Energy Saver\n\n"
    "Every afternoon, once the day-ahead prices are published, I send tomorrow's plan: "
    "when each device runs and how much that saves.\n\n"
    "/today — today's plan\n"
    "/tomorrow — tomorrow's plan (from about 13:00)\n"
    "/id — this chat's id, for PLAN_CHAT_ID"
)

BOT_COMMANDS = [
    BotCommand(command="today", description="Today's plan"),
    BotCommand(command="tomorrow", description="Tomorrow's plan"),
    BotCommand(command="help", description="How it works"),
]


async def plan_text(service: PlanService, days_ahead: int, bidding_zone: str) -> str:
    day = service.today() + timedelta(days=days_ahead)
    plan = await service.plan(day)
    return format_plan(plan, bidding_zone, await service.attribution())


class AllowedChat(Filter):
    def __init__(self, chat_id: int | None) -> None:
        self.chat_id = chat_id

    async def __call__(self, message: Message) -> bool:
        return self.chat_id is None or message.chat.id == self.chat_id


def build_router(service: PlanService, bidding_zone: str, chat_id: int | None) -> Router:
    router = Router()

    @router.message(Command("id"))
    async def chat_id_command(message: Message) -> None:
        await message.answer(f"This chat's id: {message.chat.id}")

    allowed = AllowedChat(chat_id)

    @router.message(Command("start", "help"), allowed)
    async def help_command(message: Message) -> None:
        await message.answer(HELP_TEXT)

    @router.message(Command("today"), allowed)
    async def today_command(message: Message) -> None:
        await message.answer(await plan_text(service, 0, bidding_zone))

    @router.message(Command("tomorrow"), allowed)
    async def tomorrow_command(message: Message) -> None:
        await message.answer(await plan_text(service, 1, bidding_zone))

    return router
