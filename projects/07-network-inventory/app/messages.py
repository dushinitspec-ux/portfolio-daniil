"""Alert texts (plain text, no Markdown, so host names cannot break the formatting).

One message per scan, never one per device: a new office switch with 20 devices behind it
must not produce 20 notifications. The first scan of an empty register is a summary only,
because everything in it is "new".
"""

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.changes import ChangeKind
from app.db import Device
from app.oui import MacKind
from app.risks import Severity, assess, describe_ports, highest, risky_ports, service_name

if TYPE_CHECKING:
    from app.inventory import ScanReport

MAX_LINES = 15


def device_line(device: Device) -> str:
    parts = [device.ip]
    if device.mac:
        parts.append(device.mac)
    randomised = device.mac_kind == MacKind.RANDOMISED
    what = device.name or device.vendor or ("randomised MAC" if randomised else "")
    if device.hostname:
        what = f"{what}, {device.hostname}" if what else device.hostname
    return " · ".join(parts) + (f" ({what})" if what else "")


def format_alert(report: "ScanReport", tz_name: str) -> str | None:
    tz = ZoneInfo(tz_name)
    when = report.scan.finished_at or report.scan.started_at
    header = f"Network inventory · {report.scan.scope} · {when.astimezone(tz):%d %b %H:%M}"
    by_key = report.devices

    if report.first_scan:
        risky = [d for d in by_key.values() if highest(assess(d.open_ports)) is Severity.HIGH]
        lines = [
            header,
            f"First scan: {report.scan.devices_found} devices added to the register.",
        ]
        if risky:
            lines.append(f"{len(risky)} with a high-risk open service - see the inventory page.")
        return "\n".join(lines)

    new = [by_key[c.key] for c in report.of_kind(ChangeKind.NEW)]
    risky_opened = [
        (by_key[c.key], sorted(risky_ports(c.ports)))
        for c in report.of_kind(ChangeKind.PORT_OPENED)
        if risky_ports(c.ports)
    ]
    if not new and not risky_opened:
        return None

    lines = [header]
    if new:
        lines.append(f"New device{'s' if len(new) > 1 else ''} ({len(new)}):")
        for device in new[:MAX_LINES]:
            lines.append(f"• {device_line(device)}")
            lines.append(f"  open: {describe_ports(device.open_ports)}")
            lines.extend(f"  ⚠ {r.title} ({r.severity.label})" for r in assess(device.open_ports))
        if len(new) > MAX_LINES:
            lines.append(f"… and {len(new) - MAX_LINES} more")
    if risky_opened:
        lines.append("New risky port:" if len(risky_opened) == 1 else "New risky ports:")
        for device, ports in risky_opened[:MAX_LINES]:
            opened = ", ".join(f"{p} {service_name(p)}" for p in ports)
            lines.append(f"• {device.label} ({device.ip}): {opened}")
    return "\n".join(lines)
