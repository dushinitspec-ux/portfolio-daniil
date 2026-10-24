import shutil
import subprocess
from pathlib import Path

import pytest

from app.oui import DEFAULT_OUI_FILE, MacKind, OuiDatabase, normalize_mac

PROJECT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "text",
    [
        "8c-86-dd-00-00-01",  # Windows
        "8C:86:DD:00:00:01",  # upper case
        "8c86.dd00.0001",  # Cisco
        "8c:86:dd:0:0:1",  # macOS drops leading zeros
        " 8c:86:dd:00:00:01 ",
    ],
)
def test_normalize_mac_formats(text: str) -> None:
    assert normalize_mac(text) == "8c:86:dd:00:00:01"


@pytest.mark.parametrize(
    "text",
    [
        "ff-ff-ff-ff-ff-ff",  # broadcast
        "01-00-5e-00-00-fb",  # IPv4 multicast
        "33:33:00:00:00:01",  # IPv6 multicast
        "00-00-00-00-00-00",  # Windows: unresolved entry
        "8c-86-dd-00-00",  # too short
        "8c:86-dd:00:00:01",  # mixed separators
        "not a mac",
    ],
)
def test_normalize_mac_rejects_non_devices(text: str) -> None:
    assert normalize_mac(text) is None


def test_vendor_lookup_with_real_prefixes(oui: OuiDatabase) -> None:
    # Prefixes from the real ARP table of the development machine.
    assert oui.lookup("8c:86:dd:00:00:01").vendor == "TP-Link"  # the home router
    assert oui.lookup("f0:b0:40:00:00:03").vendor == "FN-Link"  # a Wi-Fi module maker
    assert oui.lookup("48:8f:5a:00:00:01").vendor == "MikroTik"
    assert oui.lookup("dc:a6:32:00:00:01").vendor == "Raspberry Pi"


def test_randomised_mac_has_no_vendor(oui: OuiDatabase) -> None:
    # 9a:60:0f... from the same ARP table: a phone with a private Wi-Fi address.
    info = oui.lookup("9a:60:0f:00:00:0b")
    assert info.kind is MacKind.RANDOMISED
    assert info.vendor is None
    # Even when the random bytes happen to look like a real prefix with the local bit set.
    assert oui.lookup("4a:8f:5a:00:00:01").vendor is None  # 48:8f:5a is MikroTik


def test_unknown_vendor(oui: OuiDatabase) -> None:
    info = oui.lookup("00:00:5e:00:01:01")  # IANA VRRP, not in the bundled subset
    assert info.kind is MacKind.VENDOR
    assert info.vendor is None


def test_bundled_vendor_file_is_small_and_valid(oui: OuiDatabase) -> None:
    assert DEFAULT_OUI_FILE.stat().st_size < 200_000
    assert len(oui) > 5_000
    lines = DEFAULT_OUI_FILE.read_text(encoding="utf-8").splitlines()
    assert "standards-oui.ieee.org" in lines[1]  # the source is named in the file
    rows = [line.split(",") for line in lines if not line.startswith("#")][1:]
    assert all(len(p) == 6 and int(p, 16) >= 0 and v for p, v in rows)


def test_all_zero_mac_is_never_labelled_xerox(oui: OuiDatabase) -> None:
    # 00:00:00 is a real IEEE assignment (Xerox), but an all-zero MAC means "unresolved".
    assert oui.lookup("00:00:00:00:00:01").vendor == "Xerox"
    assert normalize_mac("00-00-00-00-00-00") is None


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_files_the_app_needs_are_not_git_ignored() -> None:
    # The repository ignores every "data/" directory (SQLite files live there). The vendor
    # table used to sit in app/data/ and would have been left out of every commit.
    needed = [DEFAULT_OUI_FILE, *PROJECT.glob("app/templates/*.html")]
    needed += PROJECT.glob("tests/fixtures/*.txt")
    paths = [p.relative_to(PROJECT).as_posix() for p in needed]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", *paths],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 128:
        pytest.skip("not inside a git checkout")
    assert result.stdout == "", f"ignored by .gitignore: {result.stdout}"
