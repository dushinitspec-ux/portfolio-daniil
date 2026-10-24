"""The Claude extractor with a stub client: request shape, reply parsing, failures.
No network and no API key: the stub returns what the API would."""

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal as D
from typing import Any

import anthropic
import httpx
import pytest

from app.config import ExtractorChoice, Settings
from app.extract import ExtractionError, create_extractor
from app.extract.claude import EXTRACTION_SCHEMA, FALLBACK_BETA, ClaudeExtractor
from app.extract.complete import complete
from app.model import VatCategory
from app.pdf_text import read_pdf
from app.validation import validate
from tests.conftest import sample_bytes

PARTY = dict.fromkeys(
    ["name", "street", "postcode", "city", "country_code", "vat_id", "legal_registration_id",
     "electronic_address", "contact_name", "contact_phone", "contact_email"], ""
)  # fmt: skip


def reply_for_muster() -> dict[str, Any]:
    """What Claude returns for samples/de-muster-gmbh.pdf, written by hand."""
    line = {"vat_category": "S"}
    return {
        "invoice_number": "RE-2026-0142", "issue_date": "2026-10-15", "due_date": "2026-10-29",
        "delivery_date": "2026-09-30", "period_start": "", "period_end": "", "currency": "EUR",
        "buyer_reference": "", "order_reference": "PO-7781", "note": "",
        "seller": {**PARTY, "name": "Muster GmbH", "street": "Musterstraße 1",
                   "postcode": "10115", "city": "Berlin", "country_code": "DE",
                   "vat_id": "DE 123456789", "contact_name": "Max Mustermann",
                   "contact_phone": "+49 30 000000",
                   "contact_email": "rechnung@muster-gmbh.example",
                   "electronic_address": "rechnung@muster-gmbh.example"},
        "buyer": {**PARTY, "name": "Beispiel AG", "street": "Beispielweg 12",
                  "postcode": "20095", "city": "Hamburg", "country_code": "",
                  "vat_id": "DE987654321", "electronic_address": "rechnung@beispiel-ag.example"},
        "payment": {"iban": "DE52 0000 0000 0012 3456 78", "bic": "", "account_name": "",
                    "terms": "ohne Abzug bis zum 29.10.2026"},
        "lines": [
            {**line, "id": "1", "name": "Wartung Netzwerk (September)", "quantity": "8",
             "unit": "Std.", "net_price": "85.00", "vat_rate": "19", "net_amount": "680.00"},
            {**line, "id": "2", "name": "Patchkabel Cat 6, 2 m", "quantity": "25",
             "unit": "Stk.", "net_price": "4.90", "vat_rate": "19", "net_amount": "122.50"},
            {**line, "id": "3", "name": "Fachbuch", "quantity": "2", "unit": "Stk.",
             "net_price": "39.90", "vat_rate": "7", "net_amount": "79.80"},
        ],
        "vat_breakdown": [
            {"category": "S", "rate": "19", "taxable_amount": "802.50", "tax_amount": "152.48",
             "exemption_reason": ""},
            {"category": "S", "rate": "7", "taxable_amount": "79.80", "tax_amount": "5.59",
             "exemption_reason": ""},
        ],
        "totals": {"line_net_total": "882.30", "tax_exclusive": "882.30", "vat_total": "158.07",
                   "tax_inclusive": "1040.37", "prepaid": "", "payable": "1040.37"},
    }  # fmt: skip


@dataclass
class Block:
    text: str
    type: str = "text"


@dataclass
class Reply:
    content: list[Block]
    stop_reason: str = "end_turn"


@dataclass
class StubMessages:
    reply: Reply | Exception
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> Reply:
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class StubClient:
    def __init__(self, reply: Reply | Exception) -> None:
        self.messages = StubMessages(reply)
        self.beta = self


def extractor(reply: Reply | Exception) -> tuple[ClaudeExtractor, StubMessages]:
    client = StubClient(reply)
    return ClaudeExtractor(client, "claude-opus-5-5", "medium"), client.messages  # type: ignore[arg-type]


PDF = read_pdf(sample_bytes("de-muster-gmbh.pdf"))


async def test_reply_becomes_a_typed_valid_invoice() -> None:
    ex, _ = extractor(Reply([Block(json.dumps(reply_for_muster()))]))
    x = complete(await ex.extract(PDF))
    inv = x.invoice
    assert x.extractor == "claude"
    assert inv.issue_date == date(2026, 10, 15)
    assert inv.seller.vat_id == "DE123456789"  # spaces removed
    assert inv.payment.iban == "DE52000000000012345678"
    assert inv.lines[0].unit_code == "HUR"
    assert inv.lines[2].vat_category is VatCategory.STANDARD
    assert inv.totals.tax_inclusive == D("1040.37")
    assert isinstance(inv.totals.tax_inclusive, D)
    assert inv.buyer.address.country == "DE"  # derived from the VAT ID, and noted
    assert validate(inv).valid


async def test_request_uses_structured_output_and_the_pdf_text() -> None:
    ex, messages = extractor(Reply([Block(json.dumps(reply_for_muster()))]))
    await ex.extract(PDF)
    (call,) = messages.calls
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": EXTRACTION_SCHEMA}
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    prompt = call["messages"][0]["content"]
    assert "<invoice_text>" in prompt and "RE-2026-0142" in prompt
    assert "Do not calculate" in call["system"]


def test_schema_fits_structured_output_limits() -> None:
    # Every object closed and fully required: no optional or union parameters to count.
    def walk(node: dict[str, Any]) -> None:
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert sorted(node["required"]) == sorted(node["properties"])
            for child in node["properties"].values():
                walk(child)
        if node.get("type") == "array":
            walk(node["items"])

    walk(EXTRACTION_SCHEMA)


async def test_unreadable_values_become_warnings() -> None:
    data = reply_for_muster()
    data["lines"][0]["quantity"] = "eight"
    data["issue_date"] = "sometime in October"
    ex, _ = extractor(Reply([Block(json.dumps(data))]))
    x = await ex.extract(PDF)
    assert x.invoice.lines[0].quantity is None
    assert x.invoice.issue_date is None
    assert len(x.warnings) == 2
    assert not validate(complete(x).invoice).valid  # BR-22 and BR-03 report them


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (Reply([], stop_reason="refusal"), "declined"),
        (Reply([Block("{")], stop_reason="max_tokens"), "max_tokens"),
        (Reply([Block("not json")]), "unexpected reply format"),
        (Reply([Block(json.dumps({"invoice_number": "1"}))]), "unexpected reply format"),
        (Reply([]), "no text"),
        (
            anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.example")),
            "Anthropic API error",
        ),
    ],
)
async def test_failures_raise_extraction_error(reply: Reply | Exception, message: str) -> None:
    ex, _ = extractor(reply)
    with pytest.raises(ExtractionError, match=message):
        await ex.extract(PDF)


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (Settings(_env_file=None, anthropic_api_key="sk-test"), "claude"),
        (Settings(_env_file=None, anthropic_api_key="sk-test", demo_mode=True), "rules"),
        (Settings(_env_file=None), "rules"),
        (
            Settings(_env_file=None, anthropic_api_key="sk-test", extractor=ExtractorChoice.RULES),
            "rules",
        ),
    ],
)
def test_extractor_choice(settings: Settings, expected: str) -> None:
    assert create_extractor(settings).name == expected
