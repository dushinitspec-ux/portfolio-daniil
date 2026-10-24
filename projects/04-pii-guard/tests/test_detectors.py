from datetime import date

import pytest

from app.detectors import Detector, find_dates_of_birth, find_phones
from app.entities import Entity, EntityType
from app.samples import SAMPLES_BY_ID
from tests.conftest import CARD, EMAIL, IBAN, PHONE, VAT

T = EntityType


def found(detector: Detector, text: str) -> list[tuple[EntityType, str]]:
    return [(e.type, e.value) for e in detector.detect(text)]


def test_refund_sample_finds_every_value(detector: Detector) -> None:
    text = SAMPLES_BY_ID["refund"].text
    assert found(detector, text) == [
        (T.NAME, "Anna Schmidt"),
        (T.IBAN, IBAN),
        (T.EMAIL, EMAIL),
        (T.PHONE, PHONE),
        (T.VAT_ID, VAT),
    ]


def test_iban_does_not_swallow_the_next_word(detector: Detector) -> None:
    text = f"IBAN: {IBAN} BIC COBADEFFXXX"
    assert found(detector, text) == [(T.IBAN, IBAN)]


def test_iban_with_no_break_spaces(detector: Detector) -> None:
    # Copied from a PDF or a web page, the groups are often separated by U+00A0.
    text = "IBAN " + IBAN.replace(" ", " ")
    assert [(t, v.replace(" ", " ")) for t, v in found(detector, text)] == [(T.IBAN, IBAN)]


def test_iban_digits_are_not_also_reported_as_a_phone_number(detector: Detector) -> None:
    # "0044 0532 0130 00" inside the IBAN reads like an international UK number.
    assert [t for t, _ in found(detector, f"Konto {IBAN}")] == [T.IBAN]


def test_iban_with_a_wrong_checksum_is_not_an_iban(detector: Detector) -> None:
    assert T.IBAN not in [t for t, _ in found(detector, "DE89 3704 0044 0532 0130 01")]


def test_card_inside_a_longer_run_of_digit_groups(detector: Detector) -> None:
    assert found(detector, f"ref 12 {CARD} thanks") == [(T.CARD, CARD)]


@pytest.mark.parametrize(
    "text",
    [
        "card 4111 1111 1111 1112",  # Luhn fails
        "order 1000 0000 0000 0008",  # Luhn passes, but no issuer starts with 1
    ],
)
def test_card_lookalikes_are_ignored(detector: Detector, text: str) -> None:
    assert T.CARD not in [t for t, _ in found(detector, text)]


def test_card_with_hyphens(detector: Detector) -> None:
    assert found(detector, "Amex 3782-822463-10005.") == [(T.CARD, "3782-822463-10005")]


@pytest.mark.parametrize(
    "number",
    ["+49 30 12345678", "0049 30 12345678", "030 12345678", "+49 (0)30 12345678", "0151 23456789"],
)
def test_german_phone_formats(detector: Detector, number: str) -> None:
    assert found(detector, f"Tel. {number}, bitte zurückrufen") == [(T.PHONE, number)]


def test_national_formats_depend_on_the_configured_region() -> None:
    text = "Appelez le 01 23 45 67 89"
    assert list(find_phones(text, ["DE"])) == []
    assert [e.value for e in find_phones(text, ["FR"])] == ["01 23 45 67 89"]


def test_international_numbers_only_need_to_be_possible() -> None:
    # Ofcom's drama range: well-formed but never assigned. Still masked: tomorrow it may be.
    assert [e.canonical for e in find_phones("ring +44 7700 900123", ["DE"])] == ["+447700900123"]


def test_dates_and_invoice_numbers_are_not_personal_data(detector: Detector) -> None:
    assert found(detector, "Invoice 2026-114 from 24.10.2026, due in 14 days.") == []


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Max Mustermann (geb. 14.03.1985)", "14.03.1985"),
        ("date of birth: 1985-03-14", "1985-03-14"),
        ("родился 01.02.1990 в Москве", "01.02.1990"),
        ("Doğum tarihi: 01.02.1990", "01.02.1990"),
        ("Mme Dupont, née le 01/02/1990", "01/02/1990"),
        ("born on 12/31/1990", "12/31/1990"),  # day-first impossible, so month-first
    ],
)
def test_dates_of_birth(text: str, value: str) -> None:
    hits = list(find_dates_of_birth(text, date(2026, 10, 24)))
    assert [(e.type, e.value) for e in hits] == [(T.DATE_OF_BIRTH, value)]


@pytest.mark.parametrize(
    "text",
    [
        "Meeting on 14.03.2026 at 10:00",  # no birth word nearby
        "born 31.02.1990",  # no such date
        "born 01.01.2030",  # in the future
        "born in Berlin, which is a long way from here, and the contract is 01.02.1990",
    ],
)
def test_not_dates_of_birth(text: str) -> None:
    assert list(find_dates_of_birth(text, date(2026, 10, 24))) == []


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("USt-IdNr. DE 123 456 789", "DE 123 456 789"),
        ("VAT DK12 34 56 78, thanks", "DK12 34 56 78"),
        ("Muster S.L., ESX1234567X.", "ESX1234567X"),
    ],
)
def test_vat_ids_as_people_write_them(detector: Detector, text: str, value: str) -> None:
    assert (T.VAT_ID, value) in found(detector, text)


def test_vat_prefix_must_be_uppercase(detector: Detector) -> None:
    assert T.VAT_ID not in [t for t, _ in found(detector, "see de123456789")]


def test_ipv4_and_email_at_the_end_of_a_sentence(detector: Detector) -> None:
    assert found(detector, f"Write to {EMAIL}. Login from 203.0.113.42.") == [
        (T.EMAIL, EMAIL),
        (T.IPV4, "203.0.113.42"),
    ]


def test_version_numbers_are_not_ip_addresses(detector: Detector) -> None:
    assert found(detector, "upgrade to 1.2.3.4.5 or 300.1.1.1") == []


def test_names_from_the_list_only_as_whole_words(detector: Detector) -> None:
    text = "Anna  Schmidt wrote to Max Mustermann; Maximilian Mustermanns is someone else."
    assert found(detector, text) == [(T.NAME, "Anna  Schmidt"), (T.NAME, "Max Mustermann")]


def test_entity_repr_never_shows_the_value() -> None:
    entity = Entity(T.EMAIL, 0, len(EMAIL), EMAIL, EMAIL)
    assert EMAIL not in repr(entity)
    assert "EMAIL" in repr(entity)
