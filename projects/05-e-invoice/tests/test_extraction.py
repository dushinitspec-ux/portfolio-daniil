"""The offline extractor on every bundled layout. Expected values are written out here, not
imported from samples/generate.py, so a bug in the generator cannot hide one in the reader."""

import io
from datetime import date
from decimal import Decimal as D

import pytest
from fpdf import FPDF

from app.extract.parsing import parse_date, unit_code
from app.model import VatCategory
from app.pdf_text import PdfError, read_pdf
from tests.conftest import extract_sample, sample_bytes


def test_german_din_layout_with_two_vat_rates() -> None:
    x = extract_sample("de-muster-gmbh.pdf")
    inv = x.invoice
    assert inv.number == "RE-2026-0142"
    assert inv.issue_date == date(2026, 10, 15)
    assert inv.delivery_date == date(2026, 9, 30)
    assert inv.due_date == date(2026, 10, 29)  # from "... ohne Abzug bis zum 29.10.2026."
    assert inv.order_reference == "PO-7781"

    s = inv.seller
    assert (s.name, s.address.street, s.address.postcode, s.address.city) == (
        "Muster GmbH", "Musterstraße 1", "10115", "Berlin"
    )  # fmt: skip
    assert s.vat_id == "DE123456789"
    assert (s.contact_name, s.contact_phone) == ("Max Mustermann", "+49 30 000000")
    assert s.contact_email == s.electronic_address == "rechnung@muster-gmbh.example"

    b = inv.buyer  # the DIN 5008 address window under the sender line
    assert (b.name, b.address.street, b.address.postcode, b.address.city) == (
        "Beispiel AG", "Beispielweg 12", "20095", "Hamburg"
    )  # fmt: skip
    assert b.vat_id == "DE987654321"  # "Ihre USt-IdNr.", not the seller's
    assert b.electronic_address == "rechnung@beispiel-ag.example"

    assert [(ln.name, ln.quantity, ln.unit_code, ln.net_price, ln.vat_rate, ln.net_amount)
            for ln in inv.lines] == [
        ("Wartung Netzwerk (September)", D("8"), "HUR", D("85.00"), D("19"), D("680.00")),
        ("Patchkabel Cat 6, 2 m", D("25"), "H87", D("4.90"), D("19"), D("122.50")),
        ('Fachbuch "Netzwerke für Einsteiger"', D("2"), "H87", D("39.90"), D("7"), D("79.80")),
    ]  # fmt: skip
    assert [(v.rate, v.taxable_amount, v.tax_amount) for v in inv.vat_breakdown] == [
        (D("19"), D("802.50"), D("152.48")),
        (D("7"), D("79.80"), D("5.59")),
    ]
    assert inv.totals.line_net_total == D("882.30")
    assert inv.totals.tax_inclusive == D("1040.37")
    assert inv.payment.iban == "DE52000000000012345678"


def test_english_layout_with_side_by_side_addresses() -> None:
    inv = extract_sample("en-sample-studio.pdf").invoice
    assert inv.number == "INV-2026-0042"
    assert inv.issue_date == date(2026, 10, 8)
    assert inv.due_date == date(2026, 11, 7)
    assert (inv.period_start, inv.period_end) == (date(2026, 9, 1), date(2026, 9, 30))
    # "FROM" and "BILL TO" sit next to each other: the columns must not mix.
    assert inv.seller.name == "Sample Studio GmbH"
    assert (inv.seller.address.city, inv.seller.address.country) == ("Munich", "DE")
    assert inv.buyer.name == "Muster Handel KG"
    assert (inv.buyer.address.street, inv.buyer.address.city) == ("Musterring 99", "Cologne")
    assert inv.buyer.vat_id == "DE444555666"
    assert inv.buyer.electronic_address == "ap@muster-handel.example"
    assert inv.seller.contact_phone == "+49 89 000000"
    # English number format, units inside the quantity cell
    assert [(ln.quantity, ln.unit_code, ln.net_price) for ln in inv.lines] == [
        (D("1"), "MON", D("1200.00")),
        (D("2"), "DAY", D("650.00")),
        (D("3"), "H87", D("19.99")),
    ]
    assert inv.totals.tax_inclusive == D("3046.36")
    assert inv.payment.terms == "30 days net"


