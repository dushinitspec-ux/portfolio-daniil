"""Writes the invoice as an XRechnung 3.0 UBL 2.1 Invoice.

The element order follows the UBL 2.1 Invoice schema (the XSD uses xsd:sequence, so order
matters) and the mapping of business terms follows the official XRechnung UBL examples, e.g.
BT-27 Seller name -> cac:PartyLegalEntity/cbc:RegistrationName. Elements whose value is
missing are left out; validation has already reported them.
"""

from decimal import Decimal

from lxml import etree

from app.model import PEPPOL_BILLING_PROFILE, Invoice, Party, VatBreakdown
from app.money import format_amount, format_number, format_price

NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NSMAP = {"ubl": NS_INVOICE, "cac": NS_CAC, "cbc": NS_CBC}


def _cac(parent: etree._Element, name: str) -> etree._Element:
    return etree.SubElement(parent, f"{{{NS_CAC}}}{name}")


def _cbc(
    parent: etree._Element, name: str, value: str | None, **attributes: str
) -> etree._Element | None:
    if value is None or value == "":
        return None
    element = etree.SubElement(parent, f"{{{NS_CBC}}}{name}", attributes)
    element.text = value
    return element


def _amount(parent: etree._Element, name: str, value: Decimal | None, currency: str) -> None:
    if value is not None:
        _cbc(parent, name, format_amount(value), currencyID=currency)


def _party(parent: etree._Element, party: Party, *, seller: bool) -> None:
    node = _cac(parent, "Party")
    if party.electronic_address:  # BT-34 / BT-49, scheme EM = e-mail
        _cbc(node, "EndpointID", party.electronic_address, schemeID="EM")
    address = party.address
    if not address.is_empty:
        postal = _cac(node, "PostalAddress")
        _cbc(postal, "StreetName", address.street)
        _cbc(postal, "CityName", address.city)
        _cbc(postal, "PostalZone", address.postcode)
        if address.country:
            _cbc(_cac(postal, "Country"), "IdentificationCode", address.country)
    if party.vat_id:
        tax = _cac(node, "PartyTaxScheme")
        _cbc(tax, "CompanyID", party.vat_id)
        _cbc(_cac(tax, "TaxScheme"), "ID", "VAT")
    legal = _cac(node, "PartyLegalEntity")
    _cbc(legal, "RegistrationName", party.name)
    _cbc(legal, "CompanyID", party.legal_id)
    if seller and (party.contact_name or party.contact_phone or party.contact_email):
        contact = _cac(node, "Contact")
        _cbc(contact, "Name", party.contact_name)
        _cbc(contact, "Telephone", party.contact_phone)
        _cbc(contact, "ElectronicMail", party.contact_email)


def _tax_category(parent: etree._Element, name: str, code: str, rate: Decimal | None) -> None:
    category = _cac(parent, name)
    _cbc(category, "ID", code)
    if rate is not None:
        _cbc(category, "Percent", format_number(rate))
    _cbc(_cac(category, "TaxScheme"), "ID", "VAT")


def _subtotal(parent: etree._Element, item: VatBreakdown, currency: str) -> None:
    subtotal = _cac(parent, "TaxSubtotal")
    _amount(subtotal, "TaxableAmount", item.taxable_amount, currency)
    _amount(subtotal, "TaxAmount", item.tax_amount, currency)
    category = _cac(subtotal, "TaxCategory")
    _cbc(category, "ID", item.category.value)
    if item.rate is not None:
        _cbc(category, "Percent", format_number(item.rate))
    _cbc(category, "TaxExemptionReason", item.exemption_reason)
    _cbc(_cac(category, "TaxScheme"), "ID", "VAT")


