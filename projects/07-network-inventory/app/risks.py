"""Risk rules: what an open TCP port tells you, and what to do about it.

Every rule is based only on what a TCP connect can observe: the port accepted a
connection. Nothing here logs in, sends a payload or checks a version, so the rules say
"this service is reachable from where the scanner runs", never "this device is vulnerable".
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Risk:
    code: str
    severity: Severity
    ports: tuple[int, ...]
    title: str
    why: str
    fix: str


SERVICE_NAMES = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    80: "HTTP",
    139: "NetBIOS",
    443: "HTTPS",
    445: "SMB",
    554: "RTSP",
    3389: "RDP",
    5900: "VNC",
    8080: "HTTP-alt",
    8291: "Winbox",
    8443: "HTTPS-alt",
    9100: "Raw print",
}

HTTP_PORTS = frozenset({80, 8080})
HTTPS_PORTS = frozenset({443, 8443})


@dataclass(frozen=True)
class PortRule:
    port: int
    code: str
    severity: Severity
    title: str
    why: str
    fix: str


PORT_RULES: tuple[PortRule, ...] = (
    PortRule(
        23,
        "telnet",
        Severity.HIGH,
        "Telnet is open",
        "Telnet sends the login and password as plain text, so anyone on the same network "
        "segment can read them. On cameras and old switches it is often left on by default.",
        "Turn Telnet off and manage the device over SSH or HTTPS.",
    ),
    PortRule(
        21,
        "ftp",
        Severity.MEDIUM,
        "FTP is open",
        "FTP sends passwords and files unencrypted. Printers use it for scan-to-folder and "
        "NAS boxes for old backups, and the account often has a default password.",
        "Turn FTP off, or use SFTP/FTPS and a separate account with a strong password.",
    ),
    PortRule(
        3389,
        "rdp",
        Severity.HIGH,
        "Remote Desktop (RDP) is reachable",
        "RDP is one of the most common ways ransomware gets in once an attacker is inside a "
        "network, by guessing passwords. Every device that can reach this port can try.",
        "Allow RDP only from an admin network or over a VPN, with Network Level "
        "Authentication and account lockout. Never forward it from the internet.",
    ),
    PortRule(
        445,
        "smb",
        Severity.MEDIUM,
        "File sharing (SMB) is reachable",
        "SMB is how worms such as WannaCry spread from computer to computer. It belongs on "
        "the office network, not on the guest Wi-Fi or the camera network.",
        "Check that this host should share files at all, that SMBv1 is off, and that guest "
        "and camera networks cannot reach it.",
    ),
    PortRule(
        139,
        "netbios",
        Severity.LOW,
        "NetBIOS session service is open",
        "An old Windows file-sharing protocol that also leaks the computer and user names.",
        "Disable NetBIOS over TCP/IP if nothing on the network needs it.",
    ),
    PortRule(
        5900,
        "vnc",
        Severity.HIGH,
        "VNC remote control is open",
        "VNC servers often have a short password or none at all, and many send the screen "
        "without encryption.",
        "Turn VNC off or tunnel it over SSH/VPN, and set a strong password.",
    ),
    PortRule(
        554,
        "rtsp",
        Severity.MEDIUM,
        "Camera video stream (RTSP) is reachable",
        "RTSP is the live video of an IP camera or recorder. Many cameras accept the default "
        "password, and some allow the stream without one.",
        "Change the default password, keep cameras on their own VLAN, and check the stream "
        "asks for a login.",
    ),
    PortRule(
        8291,
        "winbox",
        Severity.MEDIUM,
        "MikroTik Winbox management port is open",
        "Winbox gives full control of the router. Old RouterOS versions had serious Winbox "
        "vulnerabilities, so it should only be reachable by the people who manage it.",
        "Keep RouterOS updated and allow Winbox only from the admin network (IP > Services).",
    ),
    PortRule(
        9100,
        "raw-print",
        Severity.LOW,
        "Raw printing port is open",
        "Anyone on this network can send print jobs without a login. Printers also tend to "
        "run years-old firmware.",
        "Fine on the office network; make sure guests and cameras cannot reach the printer.",
    ),
)

HTTP_ONLY = PortRule(
    80,
    "http-only",
    Severity.MEDIUM,
    "Web interface without HTTPS",
    "The device answers on HTTP but not on HTTPS, so the admin password crosses the network "
    "in plain text when someone logs in.",
    "Enable HTTPS on the device and turn plain HTTP off. If it cannot do HTTPS, keep its "
    "management on a separate admin network.",
)

_RULES_BY_PORT = {rule.port: rule for rule in PORT_RULES}


def _risk(rule: PortRule, ports: tuple[int, ...]) -> Risk:
    return Risk(rule.code, rule.severity, ports, rule.title, rule.why, rule.fix)


def assess(open_ports: Iterable[int]) -> list[Risk]:
    """Risks for one device, most severe first."""
    ports = set(open_ports)
    risks = [_risk(_RULES_BY_PORT[p], (p,)) for p in sorted(ports) if p in _RULES_BY_PORT]
    http = tuple(sorted(ports & HTTP_PORTS))
    if http and not ports & HTTPS_PORTS:
        risks.append(_risk(HTTP_ONLY, http))
    return sorted(risks, key=lambda r: (-r.severity, r.ports))


def risky_ports(open_ports: Iterable[int]) -> set[int]:
    """Ports that trigger a rule on their own (used to decide what deserves an alert)."""
    return {p for p in open_ports if p in _RULES_BY_PORT}


def highest(risks: Iterable[Risk]) -> Severity | None:
    return max((r.severity for r in risks), default=None)


def service_name(port: int) -> str:
    return SERVICE_NAMES.get(port, "")


def describe_ports(ports: Iterable[int]) -> str:
    """'22 SSH, 80 HTTP, 9999' for alerts and tooltips."""
    return ", ".join(f"{p} {service_name(p)}".strip() for p in sorted(ports)) or "none"
