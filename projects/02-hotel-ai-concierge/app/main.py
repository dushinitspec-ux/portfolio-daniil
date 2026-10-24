"""Entry point: runs the Telegram bot."""

import asyncio
import logging
import sys

from aiogram import Bot

from app.bot import BOT_COMMANDS, create_dispatcher
from app.concierge import Concierge
from app.config import Settings, get_settings
from app.db import Repository
from app.knowledge import KnowledgeBase
from app.llm import create_llm

logger = logging.getLogger("concierge")


async def run(settings: Settings) -> None:
    knowledge = KnowledgeBase(settings.knowledge_path)
    repo = await Repository.connect(settings.database_path)
    concierge = Concierge(create_llm(settings), knowledge, repo, settings)
    bot = Bot(settings.bot_token)

    logger.info(
        "LLM provider: %s. Knowledge base: %d topics.",
        settings.llm_provider,
        len(knowledge.sections),
    )
    if settings.staff_chat_id is None:
        logger.warning(
            "STAFF_CHAT_ID is not set: unknown questions cannot reach staff. "
            "Add the bot to the staff group, send /id there and put the number in .env."
        )
    if not settings.admin_ids:
        logger.warning("ADMIN_IDS is not set: nobody can use /reload and /stats.")

    try:
        await bot.set_my_commands(BOT_COMMANDS)
        await create_dispatcher(concierge, knowledge, settings).start_polling(bot)
    finally:
        await bot.session.close()
        await repo.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    if not settings.bot_token:
        sys.exit(
            "BOT_TOKEN is not set. Put your bot token in .env, "
            "or try the offline demo: uv run python -m app.demo"
        )
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
