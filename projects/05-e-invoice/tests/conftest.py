from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.db import Repository
from app.extract.complete import complete
from app.extract.rules import extract_text
from app.model import (
    Address,
    Extraction,
    Invoice,
    InvoiceLine,
    Party,
    Payment,
    Totals,
    VatBreakdown,
    VatCategory,
)
from app.pdf_text import read_pdf

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
S, AE = VatCategory.STANDARD, VatCategory.REVERSE_CHARGE


def sample_bytes(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


def extract_sample(name: str) -> Extraction:
    """Offline extraction plus derivation, as the pipeline does it."""
    return complete(extract_text(read_pdf(sample_bytes(name))))


def make_invoice() -> Invoice:
    """A complete, correct invoice with two VAT rates: passes every rule."""
    return Invoice(
        number="RE-2026-0001",
        issue_date=date(2026, 10, 15),
        due_date=date(2026, 10, 29),
        buyer_reference="PO-7781",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        seller=Party(
            name="Muster GmbH",
            address=Address(street="Musterstraße 1", postcode="10115", city="Berlin", country="DE"),
            vat_id="DE123456789",
            electronic_address="rechnung@muster-gmbh.example",
            contact_name="Max Mustermann",
            contact_phone="+49 30 000000",
            contact_email="rechnung@muster-gmbh.example",
        ),
        buyer=Party(
            name="Beispiel AG",
            address=Address(
                street="Beispielweg 12", postcode="20095", city="Hamburg", country="DE"
            ),
            vat_id="DE987654321",
            electronic_address="rechnung@beispiel-ag.example",
        ),
        payment=Payment(iban="DE52000000000012345678", terms="14 Tage netto"),
        lines=[
            InvoiceLine(
                id="1",
                name="Wartung",
                quantity=D("8"),
                unit_code="HUR",
                net_price=D("85.00"),
                vat_category=S,
                vat_rate=D("19"),
                net_amount=D("680.00"),
            ),
            InvoiceLine(
                id="2",
                name="Fachbuch",
                quantity=D("2"),
                unit_code="H87",
                net_price=D("39.90"),
                vat_category=S,
                vat_rate=D("7"),
                net_amount=D("79.80"),
            ),
        ],
        vat_breakdown=[
            VatBreakdown(
                category=S, rate=D("19"), taxable_amount=D("680.00"), tax_amount=D("129.20")
            ),
            VatBreakdown(category=S, rate=D("7"), taxable_amount=D("79.80"), tax_amount=D("5.59")),
        ],
        totals=Totals(
            line_net_total=D("759.80"),
            tax_exclusive=D("759.80"),
            vat_total=D("134.79"),
            tax_inclusive=D("894.59"),
            payable=D("894.59"),
        ),
    )


def make_reverse_charge_invoice() -> Invoice:
    """Austrian seller, German buyer, reverse charge (VAT category AE)."""
    invoice = make_invoice()
    invoice.seller.vat_id = "ATU12345678"
    invoice.seller.address = Address(
        street="Musterweg 7/2", postcode="1010", city="Vienna", country="AT"
    )
    invoice.lines = [
        InvoiceLine(
            id="1",
            name="Licence",
            quantity=D("5"),
            net_price=D("240.00"),
            vat_category=AE,
            vat_rate=D("0"),
            net_amount=D("1200.00"),
        ),
        InvoiceLine(
            id="2",
            name="Workshop",
            quantity=D("1"),
            unit_code="LS",
            net_price=D("450.00"),
            vat_category=AE,
            vat_rate=D("0"),
            net_amount=D("450.00"),
        ),
    ]
    invoice.vat_breakdown = [
        VatBreakdown(
            category=AE,
            rate=D("0"),
            taxable_amount=D("1650.00"),
            tax_amount=D("0.00"),
            exemption_reason="Reverse charge",
        ),
    ]
    invoice.totals = Totals(
        line_net_total=D("1650.00"),
        tax_exclusive=D("1650.00"),
        vat_total=D("0.00"),
        tax_inclusive=D("1650.00"),
        payable=D("1650.00"),
    )
    return invoice


@pytest.fixture
def invoice() -> Invoice:
    return make_invoice()


@pytest.fixture
async def repo() -> AsyncIterator[Repository]:
    repository = await Repository.connect(":memory:")
    yield repository
    await repository.close()
