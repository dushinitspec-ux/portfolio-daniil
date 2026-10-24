"""Fills values the PDF does not print but EN 16931 needs, and says so.

Every derived value is listed in `Extraction.derived`, and the web page marks it. Arithmetic
rules on a derived value pass by construction, so the note matters: "BT-110 was computed"
is not the same as "the seller's BT-110 is correct".
"""

import re
from decimal import Decimal

from app.model import Extraction, Invoice, Party, VatBreakdown, VatCategory
from app.money import ZERO, vat_amount

# VAT ID prefixes that are not the ISO country code.
VAT_PREFIX_COUNTRY = {"EL": "GR"}


def _country_from_vat_id(party: Party) -> str:
    prefix = party.vat_id[:2].upper()
    if not re.fullmatch(r"[A-Z]{2}", prefix):
        return ""
    return VAT_PREFIX_COUNTRY.get(prefix, prefix)


def _countries(invoice: Invoice, derived: list[str]) -> None:
    for role, party in (("Seller", invoice.seller), ("Buyer", invoice.buyer)):
        if party.address.country or party.address.is_empty:
            continue
        if code := _country_from_vat_id(party):
            party.address.country = code
            derived.append(f"{role} country {code} taken from the VAT ID prefix")
    seller_country = invoice.seller.address.country
    buyer = invoice.buyer.address
    if not buyer.country and seller_country == "DE" and re.fullmatch(r"\d{5}", buyer.postcode):
        buyer.country = "DE"
        derived.append("Buyer country DE assumed: German 5-digit postcode, seller in Germany")


def _lines(invoice: Invoice, derived: list[str]) -> None:
    rates = {b.rate for b in invoice.vat_breakdown if b.rate is not None}
    single_rate = next(iter(rates)) if len(rates) == 1 else None
    rate_notes = 0
    for index, line in enumerate(invoice.lines, start=1):
        if not line.id:
            line.id = str(index)
        if line.vat_rate is None and single_rate is not None:
            line.vat_rate = single_rate
            rate_notes += 1
        if line.vat_category is None and line.vat_rate is not None:
            line.vat_category = _category_for(invoice, line.vat_rate)
        if line.net_amount is None and line.quantity is not None and line.net_price is not None:
            line.net_amount = (line.quantity * line.net_price).quantize(Decimal("0.01"))
            derived.append(f"Line {line.id}: net amount = quantity x price (not printed)")
    if rate_notes:
        derived.append(
            f"VAT rate {single_rate} % set on {rate_notes} line(s) from the only VAT rate in "
            "the totals (the table has no VAT column)"
        )


def _category_for(invoice: Invoice, rate: Decimal) -> VatCategory | None:
    if rate > 0:
        return VatCategory.STANDARD
    zero = [b.category for b in invoice.vat_breakdown if b.rate == 0]
    return zero[0] if len(zero) == 1 else None


def _breakdown(invoice: Invoice, derived: list[str]) -> None:
    groups: dict[tuple[VatCategory, Decimal], Decimal] = {}
    for line in invoice.lines:
        if line.vat_category is None or line.vat_rate is None or line.net_amount is None:
            continue
        key = (line.vat_category, line.vat_rate)
        groups[key] = groups.get(key, ZERO) + line.net_amount

    if not invoice.vat_breakdown and groups:
        for (category, rate), taxable in groups.items():
            invoice.vat_breakdown.append(
                VatBreakdown(
                    category=category,
                    rate=rate,
                    taxable_amount=taxable,
                    tax_amount=vat_amount(taxable, rate),
                )
            )
        derived.append("VAT breakdown computed from the lines (not printed per rate)")
        return

    for item in invoice.vat_breakdown:
        if item.taxable_amount is None and item.rate is not None:
            item.taxable_amount = groups.get((item.category, item.rate), ZERO)
            derived.append(
                f"VAT {item.rate} %: taxable amount = sum of the lines at this rate (not printed)"
            )
        if item.tax_amount is None and item.rate is not None and item.taxable_amount is not None:
            item.tax_amount = vat_amount(item.taxable_amount, item.rate)
            derived.append(f"VAT {item.rate} %: tax amount computed (not printed)")


def _totals(invoice: Invoice, derived: list[str]) -> None:
    t = invoice.totals
    nets = [line.net_amount for line in invoice.lines]
    if t.line_net_total is None and nets and None not in nets:
        t.line_net_total = sum((n for n in nets if n is not None), ZERO)
        derived.append("BT-106 sum of line net amounts computed (not printed)")
    if t.tax_exclusive is None and t.line_net_total is not None:
        t.tax_exclusive = t.line_net_total
        derived.append("BT-109 total without VAT = BT-106 (no allowances or charges)")
    taxes = [b.tax_amount for b in invoice.vat_breakdown]
    if t.vat_total is None and taxes and None not in taxes:
        t.vat_total = sum((x for x in taxes if x is not None), ZERO)
        if len(taxes) > 1:
            derived.append("BT-110 total VAT = sum of the VAT amounts per rate")
    if t.tax_inclusive is None and t.tax_exclusive is not None and t.vat_total is not None:
        t.tax_inclusive = t.tax_exclusive + t.vat_total
        derived.append("BT-112 total with VAT computed (not printed)")
    if t.payable is None and t.tax_inclusive is not None:
        t.payable = t.tax_inclusive - (t.prepaid or ZERO)
        if t.prepaid:
            derived.append("BT-115 amount due = total with VAT minus the prepaid amount")


def complete(extraction: Extraction) -> Extraction:
    """Return a copy with derived values filled in and listed in `derived`."""
    result = extraction.model_copy(deep=True)
    invoice, derived = result.invoice, result.derived

    _countries(invoice, derived)
    _lines(invoice, derived)
    _breakdown(invoice, derived)
    _totals(invoice, derived)

    if not invoice.buyer_reference and invoice.order_reference:
        invoice.buyer_reference = invoice.order_reference
        derived.append(
            f"BT-10 buyer reference: none printed, used the order number {invoice.order_reference}"
        )
    seller = invoice.seller
    if not seller.electronic_address and seller.contact_email:
        seller.electronic_address = seller.contact_email
    return result
