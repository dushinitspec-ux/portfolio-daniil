"""The web app (upload, result page, XML download, JSON API), the history and the CLI."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import httpx
import pytest
from lxml import etree

from app.db import Repository
from app.extract.rules import RuleBasedExtractor
from app.main import main
from app.pipeline import convert
from app.web import AppConfig, create_app
from tests.conftest import SAMPLES, sample_bytes

CONFIG = AppConfig(
    demo=True,
    extractor_name="rules",
    samples_dir=SAMPLES,
    max_upload_bytes=200_000,
    max_pages=20,
)


@pytest.fixture
async def client(repo: Repository) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(repo, RuleBasedExtractor(), CONFIG)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def upload(client: httpx.AsyncClient, name: str, **form: str) -> httpx.Response:
    files = {"file": (name, sample_bytes(name), "application/pdf")}
    return await client.post("/convert", files=files, data=form)


async def test_index_lists_samples_and_demo_mode(client: httpx.AsyncClient) -> None:
    html = (await client.get("/")).text
    assert "Turn a PDF invoice into an e-invoice." in html
    assert "demo · offline extractor" in html
    for name in ("de-muster-gmbh.pdf", "en-sample-studio.pdf", "de-beispiel-it-service.pdf"):
        assert name in html
    assert "Nothing processed yet." in html


async def test_upload_shows_fields_rules_and_xml(client: httpx.AsyncClient) -> None:
    resp = await upload(client, "de-muster-gmbh-with-errors.pdf")
    assert resp.status_code == 303
    page = await client.get(resp.headers["location"])
    html = page.text
    assert page.status_code == 200
    assert "Invoice RE-2026-0143" in html
    assert "Muster GmbH" in html and "Beispiel AG" in html
    assert "2 errors" in html and "1 warning" in html
    # Every failed rule shows its ID and a human message.
    assert "BR-CO-10" in html and "the lines add up to 882.30, the invoice says 882.80" in html
    assert "BR-CO-15" in html and "BR-DE-19" in html
    assert 'class="flag"' in html  # the wrong total is marked in the totals table
    assert "&lt;cbc:CustomizationID&gt;" in html  # XML preview, escaped
    history = (await client.get("/")).text
    assert "RE-2026-0143" in history and "invalid" in history


async def test_xml_download(client: httpx.AsyncClient) -> None:
    location = (await upload(client, "en-sample-studio.pdf")).headers["location"]
    resp = await client.get(f"{location}/xml")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/xml"
    assert resp.headers["content-disposition"] == 'attachment; filename="INV-2026-0042.xml"'
    root = etree.fromstring(resp.content)
    assert etree.QName(root).localname == "Invoice"
    pdf = await client.get(f"{location}/pdf")
    assert pdf.content == sample_bytes("en-sample-studio.pdf")


async def test_sample_button(client: httpx.AsyncClient) -> None:
    resp = await client.post("/samples/en-beispiel-software-reverse-charge.pdf")
    assert resp.status_code == 303
    html = (await client.get(resp.headers["location"])).text
    assert "No errors" in html and "BR-AE-01" in html
    assert (await client.post("/samples/../app/main.py")).status_code == 404


async def test_adding_the_buyer_address_fixes_r010(client: httpx.AsyncClient) -> None:
    location = (await upload(client, "de-beispiel-it-service.pdf")).headers["location"]
    html = (await client.get(location)).text
    assert "PEPPOL-EN16931-R010" in html and "1 error" in html
    resp = await client.post(
        f"{location}/buyer-email", data={"buyer_email": "rechnung@stadt-musterstadt.example"}
    )
    assert resp.status_code == 303 and resp.headers["location"] == location
    html = (await client.get(location)).text
    assert "No errors" in html
    assert "BT-49 buyer e-invoice address entered by the user" in html
    xml = (await client.get(f"{location}/xml")).text
    assert 'schemeID="EM">rechnung@stadt-musterstadt.example<' in xml


async def test_buyer_address_on_upload_and_bad_address(client: httpx.AsyncClient) -> None:
    ok = await upload(client, "de-beispiel-it-service.pdf", buyer_email="it@musterstadt.example")
    assert "No errors" in (await client.get(ok.headers["location"])).text
    bad = await upload(client, "de-beispiel-it-service.pdf", buyer_email="not an address")
    assert bad.status_code == 422
    assert "is not an e-mail address" in bad.text


async def test_rejects_non_pdf_and_large_files(client: httpx.AsyncClient) -> None:
    resp = await client.post("/convert", files={"file": ("a.pdf", b"hello", "application/pdf")})
    assert resp.status_code == 422 and "This is not a PDF file." in resp.text
    big = b"%PDF-1.7\n" + b"0" * 300_000
    resp = await client.post("/convert", files={"file": ("big.pdf", big, "application/pdf")})
    assert resp.status_code == 413
    broken = b"%PDF-1.7\nnot really"
    resp = await client.post("/convert", files={"file": ("x.pdf", broken, "application/pdf")})
    assert resp.status_code == 422 and "Could not read the PDF" in resp.text


async def test_json_api(client: httpx.AsyncClient) -> None:
    files = {"file": ("x.pdf", sample_bytes("de-muster-gmbh.pdf"), "application/pdf")}
    data = (await client.post("/api/convert", files=files)).json()
    assert data["valid"] is True
    assert data["extractor"] == "rules"
    assert data["invoice"]["number"] == "RE-2026-0142"
    assert data["invoice"]["totals"]["tax_inclusive"] == "1040.37"  # Decimal as a string
    rules = {r["id"]: r for r in data["rules"]}
    assert rules["BR-CO-10"]["status"] == "passed"
    assert rules["BR-29"]["status"] == "n/a"
    assert data["xml"].startswith('<?xml version="1.0" encoding="UTF-8"?>')


async def test_unknown_invoice_and_health(client: httpx.AsyncClient) -> None:
    assert (await client.get("/invoices/999")).status_code == 404
    assert (await client.get("/invoices/999/xml")).status_code == 404
    assert (await client.get("/healthz")).json() == {"status": "ok"}


async def test_history_stores_money_exactly(repo: Repository) -> None:
    conversion = await convert(sample_bytes("en-sample-studio.pdf"), RuleBasedExtractor(), "a.pdf")
    at = datetime(2026, 10, 24, 9, 30, tzinfo=UTC)
    invoice_id = await repo.add(conversion, b"%PDF", now=at)
    (row,) = await repo.recent()
    assert (row.id, row.number, row.seller, row.currency) == (
        invoice_id, "INV-2026-0042", "Sample Studio GmbH", "EUR"
    )  # fmt: skip
    assert row.total == D("3046.36") and isinstance(row.total, D)
    assert row.valid and row.failed_rules == []
    assert row.created_at == at
    stored = await repo.get(invoice_id)
    assert stored is not None
    assert stored.extraction.invoice.totals.payable == D("3046.36")
    assert stored.xml == conversion.xml and stored.pdf == b"%PDF"
    assert await repo.get(invoice_id + 1) is None


def test_cli_convert(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out.xml"
    code = main(["--demo", "convert", str(SAMPLES / "de-muster-gmbh.pdf"), "-o", str(out)])
    assert code == 0
    assert (
        etree.parse(str(out))
        .getroot()
        .findtext("{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID")
        == "RE-2026-0142"
    )
    assert "rules: " in capsys.readouterr().out


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    errors = SAMPLES / "de-muster-gmbh-with-errors.pdf"
    assert main(["--demo", "convert", str(errors), "-o", str(tmp_path / "e.xml")]) == 1
    assert "BR-CO-10" in capsys.readouterr().out
    assert (tmp_path / "e.xml").exists()  # written anyway, marked as not compliant
    assert main(["--demo", "convert", str(tmp_path / "missing.pdf")]) == 2
    city = SAMPLES / "de-beispiel-it-service.pdf"
    args = ["--demo", "convert", str(city), "-o", str(tmp_path / "c.xml")]
    assert main(args) == 1  # PEPPOL-EN16931-R010: no buyer e-invoice address
    assert main([*args, "--buyer-email", "it@musterstadt.example"]) == 0
