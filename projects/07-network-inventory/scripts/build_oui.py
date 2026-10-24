"""Builds app/resources/oui.csv, the small vendor table bundled with the app.

The source is the IEEE Registration Authority public MA-L listing (the "OUI list"):
https://standards-oui.ieee.org/oui/oui.csv - about 40 000 rows and 3.8 MB with addresses.
The app only needs vendors that show up on office and hotel networks, so this script keeps
the assignments of those vendors, drops the addresses and shortens the names.

Usage:
    curl -o oui-full.csv https://standards-oui.ieee.org/oui/oui.csv
    uv run python scripts/build_oui.py oui-full.csv
"""

import csv
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "resources" / "oui.csv"

# (short name shown in the app, pattern for the IEEE "Organization Name"). First match wins,
# so the more specific names come first ("Cisco Meraki" before "Cisco").
VENDORS: list[tuple[str, str]] = [
    # Routers, switches, access points, firewalls
    ("MikroTik", r"^Routerboard\.com"),
    ("Ubiquiti", r"^Ubiquiti"),
    ("TP-Link", r"^TP-LINK|^TP-Link"),
    ("Mercusys", r"^MERCUSYS"),
    ("Cisco Meraki", r"^Cisco Meraki"),
    ("Linksys", r"^Cisco-Linksys"),
    ("Cisco", r"^Cisco Systems"),
    ("HPE / Aruba", r"^Hewlett Packard Enterprise"),
    ("HP", r"^Hewlett Packard|^HP Inc\."),
    ("Ruckus", r"^Ruckus Wireless"),
    ("Cambium", r"^Cambium Networks"),
    ("Netgear", r"^NETGEAR"),
    ("D-Link", r"^D-Link"),
    ("Zyxel", r"^Zyxel|^ZyXEL"),
    ("Keenetic", r"^Keenetic"),
    ("Fortinet", r"^Fortinet"),
    ("Juniper", r"^Juniper Networks"),
    ("Tenda", r"^Tenda Technology"),
    ("Edimax", r"^Edimax"),
    ("Huawei", r"^HUAWEI TECHNOLOGIES"),
    # Cameras and recorders
    ("Hikvision", r"^Hangzhou Hikvision"),
    ("EZVIZ", r"^Hangzhou Ezviz"),
    ("Dahua", r"^Zhejiang Dahua"),
    ("Uniview", r"^Zhejiang Uniview"),
    ("Axis", r"^Axis Communications"),
    ("Hanwha Vision", r"^HANWHA VISION|^Hanwha Vision|^Hanwha Techwin"),
    ("Reolink", r"^Reolink"),
    # Storage
    ("Synology", r"^Synology"),
    ("QNAP", r"^QNAP"),
    # Printers and label printers
    ("Brother", r"^Brother industries"),
    ("Canon", r"^CANON INC"),
    ("Epson", r"^Seiko Epson"),
    ("Kyocera", r"^KYOCERA"),
    ("Ricoh", r"^RICOH"),
    ("Xerox", r"^XEROX"),
    ("Konica Minolta", r"^KONICA MINOLTA"),
    ("Lexmark", r"^LEXMARK"),
    ("Zebra", r"^Zebra Technologies"),
    # IP phones
    ("Yealink", r"^YEALINK"),
    ("Grandstream", r"^Grandstream"),
    ("Polycom", r"^Polycom"),
    # Computers and the network chips inside them
    ("Intel", r"^Intel Corporate"),
    ("Realtek", r"^REALTEK SEMICONDUCTOR"),
    ("Dell", r"^Dell Inc"),
    ("Lenovo", r"^LENOVO"),
    ("ASUS", r"^ASUSTek"),
    ("Gigabyte", r"^GIGA-BYTE"),
    ("MSI", r"^MICRO-STAR"),
    ("Supermicro", r"^Super Micro Computer"),
    ("Apple", r"^Apple, Inc"),
    ("Microsoft", r"^Microsoft"),
    ("Foxconn", r"^Hon Hai Precision"),
    ("Lite-On", r"^Liteon Technology"),
    ("AzureWave", r"^AzureWave"),
    ("Murata", r"^Murata Manufacturing"),
    ("FN-Link", r"^HUNAN FN-LINK"),
    ("Cloud Network Technology", r"^CLOUD NETWORK TECHNOLOGY"),
    ("Gaoshengda", r"^Hui Zhou Gaoshengda"),
    # Phones, TVs, speakers, small IoT boards
    ("Samsung", r"^Samsung Electronics"),
    ("Xiaomi", r"^Xiaomi Communications"),
    ("Honor", r"^Honor Device"),
    ("Google", r"^Google, Inc"),
    ("Amazon", r"^Amazon Technologies"),
    ("LG", r"^LG Electronics"),
    ("Sonos", r"^SONOS"),
    ("Raspberry Pi", r"^Raspberry Pi"),
    ("Espressif", r"^Espressif"),
    # Virtual machines
    ("VMware", r"^VMware"),
    ("VirtualBox", r"^PCS Systemtechnik"),
    ("Parallels", r"^Parallels"),
    ("Xen", r"^Xensource"),
]

_COMPILED = [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in VENDORS]


def short_name(organization: str) -> str | None:
    return next((name for name, rx in _COMPILED if rx.search(organization.strip())), None)


def build(source: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with source.open(encoding="utf-8", newline="") as f:
        for record in csv.DictReader(f):
            if record["Registry"] != "MA-L":
                continue
            vendor = short_name(record["Organization Name"])
            if vendor:
                rows.append((record["Assignment"].upper(), vendor))
    return sorted(set(rows))


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    rows = build(Path(sys.argv[1]))
    today = datetime.now(UTC).date().isoformat()
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        f.write(
            "# Subset of the IEEE Registration Authority MA-L public listing\n"
            "# (https://standards-oui.ieee.org/oui/oui.csv), downloaded " + today + ".\n"
            "# Only vendors common on office and hotel networks; names shortened, addresses\n"
            "# removed. Rebuild with scripts/build_oui.py. See README, 'MAC vendor data'.\n"
        )
        f.write("prefix,vendor\n")
        f.writelines(f"{prefix},{vendor}\n" for prefix, vendor in rows)
    vendors = len({v for _, v in rows})
    print(f"{OUT}: {len(rows)} prefixes, {vendors} vendors, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
