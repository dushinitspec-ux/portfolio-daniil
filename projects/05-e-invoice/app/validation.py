"""A subset of the EN 16931 and XRechnung business rules, implemented in Python.

Rule IDs and texts come from the official validation artefacts:
- EN 16931: CEN schematron, ConnectingEurope/eInvoicing-EN16931 (validation-1.3.17)
- XRechnung: KoSIT schematron, itplr-kosit/xrechnung-schematron (v2.6.0, XRechnung 3.0),
  which also enforces some Peppol rules (PEPPOL-EN16931-R010/R020)
The arithmetic follows the schematron tests, not only the rule texts: they decide where to
round, the tolerance of BR-CO-17, and that BR-CO-13 compares with BT-106. "APP-" rules are
this project's own checks, not official ones. scripts/official_check.py runs the official
schematron on the same samples to compare.

The official KoSIT validator (Java) remains the reference. This module checks the rules a PDF
conversion most often breaks, and explains each failure in plain words.
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.iban import iban_problem
from app.model import XRECHNUNG_CIUS, Invoice, InvoiceLine, Party, VatCategory
from app.money import ZERO, decimals, money

# ISO 3166-1 alpha-2 codes (the list in BR-CO-09), plus "EL", which Greece may use.
_ISO_COUNTRY_LIST = (
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ "
    "BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM "
    "DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS "
    "GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN "
    "KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ "
    "MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM "
    "PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV "
    "SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI "
    "VN VU WF WS YE YT ZA ZM ZW"
)
ISO_COUNTRIES = frozenset(_ISO_COUNTRY_LIST.split())
VAT_PREFIXES = ISO_COUNTRIES | {"EL", "XI"}  # XI: Northern Ireland, accepted by the CEN rule
# BR-DE-16: VAT categories that need a seller VAT ID or tax number in XRechnung.
DE16_CATEGORIES = {"S", "Z", "E", "AE", "K", "G", "L", "M"}


class Status(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "n/a"


class Severity(StrEnum):
    FATAL = "fatal"  # the invoice is not compliant
    WARNING = "warning"  # should be fixed; the official validator reports a warning too


class Source(StrEnum):
    EN16931 = "EN 16931"
    XRECHNUNG = "XRechnung 3.0"
    APP = "this app"


@dataclass(frozen=True)
class RuleResult:
    id: str
    title: str
    source: Source
    severity: Severity
    status: Status
    message: str = ""

    @property
    def failed(self) -> bool:
        return self.status is Status.FAILED


class NotApplicable(Exception):
    """Raised by a check when the rule does not apply to this invoice."""


Check = Callable[[Invoice], str | None]


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    source: Source
    severity: Severity
    check: Check

    def run(self, invoice: Invoice) -> RuleResult:
        try:
            problem = self.check(invoice)
        except NotApplicable:
            return RuleResult(
                self.id, self.title, self.source, self.severity, Status.NOT_APPLICABLE
            )
        status = Status.FAILED if problem else Status.PASSED
        return RuleResult(self.id, self.title, self.source, self.severity, status, problem or "")


RULES: list[Rule] = []


def rule(
    rule_id: str, title: str, source: Source = Source.EN16931, severity: Severity = Severity.FATAL
) -> Callable[[Check], Check]:
    def register(check: Check) -> Check:
        RULES.append(Rule(rule_id, title, source, severity, check))
        return check

    return register


# --- helpers ---------------------------------------------------------------------------


def _fmt(value: Decimal | None) -> str:
    return "missing" if value is None else f"{value:f}"


def _lines_where(invoice: Invoice, check: Callable[[InvoiceLine], bool]) -> str | None:
    bad = [line.id or str(i) for i, line in enumerate(invoice.lines, start=1) if check(line)]
    if not invoice.lines:
        raise NotApplicable
    return f"line(s) {', '.join(bad)}" if bad else None


def _category_lines(invoice: Invoice, category: VatCategory) -> list[InvoiceLine]:
    lines = [line for line in invoice.lines if line.vat_category == category]
    if not lines:
        raise NotApplicable
    return lines


def _sum(values: Iterable[Decimal | None]) -> Decimal:
    return sum((v for v in values if v is not None), ZERO)


def _xpath_round(value: Decimal) -> Decimal:
    """round(x * 100) div 100, as the schematron writes it: halves round up."""
    return money(value)


# --- EN 16931: presence of the core fields ---------------------------------------------


@rule("BR-01", "An Invoice shall have a Specification identifier (BT-24).")
def br_01(inv: Invoice) -> str | None:
    return None if inv.specification_id.strip() else "BT-24 is empty"


@rule("BR-02", "An Invoice shall have an Invoice number (BT-1).")
def br_02(inv: Invoice) -> str | None:
    return None if inv.number.strip() else "no invoice number found"


@rule("BR-03", "An Invoice shall have an Invoice issue date (BT-2).")
def br_03(inv: Invoice) -> str | None:
    return None if inv.issue_date else "no issue date found"


@rule("BR-04", "An Invoice shall have an Invoice type code (BT-3).")
def br_04(inv: Invoice) -> str | None:
    return None if inv.type_code.strip() else "no invoice type code"


@rule("BR-05", "An Invoice shall have an Invoice currency code (BT-5).")
def br_05(inv: Invoice) -> str | None:
    if re.fullmatch(r"[A-Z]{3}", inv.currency):
        return None
    return f"currency code {inv.currency!r} is not an ISO 4217 code"


@rule("BR-06", "An Invoice shall contain the Seller name (BT-27).")
def br_06(inv: Invoice) -> str | None:
    return None if inv.seller.name.strip() else "no seller name found"


@rule("BR-07", "An Invoice shall contain the Buyer name (BT-44).")
def br_07(inv: Invoice) -> str | None:
    return None if inv.buyer.name.strip() else "no buyer name found"


@rule("BR-08", "An Invoice shall contain the Seller postal address (BG-5).")
def br_08(inv: Invoice) -> str | None:
    return None if not inv.seller.address.is_empty else "no seller address found"


def _country_problem(party: Party) -> str | None:
    code = party.address.country
    if not code:
        return "no country code"
    return None if code in ISO_COUNTRIES else f"{code!r} is not an ISO 3166-1 code"


@rule("BR-09", "The Seller postal address (BG-5) shall contain a Seller country code (BT-40).")
def br_09(inv: Invoice) -> str | None:
    return _country_problem(inv.seller)


@rule("BR-10", "An Invoice shall contain the Buyer postal address (BG-8).")
def br_10(inv: Invoice) -> str | None:
    return None if not inv.buyer.address.is_empty else "no buyer address found"


@rule("BR-11", "The Buyer postal address shall contain a Buyer country code (BT-55).")
def br_11(inv: Invoice) -> str | None:
    return _country_problem(inv.buyer)


@rule("BR-12", "An Invoice shall have the Sum of Invoice line net amount (BT-106).")
def br_12(inv: Invoice) -> str | None:
    return None if inv.totals.line_net_total is not None else "BT-106 is missing"


@rule("BR-13", "An Invoice shall have the Invoice total amount without VAT (BT-109).")
def br_13(inv: Invoice) -> str | None:
    return None if inv.totals.tax_exclusive is not None else "BT-109 is missing"


@rule("BR-14", "An Invoice shall have the Invoice total amount with VAT (BT-112).")
def br_14(inv: Invoice) -> str | None:
    return None if inv.totals.tax_inclusive is not None else "BT-112 is missing"


@rule("BR-15", "An Invoice shall have the Amount due for payment (BT-115).")
def br_15(inv: Invoice) -> str | None:
    return None if inv.totals.payable is not None else "BT-115 is missing"


@rule("BR-16", "An Invoice shall have at least one Invoice line (BG-25).")
def br_16(inv: Invoice) -> str | None:
    return None if inv.lines else "no invoice lines found"


# --- EN 16931: invoice lines -----------------------------------------------------------


@rule("BR-21", "Each Invoice line (BG-25) shall have an Invoice line identifier (BT-126).")
def br_21(inv: Invoice) -> str | None:
    bad = _lines_where(inv, lambda line: not line.id.strip())
    return f"no line identifier on {bad}" if bad else None


@rule("BR-22", "Each Invoice line (BG-25) shall have an Invoiced quantity (BT-129).")
def br_22(inv: Invoice) -> str | None:
    bad = _lines_where(inv, lambda line: line.quantity is None)
    return f"no quantity on {bad}" if bad else None


@rule("BR-24", "Each Invoice line (BG-25) shall have an Invoice line net amount (BT-131).")
def br_24(inv: Invoice) -> str | None:
    bad = _lines_where(inv, lambda line: line.net_amount is None)
    return f"no net amount on {bad}" if bad else None


@rule("BR-25", "Each Invoice line (BG-25) shall contain the Item name (BT-153).")
def br_25(inv: Invoice) -> str | None:
    bad = _lines_where(inv, lambda line: not line.name.strip())
    return f"no item name on {bad}" if bad else None


@rule("BR-26", "Each Invoice line (BG-25) shall contain the Item net price (BT-146).")
def br_26(inv: Invoice) -> str | None:
    bad = _lines_where(inv, lambda line: line.net_price is None)
    return f"no net price on {bad}" if bad else None


@rule("BR-27", "The Item net price (BT-146) shall NOT be negative.")
def br_27(inv: Invoice) -> str | None:
    bad = _lines_where(inv, lambda line: line.net_price is not None and line.net_price < 0)
    return f"negative net price on {bad}" if bad else None


@rule(
    "BR-29",
    "If both Invoicing period start date (BT-73) and end date (BT-74) are given then the end "
    "date shall be later or equal to the start date.",
)
def br_29(inv: Invoice) -> str | None:
    if inv.period_start is None or inv.period_end is None:
        raise NotApplicable
    if inv.period_end >= inv.period_start:
        return None
    return f"the period ends ({inv.period_end}) before it starts ({inv.period_start})"


@rule(
    "BR-CO-04",
    "Each Invoice line (BG-25) shall be categorized with an Invoiced item VAT category code "
    "(BT-151).",
)
def br_co_04(inv: Invoice) -> str | None:
    bad = _lines_where(inv, lambda line: line.vat_category is None)
    return f"no VAT category on {bad}" if bad else None


@rule(
    "BR-CO-09",
    "The Seller VAT identifier (BT-31) and the Buyer VAT identifier (BT-48) shall have a prefix "
    "in accordance with ISO code ISO 3166-1 alpha-2. Nevertheless, Greece may use the prefix ‘EL’.",
)
def br_co_09(inv: Invoice) -> str | None:
    ids = [(role, p.vat_id) for role, p in (("seller", inv.seller), ("buyer", inv.buyer))]
    ids = [(role, vat_id) for role, vat_id in ids if vat_id]
    if not ids:
        raise NotApplicable
    bad = [f"{role} {vat_id}" for role, vat_id in ids if vat_id[:2] not in VAT_PREFIXES]
    return f"no country prefix: {', '.join(bad)}" if bad else None


# --- EN 16931: totals ------------------------------------------------------------------


@rule("BR-CO-10", "Sum of Invoice line net amount (BT-106) = Σ Invoice line net amount (BT-131).")
def br_co_10(inv: Invoice) -> str | None:
    if inv.totals.line_net_total is None or not inv.lines:
        raise NotApplicable
    expected = _xpath_round(_sum(line.net_amount for line in inv.lines))
    if inv.totals.line_net_total == expected:
        return None
    return f"the lines add up to {expected:f}, the invoice says {inv.totals.line_net_total:f}"


@rule(
    "BR-CO-13",
    "Invoice total amount without VAT (BT-109) = Σ Invoice line net amount (BT-131) - Sum of "
    "allowances on document level (BT-107) + Sum of charges on document level (BT-108).",
)
def br_co_13(inv: Invoice) -> str | None:
    # The official schematron compares BT-109 with BT-106 (LineExtensionAmount), not with the
    # sum of the lines: that sum is BR-CO-10's job. Without document-level allowances or
    # charges (not in this model) the test is BT-109 = BT-106.
    t = inv.totals
    if t.tax_exclusive is None or t.line_net_total is None:
        raise NotApplicable
    if t.tax_exclusive == t.line_net_total:
        return None
    return f"total without VAT is {t.tax_exclusive:f}, sum of lines is {t.line_net_total:f}"


@rule("BR-CO-14", "Invoice total VAT amount (BT-110) = Σ VAT category tax amount (BT-117).")
def br_co_14(inv: Invoice) -> str | None:
    if inv.totals.vat_total is None or not inv.vat_breakdown:
        raise NotApplicable
    expected = _xpath_round(_sum(b.tax_amount for b in inv.vat_breakdown))
    if inv.totals.vat_total == expected:
        return None
    return f"the VAT per rate adds up to {expected:f}, the total VAT is {inv.totals.vat_total:f}"


@rule(
    "BR-CO-15",
    "Invoice total amount with VAT (BT-112) = Invoice total amount without VAT (BT-109) + "
    "Invoice total VAT amount (BT-110).",
)
def br_co_15(inv: Invoice) -> str | None:
    t = inv.totals
    if t.tax_inclusive is None or t.tax_exclusive is None or t.vat_total is None:
        raise NotApplicable
    expected = _xpath_round(t.tax_exclusive + t.vat_total)
    if t.tax_inclusive == expected:
        return None
    return (
        f"{t.tax_exclusive:f} + {t.vat_total:f} = {expected:f}, "
        f"but the total with VAT is {t.tax_inclusive:f}"
    )


@rule(
    "BR-CO-16",
    "Amount due for payment (BT-115) = Invoice total amount with VAT (BT-112) - Paid amount "
    "(BT-113) + Rounding amount (BT-114).",
)
def br_co_16(inv: Invoice) -> str | None:
    t = inv.totals
    if t.payable is None or t.tax_inclusive is None:
        raise NotApplicable
    expected = _xpath_round(t.tax_inclusive - (t.prepaid or ZERO))
    if t.payable == expected:
        return None
    return f"expected {expected:f}, the amount due is {t.payable:f}"


@rule(
    "BR-CO-17",
    "VAT category tax amount (BT-117) = VAT category taxable amount (BT-116) x (VAT category "
    "rate (BT-119) / 100), rounded to two decimals.",
)
def br_co_17(inv: Invoice) -> str | None:
    rows = [b for b in inv.vat_breakdown if b.rate is not None and b.tax_amount is not None]
    if not rows:
        raise NotApplicable
    problems = []
    for b in rows:
        rate, tax = b.rate or ZERO, b.tax_amount or ZERO
        expected = _xpath_round(abs(b.taxable_amount or ZERO) * rate / 100)
        if rate.quantize(Decimal(1), ROUND_HALF_UP) == 0:
            ok = tax.quantize(Decimal(1), ROUND_HALF_UP) == 0
        else:
            # The CEN schematron accepts a difference below 1.00 (e.g. VAT summed per line).
            ok = abs(abs(tax) - expected) < 1
        if not ok:
            problems.append(
                f"{rate:f} %: {_fmt(b.taxable_amount)} gives {expected:f}, the invoice says {tax:f}"
            )
    return "; ".join(problems) or None


@rule("BR-CO-18", "An Invoice shall at least have one VAT breakdown group (BG-23).")
def br_co_18(inv: Invoice) -> str | None:
    return None if inv.vat_breakdown else "no VAT breakdown"


@rule(
    "BR-CO-25",
    "In case the Amount due for payment (BT-115) is positive, either the Payment due date (BT-9) "
    "or the Payment terms (BT-20) shall be present.",
)
def br_co_25(inv: Invoice) -> str | None:
    if inv.totals.payable is None or inv.totals.payable <= 0:
        raise NotApplicable
    if inv.due_date or inv.payment.terms.strip():
        return None
    return "neither a due date nor payment terms were found"


@rule(
    "BR-CO-26",
    "In order for the buyer to automatically identify a supplier, the Seller identifier (BT-29), "
    "the Seller legal registration identifier (BT-30) and/or the Seller VAT identifier (BT-31) "
    "shall be present.",
)
def br_co_26(inv: Invoice) -> str | None:
    if inv.seller.vat_id or inv.seller.legal_id:
        return None
    return "no seller VAT ID or registration number found"


# --- EN 16931: standard rated VAT (S) --------------------------------------------------


@rule(
    "BR-S-02",
    "An Invoice that contains an Invoice line where the Invoiced item VAT category code (BT-151) "
    'is "Standard rated" shall contain the Seller VAT Identifier (BT-31), the Seller tax '
    "registration identifier (BT-32) and/or the Seller tax representative VAT identifier (BT-63).",
)
def br_s_02(inv: Invoice) -> str | None:
    _category_lines(inv, VatCategory.STANDARD)
    return None if inv.seller.vat_id else "standard-rated lines, but no seller VAT ID"


@rule(
    "BR-S-05",
    'In an Invoice line where the Invoiced item VAT category code (BT-151) is "Standard rated" '
    "the Invoiced item VAT rate (BT-152) shall be greater than zero.",
)
def br_s_05(inv: Invoice) -> str | None:
    lines = _category_lines(inv, VatCategory.STANDARD)
    bad = [line.id for line in lines if line.vat_rate is None or line.vat_rate <= 0]
    return f"no positive VAT rate on line(s) {', '.join(bad)}" if bad else None


@rule(
    "BR-S-08",
    "For each different value of VAT category rate (BT-119) where the VAT category code (BT-118) "
    'is "Standard rated", the VAT category taxable amount (BT-116) shall equal the sum of '
    "Invoice line net amounts (BT-131) with that rate.",
)
def br_s_08(inv: Invoice) -> str | None:
    rows = [b for b in inv.vat_breakdown if b.category == VatCategory.STANDARD]
    if not rows:
        raise NotApplicable
    problems = []
    for b in rows:
        lines = _sum(
            line.net_amount
            for line in inv.lines
            if line.vat_category == VatCategory.STANDARD and line.vat_rate == b.rate
        )
        # The schematron accepts a difference below 1.00 here as well.
        if b.taxable_amount is None or abs(b.taxable_amount - lines) >= 1:
            problems.append(
                f"{_fmt(b.rate)} %: lines add up to {lines:f}, "
                f"taxable amount is {_fmt(b.taxable_amount)}"
            )
    return "; ".join(problems) or None


# --- EN 16931: reverse charge (AE) -----------------------------------------------------


@rule(
    "BR-AE-01",
    'An Invoice that contains an Invoice line where the VAT category code is "Reverse charge" '
    "shall contain in the VAT Breakdown (BG-23) exactly one VAT category code (BT-118) equal "
    'with "VAT reverse charge".',
)
def br_ae_01(inv: Invoice) -> str | None:
    _category_lines(inv, VatCategory.REVERSE_CHARGE)
    count = sum(b.category == VatCategory.REVERSE_CHARGE for b in inv.vat_breakdown)
    return None if count == 1 else f"{count} reverse-charge rows in the VAT breakdown"


@rule(
    "BR-AE-02",
    'An Invoice that contains an Invoice line where the VAT category code (BT-151) is "Reverse '
    'charge" shall contain the Seller VAT Identifier (BT-31) and the Buyer VAT identifier (BT-48).',
)
def br_ae_02(inv: Invoice) -> str | None:
    _category_lines(inv, VatCategory.REVERSE_CHARGE)
    missing = [role for role, p in (("seller", inv.seller), ("buyer", inv.buyer)) if not p.vat_id]
    return f"reverse charge needs the {' and '.join(missing)} VAT ID" if missing else None


@rule(
    "BR-AE-05",
    'In an Invoice line where the Invoiced item VAT category code (BT-151) is "Reverse charge" '
    "the Invoiced item VAT rate (BT-152) shall be 0 (zero).",
)
def br_ae_05(inv: Invoice) -> str | None:
    lines = _category_lines(inv, VatCategory.REVERSE_CHARGE)
    bad = [line.id for line in lines if line.vat_rate != 0]
    return f"VAT rate is not 0 on line(s) {', '.join(bad)}" if bad else None


@rule(
    "BR-AE-08",
    'In a VAT breakdown (BG-23) where the VAT category code (BT-118) is "Reverse charge" the VAT '
    "category taxable amount (BT-116) shall equal the sum of Invoice line net amounts (BT-131) "
    'where the VAT category code (BT-151) is "Reverse charge".',
)
def br_ae_08(inv: Invoice) -> str | None:
    rows = [b for b in inv.vat_breakdown if b.category == VatCategory.REVERSE_CHARGE]
    if not rows:
        raise NotApplicable
    total = _sum(
        line.net_amount for line in inv.lines if line.vat_category == VatCategory.REVERSE_CHARGE
    )
    bad = [b for b in rows if b.taxable_amount != total]
    if not bad:
        return None
    return f"lines add up to {total:f}, taxable amount is {_fmt(bad[0].taxable_amount)}"


@rule(
    "BR-AE-09",
    "The VAT category tax amount (BT-117) in a VAT breakdown (BG-23) where the VAT category code "
    '(BT-118) is "Reverse charge" shall be 0 (zero).',
)
def br_ae_09(inv: Invoice) -> str | None:
    rows = [b for b in inv.vat_breakdown if b.category == VatCategory.REVERSE_CHARGE]
    if not rows:
        raise NotApplicable
    bad = [b for b in rows if b.tax_amount != 0]
    return f"reverse-charge VAT amount is {_fmt(bad[0].tax_amount)}" if bad else None


@rule(
    "BR-AE-10",
    'A VAT Breakdown (BG-23) with VAT Category code (BT-118) "Reverse charge" shall have a VAT '
    'exemption reason code (BT-121), meaning "Reverse charge" or the VAT exemption reason text '
    '(BT-120) "Reverse charge" (or the equivalent standard text in another language).',
)
def br_ae_10(inv: Invoice) -> str | None:
    rows = [b for b in inv.vat_breakdown if b.category == VatCategory.REVERSE_CHARGE]
    if not rows:
        raise NotApplicable
    return None if all(b.exemption_reason.strip() for b in rows) else "no exemption reason text"


# --- EN 16931: at most two decimals (BR-DEC) -------------------------------------------


def _decimals_rule(
    rule_id: str, term: str, values: Callable[[Invoice], list[Decimal | None]]
) -> None:
    def check(inv: Invoice) -> str | None:
        present = [v for v in values(inv) if v is not None]
        if not present:
            raise NotApplicable
        bad = [f"{v:f}" for v in present if decimals(v) > 2]
        return f"more than two decimals: {', '.join(bad)}" if bad else None

    RULES.append(
        Rule(
            rule_id,
            f"The allowed maximum number of decimals for the {term} is 2.",
            Source.EN16931,
            Severity.FATAL,
            check,
        )
    )


_decimals_rule(
    "BR-DEC-09", "Sum of Invoice line net amount (BT-106)", lambda i: [i.totals.line_net_total]
)
_decimals_rule(
    "BR-DEC-12", "Invoice total amount without VAT (BT-109)", lambda i: [i.totals.tax_exclusive]
)
_decimals_rule("BR-DEC-13", "Invoice total VAT amount (BT-110)", lambda i: [i.totals.vat_total])
_decimals_rule(
    "BR-DEC-14", "Invoice total amount with VAT (BT-112)", lambda i: [i.totals.tax_inclusive]
)
_decimals_rule("BR-DEC-18", "Amount due for payment (BT-115)", lambda i: [i.totals.payable])
_decimals_rule(
    "BR-DEC-19",
    "VAT category taxable amount (BT-116)",
    lambda i: [b.taxable_amount for b in i.vat_breakdown],
)
_decimals_rule(
    "BR-DEC-20",
    "VAT category tax amount (BT-117)",
    lambda i: [b.tax_amount for b in i.vat_breakdown],
)
_decimals_rule(
    "BR-DEC-23", "Invoice line net amount (BT-131)", lambda i: [line.net_amount for line in i.lines]
)


# --- XRechnung 3.0 (BR-DE) -------------------------------------------------------------

XR = Source.XRECHNUNG


@rule("BR-DE-5", 'Das Element "Seller contact point" (BT-41) muss übermittelt werden.', XR)
def br_de_5(inv: Invoice) -> str | None:
    return None if inv.seller.contact_name.strip() else "no seller contact person found"


@rule(
    "BR-DE-6", 'Das Element "Seller contact telephone number" (BT-42) muss übermittelt werden.', XR
)
def br_de_6(inv: Invoice) -> str | None:
    return None if inv.seller.contact_phone.strip() else "no seller phone number found"


@rule("BR-DE-7", 'Das Element "Seller contact email address" (BT-43) muss übermittelt werden.', XR)
def br_de_7(inv: Invoice) -> str | None:
    return None if inv.seller.contact_email.strip() else "no seller e-mail address found"


@rule("BR-DE-3", 'Das Element "Seller city" (BT-37) muss übermittelt werden.', XR)
def br_de_3(inv: Invoice) -> str | None:
    return None if inv.seller.address.city.strip() else "no seller city found"


@rule("BR-DE-4", 'Das Element "Seller post code" (BT-38) muss übermittelt werden.', XR)
def br_de_4(inv: Invoice) -> str | None:
    return None if inv.seller.address.postcode.strip() else "no seller post code found"


@rule("BR-DE-8", 'Das Element "Buyer city" (BT-52) muss übermittelt werden.', XR)
def br_de_8(inv: Invoice) -> str | None:
    return None if inv.buyer.address.city.strip() else "no buyer city found"


@rule("BR-DE-9", 'Das Element "Buyer post code" (BT-53) muss übermittelt werden.', XR)
def br_de_9(inv: Invoice) -> str | None:
    return None if inv.buyer.address.postcode.strip() else "no buyer post code found"


@rule("BR-DE-14", 'Das Element "VAT category rate" (BT-119) muss übermittelt werden.', XR)
def br_de_14(inv: Invoice) -> str | None:
    if not inv.vat_breakdown:
        raise NotApplicable
    return None if all(b.rate is not None for b in inv.vat_breakdown) else "a VAT row has no rate"


@rule("BR-DE-15", 'Das Element "Buyer reference" (BT-10) muss übermittelt werden.', XR)
def br_de_15(inv: Invoice) -> str | None:
    if inv.buyer_reference.strip():
        return None
    return "no buyer reference (Leitweg-ID, order number or the reference the buyer asked for)"


@rule(
    "BR-DE-16",
    "Wenn in einer Rechnung die Steuercodes S, Z, E, AE, K, G, L oder M verwendet werden, muss "
    'mindestens eines der Elemente "Seller VAT identifier" (BT-31), "Seller tax registration '
    'identifier" (BT-32) oder "SELLER TAX REPRESENTATIVE PARTY" (BG-11) übermittelt werden.',
    XR,
)
def br_de_16(inv: Invoice) -> str | None:
    used = {line.vat_category for line in inv.lines if line.vat_category}
    if not used & DE16_CATEGORIES:
        raise NotApplicable
    return None if inv.seller.vat_id else "no seller VAT ID found"


@rule(
    "BR-DE-19",
    '"Payment account identifier" (BT-84) soll eine korrekte IBAN enthalten, wenn in "Payment '
    'means type code" (BT-81) mit dem Code 58 SEPA als Zahlungsmittel gefordert wird.',
    XR,
    Severity.WARNING,
)
def br_de_19(inv: Invoice) -> str | None:
    if inv.payment.means_code != "58" or not inv.payment.iban:
        raise NotApplicable
    problem = iban_problem(inv.payment.iban)
    return f"IBAN {inv.payment.iban}: {problem}" if problem else None


@rule(
    "BR-DE-21",
    'Das Element "Specification identifier" (BT-24) soll syntaktisch der Kennung des Standards '
    "XRechnung entsprechen.",
    XR,
    Severity.WARNING,
)
def br_de_21(inv: Invoice) -> str | None:
    return None if inv.specification_id == XRECHNUNG_CIUS else f"BT-24 is {inv.specification_id!r}"


@rule(
    "BR-DE-23-a",
    'Wenn BT-81 "Payment means type code" einen Schlüssel für Überweisungen enthält (30, 58), '
    'muss BG-17 "CREDIT TRANSFER" übermittelt werden.',
    XR,
)
def br_de_23a(inv: Invoice) -> str | None:
    if inv.payment.means_code not in {"30", "58"}:
        raise NotApplicable
    return None if inv.payment.iban else "credit transfer, but no IBAN found"


# --- this project's own check ----------------------------------------------------------

APP = Source.APP


@rule("APP-01", "The payment due date (BT-9) is not before the issue date (BT-2).", APP)
def app_01(inv: Invoice) -> str | None:
    if inv.due_date is None or inv.issue_date is None:
        raise NotApplicable
    if inv.due_date >= inv.issue_date:
        return None
    return f"due {inv.due_date}, issued {inv.issue_date}"


# --- Peppol rules that the KoSIT XRechnung 3.0 schematron also enforces --------------


@rule("PEPPOL-EN16931-R020", "Seller electronic address MUST be provided", XR)
def peppol_r020(inv: Invoice) -> str | None:
    return None if inv.seller.electronic_address else "no seller e-mail address (BT-34) found"


@rule("PEPPOL-EN16931-R010", "Buyer electronic address MUST be provided", XR)
def peppol_r010(inv: Invoice) -> str | None:
    if inv.buyer.electronic_address:
        return None
    return "the buyer's e-invoice address (BT-49) is not on the PDF; ask the buyer and enter it"


# --- running ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Report:
    results: list[RuleResult]

    @property
    def errors(self) -> list[RuleResult]:
        return [r for r in self.results if r.failed and r.severity is Severity.FATAL]

    @property
    def warnings(self) -> list[RuleResult]:
        return [r for r in self.results if r.failed and r.severity is Severity.WARNING]

    @property
    def passed(self) -> list[RuleResult]:
        return [r for r in self.results if r.status is Status.PASSED]

    @property
    def not_applicable(self) -> list[RuleResult]:
        return [r for r in self.results if r.status is Status.NOT_APPLICABLE]

    @property
    def valid(self) -> bool:
        return not self.errors

    def result(self, rule_id: str) -> RuleResult:
        return next(r for r in self.results if r.id == rule_id)


def validate(invoice: Invoice) -> Report:
    return Report([r.run(invoice) for r in RULES])
