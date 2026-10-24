import itertools
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.planner import (
    NO_PRICES,
    OVER_CAP,
    TOO_SHORT,
    cheapest_block,
    cheapest_min_blocks,
    cheapest_slots,
    earliest_block,
    fallback_plan,
    horizon,
    peak_load,
    plan_day,
    window_bounds,
)
from app.prices import SLOT, PricePoint, day_bounds, to_grid
from tests.conftest import (
    AUTUMN_HOURLY,
    SPRING_15MIN,
    TZ,
    flat_grid,
    grid_from,
    hours,
    make_device,
    real_grid,
)

DAY = date(2026, 10, 22)  # an ordinary Thursday
MIDNIGHT = datetime(2026, 10, 21, 22, tzinfo=UTC)  # 22 Oct 00:00 in Berlin


def prices(*values: int) -> list[Decimal]:
    return [Decimal(v) for v in values]


# --- Single device -------------------------------------------------------------------------


def test_contiguous_block_is_the_cheapest_sliding_window() -> None:
    p = prices(5, 1, 9, 2, 2, 7)
    assert cheapest_block(p, [True] * 6, 2) == [3, 4]  # 4 beats 1+9
    assert cheapest_block(p, [True, True, True, False, True, True], 2) == [0, 1]


def test_cheapest_slots_any_order_and_earliest_on_ties() -> None:
    assert cheapest_slots(prices(5, 1, 9, 1, 3, 1), [True] * 6, 2) == [1, 3]
    assert cheapest_slots(prices(5, 1), [True, False], 2) is None


def test_min_block_refuses_isolated_cheap_slots() -> None:
    p = prices(1, 9, 1, 9, 1, 9, 4, 4)
    assert cheapest_slots(p, [True] * 8, 2) == [0, 2]
    assert cheapest_min_blocks(p, [True] * 8, 2, 2) == [6, 7]  # 8 < 1+9


def test_min_block_dynamic_programming_matches_brute_force() -> None:
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(3, 10)
        k = rng.randint(1, n)
        m = rng.randint(2, k) if k >= 2 else 1
        p = [Decimal(rng.randint(-20, 300)) for _ in range(n)]
        free = [rng.random() > 0.15 for _ in range(n)]

        def valid(chosen: tuple[int, ...], free=free, m=m) -> bool:
            if not all(free[i] for i in chosen):
                return False
            runs = [
                len(list(g)) for _, g in itertools.groupby(enumerate(chosen), lambda t: t[1] - t[0])
            ]
            return all(r >= m for r in runs)

        options = [c for c in itertools.combinations(range(n), k) if valid(c)]
        result = cheapest_min_blocks(p, free, k, m)
        if not options:
            assert result is None
            continue
        best = min(sum(p[i] for i in c) for c in options)
        assert result is not None and valid(tuple(result))
        assert sum(p[i] for i in result) == best


def test_baseline_takes_the_first_free_block() -> None:
    assert earliest_block([True] * 6, 3) == [0, 1, 2]
    assert earliest_block([True, False, True, True, True, True], 3) == [2, 3, 4]
    assert earliest_block([True, False, True], 2) is None


# --- Windows, midnight and DST -------------------------------------------------------------


def test_night_window_belongs_to_the_day_it_ends_on() -> None:
    device = make_device(window="22:00-07:00")
    start, end = window_bounds(device, DAY, TZ)
    assert start == datetime(2026, 10, 21, 20, tzinfo=UTC)  # Wed 22:00 CEST
    assert end == datetime(2026, 10, 22, 5, tzinfo=UTC)  # Thu 07:00 CEST
    assert horizon([device], DAY, TZ) == (start, day_bounds(DAY, TZ)[1])


def test_night_window_is_10_hours_when_clocks_go_back_and_8_when_forward() -> None:
    device = make_device(window="22:00-07:00")
    autumn = window_bounds(device, date(2026, 10, 25), TZ)
    spring = window_bounds(device, date(2026, 3, 29), TZ)
    assert autumn[1] - autumn[0] == hours(10)
    assert spring[1] - spring[0] == hours(8)


