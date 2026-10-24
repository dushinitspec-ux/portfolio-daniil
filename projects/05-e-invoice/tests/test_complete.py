"""Derived values are filled in, and every one of them is listed."""

from decimal import Decimal as D

from app.extract.complete import complete
from app.model import Extraction, Invoice, Totals, VatCategory


def run(invoice: Invoice) -> Extraction:
    return complete(Extraction(invoice=invoice, extractor="test"))


def test_a_complete_invoice_derives_nothing(invoice: Invoice) -> None:
    assert run(invoice).derived == []


def test_original_is_not_modified(invoice: Invoice) -> None:
    invoice.totals = Totals()
    run(invoice)
    assert invoice.totals.line_net_total is None


def test_totals_are_computed_from_lines_and_noted(invoice: Invoice) -> None:
    invoice.vat_breakdown = []
    invoice.totals = Totals()
    x = run(invoice)
    t = x.invoice.totals
    assert (t.line_net_total, t.tax_exclusive, t.vat_total, t.tax_inclusive, t.payable) == (
        D("759.80"), D("759.80"), D("134.79"), D("894.59"), D("894.59")
    )  # fmt: skip
    assert [(b.rate, b.taxable_amount, b.tax_amount) for b in x.invoice.vat_breakdown] == [
        (D("19"), D("680.00"), D("129.20")),
        (D("7"), D("79.80"), D("5.59")),
    ]
    assert any("VAT breakdown computed" in d for d in x.derived)
    assert any(d.startswith("BT-106") for d in x.derived)
    assert any(d.startswith("BT-112") for d in x.derived)


def test_single_vat_rate_is_assigned_to_lines_without_one(invoice: Invoice) -> None:
    invoice.lines = invoice.lines[:1]
    invoice.lines[0].vat_rate = None
    invoice.lines[0].vat_category = None
    invoice.vat_breakdown = invoice.vat_breakdown[:1]
    x = run(invoice)
    assert x.invoice.lines[0].vat_rate == D("19")
    assert x.invoice.lines[0].vat_category is VatCategory.STANDARD
    assert any("set on 1 line(s)" in d for d in x.derived)


def test_buyer_reference_falls_back_to_the_order_number(invoice: Invoice) -> None:
    invoice.buyer_reference = ""
    invoice.order_reference = "4500012345"
    x = run(invoice)
    assert x.invoice.buyer_reference == "4500012345"
    assert any(d.startswith("BT-10") for d in x.derived)


def test_country_from_vat_id_prefix(invoice: Invoice) -> None:
    invoice.seller.address.country = ""
    invoice.buyer.vat_id = "EL123456789"
    invoice.buyer.address.country = ""
    x = run(invoice)
    assert x.invoice.seller.address.country == "DE"
    assert x.invoice.buyer.address.country == "GR"  # Greek VAT IDs start with EL


def test_line_net_amount_from_quantity_and_price(invoice: Invoice) -> None:
    invoice.lines[0].net_amount = None
    x = run(invoice)
    assert x.invoice.lines[0].net_amount == D("680.00")
    assert any("Line 1: net amount" in d for d in x.derived)
