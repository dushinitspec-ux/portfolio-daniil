"""A small, polite, same-origin crawler.

- Starts at one URL and follows <a href> links on the same origin (scheme + host + port).
- Reads robots.txt first and obeys it (RFC 9309), including Crawl-delay.
- Stops after `max_pages` requests, with a fixed number of workers and a pause after each
  request, so a small shop's server never sees more than a few requests per second.
- Follows redirects hop by hop. The start URL may move to another origin once
  (http -> https, example.com -> www.example.com); after that, off-site redirects are
  recorded and not followed.
"""

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from app.links import extract_links, parse_html
from app.robots import Robots
from app.urls import normalize, origin, same_origin

logger = logging.getLogger(__name__)

HTML_TYPES = ("text/html", "application/xhtml+xml")
ROBOTS_MAX_BYTES = 512_000  # RFC 9309 asks crawlers to parse at least 500 KiB
MAX_SKIPPED_LISTED = 100


@dataclass(frozen=True)
class CrawlOptions:
    max_pages: int = 20
    concurrency: int = 2
    delay_s: float = 0.5
    max_bytes: int = 3_000_000
    max_redirects: int = 5
    user_agent: str = "AccessibilityCheckBot/0.1.0"
    max_crawl_delay_s: float = 10.0  # a larger Crawl-delay would make a scan take hours

    @property
    def product_token(self) -> str:
        return self.user_agent.split("/", 1)[0].strip()


@dataclass
class FetchedPage:
    url: str
    final_url: str
    index: int = 0  # discovery order, for a stable report
    status_code: int | None = None
    content_type: str = ""
    redirects: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    error: str | None = None
    # Set when the HTML is byte-for-byte the same as a page already scanned ("/" and
    # "/index.html"), so its issues are not counted twice.
    duplicate_of: str | None = None
    body_hash: str = ""
    # Parsed HTML, only for HTML pages read in full. Dropped after the callback.
    soup: BeautifulSoup | None = None

    @property
    def is_html(self) -> bool:
        return self.content_type.split(";")[0].strip().lower() in HTML_TYPES


@dataclass
class CrawlResult:
    start_url: str
    origin: str
    robots_status: str = ""
    pages: list[FetchedPage] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    skipped_total: int = 0


PageCallback = Callable[[FetchedPage], Awaitable[None]]
UrlGuard = Callable[[str], Awaitable[None]]


