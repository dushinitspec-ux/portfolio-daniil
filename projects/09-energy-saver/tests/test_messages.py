from datetime import UTC, date, datetime
from decimal import Decimal

from app.messages import clock, format_not_published, format_plan, money, percent
from app.planner import plan_day
from tests.conftest import AUTUMN_HOURLY, TZ, grid_from, hours, make_device, real_grid

MIDNIGHT = datetime(2026, 10, 21, 22, tzinfo=UTC)  # 22 Oct 2026 00:00 in Berlin


def test_money_rounds_half_up_and_has_no_negative_zero() -> None:
    assert money(Decimal("1.005")) == "1.01 €"
    assert money(Decimal("-0.00015")) == "0.00 €"  # real case: -0.01 EUR/MWh slots
    assert money(Decimal("-1.2")) == "-1.20 €"
    assert money(None) == "—"
    assert percent(Decimal("47.149")) == "47.1 %"


def test_repeated_hour_is_labelled_with_the_time_zone() -> None:
    first = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # 02:30 CEST
    second = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)  # 02:30 CET
    assert clock(first, TZ) == "02:30 CEST"
    assert clock(second, TZ) == "02:30 CET"
    assert clock(datetime(2026, 10, 25, 3, tzinfo=UTC), TZ) == "04:00"


def test_daily_message_lists_times_costs_and_the_saving() -> None:
    grid = grid_from(MIDNIGHT - hours(2), [100] * 8 + [20] * 4 + [60] * 88)
    boiler = make_device(name="Boiler", power_kw="6", run_time="1h", window="22:00-07:00")
    dryer = make_device(
        name="Dryer_2", power_kw="5", run_time="2h", window="09:00-18:00", contiguous=True
    )
    text = format_plan(
        plan_day([boiler, dryer], grid, date(2026, 10, 22), TZ), "DE-LU", "Prices: X"
    )
    assert text.splitlines()[0] == "⚡ Plan for Thursday 22 Oct 2026 · DE-LU day-ahead"
    assert "Boiler · 6 kW · 1 h\n  00:00–01:00\n  0.12 € instead of 0.60 €, saves 0.48 €" in text
    assert "Dryer_2 · 5 kW · 2 h\n  09:00–11:00\n  0.60 € instead of 0.60 €\n" in text
    assert "Expected cost 0.72 € instead of 1.20 €" in text
    assert "Saving 0.48 € (40.0 %)." in text
    assert text.endswith("Prices: X")
    assert "Clocks" not in text


def test_message_on_the_25_hour_day() -> None:
    grid = real_grid(AUTUMN_HOURLY)
    boiler = make_device(name="Boiler", power_kw="6", run_time="3h", window="22:00-07:00")
    text = format_plan(plan_day([boiler], grid, date(2024, 10, 27), TZ), "DE-LU")
    assert "this day has 25 hours" in text
    assert "not planned" not in text


def test_message_when_prices_are_missing() -> None:
    boiler = make_device(name="Boiler", window="22:00-07:00")
    text = format_plan(plan_day([boiler], [], date(2026, 10, 22), TZ), "DE-LU")
    assert "Boiler · 1 kW · 1 h\n  not planned: no prices for this window yet" in text
    assert "Nothing could be planned" in text
    warning = format_not_published("Thu 22 Oct", "DE-LU")
    assert warning.startswith("⚠️ Day-ahead prices for Thu 22 Oct (DE-LU)")
