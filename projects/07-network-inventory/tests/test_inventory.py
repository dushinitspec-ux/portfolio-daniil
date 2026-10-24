import asyncio
import shutil
import time
from collections.abc import AsyncIterator

import pytest

from app.changes import ChangeKind
from app.db import Repository
from app.discovery import NetworkScanner, Observation, ReverseDns, clean_hostname, ping
from app.inventory import Inventory, ScanInProgressError, record_scan
from app.oui import MacInfo, OuiDatabase
from app.scope import parse_scope
from tests.conftest import Clock, RecordingNotifier, ScriptedScanner

SCOPE = parse_scope("192.168.10.0/24")
ROUTER = "48:8f:5a:00:00:01"
CAMERA = "3c:ef:8c:00:00:22"
LAPTOP = "18:66:da:00:00:60"
PI = "dc:a6:32:00:00:99"

SCAN_1 = [
    Observation("192.168.10.1", ROUTER, "gw.office.lan", frozenset({22, 80})),
    Observation("192.168.10.22", CAMERA, None, frozenset({80, 554})),
    Observation("192.168.10.60", LAPTOP, "pc.office.lan", frozenset({445})),
]
SCAN_2 = [
    Observation("192.168.10.1", ROUTER, "gw.office.lan", frozenset({22, 80})),
    Observation("192.168.10.22", CAMERA, None, frozenset({23, 80, 554})),
    Observation("192.168.10.99", PI, None, frozenset({22, 5900})),
]


def make_inventory(
    repo: Repository, oui: OuiDatabase, *rounds: list[Observation]
) -> tuple[Inventory, RecordingNotifier]:
    notifier = RecordingNotifier()
    inventory = Inventory(
        repo, ScriptedScanner(*rounds), SCOPE, oui, notifier, tz_name="UTC", clock=Clock()
    )
    return inventory, notifier


async def test_two_scans_build_the_register_and_the_diff(
    repo: Repository, oui: OuiDatabase
) -> None:
    inventory, _ = make_inventory(repo, oui, SCAN_1, SCAN_2)
    first = await inventory.scan()
    second = await inventory.scan()

    assert first.first_scan and len(first.changes) == 3
    assert {(c.kind, c.key) for c in second.changes} == {
        (ChangeKind.PORT_OPENED, f"mac:{CAMERA}"),
        (ChangeKind.GONE, f"mac:{LAPTOP}"),
        (ChangeKind.NEW, f"mac:{PI}"),
    }
    devices = {d.mac: d for d in await repo.devices()}
    assert devices[ROUTER].vendor == "MikroTik"
    assert devices[ROUTER].first_seen < devices[ROUTER].last_seen
    assert devices[LAPTOP].last_scan_id == first.scan.id  # kept in the register, not deleted
    assert devices[CAMERA].open_ports == {23, 80, 554}
    stored = await repo.changes(second.scan.id)
    assert len(stored) == 3


async def test_ip_history_follows_the_mac(repo: Repository, oui: OuiDatabase) -> None:
    moved = [Observation("192.168.10.65", LAPTOP)]
    inventory, _ = make_inventory(repo, oui, SCAN_1, moved)
    await inventory.scan()
    report = await inventory.scan()
    laptop = report.devices[f"mac:{LAPTOP}"]
    assert [r.ip for r in await repo.ip_history(laptop.id)] == ["192.168.10.65", "192.168.10.60"]
    assert any(c.kind is ChangeKind.IP_CHANGED for c in report.changes)


async def test_first_scan_sends_one_summary_not_one_alert_per_device(
    repo: Repository, oui: OuiDatabase
) -> None:
    inventory, notifier = make_inventory(repo, oui, SCAN_1)
    await inventory.scan()
    [message] = notifier.messages
    assert "First scan: 3 devices" in message
    assert "192.168.10.22" not in message


async def test_alert_for_new_device_and_new_risky_port(repo: Repository, oui: OuiDatabase) -> None:
    inventory, notifier = make_inventory(repo, oui, SCAN_1, SCAN_2)
    await inventory.scan()
    await inventory.scan()
    message = notifier.messages[-1]
    assert "New device (1):" in message
    assert "192.168.10.99" in message and "Raspberry Pi" in message
    assert "VNC remote control is open (high)" in message
    assert "New risky port:" in message and "23 Telnet" in message
    assert LAPTOP not in message  # a device that left is shown on the page, not alerted


async def test_no_alert_when_nothing_risky_changed(repo: Repository, oui: OuiDatabase) -> None:
    quieter = [
        Observation("192.168.10.1", ROUTER, "gw.office.lan", frozenset({22})),  # 80 closed
        Observation("192.168.10.22", CAMERA, None, frozenset({80, 443, 554})),  # HTTPS opened
    ]
    inventory, notifier = make_inventory(repo, oui, SCAN_1, quieter)
    await inventory.scan()
    report = await inventory.scan()
    assert report.changes  # things did change...
    assert len(notifier.messages) == 1  # ...but only the first-scan summary was sent


