"""The XML: parsed back and checked element by element."""

import re

from lxml import etree

from app.model import PEPPOL_BILLING_PROFILE, XRECHNUNG_CIUS, Invoice
from app.ubl import NS_CAC, NS_CBC, NS_INVOICE, to_xml
from tests.conftest import extract_sample, make_reverse_charge_invoice

NS = {"ubl": NS_INVOICE, "cac": NS_CAC, "cbc": NS_CBC}

# Top-level order required by the UBL 2.1 Invoice schema (xsd:sequence), for the elements
# this project writes.
UBL_ORDER = [
    "CustomizationID", "ProfileID", "ID", "IssueDate", "DueDate", "InvoiceTypeCode", "Note",
    "DocumentCurrencyCode", "BuyerReference", "InvoicePeriod", "OrderReference",
    "AccountingSupplierParty", "AccountingCustomerParty", "Delivery", "PaymentMeans",
    "PaymentTerms", "TaxTotal", "LegalMonetaryTotal", "InvoiceLine",
]  # fmt: skip


def parse(invoice: Invoice) -> etree._Element:
    return etree.fromstring(to_xml(invoice))


def text(root: etree._Element, path: str) -> str | None:
    return root.findtext(path, namespaces=NS)


def test_header_and_identifiers(invoice: Invoice) -> None:
    root = parse(invoice)
    assert root.tag == f"{{{NS_INVOICE}}}Invoice"
    assert text(root, "cbc:CustomizationID") == XRECHNUNG_CIUS
    assert XRECHNUNG_CIUS.endswith("#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0")
    assert text(root, "cbc:ProfileID") == PEPPOL_BILLING_PROFILE
    assert text(root, "cbc:ID") == "RE-2026-0001"
    assert text(root, "cbc:IssueDate") == "2026-10-15"
    assert text(root, "cbc:DueDate") == "2026-10-29"
    assert text(root, "cbc:InvoiceTypeCode") == "380"
    assert text(root, "cbc:DocumentCurrencyCode") == "EUR"
    assert text(root, "cbc:BuyerReference") == "PO-7781"
    assert text(root, "cac:InvoicePeriod/cbc:StartDate") == "2026-09-01"


def test_parties(invoice: Invoice) -> None:
    root = parse(invoice)
    seller = root.find("cac:AccountingSupplierParty/cac:Party", NS)
    assert seller is not None
    endpoint = seller.find("cbc:EndpointID", NS)
    assert endpoint is not None and endpoint.get("schemeID") == "EM"
    assert endpoint.text == "rechnung@muster-gmbh.example"
    # BT-27 Seller name goes to RegistrationName in the UBL binding
    assert text(seller, "cac:PartyLegalEntity/cbc:RegistrationName") == "Muster GmbH"
    assert text(seller, "cac:PostalAddress/cbc:StreetName") == "Musterstraße 1"
    assert text(seller, "cac:PostalAddress/cac:Country/cbc:IdentificationCode") == "DE"
    assert text(seller, "cac:PartyTaxScheme/cbc:CompanyID") == "DE123456789"
    assert text(seller, "cac:PartyTaxScheme/cac:TaxScheme/cbc:ID") == "VAT"
    assert text(seller, "cac:Contact/cbc:Telephone") == "+49 30 000000"
    buyer = root.find("cac:AccountingCustomerParty/cac:Party", NS)
    assert buyer is not None
    assert text(buyer, "cac:PartyLegalEntity/cbc:RegistrationName") == "Beispiel AG"
    assert buyer.find("cac:Contact", NS) is None  # only the seller contact is written


def test_totals_and_vat_breakdown(invoice: Invoice) -> None:
    root = parse(invoice)
    assert text(root, "cac:TaxTotal/cbc:TaxAmount") == "134.79"
    subtotals = root.findall("cac:TaxTotal/cac:TaxSubtotal", NS)
    assert [
        (text(s, "cbc:TaxableAmount"), text(s, "cbc:TaxAmount"),
         text(s, "cac:TaxCategory/cbc:ID"), text(s, "cac:TaxCategory/cbc:Percent"))
        for s in subtotals
    ] == [("680.00", "129.20", "S", "19"), ("79.80", "5.59", "S", "7")]  # fmt: skip
    total = "cac:LegalMonetaryTotal/cbc:"
    assert text(root, total + "LineExtensionAmount") == "759.80"
    assert text(root, total + "TaxExclusiveAmount") == "759.80"
    assert text(root, total + "TaxInclusiveAmount") == "894.59"
    assert text(root, total + "PayableAmount") == "894.59"


def test_lines(invoice: Invoice) -> None:
    lines = parse(invoice).findall("cac:InvoiceLine", NS)
    assert len(lines) == 2
    first = lines[0]
    quantity = first.find("cbc:InvoicedQuantity", NS)
    assert quantity is not None and (quantity.text, quantity.get("unitCode")) == ("8", "HUR")
    assert text(first, "cbc:LineExtensionAmount") == "680.00"
    assert text(first, "cac:Item/cbc:Name") == "Wartung"
    assert text(first, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID") == "S"
    assert text(first, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent") == "19"
    assert text(first, "cac:Price/cbc:PriceAmount") == "85.00"


def test_payment(invoice: Invoice) -> None:
    root = parse(invoice)
    assert text(root, "cac:PaymentMeans/cbc:PaymentMeansCode") == "58"
    assert text(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID") == (
        "DE52000000000012345678"
    )
    assert text(root, "cac:PaymentTerms/cbc:Note") == "14 Tage netto"


def test_element_order_follows_the_ubl_schema(invoice: Invoice) -> None:
    names = [etree.QName(child).localname for child in parse(invoice)]
    positions = [UBL_ORDER.index(name) for name in names]
    assert positions == sorted(positions), names


def test_every_amount_has_two_decimals_and_a_currency(invoice: Invoice) -> None:
    root = parse(invoice)
    amounts = [e for e in root.iter() if e.get("currencyID") is not None]
    assert len(amounts) > 10
    assert all(e.get("currencyID") == "EUR" for e in amounts)
    for element in amounts:
        assert re.fullmatch(r"-?\d+\.\d{2}", element.text or ""), (element.tag, element.text)


def test_missing_values_are_left_out_not_written_empty(invoice: Invoice) -> None:
    invoice.due_date = None
    invoice.order_reference = ""
    invoice.seller.contact_phone = ""
    root = parse(invoice)
    assert root.find("cbc:DueDate", NS) is None
    assert root.find("cac:OrderReference", NS) is None
    assert root.find(".//cac:Contact/cbc:Telephone", NS) is None
    assert all((e.text or "").strip() or len(e) for e in root.iter())


def test_reverse_charge_xml() -> None:
    root = parse(make_reverse_charge_invoice())
    category = root.find("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory", NS)
    assert category is not None
    assert text(category, "cbc:ID") == "AE"
    assert text(category, "cbc:Percent") == "0"
    assert text(category, "cbc:TaxExemptionReason") == "Reverse charge"
    assert text(root, "cac:TaxTotal/cbc:TaxAmount") == "0.00"


def test_declaration_and_encoding() -> None:
    xml = to_xml(extract_sample("de-muster-gmbh.pdf").invoice)
    assert xml.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n<ubl:Invoice')
    assert "Musterstraße 1" in xml.decode("utf-8")
    assert "Netzwerke für Einsteiger" in xml.decode("utf-8")
