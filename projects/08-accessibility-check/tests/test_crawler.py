"""The crawler against fake websites served by httpx.MockTransport."""

import httpx
import pytest

from app.crawler import Crawler, CrawlOptions, CrawlResult, FetchedPage, UrlGuard
from app.urls import TargetNotAllowed
from tests.conftest import FakeSite, RecordingSleep, links

OPTIONS = CrawlOptions(max_pages=20, concurrency=2, delay_s=0.5)


async def crawl(
    site: FakeSite,
    start: str = "https://shop.test/",
    options: CrawlOptions = OPTIONS,
    sleep: RecordingSleep | None = None,
    guard: UrlGuard | None = None,
) -> CrawlResult:
    async with httpx.AsyncClient(transport=site.transport) as client:
        crawler = Crawler(client, options, guard=guard, sleep=sleep or RecordingSleep())
        return await crawler.crawl(start)


def robots(site: FakeSite, text: str, origin: str = "https://shop.test") -> None:
    site.routes[f"{origin}/robots.txt"] = (200, {"content-type": "text/plain"}, text)


async def test_follows_links_on_the_same_origin_only(site: FakeSite) -> None:
    robots(site, "User-agent: *\nDisallow:\n")
    site.page(
        "https://shop.test/",
        links("/about", "https://other.test/", "http://shop.test/http-is-another-origin",
              "mailto:a@b.test", "/catalogue.pdf"),
    )  # fmt: skip
    site.page("https://shop.test/about", links("/"))

    result = await crawl(site)

    assert site.page_requests() == ["https://shop.test/", "https://shop.test/about"]
    assert [p.url for p in result.pages] == ["https://shop.test/", "https://shop.test/about"]
    assert all(p.status_code == 200 for p in result.pages)


async def test_robots_txt_disallow_is_obeyed(site: FakeSite) -> None:
    robots(site, "User-agent: *\nDisallow: /private\n")
    site.page("https://shop.test/", links("/private/staff", "/public"))
    site.page("https://shop.test/public", links())

    result = await crawl(site)

    assert "https://shop.test/private/staff" not in site.requests
    assert ("https://shop.test/private/staff", "blocked by robots.txt") in result.skipped
    assert result.robots_status == "robots.txt found and obeyed"


async def test_page_limit_counts_requests(site: FakeSite) -> None:
    robots(site, "User-agent: *\nDisallow:\n")
    site.page("https://shop.test/", links(*[f"/p{i}" for i in range(10)]))
    for i in range(10):
        site.page(f"https://shop.test/p{i}", links())

    result = await crawl(site, options=CrawlOptions(max_pages=3, concurrency=2, delay_s=0))

    assert len(site.page_requests()) == 3
    assert len(result.pages) == 3
    assert result.skipped_total == 8
    assert all("page limit (3)" in reason for _, reason in result.skipped)


async def test_status_codes_and_errors_are_recorded(site: FakeSite) -> None:
    robots(site, "")
    site.page("https://shop.test/", links("/missing", "/broken", "/image"))
    site.page("https://shop.test/broken", "oops", status=500)
    site.routes["https://shop.test/image"] = (200, {"content-type": "image/png"}, "PNG")

    result = await crawl(site)
    by_url = {p.url: p for p in result.pages}

    assert by_url["https://shop.test/missing"].status_code == 404
    assert by_url["https://shop.test/broken"].status_code == 500
    assert by_url["https://shop.test/image"].status_code == 200
    assert not by_url["https://shop.test/image"].is_html


async def test_same_origin_redirect_is_followed_and_recorded(site: FakeSite) -> None:
    robots(site, "")
    site.page("https://shop.test/", links("/old"))
    site.redirect("https://shop.test/old", "/new")
    site.page("https://shop.test/new", links())

    result = await crawl(site)
    old = next(p for p in result.pages if p.url == "https://shop.test/old")

    assert old.final_url == "https://shop.test/new"
    assert old.redirects == ["https://shop.test/old"]
    assert old.status_code == 200


async def test_off_site_redirect_is_not_followed(site: FakeSite) -> None:
    robots(site, "")
    site.page("https://shop.test/", links("/go"))
    site.redirect("https://shop.test/go", "https://tracker.test/x")

    result = await crawl(site)
    go = next(p for p in result.pages if p.url == "https://shop.test/go")

    assert "another site" in (go.error or "")
    assert not any(u.startswith("https://tracker.test") for u in site.requests)