def test_compact_german_layout_with_leitweg_id() -> None:
    x = extract_sample("de-beispiel-it-service.pdf")
    inv = x.invoice
    # "Rechnung RE-2610-007 vom 20.10.2026": number and date from the title line
    assert inv.number == "RE-2610-007"
    assert inv.issue_date == date(2026, 10, 20)
    assert inv.buyer_reference == "04011000-12345-03"
    # recipient on one line, comma separated
    assert inv.buyer.name == "Stadt Musterstadt"
    assert (inv.buyer.address.street, inv.buyer.address.postcode) == ("Rathausplatz 1", "12345")
    assert inv.buyer.electronic_address == ""  # not printed: validation will ask for it
    assert inv.seller.contact_name == "Erika Beispiel"  # "Inh. Erika Beispiel"
    assert inv.payment.account_name == "Erika Beispiel"
    assert inv.lines[1].quantity == D("2.5")
    assert inv.lines[1].unit_code == "HUR"
    assert [ln.id for ln in inv.lines] == ["1", "2"]  # "Art.-Nr." is an article code, not BT-126
    assert any("VAT rate 19 %" in note for note in x.derived)


def test_reverse_charge_layout() -> None:
    inv = extract_sample("en-beispiel-software-reverse-charge.pdf").invoice
    assert inv.number == "2026/118"
    assert inv.issue_date == date(2026, 10, 12)
    assert inv.due_date == date(2026, 10, 26)
    assert inv.seller.vat_id == "ATU12345678"
    assert inv.seller.address.country == "AT"
    assert inv.buyer.vat_id == "DE123456789"
    assert inv.buyer_reference == "Projekt Nordlicht"
    assert {ln.vat_category for ln in inv.lines} == {VatCategory.REVERSE_CHARGE}
    (row,) = inv.vat_breakdown
    assert (row.category, row.rate, row.tax_amount) == (
        VatCategory.REVERSE_CHARGE,
        D("0"),
        D("0.00"),
    )
    assert row.exemption_reason == "Reverse charge"
    assert row.taxable_amount == D("1650.00")
    assert inv.note.startswith("Reverse charge: VAT to be accounted for by the recipient")
    assert inv.payment.iban == "AT340000000012345678"


def test_wrong_numbers_are_read_as_printed_not_corrected() -> None:
    inv = extract_sample("de-muster-gmbh-with-errors.pdf").invoice
    assert sum((ln.net_amount or D(0)) for ln in inv.lines) == D("882.30")
    assert inv.totals.line_net_total == D("882.80")  # the typo on the PDF
    assert inv.payment.iban == "DE52000000000012345679"


def test_table_columns_become_separate_cells() -> None:
    lines = read_pdf(sample_bytes("de-muster-gmbh.pdf")).lines
    row = next(line for line in lines if line.text.startswith("1 Wartung"))
    assert [c.text for c in row.cells] == [
        "1", "Wartung Netzwerk (September)", "8", "Std.", "85,00", "19 %", "680,00"
    ]  # fmt: skip


def _pdf(text: str | None) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    if text:
        pdf.set_font("Helvetica", size=10)
        pdf.cell(text=text)
    return bytes(pdf.output())


def test_scanned_pdf_without_text_layer_is_rejected() -> None:
    with pytest.raises(PdfError, match="no text layer"):
        read_pdf(_pdf(None))


def test_not_a_pdf_is_rejected() -> None:
    with pytest.raises(PdfError, match="not a readable PDF"):
        read_pdf(b"%PDF-1.7 this is not really a pdf")


def test_page_limit() -> None:
    with pytest.raises(PdfError, match="limit"):
        read_pdf(_pdf("Rechnung"), max_pages=0)


def test_unknown_layout_returns_an_empty_invoice_with_a_warning() -> None:
    from app.extract.rules import extract_text

    x = extract_text(read_pdf(_pdf("Lieferschein 4711")))
    assert x.invoice.lines == []
    assert x.warnings


@pytest.mark.parametrize(
    ("text", "style", "expected"),
    [
        ("2026-10-15", "de", date(2026, 10, 15)),
        ("15.10.2026", "de", date(2026, 10, 15)),
        ("Datum: 1.9.26", "de", date(2026, 9, 1)),
        ("October 8, 2026", "en", date(2026, 10, 8)),
        ("8 October 2026", "en", date(2026, 10, 8)),
        ("15. Oktober 2026", "de", date(2026, 10, 15)),
        ("03/11/2026", "de", date(2026, 11, 3)),
        ("03/11/2026", "en", date(2026, 3, 11)),
        ("31.02.2026", "de", None),
        ("no date here", "de", None),
    ],
)
def test_parse_date(text: str, style: str, expected: date | None) -> None:
    assert parse_date(text, style) == expected  # type: ignore[arg-type]


def test_unit_codes() -> None:
    labels = ["Std.", "h", "Stk", "pcs", "Tage", "month", "flat", "users"]
    assert [unit_code(u) for u in labels] == ["HUR", "HUR", "H87", "H87", "DAY", "MON", "LS", "C62"]


def test_pdf_text_keeps_columns_for_the_llm() -> None:
    plain = read_pdf(io.BytesIO(sample_bytes("en-sample-studio.pdf")).getvalue()).plain
    assert "Muster Handel KG" in plain
    assert "Sample Studio GmbH    Muster Handel KG" in plain  # cells joined by four spaces