async def test_telegram_failure_does_not_lose_the_scan(repo: Repository, oui: OuiDatabase) -> None:
    class BrokenNotifier:
        async def send(self, text: str) -> None:
            raise ConnectionError("api.telegram.org unreachable")

    inventory = Inventory(repo, ScriptedScanner(SCAN_1), SCOPE, oui, BrokenNotifier())
    report = await inventory.scan()
    assert (await repo.latest_scan()) == report.scan


async def test_scans_do_not_overlap(repo: Repository, oui: OuiDatabase) -> None:
    release = asyncio.Event()

    class SlowScanner:
        async def scan(self, scope: object) -> list[Observation]:
            await release.wait()
            return SCAN_1

    inventory = Inventory(repo, SlowScanner(), SCOPE, oui, RecordingNotifier())
    first = asyncio.create_task(inventory.scan())
    await asyncio.sleep(0)
    assert inventory.scanning
    with pytest.raises(ScanInProgressError):
        await inventory.scan()
    release.set()
    await first
    assert not inventory.scanning


async def test_owner_and_notes_survive_rescans(repo: Repository, oui: OuiDatabase) -> None:
    inventory, _ = make_inventory(repo, oui, SCAN_1, SCAN_2)
    await inventory.scan()
    router = next(d for d in await repo.devices() if d.mac == ROUTER)
    await repo.update_details(
        router.id, name="Main router", owner="IT", location="Rack", notes="", known=True
    )
    await inventory.scan()
    router = await repo.device(router.id)
    assert router is not None
    assert (router.name, router.owner, router.known) == ("Main router", "IT", True)


async def test_sighting_without_mac_keeps_mac_and_vendor(
    repo: Repository, oui: OuiDatabase
) -> None:
    no_arp = [Observation("192.168.10.1", None, None, frozenset({22, 80}))]
    inventory, _ = make_inventory(repo, oui, SCAN_1, no_arp)
    await inventory.scan()
    report = await inventory.scan()
    router = report.devices[f"mac:{ROUTER}"]
    assert (router.mac, router.vendor, router.hostname) == (ROUTER, "MikroTik", "gw.office.lan")
    assert len(report.devices) == 3  # no duplicate "ip:192.168.10.1" entry


async def test_a_failed_scan_leaves_no_trace(repo: Repository, oui: OuiDatabase) -> None:
    class FailingOui(OuiDatabase):
        def lookup(self, mac: str) -> MacInfo:
            if mac == LAPTOP:  # the third device: two are already written
                raise RuntimeError("disk error")
            return super().lookup(mac)

    with pytest.raises(RuntimeError):
        await record_scan(repo, ScriptedScanner(SCAN_1), SCOPE, FailingOui({}), source="test")
    assert await repo.latest_scan() is None
    assert await repo.devices() == []


# --- discovery with fake ping/ARP and a real local TCP server ------------------------------


@pytest.fixture
async def open_port() -> AsyncIterator[int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    yield server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()


async def test_network_scanner_combines_ping_arp_and_tcp(open_port: int) -> None:
    async def fake_ping(host: str, timeout_s: float) -> bool:
        return host == "127.0.0.1"

    async def fake_neighbours() -> dict[str, str]:
        # 127.0.0.2 dropped the ping but answered ARP; 192.168.1.1 is outside the scope.
        return {"127.0.0.2": "aa:00:00:00:00:02", "192.168.1.1": "8c:86:dd:00:00:01"}

    scanner = NetworkScanner(
        [open_port],
        tcp_timeout_s=0.5,
        reverse_dns=False,
        pinger=fake_ping,
        neighbours=fake_neighbours,
    )
    found = await scanner.scan(parse_scope("127.0.0.0/29"))
    assert [(o.ip, o.mac, o.answered_ping) for o in found] == [
        ("127.0.0.1", None, True),
        ("127.0.0.2", "aa:00:00:00:00:02", False),
    ]
    assert found[0].open_ports == {open_port}
    assert found[1].open_ports == frozenset()


async def test_slow_reverse_lookups_do_not_starve_the_next_ones() -> None:
    # Like Windows: an address without a name blocks its thread for a while, then fails.
    def resolve(ip: str) -> str:
        if ip == "10.0.0.1":
            return "router.lan"
        time.sleep(0.6)
        raise OSError(11001, "no name")

    dns = ReverseDns(workers=4, timeout_s=0.3, resolve=resolve)
    ips = [f"10.0.0.{i}" for i in range(2, 10)] + ["10.0.0.1"]  # the named one comes last
    names = await dns.lookup_all(ips)
    assert names[-1] == "router.lan"
    assert names[:-1] == [None] * 8


def test_reverse_dns_answers_are_cleaned() -> None:
    assert clean_hostname("EX530V.", "192.168.1.1") == "EX530V"
    assert clean_hostname("192.168.1.1", "192.168.1.1") is None
    assert clean_hostname("bad\nname", "192.168.1.1") is None
    assert clean_hostname("x" * 300, "192.168.1.1") is None


@pytest.mark.skipif(shutil.which("ping") is None, reason="no ping command")
async def test_real_ping_to_localhost() -> None:
    assert await ping("127.0.0.1", 1.0)
