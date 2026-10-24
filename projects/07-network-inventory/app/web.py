"""Inventory page, device pages, CSV/JSON export and a small JSON API."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.changes import ChangeKind
from app.db import Device, Repository, Scan, StoredChange
from app.export import AssetRow, asset_rows, to_csv, to_json
from app.inventory import Inventory, ScanInProgressError
from app.oui import MacKind
from app.risks import Severity, describe_ports, risky_ports, service_name

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")

MAX_SHORT = 100
MAX_NOTES = 1000


class StatusFilter(StrEnum):
    ALL = "all"
    PRESENT = "present"
    MISSING = "missing"
    NEW = "new"
    UNKNOWN = "unknown"


class RiskFilter(StrEnum):
    ALL = "all"
    ANY = "any"
    HIGH = "high"
    NONE = "none"


@dataclass(frozen=True)
class Filters:
    q: str = ""
    status: StatusFilter = StatusFilter.ALL
    risk: RiskFilter = RiskFilter.ALL

    @property
    def active(self) -> bool:
        return self != Filters()


def is_new(row: AssetRow, latest: Scan | None, first_scan_id: int | None) -> bool:
    """First seen in the latest scan (and that scan was not the very first one)."""
    return (
        latest is not None and row.device.first_scan_id == latest.id and latest.id != first_scan_id
    )


def matches(row: AssetRow, f: Filters, latest: Scan | None, first_scan_id: int | None) -> bool:
    d = row.device
    if f.q:
        haystack = " ".join(
            filter(None, (d.ip, d.mac, d.vendor, d.hostname, d.name, d.owner, d.location, d.notes))
        ).lower()
        if f.q.lower() not in haystack:
            return False
    if f.status is StatusFilter.PRESENT and not row.present:
        return False
    if f.status is StatusFilter.MISSING and row.present:
        return False
    if f.status is StatusFilter.NEW and not is_new(row, latest, first_scan_id):
        return False
    if f.status is StatusFilter.UNKNOWN and d.known:
        return False
    if f.risk is RiskFilter.ANY and not row.risks:
        return False
    if f.risk is RiskFilter.HIGH and not any(r.severity is Severity.HIGH for r in row.risks):
        return False
    return not (f.risk is RiskFilter.NONE and row.risks)


def ip_sort(device: Device) -> tuple[int, ...]:
    return tuple(int(part) for part in device.ip.split("."))


@dataclass(frozen=True)
class ChangeRow:
    kind: ChangeKind
    device: Device
    text: str
    flagged: bool  # what the Telegram alert is sent for


def describe_change(change: StoredChange, device: Device) -> ChangeRow:
    ports = describe_ports(change.ports)
    texts = {
        ChangeKind.NEW: f"new device, open: {ports}",
        ChangeKind.RETURNED: "back on the network",
        ChangeKind.GONE: f"not seen (was {change.old_ip})",
        ChangeKind.PORT_OPENED: f"port opened: {ports}",
        ChangeKind.PORT_CLOSED: f"port closed: {ports}",
        ChangeKind.IP_CHANGED: f"IP changed {change.old_ip} → {change.new_ip}",
    }
    flagged = change.kind is ChangeKind.NEW or (
        change.kind is ChangeKind.PORT_OPENED and bool(risky_ports(change.ports))
    )
    return ChangeRow(change.kind, device, texts[change.kind], flagged)


CHANGE_ORDER = {
    ChangeKind.NEW: 0,
    ChangeKind.PORT_OPENED: 1,
    ChangeKind.GONE: 2,
    ChangeKind.RETURNED: 3,
    ChangeKind.IP_CHANGED: 4,
    ChangeKind.PORT_CLOSED: 5,
}


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=MAX_SHORT)
    owner: str | None = Field(default=None, max_length=MAX_SHORT)
    location: str | None = Field(default=None, max_length=MAX_SHORT)
    notes: str | None = Field(default=None, max_length=MAX_NOTES)
    known: bool | None = None


def create_app(
    inventory: Inventory,
    repo: Repository,
    tz: ZoneInfo,
    clock: Callable[[], datetime],
    *,
    demo: bool = False,
) -> FastAPI:
    app = FastAPI(title="Network Inventory", version="0.1.0")
    background: set[asyncio.Task[Any]] = set()

    def fmt(value: datetime | None, pattern: str = "%d %b %H:%M") -> str:
        return value.astimezone(tz).strftime(pattern) if value else "—"

    async def load_rows() -> tuple[list[AssetRow], Scan | None, int | None]:
        latest = await repo.latest_scan()
        first_id = await repo.first_scan_id()
        devices = sorted(await repo.devices(), key=ip_sort)
        rows = asset_rows(devices, latest.id if latest else None, await repo.all_ip_history())
        return rows, latest, first_id

    async def last_changes(latest: Scan | None, devices: dict[int, Device]) -> list[ChangeRow]:
        if latest is None:
            return []
        changes = [describe_change(c, devices[c.device_id]) for c in await repo.changes(latest.id)]
        return sorted(changes, key=lambda c: (CHANGE_ORDER[c.kind], ip_sort(c.device)))

    def common() -> dict[str, Any]:
        return {
            "demo": demo,
            "scope": str(inventory.scope),
            "scanning": inventory.scanning,
            "fmt": fmt,
            "service_name": service_name,
            "MacKind": MacKind,
            "Severity": Severity,
        }

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        q: Annotated[str, Query(max_length=MAX_SHORT)] = "",
        status: StatusFilter = StatusFilter.ALL,
        risk: RiskFilter = RiskFilter.ALL,
    ) -> HTMLResponse:
        filters = Filters(q.strip(), status, risk)
        rows, latest, first_id = await load_rows()
        by_id = {r.device.id: r.device for r in rows}
        changes = await last_changes(latest, by_id)
        shown = [r for r in rows if matches(r, filters, latest, first_id)]
        summary = {
            "total": len(rows),
            "present": sum(r.present for r in rows),
            "new": sum(is_new(r, latest, first_id) for r in rows),
            "gone": sum(c.kind is ChangeKind.GONE for c in changes),
            "unknown": sum(not r.device.known for r in rows),
            "high": sum(any(x.severity is Severity.HIGH for x in r.risks) for r in rows),
        }
        context = {
            **common(),
            "rows": shown,
            "filters": filters,
            "latest": latest,
            "changes": changes,
            "summary": summary,
            "new_ids": {r.device.id for r in rows if is_new(r, latest, first_id)},
        }
        return TEMPLATES.TemplateResponse(request, "index.html", context)

    @app.get("/devices/{device_id}", response_class=HTMLResponse)
    async def device_page(request: Request, device_id: int, saved: bool = False) -> HTMLResponse:
        rows, latest, _ = await load_rows()
        row = next((r for r in rows if r.device.id == device_id), None)
        if row is None:
            raise HTTPException(404, "No such device")
        by_id = {r.device.id: r.device for r in rows}
        history = [
            describe_change(c, by_id[c.device_id]) for c in await repo.device_changes(device_id)
        ]
        context = {
            **common(),
            "row": row,
            "device": row.device,
            "latest": latest,
            "ip_history": await repo.ip_history(device_id),
            "history": history,
            "saved": saved,
            "max_short": MAX_SHORT,
            "max_notes": MAX_NOTES,
        }
        return TEMPLATES.TemplateResponse(request, "device.html", context)

    @app.post("/devices/{device_id}")
    async def save_device(
        device_id: int,
        name: Annotated[str, Form(max_length=MAX_SHORT)] = "",
        owner: Annotated[str, Form(max_length=MAX_SHORT)] = "",
        location: Annotated[str, Form(max_length=MAX_SHORT)] = "",
        notes: Annotated[str, Form(max_length=MAX_NOTES)] = "",
        known: Annotated[bool, Form()] = False,
    ) -> RedirectResponse:
        found = await repo.update_details(
            device_id,
            name=name.strip(),
            owner=owner.strip(),
            location=location.strip(),
            notes=notes.strip(),
            known=known,
        )
        if not found:
            raise HTTPException(404, "No such device")
        return RedirectResponse(f"/devices/{device_id}?saved=1", status_code=303)

    @app.post("/scan")
    async def scan_from_page() -> RedirectResponse:
        if not inventory.scanning:
            task = asyncio.create_task(inventory.scan())
            background.add(task)
            task.add_done_callback(background.discard)
        return RedirectResponse("/", status_code=303)

    @app.get("/export/assets.csv")
    async def export_csv() -> Response:
        rows, _, _ = await load_rows()
        stamp = clock().astimezone(tz).strftime("%Y-%m-%d")
        # The BOM makes Excel read the file as UTF-8 (owners and notes may be Cyrillic).
        return Response(
            "﻿" + to_csv(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="assets-{stamp}.csv"'},
        )

    @app.get("/export/assets.json")
    async def export_json() -> JSONResponse:
        rows, _, _ = await load_rows()
        return JSONResponse(to_json(rows, clock()))

    @app.get("/api/devices")
    async def api_devices(
        q: Annotated[str, Query(max_length=MAX_SHORT)] = "",
        status: StatusFilter = StatusFilter.ALL,
        risk: RiskFilter = RiskFilter.ALL,
    ) -> list[dict[str, Any]]:
        filters = Filters(q.strip(), status, risk)
        rows, latest, first_id = await load_rows()
        return [r.as_dict() for r in rows if matches(r, filters, latest, first_id)]

    @app.get("/api/devices/{device_id}")
    async def api_device(device_id: int) -> dict[str, Any]:
        rows, _, _ = await load_rows()
        row = next((r for r in rows if r.device.id == device_id), None)
        if row is None:
            raise HTTPException(404, "No such device")
        data = row.as_dict()
        data["risks"] = [
            {
                "code": r.code,
                "severity": r.severity.label,
                "ports": list(r.ports),
                "title": r.title,
                "why": r.why,
                "fix": r.fix,
            }
            for r in row.risks
        ]
        return data

    @app.patch("/api/devices/{device_id}")
    async def api_update(device_id: int, update: DeviceUpdate) -> dict[str, Any]:
        device = await repo.device(device_id)
        if device is None:
            raise HTTPException(404, "No such device")
        await repo.update_details(
            device_id,
            name=device.name if update.name is None else update.name.strip(),
            owner=device.owner if update.owner is None else update.owner.strip(),
            location=device.location if update.location is None else update.location.strip(),
            notes=device.notes if update.notes is None else update.notes.strip(),
            known=device.known if update.known is None else update.known,
        )
        return await api_device(device_id)

    @app.get("/api/scans/latest")
    async def api_latest_scan() -> dict[str, Any]:
        rows, latest, _ = await load_rows()
        if latest is None:
            raise HTTPException(404, "No scan yet")
        by_id = {r.device.id: r.device for r in rows}
        return {
            "id": latest.id,
            "started_at": latest.started_at.isoformat(),
            "finished_at": latest.finished_at.isoformat() if latest.finished_at else None,
            "scope": latest.scope,
            "source": latest.source,
            "hosts_probed": latest.hosts_probed,
            "devices_found": latest.devices_found,
            "changes": [
                {
                    "kind": c.kind.value,
                    "device_id": c.device_id,
                    "ip": by_id[c.device_id].ip,
                    "ports": sorted(c.ports),
                    "old_ip": c.old_ip,
                    "new_ip": c.new_ip,
                }
                for c in await repo.changes(latest.id)
            ],
        }

    @app.post("/api/scan")
    async def api_scan() -> dict[str, Any]:
        try:
            report = await inventory.scan()
        except ScanInProgressError:
            raise HTTPException(409, "A scan is already running") from None
        return {
            "scan_id": report.scan.id,
            "devices_found": report.scan.devices_found,
            "changes": len(report.changes),
        }

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
