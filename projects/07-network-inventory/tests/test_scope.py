import ipaddress

import pytest

from app.main import main
from app.scope import ScopeError, parse_network, parse_scope


@pytest.mark.parametrize(
    "cidr", ["192.168.1.0/24", "10.20.0.0/22", "172.16.5.0/24", "172.31.255.0/24", "127.0.0.1/32"]
)
def test_private_and_loopback_ranges_are_allowed(cidr: str) -> None:
    assert parse_network(cidr) == ipaddress.ip_network(cidr)


def test_an_address_with_its_mask_means_its_network() -> None:
    # As people copy it from ipconfig: "IPv4 192.168.1.14, mask /24".
    assert str(parse_network("192.168.1.14/24")) == "192.168.1.0/24"
    assert str(parse_network("192.168.1.1")) == "192.168.1.1/32"


@pytest.mark.parametrize(
    "cidr",
    [
        "8.8.8.0/24",  # public
        "100.64.0.0/24",  # carrier-grade NAT: other customers of the ISP
        "172.32.0.0/24",  # just outside 172.16.0.0/12
        "192.0.2.0/24",  # documentation range, is_private in Python but not RFC 1918
    ],
)
def test_non_rfc1918_ranges_are_refused(cidr: str) -> None:
    with pytest.raises(ScopeError, match="not a private"):
        parse_network(cidr)


def test_public_ranges_need_an_explicit_switch() -> None:
    assert str(parse_network("203.0.113.0/28", allow_public=True)) == "203.0.113.0/28"


def test_subnet_size_is_capped() -> None:
    assert parse_network("10.0.0.0/22").num_addresses == 1024
    with pytest.raises(ScopeError, match="limit is /22"):
        parse_network("10.0.0.0/21")
    with pytest.raises(ScopeError, match="limit is /24"):
        parse_network("192.168.0.0/23", subnet_limit=24)


@pytest.mark.parametrize("text", ["", " , ", None])
def test_the_target_must_be_explicit(text: str | None) -> None:
    with pytest.raises(ScopeError, match="SCAN_CIDRS"):
        parse_scope(text or "")


@pytest.mark.parametrize("text", ["fd00::/64", "192.168.1.0/33", "office", "-n 1 8.8.8.8"])
def test_malformed_and_ipv6_targets_are_refused(text: str) -> None:
    with pytest.raises(ScopeError):
        parse_scope(text)


def test_hosts_skip_network_and_broadcast_and_duplicates() -> None:
    scope = parse_scope("192.168.1.0/30, 192.168.1.1/32, 192.168.1.0/30")
    assert list(scope.hosts()) == ["192.168.1.1", "192.168.1.2"]
    assert scope.size == 2
    assert str(scope) == "192.168.1.0/30, 192.168.1.1/32"
    assert scope.contains("192.168.1.3")
    assert not scope.contains("192.168.2.1")
    assert not scope.contains("not an ip")


def test_cli_refuses_a_public_target_before_scanning() -> None:
    with pytest.raises(SystemExit, match=r"Refusing to scan: 8.8.8.8/32 is not a private"):
        main(["scan", "--cidr", "8.8.8.8/32"])
