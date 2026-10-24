"""Generates the bundled sample invoices: four layouts in German and English, plus one copy
of the German layout with deliberate mistakes.

All parties, VAT IDs, phone numbers and IBANs are fictional ("Muster GmbH", "Beispiel AG",
bank code 0000 0000). Amounts are computed with Decimal here, so the correct samples add up.

    uv run python samples/generate.py
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent
CENT = Decimal("0.01")
GREY = (110, 110, 110)
RULE = (200, 200, 200)


@dataclass(frozen=True)
class Line:
    name: str
    qty: Decimal
    unit: str
    price: Decimal
    rate: Decimal
    code: str = ""

    @property
    def net(self) -> Decimal:
        return (self.qty * self.price).quantize(CENT, ROUND_HALF_UP)


@dataclass(frozen=True)
class Sample:
    lines: tuple[Line, ...]
    printed_net: Decimal | None = None  # override to print a wrong subtotal
    iban: str = ""

    @property
    def net(self) -> Decimal:
        return sum((line.net for line in self.lines), Decimal(0))

    def by_rate(self) -> dict[Decimal, Decimal]:
        result: dict[Decimal, Decimal] = {}
        for line in self.lines:
            result[line.rate] = result.get(line.rate, Decimal(0)) + line.net
        return dict(sorted(result.items(), reverse=True))

    def vat(self, rate: Decimal) -> Decimal:
        return (self.by_rate()[rate] * rate / 100).quantize(CENT, ROUND_HALF_UP)

    @property
    def vat_total(self) -> Decimal:
        return sum((self.vat(rate) for rate in self.by_rate()), Decimal(0))

    @property
    def gross(self) -> Decimal:
        return self.net + self.vat_total


def de(value: Decimal) -> str:
    """1.040,37"""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def en(value: Decimal) -> str:
    """1,040.37"""
    return f"{value:,.2f}"


def de_qty(value: Decimal) -> str:
    return f"{value.normalize():f}".replace(".", ",")


@dataclass
class Doc:
    pdf: FPDF = field(default_factory=lambda: FPDF(format="A4", unit="mm"))

    def __post_init__(self) -> None:
        self.pdf.set_creation_date(datetime(2026, 10, 20, 9, 0, tzinfo=UTC))
        self.pdf.set_creator("e-invoice sample generator")
        self.pdf.set_auto_page_break(False)
        self.pdf.add_page()

    def text(
        self,
        x: float,
        y: float,
        value: str,
        size: float = 9.5,
        style: str = "",
        w: float = 0,
        align: str = "L",
        color: tuple[int, int, int] = (20, 20, 20),
    ) -> None:
        self.pdf.set_font("Helvetica", style=style, size=size)
        self.pdf.set_text_color(*color)
        self.pdf.set_xy(x, y)
        self.pdf.cell(w=w, h=size * 0.45, text=value, align=align)

    def rule(self, x1: float, y: float, x2: float, width: float = 0.2) -> None:
        self.pdf.set_draw_color(*RULE)
        self.pdf.set_line_width(width)
        self.pdf.line(x1, y, x2, y)

    def save(self, name: str, title: str) -> Path:
        self.pdf.set_title(title)
        path = OUT / name
        self.pdf.output(str(path))
        return path


# --- Layout A: German business letter (DIN 5008 style), two VAT rates -------------------

MUSTER = Sample(
    lines=(
        Line("Wartung Netzwerk (September)", Decimal("8"), "Std.", Decimal("85.00"), Decimal(19)),
        Line("Patchkabel Cat 6, 2 m", Decimal("25"), "Stk.", Decimal("4.90"), Decimal(19)),
        Line(
            'Fachbuch "Netzwerke für Einsteiger"',
            Decimal("2"),
            "Stk.",
            Decimal("39.90"),
            Decimal(7),
        ),
    ),
    iban="DE52 0000 0000 0012 3456 78",
)


def layout_din(sample: Sample, name: str, number: str) -> Path:
    d = Doc()
    d.text(120, 14, "MUSTER GMBH", size=17, style="B", w=70, align="R")
    d.text(120, 22, "IT-Service & Netzwerke", size=9, w=70, align="R", color=GREY)

    d.text(20, 45, "Muster GmbH · Musterstraße 1 · 10115 Berlin", size=7, color=GREY)
    d.rule(20, 48.5, 95)
    buyer = ["Beispiel AG", "Einkauf", "Beispielweg 12", "20095 Hamburg"]
    meta = [
        f"Rechnungsnummer: {number}",
        "Rechnungsdatum: 15.10.2026",
        "Leistungsdatum: 30.09.2026",
        "Kundennummer: K-10087",
        "Ihre Bestellung: PO-7781",
        "Ihre USt-IdNr.: DE987654321",
        "Ansprechpartner: Max Mustermann",
        "E-Rechnung an: rechnung@beispiel-ag.example",
    ]
    for i, value in enumerate(buyer):
        d.text(20, 52 + i * 5, value, size=10)
    for i, value in enumerate(meta):
        d.text(125, 52 + i * 5, value, size=9)

    d.text(20, 98, "Rechnung", size=15, style="B")
    d.text(20, 108, "Sehr geehrte Damen und Herren,", size=10)
    d.text(20, 113, "für unsere Leistungen im September berechnen wir Ihnen:", size=10)

    cols = [
        (20, 10, "L"),
        (30, 72, "L"),
        (102, 16, "R"),
        (120, 16, "L"),
        (136, 22, "R"),
        (158, 14, "R"),
        (172, 18, "R"),
    ]
    head = ["Pos", "Bezeichnung", "Menge", "Einheit", "Einzelpreis", "USt.", "Betrag"]
    y = 124
    for (x, w, align), value in zip(cols, head, strict=True):
        d.text(x, y, value, size=8.5, style="B", w=w, align=align)
    d.rule(20, y + 5, 190, 0.4)
    y += 8
    for pos, line in enumerate(sample.lines, start=1):
        row = [
            str(pos),
            line.name,
            de_qty(line.qty),
            line.unit,
            de(line.price),
            f"{line.rate} %",
            de(line.net),
        ]
        for (x, w, align), value in zip(cols, row, strict=True):
            d.text(x, y, value, size=9, w=w, align=align)
        y += 6
    d.rule(20, y, 190)

    y += 4
    net = sample.printed_net if sample.printed_net is not None else sample.net
    totals = [("Summe netto", de(net))]
    for rate, base in sample.by_rate().items():
        totals.append((f"zzgl. {rate} % USt. auf {de(base)}", de(sample.vat(rate))))
    for label, value in totals:
        d.text(110, y, label, size=9, w=55)
        d.text(165, y, value, size=9, w=25, align="R")
        y += 5.5
    d.rule(110, y, 190, 0.4)
    d.text(110, y + 2, "Rechnungsbetrag", size=10, style="B", w=55)
    d.text(165, y + 2, de(sample.gross), size=10, style="B", w=25, align="R")

    y += 16
    d.text(
        20, y, "Bitte überweisen Sie den Rechnungsbetrag ohne Abzug bis zum 29.10.2026.", size=10
    )
    d.text(20, y + 5, f"Verwendungszweck: {number}", size=10)
    d.text(20, y + 15, "Mit freundlichen Grüßen", size=10)
    d.text(20, y + 20, "Muster GmbH", size=10)

    d.rule(20, 268, 190)
    footer = [
        ["Muster GmbH", "Musterstraße 1", "10115 Berlin"],
        ["Tel. +49 30 000000", "rechnung@muster-gmbh.example", "USt-IdNr. DE123456789"],
        ["Bank: Musterbank", f"IBAN {sample.iban}", "Amtsgericht Berlin HRB 000000"],
    ]
    for c, column in enumerate(footer):
        for r, value in enumerate(column):
            d.text(20 + c * 60, 271 + r * 4, value, size=7, color=GREY)
    return d.save(name, f"Rechnung {number}")


# --- Layout B: English, modern, "From" and "Bill to" side by side, one VAT rate ----------

SAMPLE_STUDIO = Sample(
    lines=(
        Line(
            "Website maintenance (monthly)", Decimal("1"), "month", Decimal("1200.00"), Decimal(19)
        ),
        Line("UX workshop, half day", Decimal("2"), "days", Decimal("650.00"), Decimal(19)),
        Line("Stock photo licence", Decimal("3"), "pcs", Decimal("19.99"), Decimal(19)),
    ),
    iban="DE45 0000 0000 0098 7654 32",
)


def layout_modern(sample: Sample, name: str) -> Path:
    d = Doc()
    d.text(20, 18, "INVOICE", size=26, style="B")
    d.text(110, 18, "Sample Studio GmbH", size=12, style="B", w=80, align="R")
    d.text(110, 24, "Design & web development", size=9, w=80, align="R", color=GREY)

    meta = [
        ("Invoice number", "INV-2026-0042"),
        ("Issue date", "October 8, 2026"),
        ("Due date", "November 7, 2026"),
        ("Service period", "September 1, 2026 to September 30, 2026"),
        ("PO number", "4500012345"),
    ]
    for i, (label, value) in enumerate(meta):
        d.text(20, 40 + i * 5.5, label, size=9, color=GREY)
        d.text(60, 40 + i * 5.5, value, size=9)

    d.text(20, 76, "FROM", size=8, style="B", color=GREY)
    d.text(110, 76, "BILL TO", size=8, style="B", color=GREY)
    seller = [
        "Sample Studio GmbH",
        "Beispielallee 5",
        "80331 Munich",
        "Germany",
        "VAT ID DE111222333",
    ]
    buyer = [
        "Muster Handel KG",
        "Attn. Accounts Payable",
        "Musterring 99",
        "50667 Cologne",
        "Germany",
        "VAT ID DE444555666",
        "ap@muster-handel.example",
    ]
    for i, value in enumerate(seller):
        d.text(20, 82 + i * 5, value, size=10, style="B" if i == 0 else "")
    for i, value in enumerate(buyer):
        d.text(110, 82 + i * 5, value, size=10, style="B" if i == 0 else "")

    y = 124
    d.pdf.set_fill_color(240, 240, 240)
    d.pdf.rect(20, y - 2, 170, 8, style="F")
    cols = [(22, 88, "L"), (110, 25, "R"), (135, 27, "R"), (162, 26, "R")]
    for (x, w, align), value in zip(
        cols, ["Description", "Qty", "Unit price", "Amount"], strict=True
    ):
        d.text(x, y, value, size=8.5, style="B", w=w, align=align)
    y += 10
    for line in sample.lines:
        row = [line.name, f"{line.qty.normalize():f} {line.unit}", en(line.price), en(line.net)]
        for (x, w, align), value in zip(cols, row, strict=True):
            d.text(x, y, value, size=9.5, w=w, align=align)
        y += 7
    d.rule(20, y, 190)

    y += 5
    (rate,) = sample.by_rate()
    for label, value, style in [
        ("Subtotal", en(sample.net), ""),
        (f"VAT {rate}%", en(sample.vat(rate)), ""),
        ("Total due (EUR)", en(sample.gross), "B"),
    ]:
        d.text(120, y, label, size=10, style=style, w=40)
        d.text(160, y, value, size=10, style=style, w=28, align="R")
        y += 6.5

    y += 10
    d.text(20, y, "PAYMENT DETAILS", size=8, style="B", color=GREY)
    for i, value in enumerate(
        [
            "Bank transfer to Sample Studio GmbH",
            f"IBAN {sample.iban}",
            "Please use INV-2026-0042 as the payment reference.",
            "Payment terms: 30 days net",
        ]
    ):
        d.text(20, y + 6 + i * 5, value, size=9.5)

    d.rule(20, 272, 190)
    d.text(
        20,
        275,
        "Contact: Erika Musterfrau · +49 89 000000 · billing@sample-studio.example",
        size=8,
        color=GREY,
    )
    d.text(20, 279, "Sample Studio GmbH · Amtsgericht München HRB 000000", size=8, color=GREY)
    return d.save(name, "Invoice INV-2026-0042")


# --- Layout C: German, compact, recipient on one line, public buyer with Leitweg-ID ------

BEISPIEL_IT = Sample(
    lines=(
        Line("Notebook-Einrichtung", Decimal("3"), "Stk", Decimal("120.00"), Decimal(19), "A-100"),
        Line("Vor-Ort-Service", Decimal("2.5"), "Std", Decimal("78.00"), Decimal(19), "A-210"),
    ),
    iban="DE97 0000 0000 0055 5555 55",
)


def layout_compact(sample: Sample, name: str) -> Path:
    d = Doc()
    d.text(
        20,
        15,
        "Beispiel IT-Service · Inh. Erika Beispiel · Am Musterpark 3 · 01067 Dresden",
        size=9,
        style="B",
    )
    d.rule(20, 21, 190, 0.5)
    d.text(20, 30, "Rechnung RE-2610-007 vom 20.10.2026", size=14, style="B")
    info = [
        "Rechnungsempfänger: Stadt Musterstadt, Amt für IT, Rathausplatz 1, 12345 Musterstadt",
        "Leitweg-ID: 04011000-12345-03",
        "Lieferdatum: 16.10.2026",
    ]
    for i, value in enumerate(info):
        d.text(20, 42 + i * 5.5, value, size=9.5)

    y = 66
    cols = [(20, 22, "L"), (42, 70, "L"), (112, 22, "R"), (134, 28, "R"), (162, 28, "R")]
    head = ["Art.-Nr.", "Bezeichnung", "Menge", "Preis/Einh.", "Gesamt"]
    for (x, w, align), value in zip(cols, head, strict=True):
        d.text(x, y, value, size=8.5, style="B", w=w, align=align)
    d.rule(20, y + 4.5, 190)
    y += 7
    for line in sample.lines:
        row = [
            line.code,
            line.name,
            f"{de_qty(line.qty)} {line.unit}",
            de(line.price),
            de(line.net),
        ]
        for (x, w, align), value in zip(cols, row, strict=True):
            d.text(x, y, value, size=9.5, w=w, align=align)
        y += 5.5
    d.rule(20, y, 190)

    y += 3
    (rate,) = sample.by_rate()
    for label, value, style in [
        ("Nettobetrag", de(sample.net), ""),
        (f"MwSt. {rate} %", de(sample.vat(rate)), ""),
        ("Gesamtbetrag", f"{de(sample.gross)} EUR", "B"),
    ]:
        d.text(120, y, label, size=9.5, style=style, w=40)
        d.text(160, y, value, size=9.5, style=style, w=30, align="R")
        y += 5.5

    y += 8
    for i, value in enumerate(
        [
            "Zahlungsziel: 14 Tage netto, fällig am 03.11.2026",
            f"Bankverbindung: IBAN {sample.iban} · Kontoinhaberin Erika Beispiel",
            "USt-IdNr.: DE999999999 · Telefon +49 351 000000 · E-Mail rechnung@beispiel-it.example",
        ]
    ):
        d.text(20, y + i * 5.5, value, size=9)
    return d.save(name, "Rechnung RE-2610-007")


# --- Layout D: English, Austrian seller, reverse charge, ISO dates -----------------------

BEISPIEL_SOFTWARE = Sample(
    lines=(
        Line(
            "Software licence Beispiel CRM, 12 months",
            Decimal("5"),
            "users",
            Decimal("240.00"),
            Decimal(0),
        ),
        Line("Onboarding workshop (remote)", Decimal("1"), "flat", Decimal("450.00"), Decimal(0)),
    ),
    iban="AT34 0000 0000 1234 5678",
)


def layout_reverse_charge(sample: Sample, name: str) -> Path:
    d = Doc()
    d.text(20, 16, "Beispiel Software OG", size=14, style="B")
    d.text(20, 23, "Musterweg 7/2, 1010 Vienna, Austria", size=9)
    d.text(20, 28, "VAT ID: ATU12345678", size=9)
    d.text(130, 16, "INVOICE", size=18, style="B", w=60, align="R")

    meta = [
        ("Invoice No.", "2026/118"),
        ("Date", "2026-10-12"),
        ("Delivery", "2026-10-09"),
        ("Due", "2026-10-26"),
    ]
    for i, (label, value) in enumerate(meta):
        d.text(130, 26 + i * 5, label, size=9, w=25, color=GREY)
        d.text(160, 26 + i * 5, value, size=9, w=30, align="R")

    d.text(20, 50, "Customer:", size=9, style="B")
    for i, value in enumerate(
        [
            "Muster GmbH",
            "Musterstraße 1",
            "10115 Berlin",
            "Germany",
            "VAT ID: DE123456789",
            "invoices@muster-gmbh.example",
        ]
    ):
        d.text(20, 56 + i * 5, value, size=10)
    d.text(20, 89, "Your reference: Projekt Nordlicht", size=9)

    y = 101
    cols = [
        (20, 10, "L"),
        (30, 78, "L"),
        (108, 18, "R"),
        (128, 14, "L"),
        (142, 22, "R"),
        (164, 26, "R"),
    ]
    head = ["No.", "Item", "Quantity", "Unit", "Price", "Net"]
    for (x, w, align), value in zip(cols, head, strict=True):
        d.text(x, y, value, size=8.5, style="B", w=w, align=align)
    d.rule(20, y + 4.5, 190, 0.4)
    y += 7
    for pos, line in enumerate(sample.lines, start=1):
        row = [
            str(pos),
            line.name,
            f"{line.qty.normalize():f}",
            line.unit,
            en(line.price),
            en(line.net),
        ]
        for (x, w, align), value in zip(cols, row, strict=True):
            d.text(x, y, value, size=9.5, w=w, align=align)
        y += 6
    d.rule(20, y, 190)

    y += 4
    for label, value, style in [
        ("Net amount", en(sample.net), ""),
        ("VAT 0% (reverse charge)", en(sample.vat_total), ""),
        ("Total EUR", en(sample.gross), "B"),
    ]:
        d.text(110, y, label, size=9.5, style=style, w=50)
        d.text(160, y, value, size=9.5, style=style, w=30, align="R")
        y += 5.5

    y += 8
    for i, value in enumerate(
        [
            "Reverse charge: VAT to be accounted for by the recipient",
            "(Article 196 of Council Directive 2006/112/EC).",
            "",
            "Payment terms: 14 days net",
            f"IBAN {sample.iban} (Beispiel Software OG)",
            "Contact: Max Beispiel, +43 1 000000, office@beispiel-software.example",
        ]
    ):
        d.text(20, y + i * 5, value, size=9)
    return d.save(name, "Invoice 2026/118")


def main() -> None:
    paths = [
        layout_din(MUSTER, "de-muster-gmbh.pdf", "RE-2026-0142"),
        layout_modern(SAMPLE_STUDIO, "en-sample-studio.pdf"),
        layout_compact(BEISPIEL_IT, "de-beispiel-it-service.pdf"),
        layout_reverse_charge(BEISPIEL_SOFTWARE, "en-beispiel-software-reverse-charge.pdf"),
        # The same German layout with two typos: a wrong subtotal and a wrong IBAN digit.
        layout_din(
            replace(MUSTER, printed_net=Decimal("882.80"), iban="DE52 0000 0000 0012 3456 79"),
            "de-muster-gmbh-with-errors.pdf",
            "RE-2026-0143",
        ),
    ]
    for path in paths:
        print(f"wrote {path.name}")


if __name__ == "__main__":
    main()
