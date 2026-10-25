"""Demo mode: a made-up office network, scanned twice, so the diff and the risks show.

Everything here is sample data: the network (192.168.10.0/24), the host names, the owners.
The MAC addresses use real vendor prefixes so the vendor lookup works, with invented last
three bytes. Between the two scans, a few things change, as they do in a real office:

- someone plugs in a Raspberry Pi with VNC open (new unknown device, risky port);
- a camera starts answering on Telnet after a factory reset (new risky port);
- the accounting laptop and a staff phone are gone, the MacBook got a new IP from DHCP;
- the lobby TV stopped answering on 8080.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.db import Repository
from app.discovery import Observation
from app.inventory import record_scan
from app.oui import OuiDatabase
from app.scope import Scope, parse_scope

DEMO_CIDR = "192.168.10.0/24"
DEMO_SCOPE = parse_scope(DEMO_CIDR)


@dataclass(frozen=True)
class DemoDevice:
    ip: str
    mac: str
    hostname: str | None
    ports: frozenset[int]
    # Filled in after the first scan, as an administrator would.
    name: str = ""
    owner: str = ""
    location: str = ""
    notes: str = ""
    known: bool = True
    # Changes in the second scan.
    gone: bool = False
    new_ip: str | None = None
    ports_later: frozenset[int] | None = None
    only_later: bool = False


def _p(*ports: int) -> frozenset[int]:
    return frozenset(ports)


OFFICE: tuple[DemoDevice, ...] = (
    DemoDevice(
        "192.168.10.1",
        "48:8f:5a:3c:10:01",
        "gw.office.lan",
        _p(22, 80, 8291),
        "Main router",
        "IT",
        "Server cabinet",
        "RouterOS; Winbox for the IT team only",
    ),
    DemoDevice(
        "192.168.10.2",
        "00:1b:54:7a:20:02",
        "core-sw.office.lan",
        _p(22, 23, 80),
        "Core switch",
        "IT",
        "Server cabinet",
        "Old managed switch, Telnet still on",
    ),
    DemoDevice(
        "192.168.10.3",
        "50:c7:bf:2b:30:03",
        None,
        _p(80),
        "Floor 2 switch",
        "IT",
        "Floor 2 corridor",
    ),
    DemoDevice(
        "192.168.10.11",
        "74:83:c2:11:40:11",
        "ap-lobby.office.lan",
        _p(22, 443),
        "AP lobby",
        "IT",
        "Lobby ceiling",
    ),
    DemoDevice(
        "192.168.10.12",
        "74:83:c2:11:40:12",
        "ap-floor1.office.lan",
        _p(22, 443),
        "AP floor 1",
        "IT",
        "Floor 1",
    ),
    DemoDevice(
        "192.168.10.13",
        "74:83:c2:11:40:13",
        "ap-floor2.office.lan",
        _p(22, 443),
        "AP floor 2",
        "IT",
        "Floor 2",
    ),
    DemoDevice(
        "192.168.10.21",
        "c0:56:e3:5d:50:21",
        None,
        _p(80, 443, 554),
        "Camera entrance",
        "Security",
        "Main entrance",
    ),
    DemoDevice(
        "192.168.10.22",
        "3c:ef:8c:6e:50:22",
        None,
        _p(80, 554),
        "Camera parking",
        "Security",
        "Parking",
        "Factory reset after a power cut",
        ports_later=_p(23, 80, 554),
    ),
    DemoDevice(
        "192.168.10.23",
        "3c:ef:8c:6e:50:23",
        None,
        _p(80, 554),
        "Camera back door",
        "Security",
        "Back door",
    ),
    DemoDevice(
        "192.168.10.30",
        "c0:56:e3:5d:60:30",
        "nvr.office.lan",
        _p(80, 443, 554),
        "Video recorder (NVR)",
        "Security",
        "Server cabinet",
        "8 channels, 30 days",
    ),
    DemoDevice(
        "192.168.10.40",
        "00:80:77:4e:70:40",
        "print-reception.office.lan",
        _p(80, 443, 9100),
        "Printer reception",
        "Reception",
        "Reception desk",
    ),
    DemoDevice(
        "192.168.10.41",
        "00:17:c8:4e:70:41",
        "print-office.office.lan",
        _p(21, 80, 9100),
        "Printer office",
        "Office",
        "Open office",
        "Scan-to-folder over FTP",
    ),
    DemoDevice(
        "192.168.10.50",
        "00:11:32:9a:80:50",
        "nas.office.lan",
        _p(22, 80, 443, 445),
        "File server (NAS)",
        "IT",
        "Server cabinet",
        "Nightly backup to USB disk",
    ),
    DemoDevice(
        "192.168.10.60",
        "18:66:da:2f:90:60",
        "reception-pc.office.lan",
        _p(139, 445, 3389),
        "Reception PC",
        "Reception",
        "Reception desk",
        "RDP enabled for remote support",
    ),
    DemoDevice(
        "192.168.10.61",
        "10:c5:95:2f:90:61",
        "accounting-lt.office.lan",
        _p(445),
        "Accounting laptop",
        "Accounting",
        "Office 3",
        gone=True,
    ),
    DemoDevice(
        "192.168.10.62",
        "f0:18:98:2f:90:62",
        "macbook-manager.office.lan",
        _p(),
        "Manager MacBook",
        "Management",
        "Office 1",
        new_ip="192.168.10.65",
    ),
    DemoDevice(
        "192.168.10.70",
        "80:5e:c0:3a:a0:70",
        None,
        _p(80, 443),
        "IP phone reception",
        "Reception",
        "Reception desk",
    ),
    DemoDevice(
        "192.168.10.80",
        "da:a1:19:5e:b0:80",
        None,
        _p(),
        "Staff phone",
        "Staff",
        "",
        "Private Wi-Fi address",
    ),
    DemoDevice(
        "192.168.10.81",
        "6e:2b:44:91:b0:81",
        None,
        _p(),
        "Staff phone 2",
        "Staff",
        "",
        "Private Wi-Fi address",
        gone=True,
    ),
    DemoDevice("192.168.10.90", "8c:79:f5:12:c0:90", None, _p(8080), known=False, ports_later=_p()),
    DemoDevice(
        "192.168.10.99",
        "dc:a6:32:7e:d0:99",
        "raspberrypi.office.lan",
        _p(22, 5900),
        known=False,
        only_later=True,
    ),
)


@dataclass
class DemoScanner:
    """Returns the office as it looks in scan 1, then in scan 2 (and stays there)."""

    devices: tuple[DemoDevice, ...] = OFFICE
    round: int = field(default=0)

    def observe(self, device: DemoDevice, later: bool) -> Observation | None:
        if (later and device.gone) or (not later and device.only_later):
            return None
        ip = device.new_ip if later and device.new_ip else device.ip
        ports = device.ports_later if later and device.ports_later is not None else device.ports
        return Observation(
            ip=ip, mac=device.mac, hostname=device.hostname, open_ports=ports, answered_ping=True
        )

    async def scan(self, scope: Scope) -> list[Observation]:
        later = self.round > 0
        self.round += 1
        observed = [self.observe(d, later) for d in self.devices]
        return [o for o in observed if o is not None and scope.contains(o.ip)]


async def seed(repo: Repository, oui: OuiDatabase, scanner: DemoScanner, now: datetime) -> None:
    """Two scans a day apart; the administrator fills in the details after the first one."""
    first_at = now - timedelta(days=1, hours=2)
    await record_scan(repo, scanner, DEMO_SCOPE, oui, source="demo", clock=lambda: first_at)

    by_mac = {d.mac: d for d in OFFICE}
    for device in await repo.devices():
        sample = by_mac.get(device.mac or "")
        if sample and sample.known:
            await repo.update_details(
                device.id,
                name=sample.name,
                owner=sample.owner,
                location=sample.location,
                notes=sample.notes,
                known=True,
            )
