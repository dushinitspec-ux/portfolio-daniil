import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.db import Repository
from app.rules import RULES, Page
from app.rules.base import Outcome


def check(rule_id: str, html: str) -> Outcome:
    """Run one rule on an HTML snippet (wrapped into a minimal page if needed)."""
    if "<html" not in html:
        html = f'<html lang="en"><head><title>T</title></head><body>{html}</body></html>'
    return RULES[rule_id].check(Page(html, "https://shop.test/"))


@dataclass
class FakeSite:
    """A website for httpx.MockTransport: path -> (status, headers, body)."""

    routes: dict[str, tuple[int, dict[str, str], str]] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)
    in_flight: int = 0
    max_in_flight: int = 0
    latency_s: float = 0.0

    def page(self, url: str, body: str, status: int = 200, **headers: str) -> "FakeSite":
        self.routes[url] = (status, {"content-type": "text/html; charset=utf-8", **headers}, body)
        return self

    def redirect(self, url: str, location: str, status: int = 301) -> "FakeSite":
        self.routes[url] = (status, {"location": location}, "")
        return self

    async def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.latency_s:
                await asyncio.sleep(self.latency_s)
            if url not in self.routes:
                return httpx.Response(404, headers={"content-type": "text/html"}, text="no")
            status, headers, body = self.routes[url]
            return httpx.Response(status, headers=headers, text=body)
        finally:
            self.in_flight -= 1

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def page_requests(self) -> list[str]:
        return [u for u in self.requests if not u.endswith("/robots.txt")]


def links(*hrefs: str) -> str:
    items = "".join(f'<a href="{h}">Page {h}</a>' for h in hrefs)
    head = f"<head><title>{len(hrefs)} links</title></head>"
    return f'<html lang="en">{head}<body><main>{items}</main></body></html>'


@pytest.fixture
def site() -> FakeSite:
    return FakeSite()


@pytest.fixture
async def repo() -> AsyncIterator[Repository]:
    repository = await Repository.connect(":memory:")
    yield repository
    await repository.close()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_path=tmp_path / "test.db",
        request_delay_s=0,
        demo_mode=False,
    )


class RecordingSleep:
    """Stands in for asyncio.sleep: records the pauses instead of waiting."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
def no_sleep() -> RecordingSleep:
    return RecordingSleep()
