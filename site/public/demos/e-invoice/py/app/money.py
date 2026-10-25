"""Money and number handling. Every amount is a Decimal; floats never touch money.

Rounding follows the official EN 16931 validation artefacts: amounts are rounded to two
decimals with XPath `round()`, which rounds halves up (2.345 -> 2.35), not to the even digit
as Python's `round()` does.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

CENT = Decimal("0.01")
ZERO = Decimal("0")

NumberStyle = Literal["de", "en"]


class AmountError(ValueError):
    """A string could not be read as a number."""


def money(value: Decimal) -> Decimal:
    """Round to cents, halves away from zero for positive amounts (EN 16931 / XPath round)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def vat_amount(taxable: Decimal, rate: Decimal) -> Decimal:
    """VAT for one rate: taxable amount x rate / 100, rounded to cents (BR-CO-17)."""
    return money(taxable * rate / 100)


def decimals(value: Decimal) -> int:
    """Number of digits after the decimal point as written (Decimal keeps "1.50" as 2)."""
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def format_amount(value: Decimal) -> str:
    """Amount for XML: always two decimals, dot as separator, no thousands separator."""
    return f"{money(value):f}"


def format_number(value: Decimal) -> str:
    """Quantity, price or percent for XML: no trailing zeros, never scientific notation."""
    text = f"{value.normalize():f}"
    return "0" if text in {"-0", ""} else text


def format_price(value: Decimal) -> str:
    """Unit price for XML: at least two decimals (85.00), more only when printed (0.125)."""
    return format_amount(value) if decimals(value) <= 2 else format_number(value)


def format_display(value: Decimal | None, style: NumberStyle = "de") -> str:
    """Human-readable amount for the web page, e.g. 1.040,37 (de) or 1,040.37 (en)."""
    if value is None:
        return "—"
    text = f"{money(value):,f}"
    if style == "de":
        text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return text


_CLEAN = re.compile(r"[\s '’]|EUR|€", re.IGNORECASE)
_NUMBER = re.compile(r"^[+-]?\d[\d.,]*$")


def parse_number(text: str, style: NumberStyle | None = None) -> Decimal:
    """Read "1.234,56", "1,234.56", "1234.56", "2,5", "-12,00" or "12,00-" as a Decimal.

    If both separators appear, the last one is the decimal separator. With only one kind,
    a group of exactly three digits after it is ambiguous ("1.234"): it is a thousands
    separator unless `style` says that character is the decimal separator.
    """
    raw = _CLEAN.sub("", text.strip())
    negative = raw.endswith("-") or raw.startswith("-")
    raw = raw.strip("+-")
    if not raw or not _NUMBER.match(raw):
        raise AmountError(f"not a number: {text!r}")

    last_dot, last_comma = raw.rfind("."), raw.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal_sep = "." if last_dot > last_comma else ","
    elif last_dot >= 0 or last_comma >= 0:
        sep = "." if last_dot >= 0 else ","
        tail = raw.rsplit(sep, 1)[1]
        several = raw.count(sep) > 1
        if several:
            decimal_sep = ""  # "1.234.567": only thousands separators
        elif len(tail) == 3 and style is not None:
            decimal_sep = (
                sep if (sep == "," and style == "de") or (sep == "." and style == "en") else ""
            )
        elif len(tail) == 3:
            decimal_sep = ""
        else:
            decimal_sep = sep
    else:
        decimal_sep = ""

    if decimal_sep:
        whole, fraction = raw.rsplit(decimal_sep, 1)
        whole = whole.replace(".", "").replace(",", "")
        normalized = f"{whole or '0'}.{fraction}"
    else:
        normalized = raw.replace(".", "").replace(",", "")
    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:  # pragma: no cover - the regex above prevents it
        raise AmountError(f"not a number: {text!r}") from exc
    return -result if negative else result
