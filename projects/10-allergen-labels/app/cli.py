"""Command line.

uv run python -m app                         web UI (DEMO_MODE and keys from .env)
uv run python -m app --demo                  web UI with the sample menu
uv run python -m app check "spaghetti, egg yolk, pecorino, guanciale"
uv run python -m app check --lang de --json "Weizenmehl, Eier"
uv run python -m app check --ai "..."         also ask the AI about unknown items
"""

import argparse
import asyncio
import io
import json
import logging
import sys

from app import allergens as annex
from app.config import get_settings
from app.i18n import Language, parse_language
from app.llm import Suggestion, create_suggester
from app.matcher import Analysis, IngredientResult, Status, analyse

_STATUS = {Status.FOUND: "found", Status.NONE: "none", Status.CHECK: "CHECK"}


def _numbers(item: IngredientResult) -> str:
    parts = [str(n) if n in item.certain else f"{n}?" for n in sorted(item.allergens)]
    return " ".join(parts) or "-"


def format_report(
    recipe: str,
    analysis: Analysis,
    language: Language,
    suggestions: dict[str, Suggestion] | None = None,
) -> str:
    suggestions = suggestions or {}
    lines = [f"Ingredients: {recipe.strip()}", ""]
    width = max((len(i.label) for i in analysis.items), default=10)
    width = min(max(width, 10), 36)
    pad = " " * (width + 11)
    for item in analysis.items:
        lines.append(f"  {item.label:<{width}}  {_STATUS[item.status]:<5}  {_numbers(item)}")
        for hit in item.hits:
            label = annex.get(hit.allergen).label(language)
            maybe = "" if hit.certain else ", possible"
            lines.append(f"{pad}{hit.allergen} {label} <- '{hit.found}'{maybe}")
        if item.unknown:
            lines.append(f"{pad}not in the dictionary: {', '.join(item.unknown)}")
        for note in item.all_notes:
            lines.append(f"{pad}note: {note}")
        suggestion = suggestions.get(item.label)
        if suggestion:
            ids = ", ".join(suggestion.allergens) or "none of the 14"
            lines.append(f"{pad}AI (needs confirmation): {ids} - {suggestion.reason}")
    lines.append("")
    found = sorted(analysis.allergens)
    summary = " · ".join(
        f"{n} {annex.get(n).label(language)}{'' if n in analysis.certain else '?'}" for n in found
    )
    lines.append(f"Allergens: {summary or 'none of the 14 found'}")
    if analysis.to_check:
        names = ", ".join(i.label for i in analysis.to_check)
        lines.append(f"A person must check {len(analysis.to_check)}: {names}")
    lines.append("'?' = possible, not certain. This tool assists; a person confirms the dish.")
    return "\n".join(lines)


async def _ai(analysis: Analysis) -> dict[str, Suggestion]:
    suggester = create_suggester(get_settings())
    if not suggester.enabled:
        print("AI suggestions need ANTHROPIC_API_KEY in .env; showing the dictionary only.\n")
        return {}
    labels = [i.label for i in analysis.to_check]
    result = await suggester.suggest("", labels)
    return {label: s for label, s in zip(labels, result, strict=False)}


def check(args: argparse.Namespace) -> int:
    recipe = " ".join(args.ingredients)
    if recipe.strip() == "-":
        recipe = sys.stdin.read()
    analysis = analyse(recipe)
    if args.json:
        data = {
            "allergens": sorted(analysis.allergens),
            "certain": sorted(analysis.certain),
            "needs_check": [i.label for i in analysis.to_check],
            "items": analysis.model_dump(mode="json")["items"],
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    suggestions = asyncio.run(_ai(analysis)) if args.ai and analysis.to_check else {}
    print(format_report(recipe, analysis, parse_language(args.lang), suggestions))
    return 0


def main(argv: list[str] | None = None) -> None:
    # On Windows a redirected stdout uses the ANSI code page (cp1251 on a Russian system),
    # which has no Turkish letters: print UTF-8 instead.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="python -m app", description=__doc__.split("\n")[0])
    parser.add_argument("--demo", action="store_true", help="run the web UI with sample data")
    sub = parser.add_subparsers(dest="command")
    serve_parser = sub.add_parser("serve", help="run the web UI (default)")
    serve_parser.add_argument("--demo", action="store_true", help="use the sample menu")
    check_parser = sub.add_parser("check", help="find allergens in an ingredient list")
    check_parser.add_argument("ingredients", nargs="+", help="comma-separated; '-' reads stdin")
    check_parser.add_argument("--lang", default="en", help="language of allergen names")
    check_parser.add_argument("--json", action="store_true", help="print JSON")
    check_parser.add_argument("--ai", action="store_true", help="ask the AI about unclear items")
    args = parser.parse_args(argv)

    if args.command == "check":
        sys.exit(check(args))

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    if args.demo:
        settings = settings.model_copy(update={"demo_mode": True})
    from app.main import serve

    asyncio.run(serve(settings))
