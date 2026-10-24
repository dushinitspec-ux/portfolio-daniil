"""MAC addresses: normalising, vendor lookup and the "randomised" flag.

The first three bytes of a MAC address (the OUI) belong to the vendor that made the network
chip. Two bits of the first byte matter here:

- bit 0 set: a multicast/broadcast address, never a device;
- bit 1 set: a *locally administered* address, not assigned by a vendor. Phones and laptops
  use them as private (randomised) Wi-Fi addresses, and virtual machines and containers get
  them too. Their first three bytes are random, so a vendor lookup would be wrong.
"""

import csv
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Not in a "data" directory: the repository ignores those (they hold SQLite files).
DEFAULT_OUI_FILE = Path(__file__).parent / "resources" / "oui.csv"

# 8c-86-dd-b6-0d-d8 (Windows), 8c:86:dd:b6:0d:d8 (Linux), 8c:86:dd:b6:d:d8 (macOS drops
# leading zeros) and 8c86.ddb6.0dd8 (Cisco).
_MAC_GROUPS = re.compile(r"^[0-9a-f]{1,2}([:-])[0-9a-f]{1,2}(?:\1[0-9a-f]{1,2}){4}$")
_MAC_CISCO = re.compile(r"^[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}$")


class MacKind(StrEnum):
    VENDOR = "vendor"  # universally administered: the OUI names the maker
    RANDOMISED = "randomised"  # locally administered: private Wi-Fi address, VM, container


def normalize_mac(text: str) -> str | None:
    """Lower-case colon form ("8c:86:dd:b6:0d:d8"), or None if it is not a device address.

    Multicast/broadcast and all-zero addresses (Windows shows 00-00-00-00-00-00 for entries
    it could not resolve) return None.
    """
    value = text.strip().lower()
    if _MAC_GROUPS.match(value):
        parts = re.split(r"[:-]", value)
    elif _MAC_CISCO.match(value):
        digits = value.replace(".", "")
        parts = [digits[i : i + 2] for i in range(0, 12, 2)]
    else:
        return None
    octets = [int(p, 16) for p in parts]
    if octets[0] & 0x01 or not any(octets):
        return None
    return ":".join(f"{o:02x}" for o in octets)


def mac_kind(mac: str) -> MacKind:
    return MacKind.RANDOMISED if int(mac[:2], 16) & 0x02 else MacKind.VENDOR


@dataclass(frozen=True)
class MacInfo:
    mac: str
    kind: MacKind
    vendor: str | None


class OuiDatabase:
    def __init__(self, vendors: dict[str, str]) -> None:
        self._vendors = vendors

    @classmethod
    def load(cls, path: Path = DEFAULT_OUI_FILE) -> "OuiDatabase":
        with path.open(encoding="utf-8", newline="") as f:
            rows = csv.DictReader(line for line in f if not line.startswith("#"))
            return cls({row["prefix"].upper(): row["vendor"] for row in rows})

    def __len__(self) -> int:
        return len(self._vendors)

    def lookup(self, mac: str) -> MacInfo:
        """`mac` must already be normalised."""
        kind = mac_kind(mac)
        if kind is MacKind.RANDOMISED:
            return MacInfo(mac, kind, None)
        prefix = mac.replace(":", "")[:6].upper()
        return MacInfo(mac, kind, self._vendors.get(prefix))
