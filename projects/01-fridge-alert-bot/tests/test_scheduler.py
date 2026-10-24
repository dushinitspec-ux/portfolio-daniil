from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from app.scheduler import parse_hhmm, seconds_until

ISTANBUL = ZoneInfo("Europe/Istanbul")


def test_parse_hhmm() -> None:
    assert parse_hhmm("09:30") == time(9, 30)
    assert parse_hhmm("") is None


def test_later_today() -> None:
    now = datetime(2026, 10, 24, 5, 0, tzinfo=UTC)  # 08:00 in Istanbul (UTC+3)
    assert seconds_until(now, time(9, 0), ISTANBUL) == 3600


def test_already_passed_today_means_tomorrow() -> None:
    now = datetime(2026, 10, 24, 7, 0, tzinfo=UTC)  # 10:00 in Istanbul
    assert seconds_until(now, time(9, 0), ISTANBUL) == 23 * 3600


def test_daylight_saving_change() -> None:
    # Berlin moves clocks back on 25 Oct 2026, so that night is 25 hours long.
    berlin = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 10, 24, 7, 0, tzinfo=UTC)  # 09:00 CEST
    assert seconds_until(now, time(9, 0), berlin) == 25 * 3600
