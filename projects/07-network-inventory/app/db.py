"""SQLite asset register: devices, their IP history, every scan and what it changed.

Timestamps are ISO 8601 strings in UTC with a fixed format, so string order is time order.
Writes are not committed one by one: a scan is stored in one transaction, so a scan that
crashes halfway leaves no half-written register behind. The web page and the scan loop share
one connection, so a lock keeps an edit from committing someone else's half-done scan.
"""

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.changes import Change, ChangeKind, Known, Sighting, Snapshot
from app.oui import MacInfo

if TYPE_CHECKING:
    # Imported where a connection is opened: the in-browser demo (Pyodide) has no threads,
    # so it cannot run aiosqlite and hands Repository a connection of its own.
    import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id            INTEGER PRIMARY KEY,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    scope         TEXT NOT NULL,
    source        TEXT NOT NULL,
    hosts_probed  INTEGER NOT NULL DEFAULT 0,
    devices_found INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS devices (
    id            INTEGER PRIMARY KEY,
    key           TEXT NOT NULL UNIQUE,
    ip            TEXT NOT NULL,
    mac           TEXT,
    mac_kind      TEXT,
    vendor        TEXT,
    hostname      TEXT,
    open_ports    TEXT NOT NULL DEFAULT '',
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    first_scan_id INTEGER NOT NULL REFERENCES scans (id),
    last_scan_id  INTEGER NOT NULL REFERENCES scans (id),
    name          TEXT NOT NULL DEFAULT '',
    owner         TEXT NOT NULL DEFAULT '',
    location      TEXT NOT NULL DEFAULT '',
    notes         TEXT NOT NULL DEFAULT '',
    known         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ip_history (
    device_id  INTEGER NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
    ip         TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    PRIMARY KEY (device_id, ip)
);

CREATE TABLE IF NOT EXISTS sightings (
    scan_id    INTEGER NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    device_id  INTEGER NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
    ip         TEXT NOT NULL,
    open_ports TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (scan_id, device_id)
);

CREATE TABLE IF NOT EXISTS changes (
    id        INTEGER PRIMARY KEY,
    scan_id   INTEGER NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    device_id INTEGER NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
    kind      TEXT NOT NULL,
    ports     TEXT NOT NULL DEFAULT '',
    old_ip    TEXT,
    new_ip    TEXT
);
CREATE INDEX IF NOT EXISTS idx_changes_scan ON changes (scan_id);
"""

DEVICE_COLUMNS = (
    "id, key, ip, mac, mac_kind, vendor, hostname, open_ports, first_seen, last_seen, "
    "first_scan_id, last_scan_id, name, owner, location, notes, known"
)


def to_db(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def from_db(value: str) -> datetime:
    return datetime.fromisoformat(value)


def ports_to_db(ports: Iterable[int]) -> str:
    return " ".join(str(p) for p in sorted(ports))


def ports_from_db(value: str) -> frozenset[int]:
    return frozenset(int(p) for p in value.split())


@dataclass(frozen=True)
class Device:
    id: int
    key: str
    ip: str
    mac: str | None
    mac_kind: str | None
    vendor: str | None
    hostname: str | None
    open_ports: frozenset[int]
    first_seen: datetime
    last_seen: datetime
    first_scan_id: int
    last_scan_id: int
    name: str = ""
    owner: str = ""
    location: str = ""
    notes: str = ""
    known: bool = False

    @property
    def label(self) -> str:
        return self.name or self.hostname or self.vendor or self.ip


@dataclass(frozen=True)
class Scan:
    id: int
    started_at: datetime
    finished_at: datetime | None
    scope: str
    source: str
    hosts_probed: int
    devices_found: int


@dataclass(frozen=True)
class StoredChange:
    scan_id: int
    device_id: int
    kind: ChangeKind
    ports: frozenset[int]
    old_ip: str | None
    new_ip: str | None


@dataclass(frozen=True)
class IpRecord:
    ip: str
    first_seen: datetime
    last_seen: datetime


def _device(row: "aiosqlite.Row") -> Device:
    return Device(
        id=row[0],
        key=row[1],
        ip=row[2],
        mac=row[3],
        mac_kind=row[4],
        vendor=row[5],
        hostname=row[6],
        open_ports=ports_from_db(row[7]),
        first_seen=from_db(row[8]),
        last_seen=from_db(row[9]),
        first_scan_id=row[10],
        last_scan_id=row[11],
        name=row[12],
        owner=row[13],
        location=row[14],
        notes=row[15],
        known=bool(row[16]),
    )


def _scan(row: "aiosqlite.Row") -> Scan:
    return Scan(
        id=row[0],
        started_at=from_db(row[1]),
        finished_at=from_db(row[2]) if row[2] else None,
        scope=row[3],
        source=row[4],
        hosts_probed=row[5],
        devices_found=row[6],
    )


class Repository:
    def __init__(self, conn: "aiosqlite.Connection") -> None:
        self._db = conn
        self._write_lock = asyncio.Lock()

    @classmethod
    async def connect(cls, path: Path | str) -> "Repository":
        import aiosqlite

        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        await conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            await conn.execute("PRAGMA journal_mode = WAL")
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._db.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """All writes go through here: one writer at a time, commit or roll back together."""
        async with self._write_lock:
            try:
                yield
            except BaseException:
                await self._db.rollback()
                raise
            await self._db.commit()

    # --- scans -------------------------------------------------------------------------

    async def add_scan(
        self,
        *,
        started_at: datetime,
        finished_at: datetime,
        scope: str,
        source: str,
        hosts_probed: int,
        devices_found: int,
    ) -> int:
        """Call inside `transaction()`, together with the sightings of this scan."""
        cursor = await self._db.execute(
            "INSERT INTO scans (started_at, finished_at, scope, source, hosts_probed, "
            "devices_found) VALUES (?, ?, ?, ?, ?, ?)",
            (to_db(started_at), to_db(finished_at), scope, source, hosts_probed, devices_found),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    async def scans(self, limit: int = 10) -> list[Scan]:
        cursor = await self._db.execute(
            "SELECT id, started_at, finished_at, scope, source, hosts_probed, devices_found "
            "FROM scans WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [_scan(row) for row in await cursor.fetchall()]

    async def latest_scan(self) -> Scan | None:
        scans = await self.scans(limit=1)
        return scans[0] if scans else None

    async def first_scan_id(self) -> int | None:
        cursor = await self._db.execute("SELECT MIN(id) FROM scans WHERE finished_at IS NOT NULL")
        row = await cursor.fetchone()
        return row[0] if row else None

    async def present_keys(self, scan_id: int) -> set[str]:
        cursor = await self._db.execute(
            "SELECT d.key FROM sightings s JOIN devices d ON d.id = s.device_id "
            "WHERE s.scan_id = ?",
            (scan_id,),
        )
        return {row[0] for row in await cursor.fetchall()}

    # --- devices -----------------------------------------------------------------------

    async def devices(self) -> list[Device]:
        cursor = await self._db.execute(f"SELECT {DEVICE_COLUMNS} FROM devices")
        return [_device(row) for row in await cursor.fetchall()]

    async def device(self, device_id: int) -> Device | None:
        cursor = await self._db.execute(
            f"SELECT {DEVICE_COLUMNS} FROM devices WHERE id = ?", (device_id,)
        )
        row = await cursor.fetchone()
        return _device(row) if row else None

    async def identities(self) -> dict[str, Known]:
        cursor = await self._db.execute("SELECT key, ip, mac FROM devices")
        return {row[0]: Known(row[1], row[2]) for row in await cursor.fetchall()}

    async def snapshots(self) -> dict[str, Snapshot]:
        """The last sighting of every device: its IP and open ports."""
        cursor = await self._db.execute("SELECT key, ip, open_ports FROM devices")
        return {row[0]: Snapshot(row[1], ports_from_db(row[2])) for row in await cursor.fetchall()}

    async def rekey(self, old: str, new: str) -> None:
        await self._db.execute("UPDATE devices SET key = ? WHERE key = ?", (new, old))

    async def save_sighting(
        self, scan_id: int, sighting: Sighting, mac_info: MacInfo | None, at: datetime
    ) -> int:
        ts = to_db(at)
        ports = ports_to_db(sighting.ports)
        kind = mac_info.kind.value if mac_info else None
        vendor = mac_info.vendor if mac_info else None
        # A sighting without a MAC or a host name keeps what the register already knows.
        cursor = await self._db.execute(
            """
            INSERT INTO devices (key, ip, mac, mac_kind, vendor, hostname, open_ports,
                                 first_seen, last_seen, first_scan_id, last_scan_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (key) DO UPDATE SET
                ip = excluded.ip,
                mac = COALESCE(excluded.mac, mac),
                mac_kind = COALESCE(excluded.mac_kind, mac_kind),
                vendor = COALESCE(excluded.vendor, vendor),
                hostname = COALESCE(excluded.hostname, hostname),
                open_ports = excluded.open_ports,
                last_seen = excluded.last_seen,
                last_scan_id = excluded.last_scan_id
            RETURNING id
            """,
            (
                sighting.key,
                sighting.ip,
                sighting.mac,
                kind,
                vendor,
                sighting.hostname,
                ports,
                ts,
                ts,
                scan_id,
                scan_id,
            ),
        )
        row = await cursor.fetchone()
        assert row is not None
        device_id: int = row[0]
        for ip in (sighting.ip, *sighting.other_ips):
            await self._db.execute(
                """
                INSERT INTO ip_history (device_id, ip, first_seen, last_seen) VALUES (?, ?, ?, ?)
                ON CONFLICT (device_id, ip) DO UPDATE SET last_seen = excluded.last_seen
                """,
                (device_id, ip, ts, ts),
            )
        await self._db.execute(
            "INSERT INTO sightings (scan_id, device_id, ip, open_ports) VALUES (?, ?, ?, ?)",
            (scan_id, device_id, sighting.ip, ports),
        )
        return device_id

    async def device_ids(self) -> dict[str, int]:
        cursor = await self._db.execute("SELECT key, id FROM devices")
        return {row[0]: row[1] for row in await cursor.fetchall()}

    async def save_changes(self, scan_id: int, changes: Iterable[Change]) -> None:
        ids = await self.device_ids()
        await self._db.executemany(
            "INSERT INTO changes (scan_id, device_id, kind, ports, old_ip, new_ip) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (scan_id, ids[c.key], c.kind.value, ports_to_db(c.ports), c.old_ip, c.new_ip)
                for c in changes
            ],
        )

    async def changes(self, scan_id: int) -> list[StoredChange]:
        cursor = await self._db.execute(
            "SELECT scan_id, device_id, kind, ports, old_ip, new_ip FROM changes "
            "WHERE scan_id = ? ORDER BY id",
            (scan_id,),
        )
        return [
            StoredChange(row[0], row[1], ChangeKind(row[2]), ports_from_db(row[3]), row[4], row[5])
            for row in await cursor.fetchall()
        ]

    async def device_changes(self, device_id: int, limit: int = 20) -> list[StoredChange]:
        cursor = await self._db.execute(
            "SELECT scan_id, device_id, kind, ports, old_ip, new_ip FROM changes "
            "WHERE device_id = ? ORDER BY id DESC LIMIT ?",
            (device_id, limit),
        )
        return [
            StoredChange(row[0], row[1], ChangeKind(row[2]), ports_from_db(row[3]), row[4], row[5])
            for row in await cursor.fetchall()
        ]

    async def ip_history(self, device_id: int) -> list[IpRecord]:
        cursor = await self._db.execute(
            "SELECT ip, first_seen, last_seen FROM ip_history WHERE device_id = ? "
            "ORDER BY last_seen DESC",
            (device_id,),
        )
        return [IpRecord(r[0], from_db(r[1]), from_db(r[2])) for r in await cursor.fetchall()]

    async def all_ip_history(self) -> dict[int, list[str]]:
        cursor = await self._db.execute(
            "SELECT device_id, ip FROM ip_history ORDER BY device_id, first_seen"
        )
        history: dict[int, list[str]] = {}
        for device_id, ip in await cursor.fetchall():
            history.setdefault(device_id, []).append(ip)
        return history

    async def update_details(
        self,
        device_id: int,
        *,
        name: str,
        owner: str,
        location: str,
        notes: str,
        known: bool,
    ) -> bool:
        async with self.transaction():
            cursor = await self._db.execute(
                "UPDATE devices SET name = ?, owner = ?, location = ?, notes = ?, known = ? "
                "WHERE id = ?",
                (name, owner, location, notes, int(known), device_id),
            )
        return cursor.rowcount > 0
