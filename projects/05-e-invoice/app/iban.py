"""IBAN checks (ISO 13616): country length table and the mod-97 checksum."""

import re

# Lengths for SEPA countries and a few neighbours (ISO 13616 registry).
IBAN_LENGTHS: dict[str, int] = {
    "AD": 24, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24, "DE": 22,
    "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22, "GI": 23, "GR": 27,
    "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27, "LI": 21, "LT": 20, "LU": 20,
    "LV": 21, "MC": 27, "MT": 31, "NL": 18, "NO": 15, "PL": 28, "PT": 25, "RO": 24,
    "SE": 24, "SI": 19, "SK": 24, "SM": 27, "TR": 26, "VA": 22,
}  # fmt: skip

_FORMAT = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}$")


def compact(iban: str) -> str:
    """Remove spaces and make upper case: "de89 3704 ..." -> "DE893704..."."""
    return re.sub(r"\s+", "", iban).upper()


def _mod97(iban: str) -> int:
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97


def iban_problem(iban: str) -> str | None:
    """None if the IBAN is valid, otherwise a short English reason."""
    value = compact(iban)
    if not _FORMAT.match(value):
        return "does not look like an IBAN (two letters, two check digits, account number)"
    expected = IBAN_LENGTHS.get(value[:2])
    if expected is not None and len(value) != expected:
        return f"{value[:2]} IBANs have {expected} characters, this one has {len(value)}"
    if _mod97(value) != 1:
        return "the check digits do not match (mod-97 checksum failed)"
    return None


def is_valid_iban(iban: str) -> bool:
    return iban_problem(iban) is None


def with_check_digits(country: str, bban: str) -> str:
    """Build a valid IBAN from a country code and account part (used for sample data)."""
    remainder = _mod97(f"{country}00{bban}")
    return f"{country}{98 - remainder:02d}{bban}"


def pretty(iban: str) -> str:
    """Groups of four for display: DE89 3704 0044 0532 0130 00."""
    value = compact(iban)
    return " ".join(value[i : i + 4] for i in range(0, len(value), 4))
