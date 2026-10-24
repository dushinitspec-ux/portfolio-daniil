import pytest

from app.parsing import decode, neighbour_command, parse_neighbours, parse_ping, ping_command
from tests.conftest import fixture_bytes

# --- ping ---------------------------------------------------------------------------------
# Real output from Windows 11 with a Russian locale (console code page cp866), captured on
# the development machine for 127.0.0.1 and the default gateway. The scanner decodes the
# raw bytes as ASCII, so the tests do exactly the same.
RU_LOCALHOST = decode(fixture_bytes("ping_ru_windows_localhost.txt"))
RU_GATEWAY = decode(fixture_bytes("ping_ru_windows_gateway.txt"))
# Real timeout output from the same machine (captured for project 03, address 192.0.2.1).
RU_TIMEOUT = decode(
    "Обмен пакетами с 192.0.2.1 по с 32 байтами данных:\r\n"
    "Превышен интервал ожидания для запроса.\r\n".encode("cp866")
)
# Format samples for other systems.
EN_WINDOWS_REPLY = "Reply from 192.168.1.1: bytes=32 time=1ms TTL=64\r\n"
EN_WINDOWS_UNREACHABLE = "Reply from 192.168.1.14: Destination host unreachable.\r\n"
LINUX_REPLY = "64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=0.61 ms\n"


def test_real_russian_output_is_unreadable_but_parsable() -> None:
    # The words are gone after decoding, only ASCII survives - which is the point.
    assert "Ответ" not in RU_LOCALHOST
    assert "TTL=128" in RU_LOCALHOST
    assert "TTL=64" in RU_GATEWAY


@pytest.mark.parametrize(
    ("returncode", "output", "alive"),
    [
        (0, RU_LOCALHOST, True),
        (0, RU_GATEWAY, True),
        (1, RU_TIMEOUT, False),
        (0, EN_WINDOWS_REPLY, True),
        (0, LINUX_REPLY, True),
        # Windows exits 0 for "Destination host unreachable": in a sweep that is the answer
        # for every empty address, so it must not count as a device.
        (0, EN_WINDOWS_UNREACHABLE, False),
        (1, "", False),
        (-1, "", False),
    ],
)
def test_parse_ping(returncode: int, output: str, alive: bool) -> None:
    assert parse_ping(returncode, output) is alive


def test_ping_command_per_platform() -> None:
    assert ping_command("10.0.0.1", 1.0, "win32") == ["ping", "-n", "1", "-w", "1000", "10.0.0.1"]
    assert ping_command("10.0.0.1", 1.0, "linux") == ["ping", "-c", "1", "-W", "1", "10.0.0.1"]
    assert ping_command("10.0.0.1", 0.3, "linux")[-2] == "1"  # never 0 = "wait forever"
    assert ping_command("10.0.0.1", 2.0, "darwin") == ["ping", "-c", "1", "-t", "2", "10.0.0.1"]


# --- neighbour table ----------------------------------------------------------------------


def test_real_russian_arp_table() -> None:
    # Real `arp -a` from the same machine. Only the last three bytes of each MAC were
    # replaced before committing; the vendor part and everything else is as captured.
    table = parse_neighbours(decode(fixture_bytes("arp_ru_windows.txt")))
    assert table == {
        "192.168.1.1": "8c:86:dd:00:00:01",
        "192.168.1.3": "f0:b0:40:00:00:03",
        "192.168.1.11": "9a:60:0f:00:00:0b",
        "192.168.1.23": "ac:f2:3c:00:00:17",
    }  # no interface header, no broadcast, no multicast entries


def test_english_windows_arp_table() -> None:
    output = (
        "\r\nInterface: 10.0.0.5 --- 0xb\r\n"
        "  Internet Address      Physical Address      Type\r\n"
        "  10.0.0.1              48-8f-5a-3c-10-01     dynamic\r\n"
        "  10.0.0.20             00-00-00-00-00-00     invalid\r\n"
        "  10.0.0.255            ff-ff-ff-ff-ff-ff     static\r\n"
        "  224.0.0.251           01-00-5e-00-00-fb     static\r\n"
    )
    assert parse_neighbours(output) == {"10.0.0.1": "48:8f:5a:3c:10:01"}


def test_linux_ip_neigh() -> None:
    output = (
        "192.168.1.1 dev eth0 lladdr 8c:86:dd:00:00:01 REACHABLE\n"
        "192.168.1.23 dev eth0 lladdr ac:f2:3c:00:00:17 STALE\n"
        "192.168.1.50 dev eth0 FAILED\n"
        "192.168.1.51 dev eth0 INCOMPLETE\n"
        "fe80::1 dev eth0 lladdr 8c:86:dd:00:00:01 router STALE\n"
    )
    assert parse_neighbours(output) == {
        "192.168.1.1": "8c:86:dd:00:00:01",
        "192.168.1.23": "ac:f2:3c:00:00:17",
    }


def test_macos_arp_drops_leading_zeros() -> None:
    output = (
        "? (192.168.1.1) at 8c:86:dd:0:0:1 on en0 ifscope [ethernet]\n"
        "? (192.168.1.7) at (incomplete) on en0 ifscope [ethernet]\n"
    )
    assert parse_neighbours(output) == {"192.168.1.1": "8c:86:dd:00:00:01"}


def test_neighbour_command_per_platform() -> None:
    assert neighbour_command("win32") == ["arp", "-a"]
    assert neighbour_command("linux") == ["ip", "-4", "neigh", "show"]
    assert neighbour_command("darwin") == ["arp", "-an"]
