from datetime import date

import pytest

from app.validators import (
    birth_date,
    card_brand,
    card_is_valid,
    email_is_valid,
    iban_is_valid,
    ipv4_is_valid,
    luhn_is_valid,
    vat_is_well_formed,
)


@pytest.mark.parametrize(
    "iban",
    [
        "DE89 3704 0044 0532 0130 00",  # the standard German example, print form
        "DE89370400440532013000",  # the same, electronic form
        "de89 3704 0044 0532 0130 00",  # people do type it in lower case
        "GB82 WEST 1234 5698 7654 32",
        "FR14 2004 1010 0505 0001 3M02 606",
        "NL91 ABNA 0417 1643 00",
        "AT61 1904 3002 3457 3201",
        "BE68 5390 0754 7034",
        "CH93 0076 2011 6238 5295 7",
    ],
)
def test_valid_ibans(iban: str) -> None:
    assert iban_is_valid(iban)


@pytest.mark.parametrize(
    ("iban", "why"),
    [
        ("DE89 3704 0044 0532 0130 01", "one digit changed"),
        ("DE98 3704 0044 0532 0130 00", "check digits swapped"),
        ("DE89 3704 0044 0532 0130 0", "one character short for DE"),
        ("DE89 3704 0044 0532 0130 000", "one character too long for DE"),
        ("XX89 3704 0044 0532 0130 00", "no such country in the registry"),
        ("DE89 3704 0044 0532 0130 0!", "not alphanumeric"),
    ],
)
def test_invalid_ibans(iban: str, why: str) -> None:
    assert not iban_is_valid(iban), why


def _mod97(iban: str) -> int:
    rearranged = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97


def test_check_digits_outside_02_98_are_refused_even_if_mod97_passes() -> None:
    # Check digits 99 can satisfy mod 97 == 1 for some account numbers, but ISO 13616 only
    # issues 02-98. Find such an account and make sure the extra rule catches it.
    for n in range(1000):
        candidate = f"DE99{n:018d}"
        if _mod97(candidate) == 1:
            break
    else:
        pytest.fail("no candidate found")
    assert not iban_is_valid(candidate)


@pytest.mark.parametrize("digits", ["4111111111111111", "79927398713", "5555555555554444"])
def test_luhn_valid(digits: str) -> None:
    assert luhn_is_valid(digits)


@pytest.mark.parametrize("digits", ["4111111111111112", "79927398710", "", "4111 1111"])
def test_luhn_invalid(digits: str) -> None:
    assert not luhn_is_valid(digits)


@pytest.mark.parametrize(
    ("digits", "brand"),
    [
        ("4111111111111111", "visa"),
        ("5555555555554444", "mastercard"),
        ("2223000048400011", "mastercard"),  # 2-series
        ("378282246310005", "amex"),
        ("6011111111111117", "discover"),
    ],
)
def test_card_brands(digits: str, brand: str) -> None:
    assert card_brand(digits) == brand
    assert card_is_valid(digits)


def test_luhn_alone_is_not_enough_for_a_card() -> None:
    # Luhn-valid, but no card issuer starts with 1: an order number, not a card.
    digits = "1000000000000008"
    assert luhn_is_valid(digits)
    assert card_brand(digits) is None
    assert not card_is_valid(digits)


@pytest.mark.parametrize(
    "vat",
    [
        "DE123456789",
        "ATU12345678",
        "FRXX123456789",
        "NL123456789B01",
        "ESX1234567X",
        "ES12345678Z",
        "IE1234567T",
        "IE1234567TW",
        "BE0123456789",
        "DK12 34 56 78",
        "XIGD123",
    ],
)
def test_vat_formats_from_vies(vat: str) -> None:
    assert vat_is_well_formed(vat)


@pytest.mark.parametrize(
    "vat",
    [
        "DE12345678",  # 8 digits, DE has 9
        "AT12345678",  # Austria needs the U
        "ES123456789",  # first and last may not both be digits
        "BE2123456789",  # Belgian numbers start with 0 or 1
        "NL123456789X01",  # 10th character must be B
        "US123456789",  # not an EU prefix
    ],
)
def test_vat_wrong_formats(vat: str) -> None:
    assert not vat_is_well_formed(vat)


@pytest.mark.parametrize(
    ("ip", "ok"),
    [("203.0.113.42", True), ("255.255.255.255", True), ("256.1.1.1", False), ("010.1.1.1", False)],
)
def test_ipv4(ip: str, ok: bool) -> None:
    assert ipv4_is_valid(ip) is ok


@pytest.mark.parametrize(
    ("email", "ok"),
    [
        ("anna.schmidt@muster-gmbh.example", True),
        ("a..b@muster.example", False),
        (".anna@muster.example", False),
        ("anna@-muster.example", False),
        ("x" * 65 + "@muster.example", False),
    ],
)
def test_email(email: str, ok: bool) -> None:
    assert email_is_valid(email) is ok


def test_birth_dates() -> None:
    today = date(2026, 10, 24)
    assert birth_date(14, 3, 1985, today) == date(1985, 3, 14)
    assert birth_date(31, 2, 1990, today) is None  # no 31 February
    assert birth_date(1, 1, 2027, today) is None  # not born yet
    assert birth_date(1, 1, 1899, today) is None
