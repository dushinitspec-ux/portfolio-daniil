from decimal import Decimal as D

import pytest

from app.iban import compact, iban_problem, is_valid_iban, pretty, with_check_digits
from app.money import (
    AmountError,
    decimals,
    format_amount,
    format_display,
    format_number,
    format_price,
    money,
    parse_number,
    vat_amount,
)


@pytest.mark.parametrize(
    ("text", "style", "expected"),
    [
        ("1.234,56", None, "1234.56"),
        ("1,234.56", None, "1234.56"),
        ("1234.56", None, "1234.56"),
        ("2,5", "de", "2.5"),
        ("882,30", "de", "882.30"),
        ("12,00-", None, "-12.00"),
        ("-0,50", None, "-0.50"),
        ("1.234.567,89", None, "1234567.89"),
        ("EUR 3,046.36", None, "3046.36"),
        ("660,45 EUR", "de", "660.45"),
        ("1.234", "de", "1234"),  # German thousands separator
        ("1.234", "en", "1.234"),  # English decimal point
        ("1,234", "de", "1.234"),
        ("1,234", "en", "1234"),
    ],
)
def test_parse_number_reads_german_and_english_formats(
    text: str, style: str | None, expected: str
) -> None:
    assert parse_number(text, style) == D(expected)  # type: ignore[arg-type]


@pytest.mark.parametrize("text", ["", "abc", "12a", "EUR", "--"])
def test_parse_number_rejects_text(text: str) -> None:
    with pytest.raises(AmountError):
        parse_number(text)


def test_money_rounds_half_up_where_float_round_does_not() -> None:
    # 2.675 is stored as 2.67499999... in binary floating point, and Python's round()
    # also rounds halves to even (0.125 -> 0.12). Decimal with ROUND_HALF_UP matches the
    # XPath round() used by the official EN 16931 schematron.
    assert round(2.675, 2) == 2.67
    assert money(D("2.675")) == D("2.68")
    assert round(0.125, 2) == 0.12
    assert money(D("0.125")) == D("0.13")
    assert money(D("152.475")) == D("152.48")


def test_vat_amount_per_rate() -> None:
    assert vat_amount(D("802.50"), D("19")) == D("152.48")  # 152.475
    assert vat_amount(D("79.80"), D("7")) == D("5.59")  # 5.586
    assert vat_amount(D("2559.97"), D("19")) == D("486.39")  # 486.3943
    assert vat_amount(D("1650.00"), D("0")) == D("0.00")


def test_sum_of_cents_is_exact_with_decimal() -> None:
    cents = [D("0.10")] * 3
    assert sum(cents, D(0)) == D("0.30")
    assert sum([0.10] * 3) != 0.30  # the float version is 0.30000000000000004


def test_xml_number_formats() -> None:
    assert format_amount(D("336.9")) == "336.90"
    assert format_amount(D("1040.375")) == "1040.38"
    assert format_number(D("19.00")) == "19"
    assert format_number(D("100")) == "100"  # not "1E+2"
    assert format_number(D("2.50")) == "2.5"
    assert format_price(D("85")) == "85.00"
    assert format_price(D("0.125")) == "0.125"
    assert decimals(D("1.50")) == 2
    assert decimals(D("12")) == 0


def test_display_format() -> None:
    assert format_display(D("1040.37")) == "1.040,37"
    assert format_display(D("1040.37"), "en") == "1,040.37"
    assert format_display(None) == "—"


@pytest.mark.parametrize(
    "iban",
    [
        "DE89 3704 0044 0532 0130 00",  # the standard example IBAN
        "DE79000000001234567890",  # KoSIT test-suite dummy
        "DE52 0000 0000 0012 3456 78",  # sample data in this repository
        "AT34 0000 0000 1234 5678",
    ],
)
def test_valid_ibans(iban: str) -> None:
    assert is_valid_iban(iban)


@pytest.mark.parametrize(
    ("iban", "reason"),
    [
        ("DE52 0000 0000 0012 3456 79", "check digits"),  # last digit changed
        ("DE52 0000 0000 0012 3456 7", "22 characters"),  # one digit missing
        ("1234 5678", "does not look like an IBAN"),
        ("", "does not look like an IBAN"),
    ],
)
def test_invalid_ibans_explain_why(iban: str, reason: str) -> None:
    problem = iban_problem(iban)
    assert problem is not None and reason in problem


def test_iban_helpers() -> None:
    built = with_check_digits("DE", "000000000012345678")
    assert built == "DE52000000000012345678"
    assert is_valid_iban(built)
    assert compact(" de52 0000 ") == "DE520000"
    assert pretty(built) == "DE52 0000 0000 0012 3456 78"