def build(invoice: Invoice) -> etree._Element:
    cur = invoice.currency
    root = etree.Element(f"{{{NS_INVOICE}}}Invoice", nsmap=NSMAP)
    _cbc(root, "CustomizationID", invoice.specification_id)  # BT-24
    _cbc(root, "ProfileID", PEPPOL_BILLING_PROFILE)  # BT-23
    _cbc(root, "ID", invoice.number)  # BT-1
    _cbc(root, "IssueDate", invoice.issue_date.isoformat() if invoice.issue_date else None)
    _cbc(root, "DueDate", invoice.due_date.isoformat() if invoice.due_date else None)  # BT-9
    _cbc(root, "InvoiceTypeCode", invoice.type_code)  # BT-3
    _cbc(root, "Note", invoice.note)  # BT-22
    _cbc(root, "DocumentCurrencyCode", cur)  # BT-5
    _cbc(root, "BuyerReference", invoice.buyer_reference)  # BT-10
    if invoice.period_start or invoice.period_end:  # BG-14
        period = _cac(root, "InvoicePeriod")
        _cbc(
            period, "StartDate", invoice.period_start.isoformat() if invoice.period_start else None
        )
        _cbc(period, "EndDate", invoice.period_end.isoformat() if invoice.period_end else None)
    if invoice.order_reference:  # BT-13
        _cbc(_cac(root, "OrderReference"), "ID", invoice.order_reference)

    _party(_cac(root, "AccountingSupplierParty"), invoice.seller, seller=True)  # BG-4
    _party(_cac(root, "AccountingCustomerParty"), invoice.buyer, seller=False)  # BG-7

    if invoice.delivery_date:  # BT-72
        _cbc(_cac(root, "Delivery"), "ActualDeliveryDate", invoice.delivery_date.isoformat())

    payment = invoice.payment
    means = _cac(root, "PaymentMeans")  # BG-16
    _cbc(means, "PaymentMeansCode", payment.means_code)  # BT-81
    _cbc(means, "PaymentID", payment.remittance_info)  # BT-83
    if payment.iban:  # BG-17
        account = _cac(means, "PayeeFinancialAccount")
        _cbc(account, "ID", payment.iban)  # BT-84
        _cbc(account, "Name", payment.account_name)  # BT-85
        if payment.bic:
            _cbc(_cac(account, "FinancialInstitutionBranch"), "ID", payment.bic)  # BT-86
    if payment.terms:
        _cbc(_cac(root, "PaymentTerms"), "Note", payment.terms)  # BT-20

    tax_total = _cac(root, "TaxTotal")
    _amount(tax_total, "TaxAmount", invoice.totals.vat_total, cur)  # BT-110
    for item in invoice.vat_breakdown:  # BG-23
        _subtotal(tax_total, item, cur)

    totals = invoice.totals
    monetary = _cac(root, "LegalMonetaryTotal")  # BG-22
    _amount(monetary, "LineExtensionAmount", totals.line_net_total, cur)  # BT-106
    _amount(monetary, "TaxExclusiveAmount", totals.tax_exclusive, cur)  # BT-109
    _amount(monetary, "TaxInclusiveAmount", totals.tax_inclusive, cur)  # BT-112
    _amount(monetary, "PrepaidAmount", totals.prepaid, cur)  # BT-113
    _amount(monetary, "PayableAmount", totals.payable, cur)  # BT-115

    for line in invoice.lines:  # BG-25
        node = _cac(root, "InvoiceLine")
        _cbc(node, "ID", line.id)  # BT-126
        if line.quantity is not None:  # BT-129, BT-130
            _cbc(node, "InvoicedQuantity", format_number(line.quantity), unitCode=line.unit_code)
        _amount(node, "LineExtensionAmount", line.net_amount, cur)  # BT-131
        item = _cac(node, "Item")
        _cbc(item, "Name", line.name)  # BT-153
        if line.vat_category is not None:  # BG-30
            _tax_category(item, "ClassifiedTaxCategory", line.vat_category.value, line.vat_rate)
        if line.net_price is not None:  # BT-146
            _cbc(_cac(node, "Price"), "PriceAmount", format_price(line.net_price), currencyID=cur)
    return root


XML_DECLARATION = b'<?xml version="1.0" encoding="UTF-8"?>\n'


def to_xml(invoice: Invoice) -> bytes:
    # lxml writes the declaration with single quotes; most XML tools print double quotes.
    return XML_DECLARATION + etree.tostring(build(invoice), encoding="UTF-8", pretty_print=True)
