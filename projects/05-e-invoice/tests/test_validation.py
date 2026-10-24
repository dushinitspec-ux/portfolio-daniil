"""Every business rule passes on a correct invoice and fails on a broken one."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal as D

import pytest

from app.model import Address, Invoice, VatBreakdown, VatCategory
from app.validation import RULES, Severity, Status, validate
from tests.conftest import extract_sample, make_invoice, make_reverse_charge_invoice

Mutation = Callable[[Invoice], None]


def _set(path: str, value: object) -> Mutation:
    """_set("seller.address.city", "") -> a function that sets that attribute."""

    def mutate(invoice: Invoice) -> None:
        *parents, last = path.split(".")
        target: object = invoice
        for name in parents:
            target = target[int(name)] if name.isdigit() else getattr(target, name)  # type: ignore[index]
        setattr(target, last, value)

    return mutate


def _duplicate_rc_row(invoice: Invoice) -> None:
    invoice.vat_breakdown.append(invoice.vat_breakdown[0].model_copy())


# rule id -> (base invoice, mutation that must make exactly this rule fail)
BREAKS: dict[str, tuple[Callable[[], Invoice], Mutation]] = {
    "BR-01": (make_invoice, _set("specification_id", "")),
    "BR-02": (make_invoice, _set("number", "")),
    "BR-03": (make_invoice, _set("issue_date", None)),
    "BR-04": (make_invoice, _set("type_code", "")),
    "BR-05": (make_invoice, _set("currency", "Euro")),
    "BR-06": (make_invoice, _set("seller.name", "")),
    "BR-07": (make_invoice, _set("buyer.name", "")),
    "BR-08": (make_invoice, _set("seller.address", Address())),
    "BR-09": (make_invoice, _set("seller.address.country", "")),
    "BR-10": (make_invoice, _set("buyer.address", Address())),
    "BR-11": (make_invoice, _set("buyer.address.country", "XX")),
    "BR-12": (make_invoice, _set("totals.line_net_total", None)),
    "BR-13": (make_invoice, _set("totals.tax_exclusive", None)),
    "BR-14": (make_invoice, _set("totals.tax_inclusive", None)),
    "BR-15": (make_invoice, _set("totals.payable", None)),
    "BR-16": (make_invoice, _set("lines", [])),
    "BR-21": (make_invoice, _set("lines.0.id", "")),
    "BR-22": (make_invoice, _set("lines.0.quantity", None)),
    "BR-24": (make_invoice, _set("lines.0.net_amount", None)),
    "BR-25": (make_invoice, _set("lines.0.name", "")),
    "BR-26": (make_invoice, _set("lines.0.net_price", None)),
    "BR-27": (make_invoice, _set("lines.0.net_price", D("-1.00"))),
    "BR-29": (make_invoice, _set("period_end", date(2026, 8, 31))),
    "BR-CO-04": (make_invoice, _set("lines.1.vat_category", None)),
    "BR-CO-09": (make_invoice, _set("buyer.vat_id", "123456789X")),
    "BR-CO-10": (make_invoice, _set("totals.line_net_total", D("760.00"))),
    "BR-CO-13": (make_invoice, _set("totals.tax_exclusive", D("760.00"))),
    "BR-CO-14": (make_invoice, _set("totals.vat_total", D("134.80"))),
    "BR-CO-15": (make_invoice, _set("totals.tax_inclusive", D("894.60"))),
    "BR-CO-16": (make_invoice, _set("totals.payable", D("900.00"))),
    "BR-CO-17": (make_invoice, _set("vat_breakdown.0.tax_amount", D("130.20"))),
    "BR-CO-18": (make_invoice, _set("vat_breakdown", [])),
    "BR-CO-25": (make_invoice, lambda i: (_set("due_date", None)(i), _set("payment.terms", "")(i))),
    "BR-CO-26": (make_invoice, _set("seller.vat_id", "")),
    "BR-S-02": (make_invoice, _set("seller.vat_id", "")),
    "BR-S-05": (make_invoice, _set("lines.0.vat_rate", D("0"))),
    "BR-S-08": (make_invoice, _set("vat_breakdown.0.taxable_amount", D("690.00"))),
    "BR-AE-01": (make_reverse_charge_invoice, _duplicate_rc_row),
    "BR-AE-02": (make_reverse_charge_invoice, _set("buyer.vat_id", "")),
    "BR-AE-05": (make_reverse_charge_invoice, _set("lines.0.vat_rate", D("19"))),
    "BR-AE-08": (make_reverse_charge_invoice, _set("vat_breakdown.0.taxable_amount", D("1600.00"))),
    "BR-AE-09": (make_reverse_charge_invoice, _set("vat_breakdown.0.tax_amount", D("10.00"))),
    "BR-AE-10": (make_reverse_charge_invoice, _set("vat_breakdown.0.exemption_reason", "")),
    "BR-DEC-09": (make_invoice, _set("totals.line_net_total", D("759.800"))),
    "BR-DEC-12": (make_invoice, _set("totals.tax_exclusive", D("759.800"))),
    "BR-DEC-13": (make_invoice, _set("totals.vat_total", D("134.790"))),
    "BR-DEC-14": (make_invoice, _set("totals.tax_inclusive", D("894.590"))),
    "BR-DEC-18": (make_invoice, _set("totals.payable", D("894.590"))),
    "BR-DEC-19": (make_invoice, _set("vat_breakdown.0.taxable_amount", D("680.000"))),
    "BR-DEC-20": (make_invoice, _set("vat_breakdown.0.tax_amount", D("129.200"))),
    "BR-DEC-23": (make_invoice, _set("lines.0.net_amount", D("680.000"))),
    "BR-DE-3": (make_invoice, _set("seller.address.city", "")),
    "BR-DE-4": (make_invoice, _set("seller.address.postcode", "")),
    "BR-DE-5": (make_invoice, _set("seller.contact_name", "")),
    "BR-DE-6": (make_invoice, _set("seller.contact_phone", "")),
    "BR-DE-7": (make_invoice, _set("seller.contact_email", "")),
    "BR-DE-8": (make_invoice, _set("buyer.address.city", "")),
    "BR-DE-9": (make_invoice, _set("buyer.address.postcode", "")),
    "BR-DE-14": (make_invoice, _set("vat_breakdown.0.rate", None)),
    "BR-DE-15": (make_invoice, _set("buyer_reference", "")),
    "BR-DE-16": (make_invoice, _set("seller.vat_id", "")),
    "BR-DE-19": (make_invoice, _set("payment.iban", "DE52000000000012345679")),
    "BR-DE-21": (make_invoice, _set("specification_id", "urn:cen.eu:en16931:2017")),
    "BR-DE-23-a": (make_invoice, _set("payment.iban", "")),
    "PEPPOL-EN16931-R010": (make_invoice, _set("buyer.electronic_address", "")),
    "PEPPOL-EN16931-R020": (make_invoice, _set("seller.electronic_address", "")),
    "APP-01": (make_invoice, _set("due_date", date(2026, 10, 1))),
}


@pytest.mark.parametrize("make", [make_invoice, make_reverse_charge_invoice])
def test_correct_invoices_pass_every_rule(make: Callable[[], Invoice]) -> None:
    report = validate(make())
    assert report.errors == []
    assert report.warnings == []
    assert report.valid


def test_every_rule_has_a_failing_case() -> None:
    assert {rule.id for rule in RULES} == set(BREAKS)
    assert len({rule.id for rule in RULES}) == len(RULES), "duplicate rule IDs"


@pytest.mark.parametrize("rule_id", list(BREAKS))
def test_rule_fails_with_its_id_and_a_message(rule_id: str) -> None:
    make, mutate = BREAKS[rule_id]
    invoice = make()
    assert validate(invoice).result(rule_id).status is Status.PASSED
    mutate(invoice)
    result = validate(invoice).result(rule_id)
    assert result.status is Status.FAILED
    assert result.message, "a failed rule must explain itself"
    assert result.title


def test_warnings_do_not_make_the_invoice_invalid(invoice: Invoice) -> None:
    invoice.payment.iban = "DE52000000000012345679"
    report = validate(invoice)
    assert [r.id for r in report.warnings] == ["BR-DE-19"]
    assert report.result("BR-DE-19").severity is Severity.WARNING
    assert report.valid


def test_rules_that_do_not_apply_are_marked(invoice: Invoice) -> None:
    invoice.period_start = invoice.period_end = None
    report = validate(invoice)
    assert report.result("BR-29").status is Status.NOT_APPLICABLE
    assert report.result("BR-AE-01").status is Status.NOT_APPLICABLE  # no reverse charge


def test_br_co_17_uses_the_official_tolerance(invoice: Invoice) -> None:
    # The CEN schematron accepts a VAT amount that differs by less than 1.00, e.g. when the
    # seller rounds VAT per line. One more cent and it fails.
    invoice.vat_breakdown[0].tax_amount = D("130.19")  # 129.20 + 0.99
    invoice.totals.vat_total = D("135.78")
    invoice.totals.tax_inclusive = invoice.totals.payable = D("895.58")
    assert validate(invoice).result("BR-CO-17").status is Status.PASSED
    invoice.vat_breakdown[0].tax_amount = D("130.20")
    assert validate(invoice).result("BR-CO-17").status is Status.FAILED


def test_br_co_17_rounds_half_up(invoice: Invoice) -> None:
    # 802.50 x 19 % = 152.475 -> 152.48 (half up), and the check is exact for it.
    invoice.vat_breakdown[0] = VatBreakdown(
        category=VatCategory.STANDARD, rate=D("19"), taxable_amount=D("802.50"),
        tax_amount=D("152.48"),
    )  # fmt: skip
    result = validate(invoice).result("BR-CO-17")
    assert result.status is Status.PASSED


def test_br_co_13_compares_with_the_sum_of_lines_total_bt_106(invoice: Invoice) -> None:
    # Regression: the rule text mentions Σ BT-131, but the official schematron tests
    # BT-109 = BT-106. A wrong BT-106 is BR-CO-10's error, not BR-CO-13's.
    invoice.totals.line_net_total = invoice.totals.tax_exclusive = D("760.00")
    report = validate(invoice)
    assert report.result("BR-CO-10").status is Status.FAILED
    assert report.result("BR-CO-13").status is Status.PASSED


def test_greek_vat_prefix_el_is_allowed(invoice: Invoice) -> None:
    invoice.buyer.vat_id = "EL123456789"
    assert validate(invoice).result("BR-CO-09").status is Status.PASSED


def test_messages_name_the_numbers(invoice: Invoice) -> None:
    invoice.totals.tax_inclusive = D("894.60")
    message = validate(invoice).result("BR-CO-15").message
    assert message == "759.80 + 134.79 = 894.59, but the total with VAT is 894.60"


@pytest.mark.parametrize(
    ("sample", "errors", "warnings"),
    [
        ("de-muster-gmbh.pdf", [], []),
        ("en-sample-studio.pdf", [], []),
        ("en-beispiel-software-reverse-charge.pdf", [], []),
        # The public buyer did not print an e-invoice address (BT-49).
        ("de-beispiel-it-service.pdf", ["PEPPOL-EN16931-R010"], []),
        # Wrong subtotal and a wrong IBAN digit. These are exactly the findings of the
        # official CEN and KoSIT schematron on the same XML (scripts/official_check.py).
        ("de-muster-gmbh-with-errors.pdf", ["BR-CO-10", "BR-CO-15"], ["BR-DE-19"]),
    ],
)
def test_bundled_samples(sample: str, errors: list[str], warnings: list[str]) -> None:
    report = validate(extract_sample(sample).invoice)
    assert sorted(r.id for r in report.errors) == sorted(errors)
    assert [r.id for r in report.warnings] == warnings
