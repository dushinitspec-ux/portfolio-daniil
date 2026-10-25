"""One scan, end to end: discover, match to the register, diff, store, alert."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.changes import Change, ChangeKind, Snapshot, diff, resolve
from app.db import Device, Repository, Scan
from app.discovery import Scanner
from app.messages import format_alert
from app.notifier import Notifier
from app.oui import OuiDatabase
from app.scope import Scope

logger = logging.getLogger("inventory")


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ScanReport:
    scan: Scan
    first_scan: bool
    changes: list[Change]
    devices: dict[str, Device]  # by register key, after this scan

    def of_kind(self, kind: ChangeKind) -> list[Change]:
        return [c for c in self.changes if c.kind is kind]


class ScanInProgressError(RuntimeError):
    pass


async def record_scan(
    repo: Repository,
    scanner: Scanner,
    scope: Scope,
    oui: OuiDatabase,
    *,
    source: str,
    clock: Callable[[], datetime] = utcnow,
) -> ScanReport:
    started = clock()
    observations = await scanner.scan(scope)
    finished = clock()

    async with repo.transaction():
        previous = await repo.latest_scan()
        previous_keys = await repo.present_keys(previous.id) if previous else set()
        resolution = resolve(observations, await repo.identities())
        for old, new in resolution.rekeys.items():
            await repo.rekey(old, new)
        previous_keys = {resolution.rekeys.get(k, k) for k in previous_keys}

        current = {k: Snapshot(s.ip, s.ports) for k, s in resolution.sightings.items()}
        changes = diff(
            last_known=await repo.snapshots(),
            previous_scan=previous_keys,
            current=current,
            in_scope=scope.contains,
        )
        scan_id = await repo.add_scan(
            started_at=started,
            finished_at=finished,
            scope=str(scope),
            source=source,
            hosts_probed=scope.size,
            devices_found=len(resolution.sightings),
        )
        for sighting in resolution.sightings.values():
            info = oui.lookup(sighting.mac) if sighting.mac else None
            await repo.save_sighting(scan_id, sighting, info, finished)
        await repo.save_changes(scan_id, changes)

    scan = await repo.latest_scan()
    assert scan is not None and scan.id == scan_id
    devices = {d.key: d for d in await repo.devices()}
    return ScanReport(scan, previous is None, changes, devices)


class Inventory:
    """Runs scans one at a time and sends the alerts."""

    def __init__(
        self,
        repo: Repository,
        scanner: Scanner,
        scope: Scope,
        oui: OuiDatabase,
        notifier: Notifier,
        *,
        source: str = "network",
        tz_name: str = "UTC",
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.repo = repo
        self.scanner = scanner
        self.scope = scope
        self.oui = oui
        self.notifier = notifier
        self.source = source
        self.tz_name = tz_name
        self.clock = clock
        self._lock = asyncio.Lock()

    @property
    def scanning(self) -> bool:
        return self._lock.locked()

    async def scan(self) -> ScanReport:
        if self._lock.locked():
            raise ScanInProgressError("a scan is already running")
        async with self._lock:
            report = await record_scan(
                self.repo, self.scanner, self.scope, self.oui, source=self.source, clock=self.clock
            )
        logger.info(
            "Scan %d: %d devices, %d changes.",
            report.scan.id,
            report.scan.devices_found,
            len(report.changes),
        )
        text = format_alert(report, self.tz_name)
        if text:
            try:
                await self.notifier.send(text)
            except Exception:
                # A Telegram outage must not lose the scan: it is already stored.
                logger.exception("Could not send the alert")
        return report

    async def run_forever(self, interval_s: float) -> None:
        while True:
            try:
                await self.scan()
            except ScanInProgressError:
                pass
            except Exception:
                logger.exception("Scan failed; trying again in %g s", interval_s)
            await asyncio.sleep(interval_s)