class Crawler:
    def __init__(
        self,
        client: httpx.AsyncClient,
        options: CrawlOptions,
        guard: UrlGuard | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._options = options
        self._guard = guard
        self._sleep = sleep
        self._headers = {"User-Agent": options.user_agent, "Accept": "text/html,*/*;q=0.5"}
        self._robots_cache: dict[str, Robots] = {}
        self._origin = ""
        self._robots = Robots.allow_all("")
        self._seen: dict[str, int] = {}
        self._final_urls: dict[str, str] = {}
        self._hashes: dict[str, str] = {}
        self._requested = 0
        self._delay = options.delay_s
        self._result = CrawlResult("", "")

    # robots.txt -------------------------------------------------------------------

    async def _load_robots(self, site: str) -> Robots:
        if site in self._robots_cache:
            return self._robots_cache[site]
        try:
            response = await self._client.get(
                f"{site}/robots.txt", headers=self._headers, follow_redirects=True
            )
        except httpx.HTTPError as exc:
            logger.info("robots.txt for %s unreachable: %r", site, exc)
            robots = Robots.disallow_all(
                "robots.txt could not be reached, so nothing was crawled (RFC 9309: "
                "an unreachable robots.txt means 'disallow all')"
            )
        else:
            status = response.status_code
            if 200 <= status < 300:
                robots = Robots.parse(
                    response.content[:ROBOTS_MAX_BYTES].decode("utf-8", "replace")
                )
                robots.status = "robots.txt found and obeyed"
            elif 400 <= status < 500:
                robots = Robots.allow_all(f"no robots.txt (HTTP {status}), all pages allowed")
            else:
                robots = Robots.disallow_all(
                    f"robots.txt returned HTTP {status}, so nothing was crawled (RFC 9309: "
                    "a server error means 'disallow all')"
                )
        self._robots_cache[site] = robots
        return robots

    async def _enter_origin(self, url: str) -> None:
        if self._guard is not None:
            await self._guard(url)
        self._origin = origin(url)
        self._robots = await self._load_robots(self._origin)

    def _allowed(self, url: str) -> bool:
        return self._robots.allowed(url, self._options.product_token)

    # Fetching ---------------------------------------------------------------------

    async def _get(self, url: str) -> tuple[httpx.Response, bytes | None, str | None]:
        """One request without following redirects. The body is read only for HTML, and
        only up to max_bytes."""
        async with self._client.stream("GET", url, headers=self._headers) as response:
            content_type = response.headers.get("content-type", "")
            is_html = content_type.split(";")[0].strip().lower() in HTML_TYPES
            if response.is_redirect or not is_html or response.status_code >= 400:
                return response, None, None
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > self._options.max_bytes:
                    limit_mb = self._options.max_bytes / 1_000_000
                    return response, None, f"Page is larger than {limit_mb:g} MB, not analysed"
            return response, bytes(body), None

    async def _fetch(self, url: str, index: int, *, is_start: bool) -> FetchedPage:
        page = FetchedPage(url=url, final_url=url, index=index)
        started = time.perf_counter()
        current = url
        try:
            for _ in range(self._options.max_redirects + 1):
                if not same_origin(current, self._origin):
                    if not is_start:
                        page.error = f"Redirects to another site ({current}), not followed"
                        return page
                    await self._enter_origin(current)
                if not self._allowed(current):
                    page.error = f"Redirect target {current} is blocked by robots.txt"
                    return page
                try:
                    response, body, problem = await self._get(current)
                except httpx.TimeoutException:
                    page.error = "Timed out"
                    return page
                except httpx.HTTPError as exc:
                    page.error = f"Request failed ({type(exc).__name__})"
                    return page
                page.status_code = response.status_code
                page.final_url = current
                location = response.headers.get("location")
                if response.is_redirect and location:
                    page.redirects.append(current)
                    current = normalize(str(httpx.URL(current).join(location)))
                    continue
                page.content_type = response.headers.get("content-type", "")
                page.error = problem
                if body is not None:
                    page.body_hash = hashlib.sha256(body).hexdigest()
                    page.soup = await asyncio.to_thread(parse_html, body, page.content_type)
                return page
            page.error = f"More than {self._options.max_redirects} redirects"
            return page
        finally:
            page.elapsed_ms = round((time.perf_counter() - started) * 1000)

    # Crawl loop ---------------------------------------------------------------------

    def _skip(self, url: str, reason: str) -> None:
        self._result.skipped_total += 1
        if len(self._result.skipped) < MAX_SKIPPED_LISTED:
            self._result.skipped.append((url, reason))

    async def _handle(
        self, page: FetchedPage, queue: asyncio.Queue[str], on_page: PageCallback | None
    ) -> None:
        if page.final_url != page.url and page.final_url in self._final_urls:
            page.duplicate_of = self._final_urls[page.final_url]
        elif page.body_hash and page.body_hash in self._hashes:
            page.duplicate_of = self._hashes[page.body_hash]
        if page.duplicate_of:
            page.soup = None  # same document: do not analyse it or follow its links again
        else:
            self._final_urls.setdefault(page.final_url, page.url)
            if page.body_hash:
                self._hashes[page.body_hash] = page.url
        self._seen.setdefault(page.final_url, page.index)
        if page.soup is not None:
            for link in extract_links(page.soup, page.final_url):
                if same_origin(link, self._origin) and link not in self._seen:
                    self._seen[link] = len(self._seen)
                    queue.put_nowait(link)
        if on_page is not None:
            try:
                await on_page(page)
            except Exception:
                logger.exception("Analysing %s failed", page.url)
                page.error = "The page could not be analysed (internal error)"
        page.soup = None
        self._result.pages.append(page)

    async def _worker(self, queue: asyncio.Queue[str], on_page: PageCallback | None) -> None:
        while True:
            url = await queue.get()
            try:
                if not self._allowed(url):
                    self._skip(url, "blocked by robots.txt")
                elif self._requested >= self._options.max_pages:
                    self._skip(url, f"page limit ({self._options.max_pages}) reached")
                else:
                    self._requested += 1
                    page = await self._fetch(url, self._seen[url], is_start=False)
                    await self._handle(page, queue, on_page)
                    await self._sleep(self._delay)
            except Exception:
                # A dead worker would leave queue.join() waiting forever.
                logger.exception("Crawling %s failed", url)
                self._result.pages.append(
                    FetchedPage(url, url, self._seen.get(url, 0), error="Internal error")
                )
            finally:
                queue.task_done()

    async def crawl(self, start_url: str, on_page: PageCallback | None = None) -> CrawlResult:
        """Crawl from start_url. Raises whatever the guard raises for a forbidden start."""
        start = normalize(start_url)
        await self._enter_origin(start)
        self._result = CrawlResult(start_url=start, origin=self._origin)
        self._result.robots_status = self._robots.status
        if not self._allowed(start):
            self._skip(start, "blocked by robots.txt")
            return self._result

        queue: asyncio.Queue[str] = asyncio.Queue()
        self._seen[start] = 0
        self._requested = 1
        first = await self._fetch(start, 0, is_start=True)
        # The start may have redirected to another origin with its own robots.txt.
        self._result.origin = self._origin
        self._result.robots_status = self._robots.status
        workers = self._options.concurrency
        crawl_delay = self._robots.crawl_delay(self._options.product_token)
        if crawl_delay:
            # Crawl-delay means "seconds between requests": one worker, that pause.
            workers = 1
            self._delay = max(self._delay, min(crawl_delay, self._options.max_crawl_delay_s))
        await self._handle(first, queue, on_page)

        if not queue.empty():
            await self._sleep(self._delay)
            tasks = [asyncio.create_task(self._worker(queue, on_page)) for _ in range(workers)]
            try:
                await queue.join()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

        self._result.pages.sort(key=lambda p: p.index)
        return self._result
