"""Command line: run the web page and the bot, evaluate, or ask one question.

uv run python -m app                    # web page on :8106 (+ Telegram bot if BOT_TOKEN)
uv run python -m app --demo             # same, offline, with sample tickets
uv run python -m app eval [--ablation] [--holdout] [--llm]
uv run python -m app --demo ask "How do I connect to the VPN?"
"""

import argparse
import asyncio
import io
import logging
import sys
from pathlib import Path

import uvicorn
from aiogram import Bot

from app.bot import BOT_COMMANDS, create_dispatcher
from app.citations import format_sources
from app.config import Settings, get_settings
from app.copilot import Copilot
from app.db import Repository
from app.demo import seed
from app.evaluate import run as run_eval
from app.knowledge import KnowledgeBaseError, load_documents
from app.llm import create_llm
from app.llm.demo import DemoLLM
from app.retrieval import Retriever
from app.web import create_app

logger = logging.getLogger("helpdesk")


def build_retriever(settings: Settings) -> Retriever:
    return Retriever(
        load_documents(settings.knowledge_dir),
        min_score=settings.min_score,
        min_coverage=settings.min_coverage,
    )


async def serve(settings: Settings) -> None:
    retriever = build_retriever(settings)
    repo = await Repository.connect(settings.database_path)
    copilot = Copilot(retriever, create_llm(settings), repo, top_k=settings.top_k)
    if settings.demo_mode and not await repo.has_tickets():
        await seed(copilot)

    app = create_app(copilot, settings.tz, settings.company_name, demo=settings.demo_mode)
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
    logger.info(
        "Knowledge base: %d sections. Answers: %s. Page: http://127.0.0.1:%d",
        len(retriever.sections),
        copilot.llm.name,
        settings.port,
    )

    bot: Bot | None = None
    tasks = [asyncio.create_task(server.serve())]
    if settings.bot_token:
        bot = Bot(settings.bot_token)
        await bot.set_my_commands(BOT_COMMANDS)
        dispatcher = create_dispatcher(copilot, settings)
        tasks.append(asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False)))
        if settings.it_chat_id is None:
            logger.warning("IT_CHAT_ID is not set: new tickets are only shown on the web page.")
    else:
        logger.warning("BOT_TOKEN is not set: only the web page runs.")
    try:
        # The web server stops on Ctrl+C; then the bot is stopped too.
        await tasks[0]
    finally:
        for task in tasks[1:]:
            task.cancel()
        await asyncio.gather(*tasks[1:], return_exceptions=True)
        if bot:
            await bot.session.close()
        await repo.close()


async def ask_once(settings: Settings, question: str) -> str:
    repo = await Repository.connect(":memory:")
    try:
        copilot = Copilot(
            build_retriever(settings), create_llm(settings), repo, top_k=settings.top_k
        )
        reply = await copilot.preview(question)
    finally:
        await repo.close()
    d = reply.decision
    lines = [f"Coverage {d.retrieval.coverage_label}"]
    if reply.answered:
        lines += ["", d.answer, "", format_sources(d.sources)]
    if reply.triage:
        t = reply.triage
        lines += ["", f"Ticket: {t.priority} {t.category} - {t.summary}", f"Why: {d.ticket_reason}"]
    return "\n".join(lines)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app", description="Helpdesk Copilot")
    parser.add_argument("--demo", action="store_true", help="offline demo mode (no API key)")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="web page and Telegram bot (default)")
    ev = sub.add_parser("eval", help="evaluate retrieval and routing on eval/questions.yaml")
    ev.add_argument("--file", type=Path, default=Path("eval/questions.yaml"))
    ev.add_argument("--ablation", action="store_true", help="show what each step adds")
    ev.add_argument("--holdout", action="store_true", help="use the held-out questions")
    ev.add_argument("--llm", action="store_true", help="answer with Claude (costs API calls)")
    ask = sub.add_parser("ask", help="answer one question in the terminal (nothing is saved)")
    ask.add_argument("question")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    # Russian and Turkish text must print even when output goes to a pipe on Windows.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = parse_args(argv)
    settings = get_settings()
    if args.demo:
        settings = settings.model_copy(update={"demo_mode": True})

    try:
        if args.command == "eval":
            if args.llm and (settings.demo_mode or not settings.anthropic_api_key):
                sys.exit("--llm needs DEMO_MODE=false and ANTHROPIC_API_KEY.")
            llm = create_llm(settings) if args.llm else DemoLLM()
            report = asyncio.run(
                run_eval(
                    load_documents(settings.knowledge_dir),
                    llm,
                    args.file,
                    min_score=settings.min_score,
                    min_coverage=settings.min_coverage,
                    top_k=settings.top_k,
                    ablation=args.ablation,
                    holdout=args.holdout,
                )
            )
            print(report)
            return
        if not settings.demo_mode and not settings.anthropic_api_key:
            sys.exit(
                "ANTHROPIC_API_KEY is not set. Put it in .env, or run the offline demo: "
                "uv run python -m app --demo"
            )
        if args.command == "ask":
            print(asyncio.run(ask_once(settings, args.question)))
        else:
            asyncio.run(serve(settings))
    except KnowledgeBaseError as exc:
        sys.exit(f"Knowledge base error: {exc}")


if __name__ == "__main__":
    main()
