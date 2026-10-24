"""Web app: upload a PDF, see the extracted fields and rule results, download the XML."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.db import Repository, StoredInvoice
from app.extract import ExtractionError, Extractor
from app.extract.parsing import EMAIL
from app.iban import pretty
from app.money import format_display
from app.pdf_text import PdfError
from app.pipeline import Conversion, convert
from app.validation import RuleResult, Source, validate

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
XML_PREVIEW_LINES = 40
# Which total on the page a failed rule points at, so the row can be marked.
RULE_TERMS: dict[str, str] = {
    "BR-12": "BT-106",
    "BR-CO-10": "BT-106",
    "BR-13": "BT-109",
    "BR-CO-13": "BT-109",
    "BR-CO-14": "BT-110",
    "BR-14": "BT-112",
    "BR-CO-15": "BT-112",
    "BR-15": "BT-115",
    "BR-CO-16": "BT-115",
    "BR-CO-17": "BT-117",
    "BR-S-08": "BT-117",
    "BR-AE-08": "BT-117",
    "BR-AE-09": "BT-117",
}


def _money(value: Decimal | None) -> str:
    return format_display(value, "en")


def _day(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value else "—"


def _rate(value: Decimal | None) -> str:
    return "—" if value is None else f"{value.normalize():f} %"


TEMPLATES.env.filters.update(money=_money, day=_day, rate=_rate, iban=pretty)


@dataclass(frozen=True)
class AppConfig:
    demo: bool
    extractor_name: str
    samples_dir: Path
    max_upload_bytes: int
    max_pages: int


def _download_name(number: str, invoice_id: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", number).strip("-")
    return f"{safe or f'invoice-{invoice_id}'}.xml"


def _api_rules(results: list[RuleResult]) -> list[dict[str, str]]:
    return [
        {
            "id": r.id,
            "status": r.status.value,
            "severity": r.severity.value,
            "source": r.source.value,
            "message": r.message,
            "rule": r.title,
        }
        for r in results
    ]


def create_app(repo: Repository, extractor: Extractor, config: AppConfig) -> FastAPI:
    app = FastAPI(title="E-Invoice", version="0.1.0")

    def samples() -> list[str]:
        if not config.samples_dir.is_dir():
            return []
        return sorted(p.name for p in config.samples_dir.glob("*.pdf"))

    async def index_page(request: Request, error: str = "", status: int = 200) -> HTMLResponse:
        context = {
            "demo": config.demo,
            "extractor": config.extractor_name,
            "samples": samples(),
            "history": await repo.recent(25),
            "error": error,
            "max_mb": config.max_upload_bytes // 1_000_000,
        }
        return TEMPLATES.TemplateResponse(request, "index.html", context, status_code=status)

    async def run(data: bytes, filename: str, buyer_email: str) -> Conversion:
        if buyer_email and not EMAIL.fullmatch(buyer_email.strip()):
            raise PdfError(f"{buyer_email!r} is not an e-mail address")
        return await convert(
            data, extractor, filename, buyer_email=buyer_email, max_pages=config.max_pages
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return await index_page(request)

    @app.post("/convert", response_model=None)
    async def convert_upload(
        request: Request,
        file: Annotated[UploadFile, File()],
        buyer_email: Annotated[str, Form()] = "",
    ) -> Response:
        data = await file.read(config.max_upload_bytes + 1)
        if len(data) > config.max_upload_bytes:
            return await index_page(request, "The file is larger than the upload limit.", 413)
        if not data.startswith(b"%PDF"):
            return await index_page(request, "This is not a PDF file.", 422)
        try:
            conversion = await run(data, file.filename or "invoice.pdf", buyer_email)
        except PdfError as exc:
            return await index_page(request, f"Could not read the PDF: {exc}.", 422)
        except ExtractionError as exc:
            return await index_page(request, f"Extraction failed: {exc}.", 502)
        invoice_id = await repo.add(conversion, data)
        return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)

    @app.post("/samples/{name}", response_model=None)
    async def convert_sample(request: Request, name: str) -> Response:
        if name not in samples():
            raise HTTPException(404, "unknown sample")
        data = (config.samples_dir / name).read_bytes()
        try:
            conversion = await run(data, name, "")
        except ExtractionError as exc:
            return await index_page(request, f"Extraction failed: {exc}.", 502)
        invoice_id = await repo.add(conversion, data)
        return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)

    async def stored(invoice_id: int) -> StoredInvoice:
        found = await repo.get(invoice_id)
        if found is None:
            raise HTTPException(404, "invoice not found")
        return found

    @app.get("/invoices/{invoice_id}", response_class=HTMLResponse)
    async def show(request: Request, invoice_id: int) -> HTMLResponse:
        item = await stored(invoice_id)
        report = validate(item.extraction.invoice)
        failed = report.errors + report.warnings
        xml_lines = item.xml.decode("utf-8").splitlines()
        context = {
            "demo": config.demo,
            "extractor": config.extractor_name,
            "row": item.row,
            "x": item.extraction,
            "inv": item.extraction.invoice,
            "report": report,
            "failed": failed,
            "official": [r for r in report.passed if r.source is not Source.APP],
            "flagged": {RULE_TERMS[r.id] for r in report.errors if r.id in RULE_TERMS},
            "xml_preview": "\n".join(xml_lines[:XML_PREVIEW_LINES]),
            "xml_more": max(0, len(xml_lines) - XML_PREVIEW_LINES),
        }
        return TEMPLATES.TemplateResponse(request, "invoice.html", context)

    @app.post("/invoices/{invoice_id}/buyer-email", response_model=None)
    async def add_buyer_email(
        request: Request, invoice_id: int, buyer_email: Annotated[str, Form()]
    ) -> Response:
        item = await stored(invoice_id)
        try:
            conversion = await run(item.pdf, item.row.filename, buyer_email)
        except (PdfError, ExtractionError) as exc:
            raise HTTPException(422, str(exc)) from exc
        await repo.replace(invoice_id, conversion)
        return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)

    @app.get("/invoices/{invoice_id}/xml")
    async def download_xml(invoice_id: int) -> Response:
        item = await stored(invoice_id)
        name = _download_name(item.row.number, invoice_id)
        return Response(
            item.xml,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get("/invoices/{invoice_id}/pdf")
    async def original_pdf(invoice_id: int) -> Response:
        item = await stored(invoice_id)
        return Response(item.pdf, media_type="application/pdf")

    @app.post("/api/convert")
    async def api_convert(
        file: Annotated[UploadFile, File()], buyer_email: Annotated[str, Form()] = ""
    ) -> dict[str, Any]:
        data = await file.read(config.max_upload_bytes + 1)
        if len(data) > config.max_upload_bytes:
            raise HTTPException(413, "file too large")
        try:
            conversion = await run(data, file.filename or "invoice.pdf", buyer_email)
        except PdfError as exc:
            raise HTTPException(422, str(exc)) from exc
        except ExtractionError as exc:
            raise HTTPException(502, str(exc)) from exc
        invoice_id = await repo.add(conversion, data)
        return {
            "id": invoice_id,
            "valid": conversion.valid,
            "extractor": conversion.extraction.extractor,
            "invoice": conversion.invoice.model_dump(mode="json"),
            "derived": conversion.extraction.derived,
            "warnings": conversion.extraction.warnings,
            "rules": _api_rules(conversion.report.results),
            "xml": conversion.xml.decode("utf-8"),
        }

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
