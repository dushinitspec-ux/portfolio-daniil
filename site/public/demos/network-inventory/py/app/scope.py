"""Which addresses may be scanned. Every scan goes through `parse_scope` first.

The rules are deliberately strict, because a ping sweep and a port probe of a network you
do not own can be illegal and will at least trip someone's intrusion detection:

- the networks must be listed explicitly (there is no "scan whatever I am connected to");
- only private ranges (RFC 1918) and loopback, unless ALLOW_PUBLIC=1;
- no network larger than /22 (1022 hosts) by default;
- IPv4 only: a /64 IPv6 subnet cannot be swept, and neighbours are found by ARP anyway.
"""

import ipaddress
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

# RFC 1918. `ipaddress.is_private` is broader (it includes 100.64.0.0/10, the carrier-grade
# NAT range shared by other ISP customers, and documentation ranges), so it is not used.
PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
LOOPBACK = ipaddress.ip_network("127.0.0.0/8")


class ScopeError(ValueError):
    """The scan target is missing, malformed or not allowed."""


@dataclass(frozen=True)
class Scope:
    networks: tuple[ipaddress.IPv4Network, ...]

    def hosts(self) -> Iterator[str]:
        """Every address to probe, without network and broadcast addresses, no duplicates."""
        seen: set[ipaddress.IPv4Address] = set()
        for network in self.networks:
            for host in network.hosts():
                if host not in seen:
                    seen.add(host)
                    yield str(host)

    def contains(self, ip: str) -> bool:
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(address in network for network in self.networks)

    @property
    def size(self) -> int:
        return sum(1 for _ in self.hosts())

    def __str__(self) -> str:
        return ", ".join(str(n) for n in self.networks)


def is_allowed_range(network: ipaddress.IPv4Network) -> bool:
    return network.subnet_of(LOOPBACK) or any(network.subnet_of(p) for p in PRIVATE_NETWORKS)


def parse_network(
    text: str, *, allow_public: bool = False, subnet_limit: int = 22
) -> ipaddress.IPv4Network:
    text = text.strip()
    try:
        # strict=False accepts "192.168.1.14/24" (an address with its mask, as people copy
        # it from ipconfig) and turns it into 192.168.1.0/24.
        network = ipaddress.ip_network(text, strict=False)
    except ValueError:
        raise ScopeError(f"{text!r} is not a network, use a form like 192.168.1.0/24") from None
    if not isinstance(network, ipaddress.IPv4Network):
        raise ScopeError(f"{text}: only IPv4 networks can be scanned")
    if network.prefixlen < subnet_limit:
        raise ScopeError(
            f"{network} has {network.num_addresses - 2} hosts; the limit is /{subnet_limit}. "
            "Split it into smaller networks or raise SUBNET_LIMIT."
        )
    if not allow_public and not is_allowed_range(network):
        raise ScopeError(
            f"{network} is not a private (RFC 1918) range. Scan only networks you are "
            "allowed to; set ALLOW_PUBLIC=1 if you really own this range."
        )
    return network


def parse_scope(
    networks: str | Iterable[str], *, allow_public: bool = False, subnet_limit: int = 22
) -> Scope:
    items = networks.split(",") if isinstance(networks, str) else list(networks)
    items = [item.strip() for item in items if item.strip()]
    if not items:
        raise ScopeError(
            "No network to scan. Set SCAN_CIDRS, for example SCAN_CIDRS=192.168.1.0/24."
        )
    parsed = [
        parse_network(item, allow_public=allow_public, subnet_limit=subnet_limit) for item in items
    ]
    return Scope(tuple(dict.fromkeys(parsed)))
