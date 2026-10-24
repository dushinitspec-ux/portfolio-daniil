"""Parsing helpers shared by the extractors: dates, units, countries, VAT IDs."""

import re
from datetime import date

from app.money import NumberStyle

MONTHS = {
    "january": 1, "jan": 1, "januar": 1, "jänner": 1,
    "february": 2, "feb": 2, "februar": 2,
    "march": 3, "mar": 3, "märz": 3, "maerz": 3,
    "april": 4, "apr": 4,
    "may": 5, "mai": 5,
    "june": 6, "jun": 6, "juni": 6,
    "july": 7, "jul": 7, "juli": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12, "dezember": 12, "dez": 12,
}  # fmt: skip

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DOTTED = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})\b")
_SLASHED = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MONTH_FIRST = re.compile(r"\b([A-Za-zäÄ]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b")
_DAY_FIRST = re.compile(r"\b(\d{1,2})\.?\s+([A-Za-zäÄ]{3,9})\.?,?\s+(\d{4})\b")

DATE_PATTERN = (
    r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{2,4}|\d{1,2}/\d{1,2}/\d{4}"
    r"|[A-Za-zä]{3,9}\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}\.?\s+[A-Za-zä]{3,9}\.?,?\s+\d{4})"
)


def _safe_date(year: int, month: int, day: int) -> date | None:
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(text: str, style: NumberStyle = "de") -> date | None:
    """First date in `text`: 2026-10-15, 15.10.2026, October 15, 2026, 15. Oktober 2026.

    Slashed dates are read day-first for German documents and month-first for English ones.
    """
    if m := _ISO.search(text):
        return _safe_date(int(m[1]), int(m[2]), int(m[3]))
    if m := _DOTTED.search(text):
        return _safe_date(int(m[3]), int(m[2]), int(m[1]))
    if m := _SLASHED.search(text):
        a, b, year = int(m[1]), int(m[2]), int(m[3])
        return _safe_date(year, b, a) if style == "de" else _safe_date(year, a, b)
    if (m := _MONTH_FIRST.search(text)) and m[1].lower() in MONTHS:
        return _safe_date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
    if (m := _DAY_FIRST.search(text)) and m[2].lower() in MONTHS:
        return _safe_date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
    return None


def all_dates(text: str, style: NumberStyle = "de") -> list[date]:
    """Every date in `text`, in order (used for periods: "1.9.2026 - 30.9.2026")."""
    found = []
    for match in re.finditer(DATE_PATTERN, text):
        parsed = parse_date(match.group(0), style)
        if parsed:
            found.append(parsed)
    return found


# UN/ECE Recommendation 20 unit codes for the units printed on typical invoices.
UNIT_CODES: dict[str, str] = {
    "h": "HUR", "std": "HUR", "std.": "HUR", "stunde": "HUR", "stunden": "HUR",
    "hour": "HUR", "hours": "HUR", "hr": "HUR", "hrs": "HUR",
    "stk": "H87", "stk.": "H87", "st.": "H87", "stück": "H87", "pcs": "H87", "pc": "H87",
    "piece": "H87", "pieces": "H87",
    "tag": "DAY", "tage": "DAY", "day": "DAY", "days": "DAY",
    "monat": "MON", "monate": "MON", "month": "MON", "months": "MON",
    "pauschal": "LS", "psch.": "LS", "psch": "LS", "flat": "LS", "lump sum": "LS",
    "kg": "KGM", "m": "MTR", "km": "KMT", "l": "LTR",
}  # fmt: skip
DEFAULT_UNIT = "C62"  # "one": a unit without a more specific code (users, licences, ...)


def unit_code(label: str) -> str:
    return UNIT_CODES.get(label.strip().lower(), DEFAULT_UNIT)


COUNTRIES: dict[str, str] = {
    "deutschland": "DE", "germany": "DE", "österreich": "AT", "austria": "AT",
    "schweiz": "CH", "switzerland": "CH", "frankreich": "FR", "france": "FR",
    "niederlande": "NL", "netherlands": "NL", "belgien": "BE", "belgium": "BE",
    "italien": "IT", "italy": "IT", "spanien": "ES", "spain": "ES", "polen": "PL",
    "poland": "PL", "irland": "IE", "ireland": "IE", "luxemburg": "LU", "luxembourg": "LU",
    "dänemark": "DK", "denmark": "DK", "tschechien": "CZ", "czechia": "CZ",
}  # fmt: skip


def country_code(name: str) -> str | None:
    return COUNTRIES.get(name.strip().strip(",.").lower())


# A VAT identifier: two-letter prefix + 8 to 12 letters/digits ("DE123456789", "ATU12345678").
VAT_ID = re.compile(r"\b([A-Z]{2})\s?([0-9A-Z]{8,12})\b")
VAT_LABEL = re.compile(
    r"(?:USt\.?-?Id(?:Nr|\.-?Nr)?\.?|VAT\s*(?:ID|No\.?|number|reg\.?\s*no\.?)|UID(?:-Nr\.?)?)\s*:?\s*",
    re.IGNORECASE,
)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"\+?\d[\d\s/()-]{5,}\d")
IBAN = re.compile(r"\bIBAN\s*:?\s*([A-Z]{2}\d{2}(?:\s?[A-Z0-9]){10,30})", re.IGNORECASE)
POSTCODE_CITY = re.compile(r"^(?:[A-Z]{1,2}-)?(\d{4,5})\s+(\S.*)$")
