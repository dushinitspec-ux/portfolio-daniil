"""The asset register as CSV (for Excel and auditors) and JSON (for other tools)."""

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.db import Device
from app.risks import Risk, assess

CSV_COLUMNS = (
    "id",
    "name",
    "ip",
    "mac",
    "mac_type",
    "vendor",
    "hostname",
    "status",
    "open_ports",
    "risks",
    "highest_risk",
    "owner",
    "location",
    "notes",
    "known",
    "first_seen",
    "last_seen",
    "ip_history",
)

# A cell starting with one of these is run as a formula by Excel and LibreOffice. Owner and
# notes are typed by users and host names come from the network, so they are not trusted.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_START) else value


@dataclass(frozen=True)
class AssetRow:
    device: Device
    present: bool
    risks: list[Risk]
    ip_history: list[str]

    @property
    def status(self) -> str:
        return "present" if self.present else "not seen in last scan"

    def as_dict(self) -> dict[str, Any]:
        d = self.device
        highest = max((r.severity for r in self.risks), default=None)
        return {
            "id": d.id,
            "name": d.name,
            "ip": d.ip,
            "mac": d.mac,
            "mac_type": d.mac_kind,
            "vendor": d.vendor,
            "hostname": d.hostname,
            "status": self.status,
            "open_ports": sorted(d.open_ports),
            "risks": [
                {
                    "code": r.code,
                    "severity": r.severity.label,
                    "ports": list(r.ports),
                    "title": r.title,
                }
                for r in self.risks
            ],
            "highest_risk": highest.label if highest else None,
            "owner": d.owner,
            "location": d.location,
            "notes": d.notes,
            "known": d.known,
            "first_seen": d.first_seen.isoformat(),
            "last_seen": d.last_seen.isoformat(),
            "ip_history": self.ip_history,
        }


def asset_rows(
    devices: list[Device], latest_scan_id: int | None, ip_history: dict[int, list[str]]
) -> list[AssetRow]:
    return [
        AssetRow(
            device=d,
            present=d.last_scan_id == latest_scan_id,
            risks=assess(d.open_ports),
            ip_history=ip_history.get(d.id, [d.ip]),
        )
        for d in devices
    ]


def to_csv(rows: list[AssetRow]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        data = row.as_dict()
        data["open_ports"] = " ".join(str(p) for p in data["open_ports"])
        data["risks"] = "; ".join(r["code"] for r in data["risks"])
        data["ip_history"] = " ".join(data["ip_history"])
        data["known"] = "yes" if data["known"] else "no"
        writer.writerow(safe_cell(str(data[c])) if data[c] is not None else "" for c in CSV_COLUMNS)
    return out.getvalue()


def to_json(rows: list[AssetRow], generated_at: datetime) -> dict[str, Any]:
    return {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "device_count": len(rows),
        "devices": [row.as_dict() for row in rows],
    }
