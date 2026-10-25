"""In-browser demo (Pyodide): the simulated office network through the real register code.

A browser cannot ping, read the ARP table or open TCP connections into a LAN, so the scanner
here is the app's own demo scanner (app/demo.py: a made-up office, scanned twice). Everything
after the scan is the real pipeline, as in `python -m app --demo`: matching to the register
(changes.resolve), the diff, the MAC vendor lookup, the risk rules, the alert text, the page
filters and the CSV/JSON export, with the register in an in-memory SQLite database (the
app's own Repository and SQL).

aiosqlite runs SQLite in a thread and the browser has no threads, so Repository gets a small
stand-in with the same awaitable methods over the standard sqlite3 module.

The visitor may also change the simulated office before the next scan: close a port (the fix
a risk asks for) or unplug a device. That only edits what the simulator returns; the scan,
the diff and the risks are computed as always.

Every function takes and returns JSON-ready values.
"""

import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db import SCHEMA, Device, Repository, Scan, StoredChange
from app.demo import DEMO_SCOPE, DemoScanner, seed
from app.discovery import Observation
from app.export import AssetRow, asset_rows, to_csv, to_json
from app.inventory import Inventory, ScanReport, utcnow
from app.listing import (
    CHANGE_ORDER,
    Filters,
    RiskFilter,
    StatusFilter,
    describe_change,
    ip_sort,
    is_new,
    matches,
)
from app.messages import format_alert
from app.oui import MacKind, OuiDatabase
from app.risks import Severity, assess, service_name
from app.scope import Scope

MAX_QUERY = 100  # the web page's limit for the search box


# --- SQLite without threads -------------------------------------------------------------


class _Cursor:
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    @property
    def lastrowid(self) -> int | None:
        return self._cursor.lastrowid

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    async def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    async def fetchone(self) -> Any:
        return self._cursor.fetchone()


class SyncConnection:
    """The part of aiosqlite.Connection that Repository uses, run in the calling thread."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    async def execute(self, sql: str, parameters: Sequence[Any] = ()) -> _Cursor:
        return _Cursor(self._conn.execute(sql, parameters))

    async def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> _Cursor:
        return _Cursor(self._conn.executemany(sql, rows))

    async def executescript(self, sql: str) -> _Cursor:
        return _Cursor(self._conn.executescript(sql))

    async def commit(self) -> None:
        self._conn.commit()

    async def rollback(self) -> None:
        self._conn.rollback()

    async def close(self) -> None:
        self._conn.close()


async def memory_repository() -> Repository:
    """An empty register in memory, set up as Repository.connect(":memory:") does."""
    conn = SyncConnection(sqlite3.connect(":memory:"))
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.executescript(SCHEMA)
    await conn.commit()
    return Repository(conn)  # type: ignore[arg-type]


# --- The simulated office, with the visitor's edits -------------------------------------


@dataclass
class VisitorOffice(DemoScanner):
    """DemoScanner plus what the visitor changed: ports closed, devices unplugged."""

    closed: dict[str, set[int]] = field(default_factory=dict)  # MAC -> ports
    unplugged: set[str] = field(default_factory=set)  # MACs

    async def scan(self, scope: Scope) -> list[Observation]:
        seen = await super().scan(scope)
        return [
            replace(o, open_ports=o.open_ports - self.closed.get(o.mac or "", set()))
            for o in seen
            if o.mac not in self.unplugged
        ]


class Outbox:
    """Stands in for Telegram: keeps the alert texts instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


@dataclass
class Session:
    repo: Repository
    office: VisitorOffice
    inventory: Inventory
    outbox: Outbox
    tz_name: str


_oui: OuiDatabase | None = None
_session: Session | None = None


def _vendors() -> OuiDatabase:
    global _oui
    if _oui is None:
        _oui = OuiDatabase.load()
    return _oui


def _zone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return "UTC"
    return name


def _current() -> Session:
    if _session is None:
        raise RuntimeError("call start() first")
    return _session


# --- JSON shapes ------------------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _ports(ports: Iterable[int]) -> list[dict[str, Any]]:
    return [{"port": p, "service": service_name(p)} for p in sorted(ports)]


