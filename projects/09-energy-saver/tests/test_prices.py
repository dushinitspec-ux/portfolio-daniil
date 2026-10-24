from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal

from app.fixtures import load_fixture
from app.prices import (
    PricePoint,
    day_bounds,
    day_hours,
    infer_minutes,
    is_complete,
    resolution_label,
    to_grid,
)
from tests.conftest import AUTUMN_HOURLY, SPRING_15MIN, SPRING_HOURLY, SWITCH_TO_15MIN, TZ

T0 = 1_792_447_200  # 2026-10-19 22:00 UTC


def test_infer_minutes_quarter_hours_and_hours() -> None:
    assert infer_minutes([T0, T0 + 900, T0 + 1800]) == [15, 15, 15]
    assert infer_minutes([T0, T0 + 3600, T0 + 7200]) == [60, 60, 60]


def test_infer_minutes_gap_keeps_the_previous_resolution() -> None:
    # A missing quarter-hour after 10:15 must not stretch 10:15 to 30 minutes.
    assert infer_minutes([T0, T0 + 900, T0 + 2700, T0 + 3600]) == [15, 15, 15, 15]
    # Nor may a 60-minute gap after a 15-minute price turn it into an hourly price.
    assert infer_minutes([T0, T0 + 900, T0 + 4500]) == [15, 15, 15]


def test_infer_minutes_single_point_claims_no_more_than_15_minutes() -> None:
    assert infer_minutes([T0]) == [15]


def test_real_switch_from_hourly_to_15_minute_prices() -> None:
    """Energy-Charts returns hourly prices for 30 Sep 2025 and 15-minute prices from
    1 Oct 2025, the first delivery day of the 15-minute day-ahead market."""
    points = load_fixture(SWITCH_TO_15MIN).prices.points
    by_day = Counter((p.start.astimezone(TZ).date(), p.minutes) for p in points)
    assert by_day == {(date(2025, 9, 30), 60): 24, (date(2025, 10, 1), 15): 96}
    grid = to_grid(points)
    assert len(grid) == 2 * 96
    start, end = day_bounds(date(2025, 9, 30), TZ)
    assert is_complete(grid, start, end)
    assert resolution_label(points) == "15-minute + hourly"


def test_hourly_price_becomes_four_equal_slots() -> None:
    start = datetime(2024, 10, 26, 10, tzinfo=UTC)
    grid = to_grid([PricePoint(start, 60, Decimal("87.12"))])
    assert [s.start.minute for s in grid] == [0, 15, 30, 45]
    assert {s.price for s in grid} == {Decimal("87.12")}
    assert all(s.minutes == 15 for s in grid)


def test_dst_days_have_23_and_25_hours() -> None:
    assert day_hours(date(2026, 3, 29), TZ) == 23
    assert day_hours(date(2026, 10, 25), TZ) == 25
    assert day_hours(date(2026, 10, 24), TZ) == 24


def test_real_dst_days_have_92_and_100_quarter_hours() -> None:
    spring = to_grid(load_fixture(SPRING_15MIN).prices.points)
    start, end = day_bounds(date(2026, 3, 29), TZ)
    assert len([s for s in spring if start <= s.start < end]) == 92
    assert is_complete(spring, start, end)

    autumn = to_grid(load_fixture(AUTUMN_HOURLY).prices.points)  # hourly, 2024
    start, end = day_bounds(date(2024, 10, 27), TZ)
    assert len([s for s in autumn if start <= s.start < end]) == 100


def test_real_hourly_spring_day_has_23_prices() -> None:
    points = load_fixture(SPRING_HOURLY).prices.points
    start, end = day_bounds(date(2025, 3, 30), TZ)
    day = [p for p in points if start <= p.start < end]
    assert len(day) == 23 and {p.minutes for p in day} == {60}
    assert is_complete(to_grid(points), start, end)


def test_incomplete_day_is_detected() -> None:
    grid = to_grid(load_fixture(SPRING_15MIN).prices.points)
    start, end = day_bounds(date(2026, 3, 29), TZ)
    assert not is_complete(grid[:-1], start, end)