def test_window_starting_inside_the_changed_hour() -> None:
    device = make_device(window="02:30-05:00")
    # Spring: 02:30 does not exist, the window opens at 03:30 summer time.
    start, end = window_bounds(device, date(2026, 3, 29), TZ)
    assert start == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    assert end - start == hours(1.5)
    # Autumn: 02:30 happens twice; the window opens at the first one (summer time).
    start, end = window_bounds(device, date(2026, 10, 25), TZ)
    assert start == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert end - start == hours(3.5)


def test_real_spring_dst_night_with_15_minute_prices() -> None:
    grid = real_grid(SPRING_15MIN)
    long_run = make_device(name="Long", run_time="8h30min", window="22:00-07:00")
    boiler = make_device(name="Boiler", run_time="3h", window="22:00-07:00", min_block="30min")
    plan = plan_day([long_run, boiler], grid, date(2026, 3, 29), TZ)
    too_long, ok = plan.devices
    assert too_long.problem == TOO_SHORT  # 9 h on paper, 8 h that night
    assert ok.planned
    assert sum(b.minutes for b in ok.blocks) == 180
    assert all(ok.window_start <= b.start and b.end <= ok.window_end for b in ok.blocks)


def test_real_autumn_dst_night_with_hourly_prices() -> None:
    """27 Oct 2024: hourly prices, 25-hour day. A 4-hour block may use both 02:00 hours."""
    grid = real_grid(AUTUMN_HOURLY)
    device = make_device(power_kw="10", run_time="4h", window="22:00-07:00", contiguous=True)
    plan = plan_day([device], grid, date(2024, 10, 27), TZ)
    (item,) = plan.devices
    assert item.planned and len(item.blocks) == 1
    block = item.blocks[0]
    assert block.end - block.start == hours(4)  # real time, whatever the clock shows
    price_at = {s.start: s.price for s in grid}
    expected = sum(price_at[block.start + i * SLOT] for i in range(16)) * 10 / 4 / 1000
    assert item.cost == expected


def test_hourly_prices_still_allow_quarter_hour_starts() -> None:
    hourly = [PricePoint(MIDNIGHT + hours(h), 60, Decimal(p)) for h, p in enumerate([90, 10, 90])]
    device = make_device(run_time="45min", window="00:00-03:00", contiguous=True)
    (item,) = plan_day([device], to_grid(hourly), DAY, TZ).devices
    assert item.blocks[0].start == MIDNIGHT + hours(1)
    assert item.cost == Decimal(10) * Decimal("0.75") / 1000


# --- Costs and the baseline ----------------------------------------------------------------


def test_baseline_starts_when_the_window_opens_and_costs_are_exact() -> None:
    # 22:00-00:00 costs 100, 00:00-07:00 costs 20 EUR/MWh.
    start = MIDNIGHT - hours(2)
    grid = grid_from(start, [100] * 8 + [20] * 28)
    device = make_device(power_kw="2", run_time="2h", window="22:00-07:00", contiguous=True)
    plan = plan_day([device], grid, DAY, TZ)
    (item,) = plan.devices
    assert item.baseline[0].start == start
    assert item.baseline_cost == Decimal("0.4")  # 2 kW * 2 h * 0.10 EUR/kWh
    assert item.cost == Decimal("0.08")  # 2 kW * 2 h * 0.02 EUR/kWh
    assert item.saving == Decimal("0.32")
    assert plan.saving_percent == Decimal(80)


def test_split_is_never_more_expensive_than_one_block() -> None:
    grid = real_grid(SPRING_15MIN)
    day = date(2026, 3, 28)
    block = make_device(name="Block", run_time="3h", window="08:00-20:00", contiguous=True)
    split = make_device(name="Split", run_time="3h", window="08:00-20:00")
    one, many = plan_day([block, split], grid, day, TZ).devices
    assert len(one.blocks) == 1
    assert many.cost is not None and one.cost is not None
    assert many.cost <= one.cost


def test_missing_prices_are_reported_not_guessed() -> None:
    grid = flat_grid(MIDNIGHT, MIDNIGHT + hours(6))
    (item,) = plan_day([make_device(window="00:00-08:00")], grid, DAY, TZ).devices
    assert item.problem == NO_PRICES
    assert item.cost is None


# --- Several devices and the power cap -----------------------------------------------------