def _scan(scan: Scan, first_id: int | None) -> dict[str, Any]:
    return {
        "id": scan.id,
        "first": scan.id == first_id,
        "started_at": _iso(scan.started_at),
        "finished_at": _iso(scan.finished_at),
        "scope": scan.scope,
        "source": scan.source,
        "hosts_probed": scan.hosts_probed,
        "devices_found": scan.devices_found,
    }


def _sim(office: VisitorOffice, device: Device) -> dict[str, Any]:
    mac = device.mac or ""
    return {"unplugged": mac in office.unplugged, "closed": sorted(office.closed.get(mac, ()))}


def _row(
    row: AssetRow, latest: Scan | None, first_id: int | None, office: VisitorOffice
) -> dict[str, Any]:
    d = row.device
    data = row.as_dict()  # the export's own fields
    data.update(
        label=d.label,
        key=d.key,
        new=is_new(row, latest, first_id),
        present=row.present,
        randomised=d.mac_kind == MacKind.RANDOMISED,
        ports=_ports(d.open_ports),
        sim=_sim(office, d),
    )
    return data


async def _load(s: Session) -> tuple[list[AssetRow], Scan | None, int | None]:
    """The rows as the web page loads them (app/web.py, load_rows)."""
    latest = await s.repo.latest_scan()
    first_id = await s.repo.first_scan_id()
    devices = sorted(await s.repo.devices(), key=ip_sort)
    rows = asset_rows(devices, latest.id if latest else None, await s.repo.all_ip_history())
    return rows, latest, first_id


def _change(change: StoredChange, device: Device) -> dict[str, Any]:
    line = describe_change(change, device)
    return {
        "kind": change.kind.value,
        "device_id": device.id,
        "label": device.label,
        "ip": device.ip,
        "ports": _ports(change.ports),
        "old_ip": change.old_ip,
        "new_ip": change.new_ip,
        "flagged": line.flagged,
        "text": line.text,
    }


async def _changes(s: Session, latest: Scan | None, by_id: dict[int, Device]) -> list[dict]:
    if latest is None:
        return []
    stored = await s.repo.changes(latest.id)
    stored.sort(key=lambda c: (CHANGE_ORDER[c.kind], ip_sort(by_id[c.device_id])))
    return [_change(c, by_id[c.device_id]) for c in stored]


async def _listing(s: Session, filters: Filters | None = None) -> dict[str, Any]:
    filters = filters or Filters()
    rows, latest, first_id = await _load(s)
    by_id = {r.device.id: r.device for r in rows}
    changes = await _changes(s, latest, by_id)
    shown = [r for r in rows if matches(r, filters, latest, first_id)]
    summary = {  # the counters at the top of the web page
        "total": len(rows),
        "present": sum(r.present for r in rows),
        "new": sum(is_new(r, latest, first_id) for r in rows),
        "gone": sum(c["kind"] == "gone" for c in changes),
        "unknown": sum(not r.device.known for r in rows),
        "high": sum(any(x.severity is Severity.HIGH for x in r.risks) for r in rows),
    }
    return {
        "scan": _scan(latest, first_id) if latest else None,
        "summary": summary,
        "devices": [_row(r, latest, first_id, s.office) for r in shown],
        "changes": changes,
    }


# --- Entry points -----------------------------------------------------------------------


async def start(tz_name: str = "UTC") -> dict[str, Any]:
    """A fresh, empty register and the office as it looks before the first scan."""
    global _session
    tz_name = _zone(tz_name)
    repo = await memory_repository()
    office = VisitorOffice()
    outbox = Outbox()
    inventory = Inventory(
        repo, office, DEMO_SCOPE, _vendors(), outbox, source="demo", tz_name=tz_name
    )
    _session = Session(repo, office, inventory, outbox, tz_name)
    return {
        "scope": str(DEMO_SCOPE),
        "hosts": DEMO_SCOPE.size,
        "vendors": len(_vendors()),
        "timezone": tz_name,
    }


