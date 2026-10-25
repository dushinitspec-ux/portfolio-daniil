"""The in-browser demo adapter (app/web_demo.py), run here in CPython.

The demo cannot run pdfplumber, so it reads the text layer exported by
scripts/export_text_layer.py. These tests make sure that export is current and that the
adapter gives exactly what the real pipeline gives for the same PDF.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app import web_demo
from app.extract.rules import RuleBasedExtractor
from app.pdf_text import from_words, read_pdf, read_words
from app.pipeline import convert as pipeline_convert
from tests.conftest import SAMPLES, sample_bytes

ROOT = Path(__file__).resolve().parent.parent
PDFS = sorted(p.name for p in SAMPLES.glob("*.pdf"))
FIXES = {
    "totals.line_net_total": "882.30",
    "totals.tax_exclusive": "882,30",  # a German decimal comma is read too
    "payment.iban": "DE52000000000012345678",
}


def _ids(result: dict[str, object], status: str) -> list[str]:
    return [r["id"] for r in result["rules"] if r["status"] == status]  # type: ignore[index, union-attr]


def test_every_sample_has_a_current_text_layer() -> None:
    assert sorted(f"{s['id']}.pdf" for s in web_demo.samples()) == PDFS
    for name in PDFS:
        data = json.loads((web_demo.TEXT_LAYER / name.replace(".pdf", ".json")).read_text("utf-8"))
        assert data["file"] == name
        words = read_words(sample_bytes(name))
        keys = ("text", "x0", "x1", "top", "size")
        expected = [[{k: w[k] for k in keys} for w in page] for page in words]
        assert data["pages"] == expected, f"run scripts/export_text_layer.py ({name})"
        assert from_words(data["pages"]).lines == read_pdf(sample_bytes(name)).lines


@pytest.mark.parametrize("name", PDFS)
async def test_same_result_as_the_pipeline(name: str) -> None:
    real = await pipeline_convert(sample_bytes(name), RuleBasedExtractor(), name)
    demo = web_demo.convert(name.removesuffix(".pdf"))
    assert demo["xml"] == real.xml.decode("utf-8")
    assert demo["derived"] == real.extraction.derived
    assert [(r["id"], r["status"], r["message"]) for r in demo["rules"]] == [
        (r.id, r.status.value, r.message) for r in real.report.results
    ]
    assert demo["summary"]["valid"] == real.valid
    assert demo["fields"]["number"] == real.invoice.number


def test_sample_with_errors_reports_rule_ids_and_terms() -> None:
    result = web_demo.convert("de-muster-gmbh-with-errors")
    assert _ids(result, "failed") == ["BR-CO-10", "BR-CO-15", "BR-DE-19"]
    assert result["summary"] == {
        "total": 67,
        "errors": 2,
        "warnings": 1,
        "passed": 57,
        "not_applicable": 7,
        "valid": False,
    }
    co10 = next(r for r in result["rules"] if r["id"] == "BR-CO-10")
    assert co10["message"] == "the lines add up to 882.30, the invoice says 882.80"
    assert co10["terms"] == ["BT-106", "BT-131"]
    assert result["fields"]["totals.line_net_total"] == "882.80"
    assert result["fields"]["lines.2.net_amount"] == "79.80"
    assert result["xml_name"] == "RE-2026-0143.xml"


def test_typed_fixes_make_every_rule_pass() -> None:
    result = web_demo.convert("de-muster-gmbh-with-errors", FIXES)
    assert result["errors"] == {}
    assert result["edited"] == list(FIXES)
    assert _ids(result, "failed") == []
    assert result["summary"]["passed"] == 60
    assert result["fields"]["totals.tax_exclusive"] == "882.30"
    assert "BT-106 entered by the user" in result["derived"]
    assert '<cbc:LineExtensionAmount currencyID="EUR">882.30<' in result["xml"]


async def test_buyer_address_matches_the_web_app_flow() -> None:
    name = "de-beispiel-it-service.pdf"
    before = web_demo.convert("de-beispiel-it-service")
    assert _ids(before, "failed") == ["PEPPOL-EN16931-R010"]
    email = "rechnung@stadt-musterstadt.example"
    real = await pipeline_convert(sample_bytes(name), RuleBasedExtractor(), name, buyer_email=email)
    demo = web_demo.convert("de-beispiel-it-service", {"buyer.electronic_address": email})
    assert demo["xml"] == real.xml.decode("utf-8")
    assert demo["derived"] == real.extraction.derived
    assert _ids(demo, "failed") == []


def test_bad_values_are_reported_and_not_used() -> None:
    edits = {
        "due_date": "31.12.2026",
        "buyer.electronic_address": "not an address",
        "totals.payable": "a lot",
        "lines.7.quantity": "1",
        "seller.password": "x",
        "lines.0.quantity": "10",
        "issue_date": "",
    }
    result = web_demo.convert("de-muster-gmbh", edits)
    assert result["errors"] == {
        "due_date": "date",
        "buyer.electronic_address": "email",
        "totals.payable": "number",
        "lines.7.quantity": "unknown",
        "seller.password": "unknown",
    }
    assert result["edited"] == ["lines.0.quantity", "issue_date"]
    assert result["fields"]["due_date"] == "2026-10-29"
    assert result["fields"]["issue_date"] == ""
    assert "BR-03" in _ids(result, "failed")  # no issue date
    assert result["fields"]["lines.0.quantity"] == "10"


def test_unknown_sample_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown sample"):
        web_demo.convert("../../etc/passwd")
    with pytest.raises(ValueError, match="unknown sample"):
        web_demo.convert("missing")


def test_imports_only_browser_safe_modules() -> None:
    """Pyodide has no FastAPI, pdfplumber, Anthropic SDK or aiosqlite, and every app module
    the adapter needs must be listed in web_demo.json (copied into the website)."""
    code = (
        "import json, sys; import app.web_demo; "
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in "
        "('app', 'fastapi', 'pdfplumber', 'pdfminer', 'anthropic', 'aiosqlite', 'httpx', "
        "'uvicorn', 'pydantic_settings', 'jinja2'))))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    modules = json.loads(out.stdout)
    assert all(m == "app" or m.startswith("app.") for m in modules), modules
    listed = set(json.loads((ROOT / "web_demo.json").read_text("utf-8"))["files"])
    for module in modules:
        path = module.replace(".", "/")
        assert f"{path}.py" in listed or f"{path}/__init__.py" in listed, module
