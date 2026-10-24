"""Entry points: the web app (default) and the `convert` command.

uv run python -m app                    # web app on http://127.0.0.1:8105
uv run python -m app --demo             # same, offline rule-based extractor only
uv run python -m app convert sample.pdf -o out.xml [--buyer-email x@y.example]
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import uvicorn

from app.config import ExtractorChoice, Settings, get_settings
from app.db import Repository
from app.extract import ExtractionError, create_extractor
from app.pdf_text import PdfError
from app.pipeline import Conversion, convert
from app.validation import Status
from app.web import AppConfig, create_app

logger = logging.getLogger("e-invoice")

EXIT_VALID, EXIT_INVALID, EXIT_ERROR = 0, 1, 2


async def serve(settings: Settings) -> None:
    extractor = create_extractor(settings)
    if settings.effective_extractor is ExtractorChoice.RULES and not settings.demo_mode:
        logger.warning("No ANTHROPIC_API_KEY: using the offline rule-based extractor.")
    repo = await Repository.connect(settings.database_path)
    config = AppConfig(
        demo=settings.demo_mode,
        extractor_name=extractor.name,
        samples_dir=settings.samples_dir,
        max_upload_bytes=int(settings.max_upload_mb * 1_000_000),
        max_pages=settings.max_pages,
    )
    app = create_app(repo, extractor, config)
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
    logger.info("E-Invoice on http://127.0.0.1:%d (extractor: %s)", settings.port, extractor.name)
    try:
        await server.serve()
    finally:
        await repo.close()


def print_summary(conversion: Conversion) -> None:
    invoice, report = conversion.invoice, conversion.report
    total = invoice.totals.payable
    print(
        f"{conversion.filename}: invoice {invoice.number or '(no number)'}, "
        f"{invoice.seller.name or '?'} -> {invoice.buyer.name or '?'}, "
        f"amount due {total if total is not None else '?'} {invoice.currency}"
    )
    counts = {s: sum(r.status is s for r in report.results) for s in Status}
    print(
        f"rules: {counts[Status.PASSED]} passed, {len(report.errors)} failed, "
        f"{len(report.warnings)} warnings, {counts[Status.NOT_APPLICABLE]} not applicable "
        f"(extractor: {conversion.extraction.extractor}, {conversion.seconds * 1000:.0f} ms)"
    )
    for result in report.errors + report.warnings:
        print(f"  {result.severity.value.upper():7} {result.id}: {result.message}")
    for note in conversion.extraction.derived:
        print(f"  derived: {note}")


def convert_command(args: argparse.Namespace, settings: Settings) -> int:
    try:
        data = args.pdf.read_bytes()
    except OSError as exc:
        print(f"error: cannot read {args.pdf}: {exc.strerror}", file=sys.stderr)
        return EXIT_ERROR
    try:
        conversion = asyncio.run(
            convert(
                data,
                create_extractor(settings),
                args.pdf.name,
                buyer_email=args.buyer_email or "",
                max_pages=settings.max_pages,
            )
        )
    except (PdfError, ExtractionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    output: Path = args.output or args.pdf.with_suffix(".xml")
    output.write_bytes(conversion.xml)
    print_summary(conversion)
    print(f"wrote {output}" + ("" if conversion.valid else " (NOT compliant, see errors above)"))
    return EXIT_VALID if conversion.valid else EXIT_INVALID


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app", description=__doc__.splitlines()[0])
    parser.add_argument("--demo", action="store_true", help="offline demo mode (no API key)")
    sub = parser.add_subparsers(dest="command")
    conv = sub.add_parser("convert", help="convert one PDF to XRechnung UBL XML")
    conv.add_argument("pdf", type=Path, help="text-based PDF invoice")
    conv.add_argument("-o", "--output", type=Path, help="XML file (default: <pdf>.xml)")
    conv.add_argument("--buyer-email", help="buyer e-invoice address (BT-49) if not on the PDF")
    conv.add_argument(
        "--extractor", choices=[c.value for c in ExtractorChoice], help="override EXTRACTOR"
    )
    conv.add_argument("--demo", action="store_true", dest="demo_sub", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = parse_args(sys.argv[1:] if argv is None else argv)
    settings = get_settings()
    if args.demo or getattr(args, "demo_sub", False):
        settings = settings.model_copy(update={"demo_mode": True})
    if args.command == "convert":
        if args.extractor:
            settings = settings.model_copy(update={"extractor": ExtractorChoice(args.extractor)})
        return convert_command(args, settings)
    asyncio.run(serve(settings))
    return EXIT_VALID
