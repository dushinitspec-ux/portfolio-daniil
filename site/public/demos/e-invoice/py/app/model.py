"""The typed invoice: the subset of the EN 16931 semantic model this project handles.

Field comments name the EN 16931 business terms (BT-n) and groups (BG-n). Money is Decimal
everywhere. Values that are missing on the PDF stay empty (None or ""), so validation can
report them instead of the extractor guessing.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

# BT-24: XRechnung 3.0 CIUS identifier, as defined in the KoSIT XRechnung schematron.
XRECHNUNG_CIUS = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
# BT-23: business process type used in the official XRechnung UBL examples (Peppol billing).
PEPPOL_BILLING_PROFILE = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"


class VatCategory(StrEnum):
    """UNTDID 5305 VAT category codes used by EN 16931 (BT-118, BT-151)."""

    STANDARD = "S"
    ZERO = "Z"
    EXEMPT = "E"
    REVERSE_CHARGE = "AE"
    INTRA_COMMUNITY = "K"
    EXPORT = "G"
    NOT_SUBJECT = "O"


class Address(BaseModel):
    street: str = ""  # BT-35 / BT-50
    postcode: str = ""  # BT-38 / BT-53
    city: str = ""  # BT-37 / BT-52
    country: str = ""  # BT-40 / BT-55, ISO 3166-1 alpha-2

    @property
    def is_empty(self) -> bool:
        return not (self.street or self.postcode or self.city or self.country)


class Party(BaseModel):
    name: str = ""  # BT-27 / BT-44
    address: Address = Field(default_factory=Address)  # BG-5 / BG-8
    vat_id: str = ""  # BT-31 / BT-48
    legal_id: str = ""  # BT-30 / BT-47, e.g. "HRB 000000"
    electronic_address: str = ""  # BT-34 / BT-49 (an e-mail address, scheme "EM")
    contact_name: str = ""  # BT-41 / BT-56
    contact_phone: str = ""  # BT-42 / BT-57
    contact_email: str = ""  # BT-43 / BT-58


class InvoiceLine(BaseModel):
    id: str = ""  # BT-126
    name: str = ""  # BT-153
    quantity: Decimal | None = None  # BT-129
    unit_code: str = "C62"  # BT-130, UN/ECE Recommendation 20/21 ("C62" = one)
    net_price: Decimal | None = None  # BT-146
    vat_category: VatCategory | None = None  # BT-151
    vat_rate: Decimal | None = None  # BT-152, percent
    net_amount: Decimal | None = None  # BT-131


class VatBreakdown(BaseModel):  # BG-23
    category: VatCategory = VatCategory.STANDARD  # BT-118
    rate: Decimal | None = None  # BT-119, percent
    taxable_amount: Decimal | None = None  # BT-116
    tax_amount: Decimal | None = None  # BT-117
    exemption_reason: str = ""  # BT-120, required for reverse charge


class Totals(BaseModel):  # BG-22
    line_net_total: Decimal | None = None  # BT-106
    tax_exclusive: Decimal | None = None  # BT-109
    vat_total: Decimal | None = None  # BT-110
    tax_inclusive: Decimal | None = None  # BT-112
    prepaid: Decimal | None = None  # BT-113
    payable: Decimal | None = None  # BT-115


class Payment(BaseModel):  # BG-16
    means_code: str = "58"  # BT-81: 58 = SEPA credit transfer, 30 = credit transfer
    iban: str = ""  # BT-84
    account_name: str = ""  # BT-85
    bic: str = ""  # BT-86
    terms: str = ""  # BT-20
    remittance_info: str = ""  # BT-83


class Invoice(BaseModel):
    specification_id: str = XRECHNUNG_CIUS  # BT-24
    number: str = ""  # BT-1
    issue_date: date | None = None  # BT-2
    type_code: str = "380"  # BT-3: 380 = commercial invoice
    currency: str = "EUR"  # BT-5
    due_date: date | None = None  # BT-9
    buyer_reference: str = ""  # BT-10 (Leitweg-ID for German public buyers)
    order_reference: str = ""  # BT-13
    delivery_date: date | None = None  # BT-72
    period_start: date | None = None  # BT-73
    period_end: date | None = None  # BT-74
    note: str = ""  # BT-22
    seller: Party = Field(default_factory=Party)  # BG-4
    buyer: Party = Field(default_factory=Party)  # BG-7
    payment: Payment = Field(default_factory=Payment)
    lines: list[InvoiceLine] = Field(default_factory=list)  # BG-25
    vat_breakdown: list[VatBreakdown] = Field(default_factory=list)  # BG-23
    totals: Totals = Field(default_factory=Totals)


class Extraction(BaseModel):
    """What an extractor returns: the invoice plus notes about how values were obtained."""

    invoice: Invoice
    extractor: str
    # Fields that were computed from other values because the PDF did not print them.
    derived: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
