"""Command line: the web page with the daily jobs (default), one-off plans, the backtest and
price downloads.

    python -m app [--demo]                         page + daily Telegram plan + plug switching
    python -m app plan [--day 2026-10-25] [--send] print (or send) one day's plan
    python -m app backtest [--days 30]             replay the last N days
    python -m app fetch --start D --end D          download prices into the cache
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import uvicorn
from aiogram import Bot, Dispatcher

from app.backtest import complete_days, format_backtest, run_backtest
from app.bot import BOT_COMMANDS, build_router
from app.config import Settings, get_settings
from app.db import PriceCache
from app.devices import DeviceConfigError, SiteConfig, load_site
from app.energy_charts import EnergyChartsClient
from app.entsoe import EntsoeClient
from app.fixtures import load_fixture, write_fixture
from app.messages import format_plan
from app.notifier import ConsoleNotifier, Notifier, TelegramNotifier
from app.prices import day_bounds, resolution_label, to_grid
from app.scheduler import DailyPlanSender, Switcher, preview_switching, run_forever
from app.service import PlanService, PriceSource
from app.shelly import ShellyController
from app.web import create_app

logger = logging.getLogger("energy")
USER_AGENT = "energy-saver/0.1 (portfolio project; day-ahead load planner)"


@dataclass
class Context:
    settings: Settings
    site: SiteConfig
    cache: PriceCache
    service: PlanService
    http: httpx.AsyncClient
    demo: bool


def utcnow() -> datetime:
    return datetime.now(UTC)


def frozen_clock(at: datetime) -> Callable[[], datetime]:
    def clock() -> datetime:
        return at

    return clock


@asynccontextmanager
async def open_context(settings: Settings, demo: bool) -> AsyncIterator[Context]:
    site = load_site(settings.devices_file)
    http = httpx.AsyncClient(headers={"User-Agent": USER_AGENT})
    source: PriceSource | None = None
    clock: Callable[[], datetime] = utcnow
    if demo:
        # Offline: real prices from the bundled file, in memory, with the clock stopped at
        # the moment they were downloaded (so "tomorrow" is the last day in the file).
        fixture = load_fixture(settings.demo_fixture)
        cache = await PriceCache.connect(":memory:")
        await cache.save(
            fixture.bidding_zone,
            fixture.prices.points,
            fixture.prices.source,
            fixture.prices.license_info,
            fixture.downloaded_at,
        )
        bzn = fixture.bidding_zone
        clock = frozen_clock(fixture.downloaded_at)
    else:
        cache = await PriceCache.connect(settings.database_path)
        bzn = settings.bidding_zone
        if settings.price_source == "entsoe":
            if not settings.entsoe_token:
                raise SystemExit("PRICE_SOURCE=entsoe needs ENTSOE_TOKEN in .env")
            source = EntsoeClient(http, settings.entsoe_token)
        else:
            source = EnergyChartsClient(http, settings.energy_charts_url)
    service = PlanService(cache, source, site, bzn, settings.tz, clock)
    try:
        yield Context(settings, site, cache, service, http, demo)
    finally:
        await cache.close()
        await http.aclose()


async def serve(ctx: Context) -> None:
    settings, service = ctx.settings, ctx.service
    bot: Bot | None = None
    notifier: Notifier = ConsoleNotifier()
    tasks: list[asyncio.Task[None]] = []
    if settings.bot_token:
        bot = Bot(settings.bot_token)
        if settings.plan_chat_id is not None:
            notifier = TelegramNotifier(bot, settings.plan_chat_id)
        dispatcher = Dispatcher()
        dispatcher.include_router(build_router(service, service.bzn, settings.plan_chat_id))
        await bot.set_my_commands(BOT_COMMANDS)
        tasks.append(asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False)))
    if bot is None or settings.plan_chat_id is None:
        logger.warning("BOT_TOKEN or PLAN_CHAT_ID is not set: the plan is printed here.")

    controller = ShellyController(ctx.http, ctx.site.devices, dry_run=settings.shelly_dry_run)
    if ctx.demo:
        day = await service.default_day()
        plan = await service.plan(day)
        await notifier.send(format_plan(plan, service.bzn, await service.attribution()))
        for line in await preview_switching(plan, controller):
            logger.info("%s", line)
    else:
        sender = DailyPlanSender(
            service, notifier, settings.send_at, settings.send_retry_until, service.bzn
        )
        tasks.append(
            asyncio.create_task(run_forever("daily plan", sender.tick, service.clock, 300))
        )
        if any(d.shelly for d in ctx.site.devices):
            switcher = Switcher(service, controller)
            tasks.append(
                asyncio.create_task(run_forever("switching", switcher.tick, service.clock, 20))
            )

    app = create_app(service, service.bzn, demo=ctx.demo, controller=controller)
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
    logger.info(
        "Energy Saver for %s (%s). Page: http://127.0.0.1:%d",
        service.bzn,
        "demo, offline" if ctx.demo else settings.price_source,
        settings.port,
    )
    try:
        await server.serve()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if bot:
            await bot.session.close()


async def plan_command(ctx: Context, day: date | None, send: bool) -> None:
    service = ctx.service
    day = day or service.today() + timedelta(days=1)
    plan = await service.plan(day)
    text = format_plan(plan, service.bzn, await service.attribution())
    settings = ctx.settings
    if send and settings.bot_token and settings.plan_chat_id is not None:
        bot = Bot(settings.bot_token)
        try:
            await TelegramNotifier(bot, settings.plan_chat_id).send(text)
        finally:
            await bot.session.close()
        print(f"Sent the plan for {day} to chat {settings.plan_chat_id}.")
    else:
        if send:
            print("BOT_TOKEN or PLAN_CHAT_ID is not set; printing instead.\n")
        print(text)
    controller = ShellyController(ctx.http, ctx.site.devices, dry_run=True)
    preview = await preview_switching(plan, controller)
    if preview:
        print("\nShelly plugs (dry run, nothing is sent):")
        print("\n".join(preview))


async def backtest_command(ctx: Context, days: int) -> None:
    service, tz = ctx.service, ctx.service.tz
    if not ctx.demo:
        # Fill the cache with one request if it is short; the replay itself is offline.
        first = day_bounds(service.today() - timedelta(days=days + 1), tz)[0]
        await service.grid(first, day_bounds(service.today() + timedelta(days=1), tz)[1])
    span = await service.cache.span(service.bzn)
    if span is None:
        raise SystemExit("No prices in the cache. Run: python -m app fetch --start ... --end ...")
    points = await service.cache.load(service.bzn, *span)
    grid = to_grid(points)
    selected = complete_days(ctx.site, grid, tz, days)
    result = run_backtest(ctx.site, grid, tz, selected)
    print(
        format_backtest(
            result, ctx.site, service.bzn, resolution_label(points), await service.attribution()
        )
    )


async def fetch_command(ctx: Context, start: date, end: date, fixture: Path | None) -> None:
    settings, service = ctx.settings, ctx.service
    if ctx.demo:
        raise SystemExit("fetch needs the network; run it without --demo / DEMO_MODE.")
    first, last = day_bounds(start, service.tz)[0], day_bounds(end, service.tz)[1]
    if fixture is not None:
        client = EnergyChartsClient(ctx.http, settings.energy_charts_url)
        response = await client.get(service.bzn, first, last)
        response.raise_for_status()
        write_fixture(fixture, response.content, str(response.url), service.bzn, datetime.now(UTC))
        print(f"Saved {fixture}")
    grid = await service.grid(first, last)
    points = await service.cache.load(service.bzn, first, last)
    print(
        f"{len(grid)} quarter-hours ({resolution_label(points)}) for {service.bzn}, "
        f"{start} to {end}, in {settings.database_path}"
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app", description=__doc__.split("\n")[0])
    parser.add_argument("--demo", action="store_true", help="bundled real prices, offline")
    sub = parser.add_subparsers(dest="command")
    plan = sub.add_parser("plan", help="print one day's plan")
    plan.add_argument("--day", type=date.fromisoformat, help="YYYY-MM-DD, default tomorrow")
    plan.add_argument("--send", action="store_true", help="send it to Telegram")
    plan.add_argument("--demo", action="store_true", default=argparse.SUPPRESS)
    backtest = sub.add_parser("backtest", help="replay the last N days")
    backtest.add_argument("--days", type=int, default=30)
    backtest.add_argument("--demo", action="store_true", default=argparse.SUPPRESS)
    fetch = sub.add_parser("fetch", help="download prices into the cache")
    fetch.add_argument("--start", type=date.fromisoformat, required=True)
    fetch.add_argument("--end", type=date.fromisoformat, required=True)
    fetch.add_argument("--save-fixture", type=Path, help="also save the raw answer here")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, settings: Settings) -> None:
    demo = settings.demo_mode or getattr(args, "demo", False)
    async with open_context(settings, demo) as ctx:
        if args.command == "plan":
            await plan_command(ctx, args.day, args.send)
        elif args.command == "backtest":
            await backtest_command(ctx, args.days)
        elif args.command == "fetch":
            await fetch_command(ctx, args.start, args.end, args.save_fixture)
        else:
            await serve(ctx)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx logs every request URL at INFO; an ENTSO-E URL contains the API token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = parse_args(argv)
    try:
        asyncio.run(run(args, get_settings()))
    except DeviceConfigError as exc:
        sys.exit(f"Device list error: {exc}")


if __name__ == "__main__":
    main()
