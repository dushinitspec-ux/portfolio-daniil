"""Wiring: settings -> detector, policy, LLM, audit log -> gateway -> web app."""

import logging

import uvicorn

from app.audit import AuditLog
from app.config import Settings
from app.detectors import Detector, load_names
from app.gateway import Gateway
from app.guard import Guard
from app.llm import create_llm
from app.policy import load_policy
from app.web import create_app

logger = logging.getLogger("pii_guard")


def build_guard(settings: Settings) -> Guard:
    names = load_names(settings.effective_names_file)
    detector = Detector(phone_regions=settings.phone_regions, names=names)
    return Guard(detector, load_policy(settings.policy_file))


async def serve(settings: Settings) -> None:
    guard = build_guard(settings)
    audit = await AuditLog.connect(settings.database_path)
    gateway = Gateway(guard, create_llm(settings), audit)
    app = create_app(gateway, settings.max_input_chars, demo=settings.demo_mode)

    if settings.demo_mode:
        logger.info("Demo mode: answers come from the offline demo model, no API key needed.")
    logger.info(
        "Model: %s. Policy: %s. Open http://127.0.0.1:%d",
        gateway.llm.name,
        settings.policy_file,
        settings.port,
    )
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
    try:
        await server.serve()
    finally:
        await audit.close()
