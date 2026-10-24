# Bugs found and fixed

Real bugs I hit while building this project, in the order I found them. The first showed up
when I ran the offline extractor on all sample layouts; the other two were found by comparing
my rule results with the official EN 16931 and XRechnung schematron
(`scripts/official_check.py`).

---

## 1. The buyer was called "nnummer: K-10087", and after the fix there was no buyer at all

**What broke.** On the German sample (a DIN 5008 business letter) the extracted buyer was:

```
"buyer": {
  "name": "nnummer: K-10087",
  "address": {"street": "", "postcode": "", "city": "", "country": ""},
  "vat_id": "DE987654321",
```

The buyer is Beispiel AG in the address window. "nnummer: K-10087" is the rest of
"Kundennummer: K-10087" (customer number) from the info block on the right.

**Root cause.** Buyer blocks are found by a label: "Bill to", "Customer", "Rechnungsempfänger",
"Kunde", ... The pattern allowed an optional colon after the label and took everything after
it, so "Kunde" matched the first five letters of "Kundennummer":

```python
label = re.compile(rf"^(?:{'|'.join(patterns)})\s*:?\s*(.*)$", re.IGNORECASE)
```

**Fix.** A block label must be the whole cell ("BILL TO") or end with a colon
("Customer: ..."):

```python
# The label is the whole cell ("BILL TO") or ends with a colon ("Customer: ..."), so
# "Kunde" does not match inside "Kundennummer: K-10087".
label = re.compile(rf"^(?:{'|'.join(patterns)})\s*(?::\s*(.*))?$", re.IGNORECASE)
```

**The second bug behind it.** After this fix the buyer was empty, and five rules failed
(BR-07, BR-10, BR-11, BR-DE-8, BR-DE-9). Without the false label match, the extractor fell back
to the address window: the lines below the small sender line "Muster GmbH · Musterstraße 1 ·
10115 Berlin". That fallback had never run before, and it stopped at once: a block ends at a
vertical gap of more than 20 points, and I measured the gap between the sender line and
"Beispiel AG" at **20.28 points**. The lines inside an address block are 14.2 points apart.

```python
# before
if cell is None or line.top - previous_top > 20:
```

```python
# after
BLOCK_GAP = 28.0  # points (~10 mm): a larger vertical gap ends an address block
...
if cell is None or line.top - previous_top > BLOCK_GAP:
```

**Lesson.** One bug can hide another: the wrong match meant the right code path never ran.
The extraction tests now check the buyer of every layout field by field.

---

## 2. My BR-CO-13 reported an error that the official schematron does not

**What broke.** For the sample with a wrong subtotal (lines add up to 882.30, the PDF says
882.80), my validator reported three errors: BR-CO-10, BR-CO-13 and BR-CO-15. The official CEN
schematron, run on the same XML, reported two:

```
== de-muster-gmbh-with-errors.pdf (this app's fatal rules: BR-CO-10, BR-CO-13, BR-CO-15)
   CEN EN 16931: 2 fatal, 0 warning/information
      [fatal] BR-CO-15: ...
      [fatal] BR-CO-10: ...
```

**Root cause.** I implemented BR-CO-13 from its rule text: "Invoice total amount without VAT
(BT-109) = Σ Invoice line net amount (BT-131) − allowances + charges". The official test does
not add up the lines. Without allowances and charges it is:

```
xs:decimal(cbc:TaxExclusiveAmount) = xs:decimal(cbc:LineExtensionAmount)
```

That is BT-109 = BT-106. Comparing the lines with BT-106 is BR-CO-10's job; with my version
one wrong subtotal was reported twice, and the report did not match what the buyer's validator
would say.

**Fix.** Follow the schematron test, and keep a regression test for it:

```python
# before
expected = _xpath_round(_sum(line.net_amount for line in inv.lines))
if inv.totals.tax_exclusive == expected:
    return None
```

```python
# after
# The official schematron compares BT-109 with BT-106 (LineExtensionAmount), not with the
# sum of the lines: that sum is BR-CO-10's job.
if t.tax_exclusive == t.line_net_total:
    return None
```

**Lesson.** For a standard, the reference implementation is the specification of the details.
I now read the schematron test of every arithmetic rule, not only its one-line text.

---

## 3. A missing buyer e-invoice address was only a warning

**What broke.** In the same comparison every sample got a fatal error from the official KoSIT
XRechnung schematron that my validator did not report as an error:

```
KoSIT XRechnung: 1 fatal, 0 warning/information
   [fatal] PEPPOL-EN16931-R010: [PEPPOL-EN16931-R010]-Buyer electronic address MUST be provided
```

**Root cause.** I knew from the XRechnung 3.0.1 release notes that BT-49 (buyer electronic
address) had become required, but the XRechnung schematron source file I read on GitHub
(`src/.../XRechnung-UBL-validation.sch`, the same at tag v2.6.0) has no rule for it, so I added
my own check as a warning. The schematron in the official release bundle is built from that
source **plus Peppol rules**, and there R010 (and R020 for the seller) are fatal. None of my
sample PDFs printed a buyer e-mail address at that point, so none of the generated XML files
would have passed the official validator.

**Fix.** The rules now have their official IDs and severity:

```python
# before
@rule("APP-03", "Buyer electronic address (BT-49): required since XRechnung 3.0.1.",
      APP, Severity.WARNING)
```

```python
# after
@rule("PEPPOL-EN16931-R010", "Buyer electronic address MUST be provided", XR)
def peppol_r010(inv: Invoice) -> str | None:
    if inv.buyer.electronic_address:
        return None
    return "the buyer's e-invoice address (BT-49) is not on the PDF; ask the buyer and enter it"
```

Because a PDF rarely contains this address, the app now asks for it: the upload form, the
result page and the CLI (`--buyer-email`) take it, and the XML is generated again. Three sample
layouts print a buyer address ("E-Rechnung an: ..."); the public-sector sample does not, to
show the case.

**Lesson.** Check against the artefact that is actually used (the release bundle), not the
source file that looks like it.
