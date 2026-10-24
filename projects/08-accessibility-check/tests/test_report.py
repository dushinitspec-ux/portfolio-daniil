"""Aggregation into the summary, and full scans of the bundled sample shop."""

import httpx
import pytest

from app.crawler import CrawlOptions
from app.models import CheckStatus, Issue, PageReport, ScanReport, Severity
from app.report import summarize
from app.samples import sample_transport
from app.scanner import run_scan

BASE = "http://127.0.0.1:8108/samples"


def page(url: str, checks: dict[str, CheckStatus], issues: list[Issue]) -> PageReport:
    return PageReport(url=url, final_url=url, analysed=True, checks=checks, issues=issues)


def test_summary_statuses_counts_and_criteria() -> None:
    img = Issue(rule_id="image-alt", severity=Severity.HIGH, message="no alt")
    contrast = Issue(rule_id="color-contrast", severity=Severity.MEDIUM, message="c", count=3)
    pages = [
        page(
            "https://s.test/a",
            {"image-alt": CheckStatus.FAIL, "color-contrast": CheckStatus.FAIL},
            [img, contrast],
        ),
        page("https://s.test/b", {"image-alt": CheckStatus.PASS}, []),
        PageReport(url="https://s.test/c.pdf", final_url="https://s.test/c.pdf"),  # not analysed
    ]

    summary = summarize(pages)
    rules = {r.rule_id: r for r in summary.rules}
    criteria = {c.number: c for c in summary.criteria}

    assert summary.pages_requested == 3 and summary.pages_analysed == 2
    assert rules["image-alt"].status is CheckStatus.FAIL
    assert (rules["image-alt"].pages_affected, rules["image-alt"].pages_checked) == (1, 2)
    assert rules["color-contrast"].issues == 3  # a deduplicated issue keeps its count
    assert rules["frame-title"].status is CheckStatus.NOT_APPLICABLE
    assert criteria["1.1.1"].status is CheckStatus.FAIL
    assert criteria["1.4.3"].issues == 3
    assert summary.issues_by_severity == {Severity.HIGH: 1, Severity.MEDIUM: 3, Severity.LOW: 0}
    assert summary.rules[0].status is CheckStatus.FAIL  # failures first


def test_worst_status_wins_for_a_criterion() -> None:
    pages = [
        page(
            "https://s.test/",
            {"form-label": CheckStatus.PASS, "duplicate-id-referenced": CheckStatus.FAIL},
            [Issue(rule_id="duplicate-id-referenced", severity=Severity.MEDIUM, message="d")],
        )
    ]
    criteria = {c.number: c for c in summarize(pages).criteria}
    assert criteria["4.1.2"].status is CheckStatus.FAIL
    assert criteria["2.4.1"].status is CheckStatus.NOT_APPLICABLE


def test_obsolete_parsing_criterion_is_listed_last() -> None:
    numbers = [c.number for c in summarize([]).criteria]
    assert numbers[-1] == "4.1.1"
    assert numbers[:3] == ["1.1.1", "1.3.1", "1.4.2"]


async def scan_sample(name: str) -> ScanReport:
    async with httpx.AsyncClient(transport=sample_transport()) as client:
        return await run_scan(
            f"{BASE}/{name}/",
            client=client,
            options=CrawlOptions(max_pages=20, delay_s=0),
            sample=name,
        )


async def test_broken_sample_shop_finds_the_planted_problems() -> None:
    report = await scan_sample("broken")
    rules = {r.rule_id: r for r in report.summary.rules}

    assert report.summary.pages_analysed == 4  # home, products, contact, about
    statuses = {p.url.rsplit("/", 1)[-1]: p.status_code for p in report.pages}
    assert statuses["cart.html"] == 404
    assert any("index.html" in p.url and p.duplicate_of for p in report.pages)
    assert any(s.url.endswith("/private/") for s in report.skipped)  # robots.txt
    expected = {
        "image-alt": 8,
        "form-label": 3,
        "label-placeholder": 1,
        "page-title": 1,
        "page-title-unique": 3,
        "html-lang": 2,
        "link-name": 3,
        "button-name": 4,
        "frame-title": 1,
        "meta-viewport": 1,
        "duplicate-id": 1,
        "duplicate-id-referenced": 1,
        "autoplay-audio": 2,
        "color-contrast": 5,
        "link-purpose": 6,
    }
    assert {k: rules[k].issues for k in expected} == expected
    assert report.summary.checks[CheckStatus.FAIL] == 10
    assert report.summary.checks[CheckStatus.PASS] == 0


async def test_fixed_sample_shop_passes_every_check() -> None:
    report = await scan_sample("fixed")
    assert report.summary.pages_analysed == 5  # the cart page exists now
    assert report.summary.checks.get(CheckStatus.FAIL, 0) == 0
    assert report.summary.checks.get(CheckStatus.WARNING, 0) == 0
    assert all(p.status_code == 200 for p in report.pages)


@pytest.mark.parametrize("name", ["broken", "fixed"])
async def test_report_round_trips_through_json(name: str) -> None:
    report = await scan_sample(name)
    again = ScanReport.model_validate_json(report.model_dump_json())
    assert again.summary == report.summary
