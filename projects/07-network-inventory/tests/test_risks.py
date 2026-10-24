import pytest

from app.risks import Severity, assess, describe_ports, highest, risky_ports


@pytest.mark.parametrize(
    ("port", "code", "severity"),
    [
        (23, "telnet", Severity.HIGH),
        (21, "ftp", Severity.MEDIUM),
        (3389, "rdp", Severity.HIGH),
        (445, "smb", Severity.MEDIUM),
        (139, "netbios", Severity.LOW),
        (5900, "vnc", Severity.HIGH),
        (554, "rtsp", Severity.MEDIUM),
        (8291, "winbox", Severity.MEDIUM),
        (9100, "raw-print", Severity.LOW),
    ],
)
def test_port_rules(port: int, code: str, severity: Severity) -> None:
    [risk] = assess([port])
    assert (risk.code, risk.severity, risk.ports) == (code, severity, (port,))
    assert risk.why and risk.fix  # every rule explains itself


def test_http_without_https() -> None:
    assert [r.code for r in assess([80])] == ["http-only"]
    assert [r.ports for r in assess([8080])] == [(8080,)]
    assert assess([80, 443]) == []
    assert assess([8080, 8443]) == []


def test_nothing_risky() -> None:
    assert assess([]) == []
    assert assess([22, 443]) == []  # SSH and HTTPS alone are what we want to see


def test_most_severe_first() -> None:
    risks = assess([80, 554, 23, 9100])  # a typical camera after a factory reset
    # Most severe first; the same severity in port order.
    assert [r.code for r in risks] == ["telnet", "http-only", "rtsp", "raw-print"]
    assert highest(risks) is Severity.HIGH
    assert highest([]) is None


def test_risky_ports_for_alerts() -> None:
    # HTTP is only risky in combination (no HTTPS), so a new port 80 alone does not alert.
    assert risky_ports([22, 80, 443, 23, 3389]) == {23, 3389}


def test_describe_ports() -> None:
    assert describe_ports([443, 22, 12345]) == "22 SSH, 443 HTTPS, 12345"
    assert describe_ports([]) == "none"
