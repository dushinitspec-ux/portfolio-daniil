"""PDF bytes in, validated e-invoice out: read text -> extract -> derive -> validate -> UBL."""

import time
from dataclasses import dataclass

from app.extract import Extractor
from app.extract.complete import complete
from app.model import Extraction, Invoice
from app.pdf_text import read_pdf
from app.ubl import to_xml
from app.validation import Report, validate


@dataclass(frozen=True)
class Conversion:
    filename: str
    extraction: Extraction
    report: Report
    xml: bytes
    seconds: float

    @property
    def invoice(self) -> Invoice:
        return self.extraction.invoice

    @property
    def valid(self) -> bool:
        return self.report.valid


async def convert(
    data: bytes,
    extractor: Extractor,
    filename: str = "invoice.pdf",
    *,
    buyer_email: str = "",
    max_pages: int = 20,
) -> Conversion:
    """Raises PdfError for unreadable PDFs and ExtractionError when the extractor fails.

    `buyer_email` is the buyer's e-invoice address (BT-49) when the PDF does not print it:
    XRechnung requires it, and only the person sending the invoice knows it.
    """
    started = time.perf_counter()
    pdf = read_pdf(data, max_pages=max_pages)
    extraction = await extractor.extract(pdf)
    if buyer_email.strip():
        extraction.invoice.buyer.electronic_address = buyer_email.strip()
        extraction.derived.append("BT-49 buyer e-invoice address entered by the user")
    extraction = complete(extraction)
    report = validate(extraction.invoice)
    xml = to_xml(extraction.invoice)
    return Conversion(filename, extraction, report, xml, time.perf_counter() - started)
