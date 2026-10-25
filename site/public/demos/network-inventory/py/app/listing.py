"""What the inventory page lists: the filters, which devices are new, one line per change.

Pure functions over the register, no web framework, so the web page (app/web.py) and the
in-browser demo (app/web_demo.py) list and filter devices the same way.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.changes import ChangeKind
from app.db import Device, Scan, StoredChange
from app.export import AssetRow
from app.risks import Severity, describe_ports, risky_ports


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
