"""Entry point.

python -m app                 web page + a scan every SCAN_INTERVAL_MIN minutes
python -m app --demo          the same with a simulated office network, no scanning
python -m app scan            one scan, print the result, exit
python -m app scan --cidr 192.168.1.1/32 --ports 80,443
"""

import argparse
import asyncio
import logging
import shutil
import sys
from zoneinfo import ZoneInfo

import uvicorn
from aiogram import Bot

from app.config import Settings, get_settings
from app.db import Repository
from app.demo import DEMO_SCOPE, DemoScanner, seed
from app.discovery import NetworkScanner
from app.inventory import Inventory, ScanReport, utcnow
from app.notifier import ConsoleNotifier, Notifier, TelegramNotifier
from app.oui import MacKind, OuiDatabase
from app.risks import assess
from app.scope import Scope, ScopeError, parse_scope
from app.web import create_app

logger = logging.getLogger("inventory")


def build_scope(settings: Settings, cidrs: str | None = None) -> Scope:
    return parse_scope(
        cidrs if cidrs is not None else settings.scan_cidrs,
        allow_public=settings.allow_public,
        subnet_limit=settings.subnet_limit,
    )


def build_scanner(settings: Settings) -> NetworkScanner:
    if shutil.which("ping") is None:
        logger.error("The 'ping' command is not installed; only the ARP table will be used.")
    return NetworkScanner(
        settings.scan_ports,
        ping_timeout_s=settings.ping_timeout_s,
        tcp_timeout_s=settings.tcp_timeout_s,
        dns_timeout_s=settings.dns_timeout_s,
        max_parallel_pings=settings.max_parallel_pings,
        max_parallel_connects=settings.max_parallel_connects,
        reverse_dns=settings.reverse_dns,
    )


def build_notifier(settings: Settings) -> tuple[Notifier, Bot | None]:
    if settings.bot_token and settings.alert_chat_id is not None:
        bot = Bot(settings.bot_token)
        return TelegramNotifier(bot, settings.alert_chat_id), bot
    logger.warning("BOT_TOKEN or ALERT_CHAT_ID is not set: alerts are printed to the console.")
    return ConsoleNotifier(), None


async def serve(settings: Settings) -> None:
    oui = OuiDatabase.load()
    notifier, bot = build_notifier(settings)
    if settings.demo_mode:
        # Demo data lives in memory: every start shows the same two scans.
        repo = await Repository.connect(":memory:")
        scanner = DemoScanner()
        inventory = Inventory(
            repo, scanner, DEMO_SCOPE, oui, notifier, source="demo", tz_name=settings.timezone
        )
        await seed(repo, oui, scanner, utcnow())
        await inventory.scan()
        interval = 0.0
    else:
        scope = build_scope(settings)
        repo = await Repository.connect(settings.database_path)
        inventory = Inventory(
            repo, build_scanner(settings), scope, oui, notifier, tz_name=settings.timezone
        )
        interval = settings.scan_interval_min * 60

    app = create_app(inventory, repo, ZoneInfo(settings.timezone), utcnow, demo=settings.demo_mode)
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
    logger.info(
        "Inventory of %s. Page: http://127.0.0.1:%d%s",
        inventory.scope,
        settings.port,
        f", scanning every {settings.scan_interval_min:g} min" if interval else "",
    )
    scans = asyncio.create_task(inventory.run_forever(interval)) if interval else None
    try:
        await server.serve()
    finally:
        if scans:
            scans.cancel()
            await asyncio.gather(scans, return_exceptions=True)
        if bot:
            await bot.session.close()
        await repo.close()


def print_report(report: ScanReport) -> None:
    devices = sorted(report.devices.values(), key=lambda d: tuple(map(int, d.ip.split("."))))
    present = [d for d in devices if d.last_scan_id == report.scan.id]
    seconds = (report.scan.finished_at or report.scan.started_at) - report.scan.started_at
    print(
        f"\nScan #{report.scan.id} of {report.scan.scope}: {report.scan.hosts_probed} addresses, "
        f"{len(present)} devices, {seconds.total_seconds():.1f} s"
    )
    for d in present:
        vendor = "randomised MAC" if d.mac_kind == MacKind.RANDOMISED else d.vendor or "-"
        ports = " ".join(str(p) for p in sorted(d.open_ports)) or "-"
        risks = ", ".join(r.code for r in assess(d.open_ports)) or "-"
        print(
            f"  {d.ip:<15} {d.mac or '-':<17}  {vendor:<16} {d.hostname or '-':<28} "
            f"ports: {ports:<16} risks: {risks}"
        )
    if report.first_scan:
        print("First scan: every device is new.")
        return
    for change in report.changes:
        ports = " ".join(str(p) for p in change.ports)
        print(f"  {change.kind.value:<12} {change.key} {ports}")
    if not report.changes:
        print("No changes since the previous scan.")


async def scan_once(settings: Settings, cidrs: str | None) -> None:
    scope = build_scope(settings, cidrs)
    notifier, bot = build_notifier(settings)
    repo = await Repository.connect(settings.database_path)
    try:
        inventory = Inventory(
            repo,
            build_scanner(settings),
            scope,
            OuiDatabase.load(),
            notifier,
            tz_name=settings.timezone,
        )
        print_report(await inventory.scan())
    finally:
        if bot:
            await bot.session.close()
        await repo.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app", description="Network inventory")
    parser.add_argument("command", nargs="?", choices=["serve", "scan"], default="serve")
    parser.add_argument("--demo", action="store_true", help="simulated office network")
    parser.add_argument("--cidr", help="networks to scan (overrides SCAN_CIDRS)")
    parser.add_argument("--ports", help="TCP ports to probe (overrides SCAN_PORTS)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    overrides: dict[str, object] = {}
    if args.demo:
        overrides["demo_mode"] = True
    if args.ports:
        overrides["scan_ports"] = args.ports
    # Command-line options win over the environment and .env.
    settings = Settings(**overrides) if overrides else get_settings()  # type: ignore[arg-type]

    try:
        if args.command == "scan":
            asyncio.run(scan_once(settings, args.cidr))
        else:
            asyncio.run(serve(settings))
    except ScopeError as exc:
        sys.exit(f"Refusing to scan: {exc}")
