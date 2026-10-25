"""The in-browser demo adapter (app/web_demo.py), run here in CPython.

The demo reads the bundled Sample Shop from files instead of crawling it over HTTP. These
tests compare it with a real crawl of the same pages through the web app's sample routes.
"""

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from app import samples as real_samples
from app import web_demo
from app.crawler import CrawlOptions
from app.models import ScanReport
from app.samples import sample_transport
from app.scanner import run_scan

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8108/samples"


async def real_scan(name: str) -> ScanReport:
    async with httpx.AsyncClient(transport=sample_transport()) as client:
        return await run_scan(
            f"{BASE}/{name}/",
            client=client,
            options=CrawlOptions(max_pages=20, delay_s=0),
            sample=name,
        )


def _path(url: str | None) -> str | None:
    return None if url is None else "/" + url.split("/", 3)[3]


def test_constants_match_the_app() -> None:
    assert web_demo.SAMPLES == real_samples.SAMPLES
    assert CrawlOptions().product_token == web_demo.PRODUCT_TOKEN
    assert CrawlOptions().max_pages == web_demo.MAX_PAGES


@pytest.mark.parametrize("name", ["broken", "fixed"])
async def test_same_report_as_a_real_crawl(name: str) -> None:
    real = await real_scan(name)
    demo = web_demo.scan_sample(name)

    assert [(p["path"], p["status"], p["analysed"], p["duplicate_of"]) for p in demo["pages"]] == [
        (_path(p.url), p.status_code, p.analysed, _path(p.duplicate_of)) for p in real.pages
    ]
    assert [s["path"] for s in demo["skipped"]] == [_path(s.url) for s in real.skipped]
    assert demo["robots"] == real.robots
    for demo_page, real_page in zip(demo["pages"], real.pages, strict=True):
        assert demo_page["title"] == real_page.title
        assert [
            (i["rule_id"], i["severity"], i["message"], i["snippet"], i["count"])
            for i in demo_page["issues"]
        ] == [
            (i.rule_id, i.severity.value, i.message, i.snippet, i.count) for i in real_page.issues
        ]
    expected = real.summary.model_dump(mode="json")
    for criterion in demo["summary"]["criteria"]:
        assert criterion.pop("url").startswith("https://www.w3.org/WAI/WCAG22/Understanding/")
    assert demo["summary"] == expected


async def test_broken_and_fixed_shop_numbers() -> None:
    broken = web_demo.scan_sample("broken")
    assert broken["summary"]["checks"] == {"fail": 10, "warning": 7, "pass": 0, "n/a": 0}
    assert broken["summary"]["pages_analysed"] == 4
    contrast = [i for p in broken["pages"] for i in p["issues"] if i["rule_id"] == "color-contrast"]
    assert [(i["colors"], i["count"]) for i in contrast] == [
        (["#999999", "#ffffff"], 1),
        (["#aaaaaa", "#ffffff"], 1),
        (["#777777", "#ffffff"], 3),
    ]
    fixed = web_demo.scan_sample("fixed")
    assert fixed["summary"]["checks"] == {"fail": 0, "warning": 0, "pass": 16, "n/a": 1}
    assert broken["rules_info"]["image-alt"]["fix"].startswith("Add an alt attribute")


def test_unknown_sample_and_files_outside_the_samples() -> None:
    with pytest.raises(ValueError, match="unknown sample"):
        web_demo.scan_sample("private")
    assert web_demo._read("https://sample-shop.example/samples/../robots.txt")[0] == 404
    assert web_demo._read("https://sample-shop.example/samples/broken/missing.html")[0] == 404
    assert web_demo._read("https://sample-shop.example/other/")[0] == 404
    status, body = web_demo._read("https://sample-shop.example/samples/broken/")
    assert status == 200 and body is not None and b"<html" in body


def test_pasted_html_is_checked_as_one_page() -> None:
    html = (
        '<html lang="en"><head><title>Shop</title></head><body><main>'
        '<img src="bag.jpg"><a href="/more">click here</a>'
        '<p style="color:#777;background:#fff">Small print</p></main></body></html>'
    )
    result = web_demo.check_html(html)
    page = result["pages"][0]
    assert page["analysed"] and page["title"] == "Shop"
    rules = {i["rule_id"] for i in page["issues"]}
    assert {"image-alt", "link-purpose", "color-contrast"} <= rules
    contrast = next(i for i in page["issues"] if i["rule_id"] == "color-contrast")
    assert contrast["colors"] == ["#777777", "#ffffff"]
    assert "4.48:1" in contrast["message"]
    statuses = {r["rule_id"]: r["status"] for r in result["summary"]["rules"]}
    assert statuses["page-title-unique"] == "n/a"  # needs more than one page
    with pytest.raises(ValueError, match="larger than"):
        web_demo.check_html("x" * 600_000)


def test_contrast_checker_uses_the_wcag_maths() -> None:
    grey = web_demo.contrast("#777", "white")
    assert grey["shown"] == "4.48:1"
    assert [c["pass"] for c in grey["checks"]] == [False, True, False, False]
    darker = web_demo.contrast("#767676", "#fff")
    assert darker["shown"] == "4.54:1" and darker["checks"][0]["pass"]
    black = web_demo.contrast("black", "#ffffff")
    assert black["shown"] == "21.00:1" and all(c["pass"] for c in black["checks"])
    assert web_demo.contrast("rgba(0, 0, 0, 0.5)", "#fff")["blended"] is True
    assert web_demo.contrast("#777", "#fff", 24, False)["large"] is True
    assert web_demo.contrast("#777", "#fff", 18.67, True)["large"] is True
    assert web_demo.contrast("var(--x)", "#fff") == {"error": "foreground"}
    assert web_demo.contrast("#000", "nonsense") == {"error": "background"}
    assert web_demo.contrast("#000", "transparent") == {"error": "background-alpha"}


def test_imports_only_browser_safe_modules() -> None:
    """Pyodide has no httpx, FastAPI or Anthropic SDK, and every app module the adapter
    needs must be listed in web_demo.json (copied into the website)."""
    code = (
        "import json, sys; import app.web_demo; "
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in "
        "('app', 'httpx', 'fastapi', 'starlette', 'anthropic', 'aiosqlite', 'uvicorn', "
        "'pydantic_settings', 'jinja2'))))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    modules = json.loads(out.stdout)
    assert all(m == "app" or m.startswith("app.") for m in modules), modules
    config = json.loads((ROOT / "web_demo.json").read_text("utf-8"))
    listed = set(config["files"])

    def is_listed(file: str) -> bool:  # an exact path or "folder/*.py"
        return file in listed or f"{file.rsplit('/', 1)[0]}/*.py" in listed

    for module in modules:
        path = module.replace(".", "/")
        assert is_listed(f"{path}.py") or is_listed(f"{path}/__init__.py"), module