async def test_start_url_may_move_to_https_and_www(site: FakeSite) -> None:
    site.routes["http://shop.test/robots.txt"] = (404, {}, "")
    site.redirect("http://shop.test/", "https://www.shop.test/")
    robots(site, "User-agent: *\nDisallow: /admin\n", origin="https://www.shop.test")
    site.page("https://www.shop.test/", links("/admin", "/bags"))
    site.page("https://www.shop.test/bags", links())

    result = await crawl(site, start="http://shop.test")

    assert result.origin == "https://www.shop.test"
    assert "https://www.shop.test/robots.txt" in site.requests
    assert "https://www.shop.test/bags" in site.requests
    assert "https://www.shop.test/admin" not in site.requests


@pytest.mark.parametrize(
    ("status", "crawled", "text"),
    [(404, True, "all pages allowed"), (503, False, "disallow all")],
)
async def test_missing_robots_allows_all_but_server_error_disallows_all(
    site: FakeSite, status: int, crawled: bool, text: str
) -> None:
    site.routes["https://shop.test/robots.txt"] = (status, {}, "")
    site.page("https://shop.test/", links())

    result = await crawl(site)

    assert ("https://shop.test/" in site.requests) is crawled
    assert text in result.robots_status


async def test_unreachable_robots_txt_means_nothing_is_crawled() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Crawler(client, OPTIONS, sleep=RecordingSleep()).crawl("https://down.test/")

    assert result.pages == []
    assert result.skipped == [("https://down.test/", "blocked by robots.txt")]


async def test_concurrency_and_delay_are_limited(site: FakeSite, no_sleep: RecordingSleep) -> None:
    robots(site, "")
    site.latency_s = 0.01
    site.page("https://shop.test/", links(*[f"/p{i}" for i in range(8)]))
    for i in range(8):
        site.page(f"https://shop.test/p{i}", links())

    await crawl(
        site, options=CrawlOptions(max_pages=20, concurrency=2, delay_s=0.5), sleep=no_sleep
    )

    assert site.max_in_flight == 2
    assert no_sleep.calls and set(no_sleep.calls) == {0.5}
    assert len(no_sleep.calls) == 9  # after the start page and after each of the 8 pages


async def test_crawl_delay_means_one_worker_and_that_pause(
    site: FakeSite, no_sleep: RecordingSleep
) -> None:
    robots(site, "User-agent: *\nCrawl-delay: 2\n")
    site.latency_s = 0.01
    site.page("https://shop.test/", links("/a", "/b", "/c"))
    for p in "abc":
        site.page(f"https://shop.test/{p}", links())

    await crawl(site, sleep=no_sleep)

    assert site.max_in_flight == 1
    assert set(no_sleep.calls) == {2.0}


async def test_same_document_under_two_urls_is_analysed_once(site: FakeSite) -> None:
    robots(site, "")
    home = links("/index.html", "/about")
    site.page("https://shop.test/", home)
    site.page("https://shop.test/index.html", home)
    site.page("https://shop.test/about", links())
    analysed: list[str] = []

    async with httpx.AsyncClient(transport=site.transport) as client:
        crawler = Crawler(client, OPTIONS, sleep=RecordingSleep())

        async def on_page(page: FetchedPage) -> None:
            if page.soup is not None:
                analysed.append(page.url)

        result = await crawler.crawl("https://shop.test/", on_page)

    duplicate = next(p for p in result.pages if p.url == "https://shop.test/index.html")
    assert duplicate.duplicate_of == "https://shop.test/"
    assert analysed == ["https://shop.test/", "https://shop.test/about"]


async def test_pages_larger_than_the_limit_are_not_analysed(site: FakeSite) -> None:
    robots(site, "")
    site.page("https://shop.test/", "<html><body>" + "x" * 50_000 + "</body></html>")

    result = await crawl(site, options=CrawlOptions(max_bytes=10_000))

    assert result.pages[0].soup is None
    assert "larger than" in (result.pages[0].error or "")


async def test_guard_runs_before_the_first_request(site: FakeSite) -> None:
    async def guard(url: str) -> None:
        raise TargetNotAllowed("private")

    with pytest.raises(TargetNotAllowed):
        await crawl(site, start="http://10.0.0.1/", guard=guard)
    assert site.requests == []


async def test_base_href_is_used_for_relative_links(site: FakeSite) -> None:
    robots(site, "")
    site.page(
        "https://shop.test/",
        '<html><head><base href="/shop/"></head><body><a href="bags">Bags</a></body></html>',
    )
    site.page("https://shop.test/shop/bags", links())

    await crawl(site)

    assert "https://shop.test/shop/bags" in site.requests