async def scan() -> dict[str, Any]:
    """The next scan. The first one is the demo's seed: scan 1 a day ago, then the
    administrator names the known devices. Later scans run as the app runs them."""
    s = _current()
    if await s.repo.latest_scan() is None:
        await seed(s.repo, _vendors(), s.office, utcnow())
        latest = await s.repo.latest_scan()
        assert latest is not None
        devices = {d.key: d for d in await s.repo.devices()}
        # seed() does not alert; this is the summary a first real scan would send.
        alert = format_alert(ScanReport(latest, True, [], devices), s.tz_name)
    else:
        s.outbox.sent.clear()
        await s.inventory.scan()
        alert = s.outbox.sent[-1] if s.outbox.sent else None
    return {"alert": alert, **await _listing(s)}


async def devices(q: str = "", risk: str = "all", status: str = "all") -> dict[str, Any]:
    """The register filtered like the web page (search, risk, status)."""
    filters = Filters(q.strip()[:MAX_QUERY], StatusFilter(status), RiskFilter(risk))
    return await _listing(_current(), filters)


async def _find(
    s: Session, device_id: int
) -> tuple[AssetRow, list[AssetRow], Scan | None, int | None]:
    rows, latest, first_id = await _load(s)
    row = next((r for r in rows if r.device.id == device_id), None)
    if row is None:
        raise ValueError(f"no device {device_id}")
    return row, rows, latest, first_id


async def device(device_id: int) -> dict[str, Any]:
    """One device: the register fields, every risk with why and what to do, IP history and
    the changes recorded for it."""
    s = _current()
    row, rows, latest, first_id = await _find(s, device_id)
    d = row.device
    data = _row(row, latest, first_id, s.office)
    data["risks"] = [
        {
            "code": r.code,
            "severity": r.severity.label,
            "ports": _ports(r.ports),
            "title": r.title,
            "why": r.why,
            "fix": r.fix,
        }
        for r in assess(d.open_ports)
    ]
    by_id = {r.device.id: r.device for r in rows}
    data["ip_records"] = [
        {"ip": rec.ip, "first_seen": _iso(rec.first_seen), "last_seen": _iso(rec.last_seen)}
        for rec in await s.repo.ip_history(device_id)
    ]
    data["history"] = [
        {**_change(c, by_id[c.device_id]), "scan_id": c.scan_id}
        for c in await s.repo.device_changes(device_id)
    ]
    return data


async def close_port(device_id: int, port: int) -> dict[str, Any]:
    """Simulate the fix: the device stops answering on `port` from the next scan on."""
    s = _current()
    row, *_ = await _find(s, device_id)
    mac = row.device.mac
    if mac is None or port not in row.device.open_ports:
        raise ValueError(f"port {port} is not open on device {device_id}")
    s.office.closed.setdefault(mac, set()).add(port)
    return _sim(s.office, row.device)


async def set_unplugged(device_id: int, unplugged: bool) -> dict[str, Any]:
    """Simulate unplugging a device (or plugging it back in) before the next scan."""
    s = _current()
    row, *_ = await _find(s, device_id)
    if row.device.mac is None:
        raise ValueError(f"device {device_id} has no MAC address")
    if unplugged:
        s.office.unplugged.add(row.device.mac)
    else:
        s.office.unplugged.discard(row.device.mac)
    return _sim(s.office, row.device)


def _stamp(s: Session) -> str:
    return utcnow().astimezone(ZoneInfo(s.tz_name)).strftime("%Y-%m-%d")


async def export_csv() -> dict[str, Any]:
    """The register as the page's CSV download (with the BOM Excel needs for UTF-8)."""
    s = _current()
    rows, _, _ = await _load(s)
    return {"filename": f"assets-{_stamp(s)}.csv", "rows": len(rows), "text": "﻿" + to_csv(rows)}


async def export_json() -> dict[str, Any]:
    s = _current()
    rows, _, _ = await _load(s)
    text = json.dumps(to_json(rows, utcnow()), ensure_ascii=False, indent=2)
    return {"filename": f"assets-{_stamp(s)}.json", "rows": len(rows), "text": text}
