"""Command line.

python -m app                start the gateway (settings from .env)
python -m app --demo         start it with the offline demo model
python -m app mask "text"    print the text as the LLM would receive it ("-" = stdin)
"""

import argparse
import asyncio
import io
import logging
import sys
from collections.abc import Sequence

from pydantic import ValidationError

from app.config import Settings
from app.guard import Guard, LeakCheckError, Message
from app.main import build_guard, serve
from app.policy import Action, PolicyError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app", description="PII Guard: mask personal data before it reaches an LLM."
    )
    parser.add_argument("--demo", action="store_true", help="use the offline demo model")
    commands = parser.add_subparsers(dest="command")

    run = commands.add_parser("serve", help="start the gateway (the default)")
    run.add_argument("--demo", action="store_true", help="use the offline demo model")
    run.add_argument("--host")
    run.add_argument("--port", type=int)

    mask = commands.add_parser("mask", help="print the masked text, without calling the LLM")
    mask.add_argument("text", nargs="?", default="-", help='text to mask, or "-" to read stdin')
    mask.add_argument("--demo", action="store_true", help="also use the demo names list")
    return parser


def mask_command(guard: Guard, text: str) -> int:
    """Masked text on stdout, a short summary on stderr. Exit code 2 when blocked."""
    try:
        prepared = guard.prepare([Message("user", text)])
    except LeakCheckError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    for f in prepared.findings:
        print(f"{f.type.value}: {f.count} found, {f.action.value}", file=sys.stderr)
    if prepared.blocked:
        blocked = ", ".join(f.type.value for f in prepared.findings if f.action is Action.BLOCK)
        print(f"blocked by policy ({blocked}): nothing would be sent", file=sys.stderr)
        return 2
    print(prepared.masked[0].content)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # On Windows, piped output uses the ANSI code page (cp1251 on a Russian system), which
    # has no "ğ" or "ß". The masked text must come out exactly as the model would get it.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    overrides: dict[str, object] = {}
    if args.demo:
        overrides["demo_mode"] = True
    if args.command == "serve":
        if args.host:
            overrides["host"] = args.host
        if args.port:
            overrides["port"] = args.port
    try:
        settings = Settings(**overrides)  # type: ignore[arg-type]
        if args.command == "mask":
            text = sys.stdin.read() if args.text == "-" else args.text
            return mask_command(build_guard(settings), text)
        asyncio.run(serve(settings))
    except (PolicyError, ValidationError, OSError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0
