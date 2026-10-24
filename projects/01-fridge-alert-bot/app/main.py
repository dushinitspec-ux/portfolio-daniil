"""Entry point: runs the HTTP API, the Telegram bot and the daily report in one process."""

import asyncio
import contextlib
import logging

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.api import create_app
from app.bot import BOT_COMMANDS, create_dispatcher
from app.config import Settings, get_settings
from app.db import Repository
from app.notifier import ConsoleNotifier, Notifier, TelegramNotifier
from app.scheduler import parse_hhmm, run_daily
from app.service import FridgeService

logger = logging.getLogger("fridge")


async def run(settings: Settings) -> None:
    repo = await Repository.connect(settings.database_path)
    bot: Bot | None = None
    notifier: Notifier = ConsoleNotifier()

    if settings.telegram_enabled:
        bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        if settings.alert_chat_id is not None:
            notifier = TelegramNotifier(bot, settings.alert_chat_id)
        else:
            logger.warning(
                "ALERT_CHAT_ID is not set: alerts go to the console. Send /id to the bot."
            )
    else:
        logger.warning("BOT_TOKEN is not set: demo mode, alerts are printed to the console.")

    if not settings.api_key:
        logger.warning("API_KEY is not set: anyone who can reach the API can post readings.")

    service = FridgeService(repo, notifier, settings)
    server = uvicorn.Server(
        uvicorn.Config(create_app(service, settings), host=settings.host, port=settings.port)
    )

    background: list[asyncio.Task[None]] = []
    report_time = parse_hhmm(settings.daily_report_time)
    if report_time:
        background.append(
            asyncio.create_task(run_daily(service.send_daily_report, report_time, settings.tz))
        )
    if bot:
        dispatcher = create_dispatcher(service, settings)
        with contextlib.suppress(Exception):
            await bot.set_my_commands(BOT_COMMANDS)
        # uvicorn owns Ctrl+C handling, so aiogram must not install its own signal handlers.
        background.append(asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False)))

    try:
        await server.serve()
    finally:
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        if bot:
            await bot.session.close()
        await repo.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
