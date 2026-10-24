"""Command line: run the web UI, or scan a site from the terminal.

uv run python -m app                    web UI on http://127.0.0.1:8108
uv run python -m app --demo             web UI with the sample reports ready
uv run python -m app scan https://example.com --max-pages 10 --json report.json
uv run python -m app scan --sample broken
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from app.config import Settings, get_settings
from app.db import Repository
from app.explain import create_explainer
from app.export import render_html, render_json
from app.models import CheckStatus, ScanReport, ScanStatus
from app.samples import SAMPLES
from app.service import ScanService
from app.urls import InvalidURL, TargetNotAllowed
from app.web import create_app

logger = logging.getLogger("accessibility")

STATUS_WORDS = {
    CheckStatus.FAIL: "FAIL",
    CheckStatus.WARNING: "WARN",
    CheckStatus.PASS: "pass",
    CheckStatus.NOT_APPLICABLE: "n/a",
}


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--demo", action="store_true", default=argparse.SUPPRESS, help="demo mode (offline)"
    )
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="Static WCAG 2.2 checks for small websites.",
        parents=[common],
    )
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", parents=[common], help="run the web UI (default)")
    serve.add_argument("--port", type=int, help="port (default: PORT or 8108)")
    scan = commands.add_parser("scan", parents=[common], help="scan a site and print a summary")
    target = scan.add_mutually_exclusive_group(required=True)
    target.add_argument("url", nargs="?", help="start URL, e.g. https://example.com")
    target.add_argument("--sample", choices=sorted(SAMPLES), help="scan a bundled sample site")
    scan.add_argument("--max-pages", type=int, help="page limit (default: MAX_PAGES or 20)")
    scan.add_argument("--json", type=Path, help="also write the report as JSON to this file")
    scan.add_argument("--html", type=Path, help="also write the report as HTML to this file")
    scan.add_argument("--explain", action="store_true", help="print the shop-owner summary")
    scan.add_argument("--language", default="en", choices=["en", "de", "ru", "tr"])
    return parser


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def format_summary(report: ScanReport) -> str:
    s = report.summary
    lines = [
        f"Accessibility Check: {report.origin or report.start_url}",
        f"{s.pages_analysed} of {s.pages_requested} pages analysed in {report.duration_s} s; "
        f"{report.robots}.",
    ]
    if report.error:
        lines.append(f"Note: {report.error}")
    lines.append("")
    for c in s.criteria:
        level = "best practice" if c.obsolete else c.level
        issues = (
            f"{plural(c.issues, 'issue')} on {plural(c.pages_affected, 'page')}" if c.issues else ""
        )
        lines.append(f"  {STATUS_WORDS[c.status]:<5} {c.number:<6} {c.name} ({level})  {issues}")
    lines.append("")
    for rule in s.rules:
        if rule.status in (CheckStatus.FAIL, CheckStatus.WARNING):
            lines.append(
                f"  {STATUS_WORDS[rule.status]:<5} {rule.title}: {plural(rule.issues, 'issue')}"
            )
            lines.append(f"        Fix: {rule.fix}")
    checks = s.checks
    lines += [
        "",
        f"Checks: {checks.get(CheckStatus.FAIL, 0)} failed, "
        f"{checks.get(CheckStatus.WARNING, 0)} warnings, {checks.get(CheckStatus.PASS, 0)} passed, "
        f"{checks.get(CheckStatus.NOT_APPLICABLE, 0)} not applicable.",
        "Static HTML checks only: test keyboard use, focus and screen readers by hand as well.",
    ]
    return "\n".join(lines)


async def open_service(settings: Settings) -> ScanService:
    repo = await Repository.connect(settings.database_path)
    return ScanService(settings, repo, create_explainer(settings))


async def run_scan_command(settings: Settings, args: argparse.Namespace) -> int:
    service = await open_service(settings)
    try:
        if args.sample:
            report = await service.scan_sample_now(args.sample)
        else:
            report = await service.scan_now(args.url, args.max_pages)
        print(format_summary(report))
        if args.json:
            args.json.write_text(render_json(report), encoding="utf-8")
            print(f"JSON report: {args.json}")
        if args.explain and report.status is ScanStatus.DONE:
            explanation = await service.explain(report.id or 0, args.language)
            report.explanation = explanation
            print(f"\nFor the shop owner ({explanation.source}):\n{explanation.summary}")
            for i, action in enumerate(explanation.actions, 1):
                print(f"{i}. {action.title}\n   {action.why}\n   What to do: {action.how}")
        if args.html:
            args.html.write_text(render_html(report), encoding="utf-8")
            print(f"HTML report: {args.html}")
        link = f"{settings.public_base_url}/reports/{report.id}"
        print(f"Saved as report {report.id}; open it at {link}")
        return 0 if report.status is ScanStatus.DONE else 1
    except (InvalidURL, TargetNotAllowed) as exc:
        print(f"Cannot scan: {exc}", file=sys.stderr)
        return 2
    finally:
        await service.repo.close()


async def serve(settings: Settings) -> None:
    service = await open_service(settings)
    interrupted = await service.repo.fail_interrupted()
    if interrupted:
        logger.warning("%d scans were interrupted by the last shutdown", interrupted)
    if settings.demo_mode:
        await service.ensure_demo_reports()
    app = create_app(service)
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
    logger.info(
        "Accessibility Check on http://127.0.0.1:%d%s",
        settings.port,
        " (demo mode)" if settings.demo_mode else "",
    )
    try:
        await server.serve()
    finally:
        await service.wait()
        await service.repo.close()


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # A Windows console with a legacy code page must not crash on a "–" in a page title.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if getattr(args, "demo", False):
        settings = settings.model_copy(update={"demo_mode": True})
    if args.command == "scan":
        if args.max_pages is not None and not 1 <= args.max_pages <= 200:
            print("--max-pages must be between 1 and 200", file=sys.stderr)
            return 2
        return asyncio.run(run_scan_command(settings, args))
    if getattr(args, "port", None):
        settings = settings.model_copy(update={"port": args.port})
    asyncio.run(serve(settings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
