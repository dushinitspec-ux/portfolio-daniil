"""Checks that turn "looks like" into "is": IBAN mod-97, Luhn, VAT ID formats, IPv4, e-mail.

Every function here is pure and works on one candidate string, so each rule is tested on
its own, without the text scanning around it.
"""

import ipaddress
import re
from datetime import date

# IBAN length per country, from the SWIFT IBAN registry (release 101). A candidate with the
# wrong length for its country code is not an IBAN, whatever its checksum.
IBAN_LENGTHS: dict[str, int] = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22,
    "BH": 22, "BI": 27, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24,
    "DE": 22, "DJ": 27, "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18,
    "FK": 18, "FO": 18, "FR": 27, "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27,
    "GT": 28, "HN": 28, "HR": 21, "HU": 28, "IE": 22, "IL": 23, "IQ": 23, "IS": 26,
    "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28, "LC": 32, "LI": 21, "LT": 20,
    "LU": 20, "LV": 21, "LY": 25, "MC": 27, "MD": 24, "ME": 22, "MK": 19, "MN": 20,
    "MR": 27, "MT": 31, "MU": 30, "NI": 28, "NL": 18, "NO": 15, "OM": 23, "PK": 24,
    "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "RU": 33, "SA": 24,
    "SC": 31, "SD": 18, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "SO": 23, "ST": 25,
    "SV": 28, "TL": 23, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
    "YE": 30,
}  # fmt: skip

_IBAN_CHARS = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]+")


def compact(value: str) -> str:
    """Remove the spaces and hyphens people put into long numbers, and uppercase."""
    return re.sub(r"[\s-]", "", value).upper()


def iban_is_valid(value: str) -> bool:
    """ISO 13616: known country, the registry length, check digits 02-98, mod 97 == 1."""
    iban = compact(value)
    if not _IBAN_CHARS.fullmatch(iban):
        return False
    if IBAN_LENGTHS.get(iban[:2]) != len(iban):
        return False
    if not 2 <= int(iban[2:4]) <= 98:
        return False
    # Move country code and check digits to the end, then A=10 ... Z=35.
    rearranged = iban[4:] + iban[:4]
    number = "".join(str(int(char, 36)) for char in rearranged)
    return int(number) % 97 == 1


def luhn_is_valid(digits: str) -> bool:
    """The Luhn (mod 10) checksum used by payment card numbers."""
    if not digits.isdigit():
        return False
    total = 0
    for i, char in enumerate(reversed(digits)):
        n = int(char)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# (brand, issuer prefix ranges, allowed lengths). Luhn alone accepts one random number in
# ten, so a card must also start with a real issuer prefix and have that brand's length.
_CARD_BRANDS: tuple[tuple[str, tuple[tuple[int, int], ...], range], ...] = (
    ("visa", ((4, 4),), range(13, 20, 3)),  # 13, 16, 19
    ("mastercard", ((51, 55), (2221, 2720)), range(16, 17)),
    ("amex", ((34, 34), (37, 37)), range(15, 16)),
    ("mir", ((2200, 2204),), range(16, 20)),
    ("jcb", ((3528, 3589),), range(16, 20)),
    ("diners", ((300, 305), (36, 36), (38, 39)), range(14, 20)),
    ("discover", ((6011, 6011), (644, 649), (65, 65)), range(16, 20)),
    ("unionpay", ((62, 62),), range(16, 20)),
    ("maestro", ((50, 50), (56, 69)), range(12, 20)),
)


def card_brand(digits: str) -> str | None:
    """The card brand for a digit string, or None if no brand issues such a number."""
    if not digits.isdigit():
        return None
    for brand, ranges, lengths in _CARD_BRANDS:
        if len(digits) not in lengths:
            continue
        for low, high in ranges:
            prefix = int(digits[: len(str(low))])
            if low <= prefix <= high:
                return brand
    return None


def card_is_valid(digits: str) -> bool:
    return card_brand(digits) is not None and luhn_is_valid(digits)


# EU VAT ID structure per country prefix, as published in the European Commission's VIES
# FAQ. Format only: the national check digits are not verified, so a well-formed but
# unissued number is still masked, which is the safe direction for a privacy filter.
VAT_FORMATS: dict[str, re.Pattern[str]] = {
    country: re.compile(pattern)
    for country, pattern in {
        "AT": r"U\d{8}",
        "BE": r"[01]\d{9}",
        "BG": r"\d{9,10}",
        "CY": r"\d{8}[A-Z]",
        "CZ": r"\d{8,10}",
        "DE": r"\d{9}",
        "DK": r"\d{8}",
        "EE": r"\d{9}",
        "EL": r"\d{9}",
        "ES": r"[A-Z]\d{7}[A-Z0-9]|\d{8}[A-Z]",  # first and last may not both be digits
        "FI": r"\d{8}",
        "FR": r"[A-Z0-9]{2}\d{9}",
        "HR": r"\d{11}",
        "HU": r"\d{8}",
        "IE": r"\d[A-Z0-9+*]\d{5}[A-Z]|\d{7}[A-Z]{1,2}",
        "IT": r"\d{11}",
        "LT": r"\d{9}|\d{12}",
        "LU": r"\d{8}",
        "LV": r"\d{11}",
        "MT": r"\d{8}",
        "NL": r"[A-Z0-9+*]{9}B[A-Z0-9+*]{2}",
        "PL": r"\d{10}",
        "PT": r"\d{9}",
        "RO": r"\d{2,10}",
        "SE": r"\d{12}",
        "SI": r"\d{8}",
        "SK": r"\d{10}",
        "XI": r"\d{9}|\d{12}|GD\d{3}|HA\d{3}",  # Northern Ireland
    }.items()
}


def vat_is_well_formed(value: str) -> bool:
    vat = compact(value).replace(".", "")
    pattern = VAT_FORMATS.get(vat[:2])
    return pattern is not None and pattern.fullmatch(vat[2:]) is not None


def ipv4_is_valid(value: str) -> bool:
    """Four octets 0-255. Leading zeros ("010") are refused: some tools read them as octal."""
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return True


def email_is_valid(value: str) -> bool:
    """Length limits from RFC 5321 and the dot rules the detector's pattern cannot express."""
    local, _, domain = value.rpartition("@")
    if not local or not domain or len(value) > 254 or len(local) > 64:
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    labels = domain.split(".")
    return len(labels) >= 2 and all(
        0 < len(label) <= 63 and not label.startswith("-") and not label.endswith("-")
        for label in labels
    )


def birth_date(day: int, month: int, year: int, today: date) -> date | None:
    """A real calendar date that a living person could be born on, or None."""
    try:
        born = date(year, month, day)
    except ValueError:
        return None
    if born.year < 1900 or born > today:
        return None
    return born
