"""One scan: crawl the site, run the rules on every HTML page, build the report."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from app import __version__
from app.crawler import Crawler, CrawlOptions, FetchedPage, UrlGuard
from app.models import (
    CheckStatus,
    Issue,
    PageReport,
    ScanOptions,
    ScanReport,
    ScanStatus,
    SkippedUrl,
)
from app.report import summarize
from app.rules import Page, check_site, run_rules
from app.rules.document import page_title

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int], Awaitable[None]]


def utcnow() -> datetime:
    return datetime.now(UTC)


PageAnalysis = tuple[str | None, list[Issue], dict[str, CheckStatus]]


def analyse(soup: BeautifulSoup, url: str) -> PageAnalysis:
    page = Page(soup, url)
    issues, checks = run_rules(page)
    return page_title(page), issues, checks


def _page_report(fetched: FetchedPage) -> PageReport:
    return PageReport(
        url=fetched.url,
        final_url=fetched.final_url,
        status_code=fetched.status_code,
        content_type=fetched.content_type.split(";")[0].strip(),
        redirects=fetched.redirects,
        elapsed_ms=fetched.elapsed_ms,
        error=fetched.error,
        duplicate_of=fetched.duplicate_of,
    )


async def run_scan(
    start_url: str,
    *,
    client: httpx.AsyncClient,
    options: CrawlOptions,
    guard: UrlGuard | None = None,
    sample: str | None = None,
    on_progress: ProgressCallback | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> ScanReport:
    report = ScanReport(
        start_url=start_url,
        sample=sample,
        created_at=clock(),
        options=ScanOptions(
            max_pages=options.max_pages, concurrency=options.concurrency, delay_s=options.delay_s
        ),
        tool_version=__version__,
    )
    started = time.perf_counter()
    results: dict[int, PageAnalysis] = {}
    analysed = 0

    async def on_page(fetched: FetchedPage) -> None:
        nonlocal analysed
        if fetched.soup is not None:
            # Parsing and rules are CPU work: keep them off the event loop.
            results[fetched.index] = await asyncio.to_thread(analyse, fetched.soup, fetched.url)
        analysed += 1
        if on_progress is not None:
            await on_progress(analysed)

    crawler = Crawler(client, options, guard=guard)
    crawl = await crawler.crawl(start_url, on_page)

    pages = []
    for fetched in crawl.pages:
        page = _page_report(fetched)
        if fetched.index in results and not fetched.error:
            page.title, page.issues, page.checks = results[fetched.index]
            page.analysed = True
        pages.append(page)
    check_site(pages)

    report.origin = crawl.origin
    report.robots = crawl.robots_status
    report.pages = pages
    report.skipped = [SkippedUrl(url=url, reason=reason) for url, reason in crawl.skipped]
    report.skipped_total = crawl.skipped_total
    report.summary = summarize(pages)
    report.finished_at = clock()
    report.duration_s = round(time.perf_counter() - started, 2)
    report.status = ScanStatus.DONE
    if not report.summary.pages_analysed:
        report.error = _nothing_analysed(report)
    logger.info(
        "Scanned %s: %d pages, %d analysed in %.1f s",
        start_url,
        len(pages),
        report.summary.pages_analysed,
        report.duration_s,
    )
    return report


def _nothing_analysed(report: ScanReport) -> str:
    if report.skipped and report.skipped[0].reason == "blocked by robots.txt" and not report.pages:
        return "robots.txt does not allow crawling this site, so nothing was checked."
    if "disallow all" in report.robots:
        return "robots.txt could not be read, so nothing was checked."
    errors = {p.error for p in report.pages if p.error}
    if errors:
        return "No page could be analysed: " + "; ".join(sorted(errors))
    return "No HTML pages were found at this address."
