import asyncio
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.backtest import complete_days, format_backtest, run_backtest
from app.bot import AllowedChat, plan_text
from app.config import DEFAULT_FIXTURE, Settings
from app.db import PriceCache
from app.devices import load_site
from app.fixtures import load_fixture
from app.main import parse_args, run
from app.prices import day_bounds, to_grid
from app.service import PlanService
from app.web import create_app
from tests.conftest import DEMO_FIXTURE, ROOT, TZ

SITE = load_site(ROOT / "devices.yaml")
FIXTURE = load_fixture(DEMO_FIXTURE)
GRID = to_grid(FIXTURE.prices.points)


# --- Backtest on the bundled real prices ---------------------------------------------------


def test_backtest_uses_the_last_30_complete_days() -> None:
    days = complete_days(SITE, GRID, TZ, 30)
    assert len(days) == 30
    assert days[0] == date(2026, 9, 26)
    assert days[-1] == date(2026, 10, 25)


def test_backtest_result_on_real_prices() -> None:
    """The numbers quoted in the README come from this run."""
    result = run_backtest(SITE, GRID, TZ, complete_days(SITE, GRID, TZ, 30))
    assert len(result.days) == 30 and not result.skipped and not result.unplanned
    assert result.saving == sum((d.saving for d in result.devices), Decimal(0))
    assert result.saving.quantize(Decimal("0.01")) == Decimal("146.47")
    assert result.per_day(result.saving).quantize(Decimal("0.01")) == Decimal("4.88")
    assert all(d.saving >= 0 for d in result.devices)
    text = format_backtest(result, SITE, "DE-LU", "15-minute", "")
    assert "30 days (2026-09-26 to 2026-10-25)" in text


def test_backtest_skips_a_day_with_a_gap() -> None:
    start, _ = day_bounds(date(2026, 10, 20), TZ)
    hole = start + timedelta(hours=3)
    grid = [s for s in GRID if s.start != hole]
    days = complete_days(SITE, grid, TZ, 30)
    assert date(2026, 10, 20) not in days
    result = run_backtest(SITE, grid, TZ, [date(2026, 10, 19), date(2026, 10, 20)])
    assert result.skipped == [date(2026, 10, 20)]


# --- Web page --------------------------------------------------------------------------------


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    cache = await PriceCache.connect(":memory:")
    prices = FIXTURE.prices
    await cache.save(
        "DE-LU", prices.points, prices.source, prices.license_info, FIXTURE.downloaded_at
    )
    service = PlanService(cache, None, SITE, "DE-LU", TZ, lambda: FIXTURE.downloaded_at)
    app = create_app(service, "DE-LU", demo=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    await cache.close()


async def test_page_defaults_to_tomorrow_the_25_hour_day(client: httpx.AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert "Sunday 25 Oct 2026" in html
    assert "this day has 25 hours" in html
    assert "<svg" in html and "Hot-water boiler" in html
    assert "Bundesnetzagentur | SMARD.de" in html
    assert "next day not published" in html
    # The price range is Sunday's own (0.0-7.2 ct/kWh), not Saturday evening's 11.1,
    # and a price of -0.01 EUR/MWh is not shown as "-0.0".
    assert '<span class="value">0.0–7.2</span>' in html
    assert "02:15 CEST  DRY-RUN Hot-water boiler ON" in html


async def test_page_for_an_ordinary_day(client: httpx.AsyncClient) -> None:
    html = (await client.get("/?day=2026-10-22")).text
    assert "Thursday 22 Oct 2026" in html
    assert "8.39 €" in html and "15.86 €" in html and "47.1 %" in html
    assert "Clocks" not in html
    assert 'href="?day=2026-10-23"' in html


async def test_api_and_chart(client: httpx.AsyncClient) -> None:
    data = (await client.get("/api/plan?day=2026-10-22")).json()
    assert data["hours"] == 24
    assert Decimal(data["saving_eur"]).quantize(Decimal("0.01")) == Decimal("7.47")
    assert data["devices"][0]["name"] == "Hot-water boiler"
    chart = await client.get("/chart.svg?day=2026-10-22")
    assert chart.headers["content-type"].startswith("image/svg+xml")
    assert chart.text.count("<rect") > 96
    assert (await client.get("/?day=2026-10-27")).status_code == 404
    assert (await client.get("/healthz")).json() == {"status": "ok"}


# --- Telegram commands and the command line -------------------------------------------------


async def test_bot_plan_text_and_chat_filter() -> None:
    cache = await PriceCache.connect(":memory:")
    prices = FIXTURE.prices
    await cache.save(
        "DE-LU", prices.points, prices.source, prices.license_info, FIXTURE.downloaded_at
    )
    service = PlanService(cache, None, SITE, "DE-LU", TZ, lambda: FIXTURE.downloaded_at)
    text = await plan_text(service, 1, "DE-LU")
    assert text.startswith("⚡ Plan for Sunday 25 Oct 2026 · DE-LU day-ahead")
    await cache.close()

    def message(chat_id: int) -> Any:
        return SimpleNamespace(chat=SimpleNamespace(id=chat_id))

    assert await AllowedChat(-100123)(message(-100123))
    assert not await AllowedChat(-100123)(message(42))
    assert await AllowedChat(None)(message(42))


def test_bundled_prices_are_not_in_an_ignored_folder() -> None:
    # The repository's .gitignore drops every data/ folder (runtime databases), so the
    # demo prices must live elsewhere or a fresh clone has no demo.
    assert "data" not in DEFAULT_FIXTURE.relative_to(ROOT).parts
    assert DEFAULT_FIXTURE.exists()


def demo_settings() -> Settings:
    return Settings(_env_file=None, demo_mode=True, devices_file=ROOT / "devices.yaml")  # type: ignore[call-arg]


def test_cli_plan_in_demo_mode(capsys: pytest.CaptureFixture[str]) -> None:
    asyncio.run(run(parse_args(["plan", "--day", "2026-10-22"]), demo_settings()))
    out = capsys.readouterr().out
    assert "⚡ Plan for Thursday 22 Oct 2026" in out
    assert "Saving 7.47 € (47.1 %)." in out
    assert "Shelly plugs (dry run, nothing is sent):" in out


def test_cli_backtest_in_demo_mode(capsys: pytest.CaptureFixture[str]) -> None:
    asyncio.run(run(parse_args(["backtest", "--days", "30"]), demo_settings()))
    out = capsys.readouterr().out
    assert "Backtest: DE-LU day-ahead prices, 30 days (2026-09-26 to 2026-10-25)" in out
    assert "saving 146.47 € (29.6 %)" in out