def test_power_cap_keeps_two_loads_apart() -> None:
    # 00:00-01:00 is cheap, 01:00-02:00 a bit dearer, then expensive.
    grid = grid_from(MIDNIGHT, [10] * 4 + [20] * 4 + [90] * 16)
    a = make_device(name="A", power_kw="10", window="00:00-06:00", contiguous=True)
    b = make_device(name="B", power_kw="8", window="00:00-06:00", contiguous=True)

    free = plan_day([a, b], grid, DAY, TZ)
    assert free.devices[0].blocks == free.devices[1].blocks  # both take 00:00-01:00
    assert peak_load(free.load) == Decimal(18)

    capped = plan_day([a, b], grid, DAY, TZ, power_cap_kw=Decimal(15))
    first, second = capped.devices
    assert peak_load(capped.load) <= 15
    assert first.blocks[0].start == MIDNIGHT  # the bigger load chooses first
    assert second.blocks[0].start == MIDNIGHT + hours(1)
    assert capped.cost > free.cost
    assert peak_load(capped.baseline_load) <= 15  # the baseline obeys the cap too


def test_least_flexible_device_is_planned_first() -> None:
    grid = grid_from(MIDNIGHT, [50] * 16 + [10] * 4 + [50] * 12)
    tight = make_device(name="Tight", power_kw="5", window="04:00-05:00", contiguous=True)
    loose = make_device(name="Loose", power_kw="8", window="00:00-08:00", contiguous=True)
    loose_plan, tight_plan = plan_day([loose, tight], grid, DAY, TZ, Decimal(10)).devices
    assert tight_plan.blocks[0].start == MIDNIGHT + hours(4)  # it had no other choice
    assert loose_plan.blocks[0].start != MIDNIGHT + hours(4)


def test_device_that_cannot_fit_under_the_cap() -> None:
    grid = flat_grid(MIDNIGHT, MIDNIGHT + hours(24))
    a = make_device(name="A", power_kw="10", run_time="2h", window="01:00-03:00", contiguous=True)
    b = make_device(name="B", power_kw="10", run_time="1h", window="01:00-03:00", contiguous=True)
    plan = plan_day([a, b], grid, DAY, TZ, Decimal(15))
    assert plan.devices[0].planned
    assert plan.devices[1].problem == OVER_CAP
    assert plan.cost == plan.devices[0].cost  # totals only count planned devices


def test_previous_day_load_counts_in_the_evening_overlap() -> None:
    grid = flat_grid(MIDNIGHT - hours(6), MIDNIGHT + hours(24))
    ev = make_device(name="EV", power_kw="11", run_time="1h", window="18:00-07:00")
    # Yesterday's plan already runs 10 kW from 18:00 to 19:00 (16:00 UTC).
    taken = {MIDNIGHT - hours(6) + i * SLOT: Decimal(10) for i in range(4)}
    (item,) = plan_day([ev], grid, DAY, TZ, Decimal(15), existing_load=taken).devices
    assert item.blocks[0].start == MIDNIGHT - hours(5)  # 19:00, the first free hour


def test_fallback_without_prices_starts_at_the_window_start() -> None:
    boiler = make_device(name="Boiler", power_kw="6", run_time="2h", window="22:00-07:00")
    plan = fallback_plan([boiler], DAY, TZ)
    (item,) = plan.devices
    assert item.blocks[0].start == MIDNIGHT - hours(2)
    assert item.cost is None


@pytest.mark.parametrize("day", [date(2026, 10, 24), date(2026, 10, 25), date(2026, 3, 29)])
def test_every_planned_block_is_inside_its_window(day: date) -> None:
    grid = flat_grid(*day_bounds(day - timedelta(days=1), TZ)) + flat_grid(*day_bounds(day, TZ))
    devices = [
        make_device(name="Night", run_time="3h", window="22:00-07:00", latest_finish="06:00"),
        make_device(name="Day", run_time="2h", window="09:00-18:00", contiguous=True),
    ]
    for item in plan_day(devices, grid, day, TZ).devices:
        assert item.planned
        assert all(item.window_start <= b.start < b.end <= item.window_end for b in item.blocks)
        assert sum(b.minutes for b in item.blocks) == item.device.run_time
