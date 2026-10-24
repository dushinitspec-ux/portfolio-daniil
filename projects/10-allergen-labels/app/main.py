"""Runs the web UI: dishes, confirmation and the printable menu."""

import logging

import uvicorn

from app.config import Settings
from app.db import Repository
from app.demo import seed
from app.llm import create_suggester
from app.service import Kitchen, utcnow
from app.web import create_app

logger = logging.getLogger("allergens")


async def serve(settings: Settings) -> None:
    repo = await Repository.connect(settings.db_path)
    kitchen = Kitchen(repo, create_suggester(settings))
    if settings.demo_mode:
        added = await seed(kitchen, utcnow())
        if added:
            logger.info("Demo mode: added %d sample dishes.", added)
    if not settings.ai_enabled:
        logger.info("AI suggestions are off: unknown ingredients are flagged for the chef.")
    app = create_app(kitchen, title=settings.menu_title, tz=settings.tz, demo=settings.demo_mode)
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
    logger.info("Open http://127.0.0.1:%d", settings.port)
    try:
        await server.serve()
    finally:
        await repo.close()
