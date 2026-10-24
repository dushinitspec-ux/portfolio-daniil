"""Starting scans and explanations. Shared by the web app and the command line."""

import asyncio
import logging

import httpx

from app.config import Settings
from app.crawler import CrawlOptions, UrlGuard
from app.db import Repository
from app.explain import Explainer, ExplainError, FixedTextExplainer
from app.models import Explanation, ScanOptions, ScanReport, ScanStatus
from app.samples import SAMPLES, sample_transport, sample_url
from app.scanner import run_scan, utcnow
from app.urls import ensure_public, parse_start_url

logger = logging.getLogger(__name__)


class ScanService:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        explainer: Explainer,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.explainer = explainer
        self._transport = transport  # tests pass an httpx.MockTransport here
        self._tasks: set[asyncio.Task[None]] = set()
        self._limit = asyncio.Semaphore(settings.max_parallel_scans)

    def options(self, max_pages: int | None = None) -> CrawlOptions:
        s = self.settings
        return CrawlOptions(
            max_pages=min(max_pages or s.max_pages, 200),
            concurrency=s.concurrency,
            delay_s=s.request_delay_s,
            max_bytes=s.max_page_bytes,
            user_agent=s.user_agent,
        )

    def _client(self, transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(self.settings.request_timeout_s),
            follow_redirects=False,
            max_redirects=5,
        )

    async def validate(self, text: str) -> str:
        """Raises InvalidURL or TargetNotAllowed with a message for the user."""
        url = parse_start_url(text)
        if not self.settings.allow_private_targets and self._transport is None:
            await ensure_public(url)
        return url

    async def _new_report(self, url: str, max_pages: int | None, sample: str | None) -> int:
        options = self.options(max_pages)
        draft = ScanReport(
            start_url=url,
            sample=sample,
            created_at=utcnow(),
            options=ScanOptions(
                max_pages=options.max_pages,
                concurrency=options.concurrency,
                delay_s=options.delay_s,
            ),
        )
        return await self.repo.create(draft)

    async def run(
        self,
        report_id: int,
        url: str,
        max_pages: int | None = None,
        sample: str | None = None,
    ) -> ScanReport:
        """Run one scan to the end and store the result under report_id."""
        transport = sample_transport() if sample else self._transport
        guard: UrlGuard | None = None
        if transport is None and not self.settings.allow_private_targets:
            # Checked again on every new host, so a redirect cannot lead to a private one.
            guard = ensure_public

        async def progress(pages: int) -> None:
            await self.repo.set_progress(report_id, pages)

        async with self._limit, self._client(transport) as client:
            try:
                report = await run_scan(
                    url,
                    client=client,
                    options=self.options(max_pages),
                    guard=guard,
                    sample=sample,
                    on_progress=progress,
                )
            except Exception as exc:
                logger.exception("Scan of %s failed", url)
                stored = await self.repo.get(report_id)
                if stored is None:
                    raise
                report = stored
                report.status = ScanStatus.FAILED
                report.error = str(exc) or type(exc).__name__
        report.id = report_id
        await self.repo.save(report)
        return report

    async def scan_now(self, text: str, max_pages: int | None = None) -> ScanReport:
        url = await self.validate(text)
        report_id = await self._new_report(url, max_pages, None)
        return await self.run(report_id, url, max_pages)

    async def scan_sample_now(self, name: str) -> ScanReport:
        url = sample_url(name, self.settings.public_base_url)
        report_id = await self._new_report(url, None, name)
        return await self.run(report_id, url, sample=name)

    def _spawn(self, report_id: int, url: str, max_pages: int | None, sample: str | None) -> None:
        task = asyncio.create_task(self.run(report_id, url, max_pages, sample))
        # Keep a reference, otherwise the task can be garbage-collected mid-scan.
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start(self, text: str, max_pages: int | None = None) -> int:
        """Validate, create the report row and scan in the background."""
        url = await self.validate(text)
        report_id = await self._new_report(url, max_pages, None)
        self._spawn(report_id, url, max_pages, None)
        return report_id

    async def start_sample(self, name: str) -> int:
        if name not in SAMPLES:
            raise KeyError(name)
        url = sample_url(name, self.settings.public_base_url)
        report_id = await self._new_report(url, None, name)
        self._spawn(report_id, url, None, name)
        return report_id

    async def wait(self) -> None:
        """Wait for background scans (tests and shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def explain(self, report_id: int, language: str) -> Explanation:
        report = await self.repo.get(report_id)
        if report is None:
            raise KeyError(report_id)
        try:
            explanation = await self.explainer.explain(report, language)
        except ExplainError as exc:
            logger.warning("Explainer failed, using the fixed texts: %s", exc)
            explanation = await FixedTextExplainer().explain(report, "en")
            explanation.note = f"Claude was not available ({exc}). " + explanation.note
        await self.repo.set_explanation(report_id, explanation)
        return explanation

    async def ensure_demo_reports(self) -> None:
        """Demo mode: make sure both sample reports exist, scanning them if needed."""
        for name in SAMPLES:
            if await self.repo.latest_sample(name) is None:
                report = await self.scan_sample_now(name)
                logger.info(
                    "Demo: scanned the %s sample (%d pages) -> report %s",
                    name,
                    report.summary.pages_analysed,
                    report.id,
                )
