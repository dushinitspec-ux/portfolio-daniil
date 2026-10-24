"""Pure logic, no I/O: which register entry an observation belongs to, and what changed.

Identity. A device is identified by its MAC address, because IP addresses change with DHCP.
When the MAC is unknown (the scanning machine itself, or a host behind a router, where ARP
cannot see it) the IP address is the identity until a MAC shows up.
"""

from collections.abc import Callable, Iterable, Mapping, Set
from dataclasses import dataclass, field
from enum import StrEnum

from app.discovery import Observation, sort_key


def mac_key(mac: str) -> str:
    return f"mac:{mac}"


def ip_key(ip: str) -> str:
    return f"ip:{ip}"


@dataclass(frozen=True)
class Known:
    """What the register remembers about a device: its last IP and MAC."""

    ip: str
    mac: str | None


@dataclass(frozen=True)
class Sighting:
    """An observation matched to a register key."""

    key: str
    ip: str
    mac: str | None
    hostname: str | None
    ports: frozenset[int]
    other_ips: tuple[str, ...] = ()


@dataclass(frozen=True)
class Resolution:
    sightings: dict[str, Sighting]
    # Register entries that were keyed by IP and now have a MAC: old key -> new key.
    rekeys: dict[str, str] = field(default_factory=dict)


def resolve(observations: Iterable[Observation], known: Mapping[str, Known]) -> Resolution:
    observed = sorted(observations, key=lambda o: (o.mac is None, sort_key(o.ip)))
    sightings: dict[str, Sighting] = {}
    rekeys: dict[str, str] = {}

    for obs in observed:
        if obs.mac:
            key = mac_key(obs.mac)
            if key in sightings:
                # One MAC with two IPs (a router with a second address, a host with an
                # alias): one device, all its ports, the other IP kept for the history.
                first = sightings[key]
                sightings[key] = Sighting(
                    key,
                    first.ip,
                    first.mac,
                    first.hostname or obs.hostname,
                    first.ports | obs.open_ports,
                    (*first.other_ips, obs.ip),
                )
                continue
            old = ip_key(obs.ip)
            if key not in known and old in known and known[old].mac is None:
                rekeys[old] = key
        else:
            # No MAC this time (its ARP entry expired, or it is the scanning host). If a
            # device with a MAC had this IP last time and is not seen elsewhere, it is that one.
            same_ip = [
                k
                for k, device in known.items()
                if device.mac and device.ip == obs.ip and k not in sightings
            ]
            key = same_ip[0] if len(same_ip) == 1 else ip_key(obs.ip)
            if key in sightings:
                continue
        sightings[key] = Sighting(key, obs.ip, obs.mac, obs.hostname, frozenset(obs.open_ports))
    return Resolution(sightings, rekeys)


class ChangeKind(StrEnum):
    NEW = "new"  # first time in the register
    RETURNED = "returned"  # in the register, missing from the previous scan, back now
    GONE = "gone"  # in the previous scan, not in this one
    PORT_OPENED = "port_opened"
    PORT_CLOSED = "port_closed"
    IP_CHANGED = "ip_changed"


@dataclass(frozen=True)
class Snapshot:
    ip: str
    ports: frozenset[int]


@dataclass(frozen=True)
class Change:
    kind: ChangeKind
    key: str
    ports: tuple[int, ...] = ()
    old_ip: str | None = None
    new_ip: str | None = None


def diff(
    *,
    last_known: Mapping[str, Snapshot],
    previous_scan: Set[str],
    current: Mapping[str, Snapshot],
    in_scope: Callable[[str], bool],
) -> list[Change]:
    """Changes between the register and this scan.

    `last_known` is the last sighting of every device ever seen, `previous_scan` the keys
    present in the previous scan. Ports are compared with the device's last sighting, even
    if that was weeks ago. A device only counts as gone if its last IP is inside the
    networks this scan covered: scanning a different subnet does not make it disappear.
    """
    changes: list[Change] = []
    for key, now in current.items():
        before = last_known.get(key)
        if before is None:
            changes.append(Change(ChangeKind.NEW, key, tuple(sorted(now.ports)), new_ip=now.ip))
            continue
        if key not in previous_scan:
            changes.append(Change(ChangeKind.RETURNED, key, new_ip=now.ip))
        if before.ip != now.ip:
            changes.append(Change(ChangeKind.IP_CHANGED, key, old_ip=before.ip, new_ip=now.ip))
        if opened := now.ports - before.ports:
            changes.append(Change(ChangeKind.PORT_OPENED, key, tuple(sorted(opened))))
        if closed := before.ports - now.ports:
            changes.append(Change(ChangeKind.PORT_CLOSED, key, tuple(sorted(closed))))

    for key in previous_scan:
        before = last_known.get(key)
        if key not in current and before is not None and in_scope(before.ip):
            changes.append(Change(ChangeKind.GONE, key, old_ip=before.ip))
    return changes
