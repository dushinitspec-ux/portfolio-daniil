"""Parsers for the output of `ping`, `arp -a` and `ip neigh`, in any language.

The commands print in the system language and, on Windows, in the console code page (cp866
on a Russian system). The output is decoded as ASCII with replacement characters, so the
words become unreadable, but everything that matters is ASCII in every language: "TTL=",
IP addresses and MAC addresses. The parsers only look at those.
"""

import ipaddress
import re
import sys

from app.oui import normalize_mac

_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
# Windows "8c-86-dd-b6-0d-d8", Linux "8c:86:dd:b6:0d:d8", macOS "8c:86:dd:b6:d:d8".
_MAC = re.compile(r"(?<![0-9a-f:-])([0-9a-f]{1,2}(?:[:-][0-9a-f]{1,2}){5})(?![0-9a-f:-])", re.I)


def decode(output: bytes) -> str:
    """Console bytes to text. Only ASCII parts are used, so the code page does not matter."""
    return output.decode("ascii", errors="replace")


def ping_command(host: str, timeout_s: float, platform: str = sys.platform) -> list[str]:
    if platform == "win32":
        return ["ping", "-n", "1", "-w", str(int(timeout_s * 1000)), host]
    if platform == "darwin":
        return ["ping", "-c", "1", "-t", str(max(1, round(timeout_s))), host]
    return ["ping", "-c", "1", "-W", str(max(1, round(timeout_s))), host]


def parse_ping(returncode: int, output: str) -> bool:
    """True if the host replied.

    Windows ping exits with 0 when the local machine or a router answers "Destination host
    unreachable" - and in a sweep of a subnet that is the answer for every empty address. So
    a reply line with a TTL is required as well; "TTL=" is printed in every language.
    """
    return returncode == 0 and "ttl=" in output.lower()


def neighbour_command(platform: str = sys.platform) -> list[str]:
    if platform == "win32":
        return ["arp", "-a"]
    if platform == "darwin":
        return ["arp", "-an"]
    return ["ip", "-4", "neigh", "show"]


def parse_neighbours(output: str) -> dict[str, str]:
    """IP -> MAC from `arp -a` (Windows, any language; macOS) or `ip neigh` (Linux).

    One parser for all formats: a line counts if it has an IPv4 address followed by a MAC.
    Interface headers ("Interface: 192.168.1.14 --- 0x7"), unresolved entries (Linux
    FAILED/INCOMPLETE, macOS "(incomplete)"), multicast and broadcast entries are skipped.
    """
    neighbours: dict[str, str] = {}
    for line in output.splitlines():
        ip_match = _IPV4.search(line)
        if not ip_match:
            continue
        mac_match = _MAC.search(line, ip_match.end())
        if not mac_match:
            continue
        mac = normalize_mac(mac_match.group(1))
        try:
            address = ipaddress.IPv4Address(ip_match.group(1))
        except ValueError:
            continue
        if mac is None or address.is_multicast or str(address) == "255.255.255.255":
            continue
        neighbours[str(address)] = mac
    return neighbours
