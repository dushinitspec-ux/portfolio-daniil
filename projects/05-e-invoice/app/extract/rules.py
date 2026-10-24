"""Rule-based extractor: the offline demo mode, no API key needed.

It reads German and English invoices with common labels ("Rechnungsnummer", "Invoice
number", "Summe netto", "Subtotal", ...), party blocks ("Bill to", the DIN 5008 address
window under the sender line) and a line-item table found by its header row. It works on the
bundled sample layouts and on invoices that look like them; anything else is a job for the
LLM extractor. It only reads what is printed; missing values are left empty and later
derived (with a note) or reported by validation.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.extract.parsing import (
    EMAIL,
    IBAN,
    PHONE,
    POSTCODE_CITY,
    VAT_ID,
    VAT_LABEL,
    all_dates,
    country_code,
    parse_date,
    unit_code,
)
from app.iban import IBAN_LENGTHS, compact
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
from app.money import AmountError, NumberStyle, parse_number
from app.pdf_text import Cell, PdfText, TextLine

NAME = "rules"

# Labels for single values. A label matches at the start of a cell; the value is the rest of
# that cell (after an optional colon) or, if that is empty, the next cell on the line.
LABELS: dict[str, list[str]] = {
    "number": [r"rechnungsnummer", r"rechnungs-?nr\.?", r"invoice\s+(?:number|no\.?|#)"],
    "issue_date": [r"rechnungsdatum", r"invoice\s+date", r"issue\s+date", r"date", r"datum"],
    "due_date": [r"due\s+date", r"due", r"fällig(?:keit)?(?:\s+am)?", r"zahlbar\s+bis"],
    "delivery_date": [r"leistungsdatum", r"lieferdatum", r"delivery(?:\s+date)?"],
    "period": [r"service\s+period", r"leistungszeitraum", r"abrechnungszeitraum"],
    "order_reference": [
        r"ihre\s+bestellung",
        r"bestell(?:nummer|-?nr\.?)",
        r"po\s+(?:number|no\.?)",
        r"purchase\s+order",
    ],
    "buyer_reference": [
        r"leitweg-?id",
        r"your\s+reference",
        r"ihr\s+zeichen",
        r"buyer\s+reference",
        r"käuferreferenz",
    ],
    "contact": [r"ansprechpartner(?:in)?", r"contact(?:\s+person)?", r"kontakt"],
    "terms": [r"payment\s+terms", r"zahlungsziel", r"zahlungsbedingungen", r"terms"],
    "account_name": [r"kontoinhaber(?:in)?", r"account\s+(?:holder|name)"],
    # Where the buyer wants to receive e-invoices (BT-49).
    "buyer_email": [
        r"e-?rechnung(?:en)?\s+an",
        r"rechnungseingang",
        r"e-?invoices?\s+to",
        r"invoice\s+e-?mail",
    ],
}

SELLER_BLOCK = [r"from", r"von", r"rechnungssteller", r"seller", r"supplier"]
BUYER_BLOCK = [
    r"bill\s+to",
    r"invoice\s+to",
    r"customer",
    r"rechnungsempfänger",
    r"kunde",
    r"an",
    r"buyer",
]

# Table header words, by column role.
COLUMNS: dict[str, list[str]] = {
    "pos": [r"pos\.?", r"no\.?", r"nr\.?", r"#"],
    "code": [r"art\.?-?nr\.?", r"artikel-?nr\.?", r"item\s+no\.?", r"sku"],
    "name": [r"bezeichnung", r"beschreibung", r"leistung", r"artikel", r"description", r"item"],
    "qty": [r"menge", r"anzahl", r"qty", r"quantity"],
    "unit": [r"einheit", r"unit"],
    "price": [r"einzelpreis", r"preis(?:/einh\.?)?", r"e-?preis", r"unit\s+price", r"price"],
    "vat": [r"ust\.?", r"mwst\.?", r"vat", r"tax", r"steuer"],
    "amount": [r"betrag", r"gesamt(?:preis)?", r"summe", r"amount", r"net", r"total", r"netto"],
}

NET_TOTAL = re.compile(
    r"^(?:summe\s+netto|nettobetrag|netto(?:summe)?|zwischensumme|gesamt\s+netto"
    r"|subtotal|net\s+(?:amount|total)|total\s+net|total\s+excl\.?\s+vat)\b",
    re.IGNORECASE,
)
GROSS_TOTAL = re.compile(
    r"^(?:rechnungsbetrag|gesamtbetrag|bruttobetrag|gesamtsumme|endbetrag|zu\s+zahlen"
    r"|total\s+due|total\s+amount|amount\s+due|total(?:\s+\(?[A-Z]{3}\)?)?|grand\s+total)\b",
    re.IGNORECASE,
)
VAT_TOTAL_LINE = re.compile(
    r"(?:zzgl\.?\s*)?(?:(?P<rate1>\d+(?:[.,]\d+)?)\s*%\s*(?:ust|mwst|vat|umsatzsteuer)"
    r"|(?:ust|mwst|vat|umsatzsteuer)\.?\s*\(?(?P<rate2>\d+(?:[.,]\d+)?)\s*%\)?)"
    r"(?:.*?\b(?:auf|on|from)\s+(?P<base>[\d.,]+))?",
    re.IGNORECASE,
)
REVERSE_CHARGE = re.compile(
    r"reverse[\s-]charge|steuerschuldnerschaft\s+des\s+leistungsempfängers"
    r"|umkehr\s+der\s+steuerschuld",
    re.IGNORECASE,
)
TITLE_NUMBER = re.compile(
    r"^(?:rechnung|invoice)\s+(?:nr\.?\s*|no\.?\s*)?(?P<number>[A-Z0-9][\w/.-]*\d[\w/.-]*)"
    r"(?:\s+(?:vom|dated|of)\s+(?P<date>.+))?$",
    re.IGNORECASE,
)
DUE_IN_SENTENCE = re.compile(
    r"(?:bis\s+(?:zum\s+)?|fällig\s+am\s+|due\s+(?:on|by)\s+)(\S+(?:\s+\S+,?\s+\d{4})?)",
    re.IGNORECASE,
)
TERMS_SENTENCE = re.compile(r"(ohne\s+abzug|zahlbar|days\s+net|tage\s+netto)", re.IGNORECASE)
CURRENCY = re.compile(r"\b(EUR|CHF|USD|GBP|PLN|CZK|SEK|DKK)\b|€")


@dataclass
class _Doc:
    lines: list[TextLine]
    style: NumberStyle

    def cells(self) -> list[tuple[int, int, Cell]]:
        return [(i, j, c) for i, line in enumerate(self.lines) for j, c in enumerate(line.cells)]


def _label_regex(patterns: list[str]) -> re.Pattern[str]:
    return re.compile(rf"^(?:{'|'.join(patterns)})\s*(?::|\.(?=\s)|\s|$)\s*(.*)$", re.IGNORECASE)


def _detect_style(text: str) -> NumberStyle:
    german = len(re.findall(r"\b(?:rechnung|menge|betrag|ust|mwst|datum|summe)\b", text, re.I))
    english = len(re.findall(r"\b(?:invoice|qty|quantity|amount|vat|total|date)\b", text, re.I))
    return "de" if german >= english else "en"


def _find_value(doc: _Doc, key: str) -> str:
    pattern = _label_regex(LABELS[key])
    for i, j, cell in doc.cells():
        # A label can also start a "·"-separated segment: "IBAN ... · Kontoinhaberin E. B."
        for segment in cell.text.split(" · "):
            match = pattern.match(segment.strip())
            if not match:
                continue
            rest = match.group(1).strip()
            if rest:
                return rest
            line = doc.lines[i]
            if j + 1 < len(line.cells):
                return line.cells[j + 1].text.strip()
    return ""


def _number(text: str, style: NumberStyle) -> Decimal | None:
    try:
        return parse_number(text, style)
    except AmountError:
        return None


# --- parties ---------------------------------------------------------------------------


def _parse_block(parts: list[str]) -> Party:
    """Party from address lines: name first, then street, "12345 City", country, VAT ID."""
    party = Party()
    address = Address()
    rest: list[str] = []
    for index, raw in enumerate(parts):
        text = raw.strip().strip(",")
        if not text:
            continue
        if index == 0:
            party.name = text
            continue
        if (vat := VAT_LABEL.match(text)) and (vid := VAT_ID.search(text[vat.end() :])):
            party.vat_id = vid.group(1) + vid.group(2)
        elif email := EMAIL.fullmatch(text):
            party.electronic_address = email.group(0)
        elif m := POSTCODE_CITY.match(text):
            address.postcode, address.city = m.group(1), m.group(2).strip()
        elif code := country_code(text):
            address.country = code
        else:
            rest.append(text)
    streets = [t for t in rest if re.search(r"\d", t) and re.search(r"[A-Za-zäöüß]{3}", t)]
    if streets:
        address.street = streets[-1]
    party.address = address
    return party


BLOCK_GAP = 28.0  # points (~10 mm): a larger vertical gap ends an address block


def _block_below(doc: _Doc, line_index: int, x0: float, tolerance: float = 6.0) -> list[str]:
    """Cells in the same column as `x0`, on the lines after `line_index`, until a gap."""
    block: list[str] = []
    previous_top = doc.lines[line_index].top
    for line in doc.lines[line_index + 1 :]:
        cell = next((c for c in line.cells if abs(c.x0 - x0) <= tolerance), None)
        if cell is None or line.top - previous_top > BLOCK_GAP:
            break
        block.append(cell.text)
        previous_top = line.top
    return block


def _labelled_block(doc: _Doc, patterns: list[str]) -> list[str] | None:
    # The label is the whole cell ("BILL TO") or ends with a colon ("Customer: ..."), so
    # "Kunde" does not match inside "Kundennummer: K-10087".
    label = re.compile(rf"^(?:{'|'.join(patterns)})\s*(?::\s*(.*))?$", re.IGNORECASE)
    for i, _, cell in doc.cells():
        match = label.match(cell.text)
        if not match:
            continue
        inline = (match.group(1) or "").strip()
        if inline:  # "Rechnungsempfänger: Stadt Musterstadt, Amt für IT, ..."
            return [part.strip() for part in inline.split(",")]
        block = _block_below(doc, i, cell.x0)
        if block:
            return block
    return None


def _sender_line(doc: _Doc) -> tuple[int, Cell] | None:
    """DIN 5008 sender line: "Muster GmbH · Musterstraße 1 · 10115 Berlin"."""
    for i, _, cell in doc.cells():
        parts = [p.strip() for p in cell.text.split("·")]
        if len(parts) >= 3 and any(POSTCODE_CITY.match(p) for p in parts):
            return i, cell
    return None


def _parties(doc: _Doc) -> tuple[Party, Party, str]:
    """Seller, buyer and the seller contact name found next to the sender line."""
    contact = ""
    seller_block = _labelled_block(doc, SELLER_BLOCK)
    buyer_block = _labelled_block(doc, BUYER_BLOCK)
    sender = _sender_line(doc)

    if seller_block is None and sender is not None:
        parts = [p.strip() for p in sender[1].text.split("·")]
        seller_block = [parts[0]]
        for part in parts[1:]:
            if re.match(r"^(?:inh\.|inhaber(?:in)?)\s+", part, re.IGNORECASE):
                contact = re.sub(r"^(?:inh\.|inhaber(?:in)?)\s+", "", part, flags=re.IGNORECASE)
            else:
                seller_block.append(part)
    if seller_block is None:
        # Letterhead: the first line is the seller name, an address line follows below it.
        first = doc.lines[0].cells[0]
        below = _block_below(doc, 0, first.x0)
        address = next((b for b in below[:3] if "," in b), "")
        seller_block = [first.text, *address.split(",")]
    if buyer_block is None and sender is not None:  # address window under the sender line
        buyer_block = _block_below(doc, sender[0], sender[1].x0)

    return _parse_block(seller_block), _parse_block(buyer_block or []), contact


# --- line items ------------------------------------------------------------------------


def _header(doc: _Doc) -> tuple[int, dict[str, Cell]] | None:
    for i, line in enumerate(doc.lines):
        roles: dict[str, Cell] = {}
        for cell in line.cells:
            for role, patterns in COLUMNS.items():
                if role not in roles and re.fullmatch("|".join(patterns), cell.text, re.I):
                    roles[role] = cell
                    break
        if {"name", "amount"} <= roles.keys() and len(roles) >= 3:
            return i, roles
    return None


def _column(cell: Cell, roles: dict[str, Cell]) -> str:
    """Column role for a body cell: the header it overlaps most, else the nearest one."""

    def overlap(header: Cell) -> float:
        return min(cell.x1, header.x1) - max(cell.x0, header.x0)

    best = max(roles.items(), key=lambda item: overlap(item[1]))
    if overlap(best[1]) > 0:
        return best[0]
    centre = (cell.x0 + cell.x1) / 2
    return min(roles.items(), key=lambda item: abs((item[1].x0 + item[1].x1) / 2 - centre))[0]


def _lines(doc: _Doc) -> list[InvoiceLine]:
    found = _header(doc)
    if not found:
        return []
    start, roles = found
    items: list[InvoiceLine] = []
    for line in doc.lines[start + 1 :]:
        values: dict[str, str] = {}
        for cell in line.cells:
            role = _column(cell, roles)
            values[role] = f"{values[role]} {cell.text}".strip() if role in values else cell.text
        amount = _number(values.get("amount", ""), doc.style)
        if values.keys() == {"name"} and items:  # description continued on the next line
            items[-1].name += " " + values["name"]
            continue
        if amount is None or not values.get("name"):
            break
        item = InvoiceLine(id=values.get("pos", "") or str(len(items) + 1), name=values["name"])
        item.net_amount = amount
        qty_text = values.get("qty", "")
        if m := re.match(r"^([\d.,]+)\s*(.*)$", qty_text):
            item.quantity = _number(m.group(1), doc.style)
            unit_label = values.get("unit", "") or m.group(2)
            item.unit_code = unit_code(unit_label) if unit_label else item.unit_code
        item.net_price = _number(values.get("price", ""), doc.style)
        if vat := re.search(r"(\d+(?:[.,]\d+)?)\s*%", values.get("vat", "")):
            item.vat_rate = _number(vat.group(1), doc.style)
        items.append(item)
    return items


# --- totals ----------------------------------------------------------------------------


def _amount_in(line: TextLine, style: NumberStyle) -> Decimal | None:
    for cell in reversed(line.cells[1:]):
        if (value := _number(cell.text, style)) is not None:
            return value
    return None


def _totals(doc: _Doc, reverse_charge: bool) -> tuple[Totals, list[VatBreakdown]]:
    totals = Totals()
    breakdown: list[VatBreakdown] = []
    for line in doc.lines:
        label = line.cells[0].text
        amount = _amount_in(line, doc.style)
        if amount is None:
            continue
        if NET_TOTAL.match(label) and totals.line_net_total is None:
            totals.line_net_total = amount
            totals.tax_exclusive = amount
        elif (m := VAT_TOTAL_LINE.match(label)) and len(line.cells) <= 3:
            rate = _number(m.group("rate1") or m.group("rate2"), doc.style)
            base = _number(m.group("base"), doc.style) if m.group("base") else None
            category = VatCategory.STANDARD
            reason = ""
            if rate == 0:
                category = VatCategory.REVERSE_CHARGE if reverse_charge else VatCategory.ZERO
                reason = "Reverse charge" if reverse_charge else ""
            breakdown.append(
                VatBreakdown(
                    category=category,
                    rate=rate,
                    taxable_amount=base,
                    tax_amount=amount,
                    exemption_reason=reason,
                )
            )
        elif GROSS_TOTAL.match(label) and totals.tax_inclusive is None:
            totals.tax_inclusive = amount
    return totals, breakdown


# --- the extractor ---------------------------------------------------------------------


def _contact(doc: _Doc, seller: Party, buyer: Party, contact_from_sender: str) -> None:
    if not buyer.electronic_address and (email := EMAIL.search(_find_value(doc, "buyer_email"))):
        buyer.electronic_address = email.group(0)
    text = "\n".join(line.text for line in doc.lines)
    if emails := [e for e in EMAIL.findall(text) if e != buyer.electronic_address]:
        seller.contact_email = emails[0]
        seller.electronic_address = emails[0]
    contact = _find_value(doc, "contact")
    parts = [p.strip() for p in re.split(r"[·,]", contact) if p.strip()]
    names = [p for p in parts if not re.search(r"[\d@]", p)]
    seller.contact_name = names[0] if names else contact_from_sender
    labelled_phone = re.compile(r"(?:tel\.?|telefon|phone|fon)\s*:?\s*(\+?\d[\d\s/()-]+\d)", re.I)
    contact_label = _label_regex(LABELS["contact"])
    for line in doc.lines:
        if m := labelled_phone.search(line.text):
            seller.contact_phone = m.group(1).strip()
            break
    if not seller.contact_phone:  # "Contact: Erika Musterfrau · +49 89 000000 · billing@..."
        for line in doc.lines:
            if contact_label.match(line.text) and (phone := PHONE.search(line.text)):
                seller.contact_phone = phone.group(0).strip()
                break


def _vat_ids(doc: _Doc, seller: Party, buyer: Party) -> None:
    labelled: list[tuple[str, str]] = []
    for line in doc.lines:
        for cell in line.cells:
            for m in VAT_LABEL.finditer(cell.text):
                if vid := VAT_ID.match(cell.text[m.end() :]):
                    labelled.append((cell.text[: m.start()], vid.group(1) + vid.group(2)))
    for prefix, vat_id in labelled:
        if re.search(r"\b(?:ihre|your|kunden)\b", prefix, re.IGNORECASE) and not buyer.vat_id:
            buyer.vat_id = vat_id
    if not seller.vat_id:
        seller.vat_id = next((v for _, v in labelled if v != buyer.vat_id), "")


def _payment(doc: _Doc, number: str) -> Payment:
    payment = Payment()
    text = "\n".join(line.text for line in doc.lines)
    if m := IBAN.search(text):
        value = compact(m.group(1))
        payment.iban = value[: IBAN_LENGTHS.get(value[:2], len(value))]
    payment.account_name = _find_value(doc, "account_name").split("·")[0].strip()
    payment.terms = _find_value(doc, "terms")
    if not payment.terms:
        sentence = next((ln.text for ln in doc.lines if TERMS_SENTENCE.search(ln.text)), "")
        payment.terms = sentence
    payment.remittance_info = number
    return payment


def extract_text(pdf: PdfText) -> Extraction:
    lines = [line for line in pdf.lines if line.cells]
    plain = "\n".join(line.text for line in lines)
    doc = _Doc(lines=lines, style=_detect_style(plain))
    warnings: list[str] = []

    invoice = Invoice()
    invoice.number = _find_value(doc, "number")
    issue = _find_value(doc, "issue_date")
    for line in lines:  # "Rechnung RE-2610-007 vom 20.10.2026"
        if m := TITLE_NUMBER.match(line.text):
            invoice.number = invoice.number or m.group("number")
            issue = issue or (m.group("date") or "")
            break
    invoice.issue_date = parse_date(issue, doc.style)
    invoice.delivery_date = parse_date(_find_value(doc, "delivery_date"), doc.style)
    invoice.due_date = parse_date(_find_value(doc, "due_date"), doc.style)
    if invoice.due_date is None:
        for line in lines:
            if (m := DUE_IN_SENTENCE.search(line.text)) and (
                due := parse_date(m.group(1), doc.style)
            ):
                invoice.due_date = due
                break
    period = all_dates(_find_value(doc, "period"), doc.style)
    if len(period) == 2:
        invoice.period_start, invoice.period_end = period
    invoice.order_reference = _find_value(doc, "order_reference")
    invoice.buyer_reference = _find_value(doc, "buyer_reference")
    if currency := CURRENCY.search(plain):
        invoice.currency = currency.group(1) or "EUR"

    seller, buyer, contact = _parties(doc)
    _contact(doc, seller, buyer, contact)
    _vat_ids(doc, seller, buyer)
    invoice.seller, invoice.buyer = seller, buyer

    reverse_charge = bool(REVERSE_CHARGE.search(plain))
    invoice.lines = _lines(doc)
    if not invoice.lines:
        warnings.append("No line-item table found (no header row with description and amount).")
    invoice.totals, invoice.vat_breakdown = _totals(doc, reverse_charge)
    if reverse_charge:  # keep the printed reverse-charge sentence as the invoice note
        for index, line in enumerate(lines):
            if REVERSE_CHARGE.search(line.text) and _amount_in(line, doc.style) is None:
                follow = lines[index + 1].text if index + 1 < len(lines) else ""
                invoice.note = f"{line.text} {follow}" if follow.startswith("(") else line.text
                break
    invoice.payment = _payment(doc, invoice.number)
    return Extraction(invoice=invoice, extractor=NAME, warnings=warnings)


class RuleBasedExtractor:
    name = NAME

    async def extract(self, pdf: PdfText) -> Extraction:
        return extract_text(pdf)
