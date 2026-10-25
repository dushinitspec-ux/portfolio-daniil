"""Entry point of the in-browser demo (Pyodide): JSON in, JSON out.

It runs the same steps as app.pipeline.convert() with the offline rule-based extractor:
text layer -> extract -> (fields typed in by the visitor) -> derive -> validate -> UBL XML.
Only the first step differs: pdfplumber does not run in the browser, so the words of the
bundled sample PDFs were exported in advance with the real pdfplumber
(scripts/export_text_layer.py) and are rebuilt into lines and cells by app.pdf_text here.

Nothing in this module imports FastAPI, the database, pdfplumber or the Anthropic SDK.
"""

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.extract.complete import complete
from app.extract.parsing import EMAIL
from app.extract.rules import extract_text
from app.model import Extraction
from app.money import AmountError, parse_number
from app.pdf_text import from_words
from app.ubl import to_xml
from app.validation import Status, validate

TEXT_LAYER = Path(__file__).resolve().parent.parent / "samples" / "text-layer"
TERM = re.compile(r"\bBT-\d+\b")

# Fields the visitor can edit: path in the Invoice model -> (EN 16931 business term, kind).
FIELDS: dict[str, tuple[str, str]] = {
    "number": ("BT-1", "text"),
    "issue_date": ("BT-2", "date"),
    "due_date": ("BT-9", "date"),
    "buyer_reference": ("BT-10", "text"),
    "seller.name": ("BT-27", "text"),
    "seller.vat_id": ("BT-31", "text"),
    "seller.electronic_address": ("BT-34", "email"),
    "buyer.name": ("BT-44", "text"),
    "buyer.vat_id": ("BT-48", "text"),
    "buyer.electronic_address": ("BT-49", "email"),
    "payment.iban": ("BT-84", "text"),
    "totals.line_net_total": ("BT-106", "amount"),
    "totals.tax_exclusive": ("BT-109", "amount"),
    "totals.vat_total": ("BT-110", "amount"),
    "totals.tax_inclusive": ("BT-112", "amount"),
    "totals.payable": ("BT-115", "amount"),
}
# Editable columns of every invoice line ("lines.<index>.<name>").
LINE_FIELDS: dict[str, tuple[str, str]] = {
    "quantity": ("BT-129", "amount"),
    "net_price": ("BT-146", "amount"),
    "net_amount": ("BT-131", "amount"),
}


class EditError(ValueError):
    """A typed-in value cannot be used; `code` says why (for the page's own wording)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _load(sample: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9-]+", sample) or not (TEXT_LAYER / f"{sample}.json").is_file():
        raise ValueError(f"unknown sample {sample!r}")
    return json.loads((TEXT_LAYER / f"{sample}.json").read_text(encoding="utf-8"))


def samples() -> list[dict[str, Any]]:
    """The bundled sample invoices whose text layer is available."""
    result = []
    for path in sorted(TEXT_LAYER.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        words = sum(len(page) for page in data["pages"])
        result.append(
            {"id": path.stem, "file": data["file"], "pages": len(data["pages"]), "words": words}
        )
    return result


def _spec(path: str) -> tuple[str, str]:
    if path in FIELDS:
        return FIELDS[path]
    parts = path.split(".")
    if len(parts) == 3 and parts[0] == "lines" and parts[1].isdigit() and parts[2] in LINE_FIELDS:
        return LINE_FIELDS[parts[2]]
    raise EditError("unknown")


def _parse(kind: str, raw: str) -> object:
    text = raw.strip()
    if kind == "text":
        return text
    if kind == "email":
        if text and not EMAIL.fullmatch(text):
            raise EditError("email")
        return text
    if not text:
        return None
    if kind == "date":
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise EditError("date") from exc
    try:
        return parse_number(text)
    except AmountError as exc:
        raise EditError("number") from exc


def _set(extraction: Extraction, path: str, raw: str) -> None:
    _term, kind = _spec(path)
    value = _parse(kind, raw)
    *parents, name = path.split(".")
    target: Any = extraction.invoice
    for part in parents:
        if part.isdigit():
            if int(part) >= len(target):
                raise EditError("unknown")
            target = target[int(part)]
        else:
            target = getattr(target, part)
    setattr(target, name, value)


def _show(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:f}"
    return str(value)


def _get(extraction: Extraction, path: str) -> str:
    target: Any = extraction.invoice
    for part in path.split("."):
        target = target[int(part)] if part.isdigit() else getattr(target, part)
    return _show(target)


def _address(party: Any) -> str:
    a = party.address
    place = " ".join(p for p in (a.postcode, a.city) if p)
    return ", ".join(p for p in (a.street, place, a.country) if p)


def _download_name(number: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", number).strip("-")
    return f"{safe or 'invoice'}.xml"


def convert(sample: str, edits: dict[str, str] | None = None) -> dict[str, Any]:
    """Convert one bundled sample. `edits` maps a field path ("buyer.electronic_address",
    "totals.line_net_total", "lines.0.quantity", ...) to the text typed into the form.

    As in the web app, typed values replace the extracted ones before the derivation step,
    so a value the visitor entered is never overwritten by a computed one.
    """
    data = _load(sample)
    extraction = extract_text(from_words(data["pages"]))
    errors: dict[str, str] = {}
    applied: list[str] = []
    for path, raw in (edits or {}).items():
        try:
            _set(extraction, path, str(raw))
        except EditError as exc:
            errors[path] = exc.code
            continue
        applied.append(path)
        term = _spec(path)[0]
        if path == "buyer.electronic_address":  # the pipeline's own wording
            extraction.derived.append("BT-49 buyer e-invoice address entered by the user")
        else:
            extraction.derived.append(f"{term} entered by the user")

    extraction = complete(extraction)
    invoice = extraction.invoice
    report = validate(invoice)
    xml = to_xml(invoice).decode("utf-8")

    fields = {path: _get(extraction, path) for path in FIELDS}
    for index in range(len(invoice.lines)):
        for name in LINE_FIELDS:
            path = f"lines.{index}.{name}"
            fields[path] = _get(extraction, path)

    rules = []
    for r in report.results:
        terms = list(dict.fromkeys(TERM.findall(f"{r.title} {r.message}")))
        rules.append(
            {
                "id": r.id,
                "status": r.status.value,
                "severity": r.severity.value,
                "source": r.source.value,
                "title": r.title,
                "message": r.message,
                "terms": terms,
            }
        )

    return {
        "sample": sample,
        "file": data["file"],
        "pages": len(data["pages"]),
        "extractor": extraction.extractor,
        "fields": fields,
        "terms": {path: _spec(path)[0] for path in fields},
        "lines": [
            {
                "id": line.id,
                "name": line.name,
                "unit": line.unit_code,
                "vat_category": line.vat_category.value if line.vat_category else "",
                "vat_rate": _show(line.vat_rate),
            }
            for line in invoice.lines
        ],
        "seller_address": _address(invoice.seller),
        "buyer_address": _address(invoice.buyer),
        "currency": invoice.currency,
        "edited": applied,
        "errors": errors,
        "derived": extraction.derived,
        "warnings": extraction.warnings,
        "rules": rules,
        "summary": {
            "total": len(report.results),
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "passed": len(report.passed),
            "not_applicable": sum(1 for r in report.results if r.status is Status.NOT_APPLICABLE),
            "valid": report.valid,
        },
        "xml": xml,
        "xml_name": _download_name(invoice.number),
    }
