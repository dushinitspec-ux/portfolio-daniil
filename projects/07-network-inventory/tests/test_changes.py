from app.changes import Change, ChangeKind, Known, Snapshot, diff, ip_key, mac_key, resolve
from app.discovery import Observation

A = "aa:00:00:00:00:01"
B = "aa:00:00:00:00:02"


def snap(ip: str, *ports: int) -> Snapshot:
    return Snapshot(ip, frozenset(ports))


def everywhere(_: str) -> bool:
    return True


def kinds(changes: list[Change]) -> set[tuple[ChangeKind, str]]:
    return {(c.kind, c.key) for c in changes}


def test_first_scan_everything_is_new() -> None:
    changes = diff(
        last_known={},
        previous_scan=set(),
        current={"mac:a": snap("10.0.0.1", 22), "mac:b": snap("10.0.0.2")},
        in_scope=everywhere,
    )
    assert kinds(changes) == {(ChangeKind.NEW, "mac:a"), (ChangeKind.NEW, "mac:b")}
    assert next(c for c in changes if c.key == "mac:a").ports == (22,)


def test_new_gone_returned_ip_and_ports() -> None:
    last_known = {
        "mac:stays": snap("10.0.0.1", 80, 554),
        "mac:leaves": snap("10.0.0.2"),
        "mac:was-away": snap("10.0.0.3", 22),
        "mac:moves": snap("10.0.0.4"),
    }
    changes = diff(
        last_known=last_known,
        previous_scan={"mac:stays", "mac:leaves", "mac:moves"},
        current={
            "mac:stays": snap("10.0.0.1", 23, 80),  # Telnet opened, RTSP closed
            "mac:was-away": snap("10.0.0.3", 22),
            "mac:moves": snap("10.0.0.40"),
            "mac:fresh": snap("10.0.0.9", 5900),
        },
        in_scope=everywhere,
    )
    by_kind = {(c.kind, c.key): c for c in changes}
    assert by_kind[(ChangeKind.PORT_OPENED, "mac:stays")].ports == (23,)
    assert by_kind[(ChangeKind.PORT_CLOSED, "mac:stays")].ports == (554,)
    assert (ChangeKind.GONE, "mac:leaves") in by_kind
    assert (ChangeKind.RETURNED, "mac:was-away") in by_kind
    moved = by_kind[(ChangeKind.IP_CHANGED, "mac:moves")]
    assert (moved.old_ip, moved.new_ip) == ("10.0.0.4", "10.0.0.40")
    assert by_kind[(ChangeKind.NEW, "mac:fresh")].ports == (5900,)
    assert len(changes) == 6  # nothing for the unchanged parts


def test_ports_are_compared_with_the_last_sighting_even_after_an_absence() -> None:
    changes = diff(
        last_known={"mac:a": snap("10.0.0.1", 80)},
        previous_scan=set(),  # missing from the previous scan
        current={"mac:a": snap("10.0.0.1", 80, 3389)},
        in_scope=everywhere,
    )
    assert kinds(changes) == {(ChangeKind.RETURNED, "mac:a"), (ChangeKind.PORT_OPENED, "mac:a")}


def test_device_outside_this_scan_is_not_gone() -> None:
    changes = diff(
        last_known={"mac:a": snap("10.0.1.5")},
        previous_scan={"mac:a"},
        current={},
        in_scope=lambda ip: ip.startswith("10.0.0."),  # this scan covered another subnet
    )
    assert changes == []


def test_device_is_identified_by_mac_when_its_ip_changes() -> None:
    known = {mac_key(A): Known("10.0.0.5", A)}
    result = resolve([Observation("10.0.0.77", A)], known)
    assert list(result.sightings) == [mac_key(A)]
    assert result.rekeys == {}


def test_ip_only_device_is_rekeyed_when_its_mac_appears() -> None:
    known = {ip_key("10.0.0.5"): Known("10.0.0.5", None)}
    result = resolve([Observation("10.0.0.5", A)], known)
    assert result.rekeys == {ip_key("10.0.0.5"): mac_key(A)}
    assert list(result.sightings) == [mac_key(A)]


def test_sighting_without_mac_keeps_the_known_device() -> None:
    # The ARP entry expired, so this time there is no MAC for 10.0.0.5.
    known = {mac_key(A): Known("10.0.0.5", A)}
    result = resolve([Observation("10.0.0.5", None, open_ports=frozenset({80}))], known)
    assert list(result.sightings) == [mac_key(A)]
    assert result.sightings[mac_key(A)].mac is None


def test_unknown_host_without_mac_is_keyed_by_ip() -> None:
    result = resolve([Observation("127.0.0.1")], {})
    assert list(result.sightings) == [ip_key("127.0.0.1")]


def test_one_mac_with_two_ips_is_one_device() -> None:
    result = resolve(
        [
            Observation("10.0.0.20", A, open_ports=frozenset({443})),
            Observation("10.0.0.3", A, "router.lan", frozenset({80})),
            Observation("10.0.0.9", B),
        ],
        {},
    )
    router = result.sightings[mac_key(A)]
    assert router.ip == "10.0.0.3"  # lowest address, compared as numbers, not strings
    assert router.other_ips == ("10.0.0.20",)
    assert router.ports == {80, 443}
    assert router.hostname == "router.lan"
    assert len(result.sightings) == 2
