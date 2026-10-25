"""Choose the cheapest 15-minute slots for every device. Pure functions, no I/O.

Per device, inside its window:
- one block (`contiguous: true`): a sliding window over the slots, O(n) with prefix sums;
- split, any block length: the k cheapest slots;
- split, blocks of at least m slots: dynamic programming over (slot, slots taken, length of
  the current block). A window has at most ~100 slots, so this is a few thousand states.

Several devices share a power cap (`power_cap_kw`). They are planned one after another,
least flexible first (smallest window slack, then the largest load), and each one only
sees the capacity the earlier ones left. That greedy order is not always the global
optimum, but it is predictable, fast and easy to explain; with a handful of devices and a
cap that binds only a few hours a night, it rarely matters. An exact answer would need a
small integer program.

The baseline is what happens without the planner: every device starts when its window
opens (or as soon as the cap allows) and runs until it is done.

Money: prices are Decimal EUR/MWh, power is Decimal kW, so costs are exact; they are
rounded to cents only for display.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.devices import Device
from app.prices import SLOT, PricePoint, day_bounds

SLOT_HOURS = Decimal("0.25")
KWH_PER_MWH = Decimal(1000)

NO_PRICES = "no prices for this window yet"
TOO_SHORT = "window too short on this day"
OVER_CAP = "does not fit under the power cap"


@dataclass(frozen=True)
class Block:
    start: datetime  # UTC
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start) / timedelta(minutes=1))


@dataclass(frozen=True)
class DevicePlan:
    device: Device
    window_start: datetime
    window_end: datetime
    blocks: tuple[Block, ...] = ()
    baseline: tuple[Block, ...] = ()
    cost: Decimal | None = None  # EUR, exact
    baseline_cost: Decimal | None = None
    problem: str | None = None  # why there is no plan

    @property
    def planned(self) -> bool:
        return self.problem is None

    @property
    def missing_prices(self) -> bool:
        return self.problem == NO_PRICES

    @property
    def saving(self) -> Decimal | None:
        if self.cost is None or self.baseline_cost is None:
            return None
        return self.baseline_cost - self.cost

    def is_on(self, at: datetime) -> bool:
        return any(b.start <= at < b.end for b in self.blocks)


@dataclass(frozen=True)
class DayPlan:
    day: date
    tz: ZoneInfo
    devices: tuple[DevicePlan, ...]
    slots: tuple[PricePoint, ...]  # prices of the horizon, for the chart
    horizon_start: datetime
    horizon_end: datetime
    power_cap_kw: Decimal | None = None
    load: Mapping[datetime, Decimal] = field(default_factory=dict)
    baseline_load: Mapping[datetime, Decimal] = field(default_factory=dict)

    @property
    def planned(self) -> list[DevicePlan]:
        return [d for d in self.devices if d.planned]

    @property
    def missing_prices(self) -> bool:
        return any(d.missing_prices for d in self.devices)

    @property
    def cost(self) -> Decimal:
        return sum((d.cost for d in self.planned if d.cost is not None), Decimal(0))

    @property
    def baseline_cost(self) -> Decimal:
        return sum(
            (d.baseline_cost for d in self.planned if d.baseline_cost is not None), Decimal(0)
        )

    @property
    def saving(self) -> Decimal:
        return self.baseline_cost - self.cost

    @property
    def saving_percent(self) -> Decimal | None:
        base = self.baseline_cost
        return self.saving / base * 100 if base > 0 else None

    @property
    def hours(self) -> float:
        start, end = day_bounds(self.day, self.tz)
        return (end - start) / timedelta(hours=1)


def _local(day: date, minute: int, tz: ZoneInfo) -> datetime:
    """Wall-clock minute of a local day (can be >= 1440) as a UTC datetime.

    Uses fold=0: in the repeated hour of an autumn DST change this is the first 02:xx; a
    time that does not exist in spring (02:30) maps to 03:30 summer time.
    """
    day = day + timedelta(days=minute // 1440)
    minute %= 1440
    local = datetime.combine(day, time(minute // 60, minute % 60), tzinfo=tz)
    return local.astimezone(UTC)


def window_bounds(device: Device, day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    spec = device.spec
    start_day = day + timedelta(days=spec.start_day_offset)
    return _local(start_day, spec.start_minute, tz), _local(start_day, spec.end_minute, tz)


def horizon(devices: Iterable[Device], day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The time a plan covers: the local day plus any window that starts the day before."""
    start, end = day_bounds(day, tz)
    for device in devices:
        w_start, w_end = window_bounds(device, day, tz)
        start, end = min(start, w_start), max(end, w_end)
    return start, end


def slot_starts(start: datetime, end: datetime) -> list[datetime]:
    count = (end - start) // SLOT
    return [start + i * SLOT for i in range(count)]


# --- Choosing slots for one device -------------------------------------------------------


def cheapest_block(prices: Sequence[Decimal], free: Sequence[bool], k: int) -> list[int] | None:
    """Start..start+k-1 with the lowest total, all slots free. Earliest wins a tie."""
    n = len(prices)
    prefix = [Decimal(0)]
    blocked = [0]
    for price, ok in zip(prices, free, strict=True):
        prefix.append(prefix[-1] + price)
        blocked.append(blocked[-1] + (not ok))
    best: tuple[Decimal, int] | None = None
    for s in range(n - k + 1):
        if blocked[s + k] - blocked[s]:
            continue
        total = prefix[s + k] - prefix[s]
        if best is None or total < best[0]:
            best = (total, s)
    return None if best is None else list(range(best[1], best[1] + k))


def cheapest_slots(prices: Sequence[Decimal], free: Sequence[bool], k: int) -> list[int] | None:
    """The k cheapest free slots, any order. Earlier slots win ties."""
    candidates = sorted((p, i) for i, (p, ok) in enumerate(zip(prices, free, strict=True)) if ok)
    if len(candidates) < k:
        return None
    return sorted(i for _, i in candidates[:k])


def cheapest_min_blocks(
    prices: Sequence[Decimal], free: Sequence[bool], k: int, m: int
) -> list[int] | None:
    """k slots with the lowest total where every run of chosen slots is at least m long.

    State after slot i: (j slots chosen, r = length of the current run capped at m, 0 = the
    last slot was not chosen). A run may only end (skip a slot, or reach the window end)
    when r is 0 or m.
    """
    width = m + 1
    best: list[Decimal | None] = [None] * ((k + 1) * width)
    best[0] = Decimal(0)
    history: list[list[tuple[int, bool] | None]] = []

    for i, price in enumerate(prices):
        new: list[Decimal | None] = [None] * ((k + 1) * width)
        came_from: list[tuple[int, bool] | None] = [None] * ((k + 1) * width)
        for state, cost in enumerate(best):
            if cost is None:
                continue
            j, r = divmod(state, width)
            if r in (0, m):  # skip slot i
                target = j * width
                current = new[target]
                if current is None or cost < current:
                    new[target], came_from[target] = cost, (state, False)
            if free[i] and j < k:  # take slot i
                target = (j + 1) * width + min(r + 1, m)
                total = cost + price
                current = new[target]
                if current is None or total < current:
                    new[target], came_from[target] = total, (state, True)
        best = new
        history.append(came_from)

    finals = [(cost, s) for s in (k * width, k * width + m) if (cost := best[s]) is not None]
    if not finals:
        return None
    _, state = min(finals)
    chosen: list[int] = []
    for i in range(len(prices) - 1, -1, -1):
        step = history[i][state]
        assert step is not None
        state, took = step
        if took:
            chosen.append(i)
    return sorted(chosen)


def choose(device: Device, prices: Sequence[Decimal], free: Sequence[bool]) -> list[int] | None:
    k = device.slots_needed
    if device.contiguous:
        return cheapest_block(prices, free, k)
    if device.min_block_slots <= 1:
        return cheapest_slots(prices, free, k)
    return cheapest_min_blocks(prices, free, k, device.min_block_slots)


def earliest_block(free: Sequence[bool], k: int) -> list[int] | None:
    """The naive schedule: switch on as soon as the window opens (and the cap allows)."""
    run = 0
    for i, ok in enumerate(free):
        run = run + 1 if ok else 0
        if run == k:
            return list(range(i - k + 1, i + 1))
    return None


# --- Whole day ---------------------------------------------------------------------------


def to_blocks(starts: Sequence[datetime]) -> tuple[Block, ...]:
    """Merge chosen slot starts into continuous blocks."""
    blocks: list[Block] = []
    for start in sorted(starts):
        if blocks and blocks[-1].end == start:
            blocks[-1] = Block(blocks[-1].start, start + SLOT)
        else:
            blocks.append(Block(start, start + SLOT))
    return tuple(blocks)


def energy_cost(prices: Iterable[Decimal], power_kw: Decimal) -> Decimal:
    """EUR for running `power_kw` during slots with these EUR/MWh prices."""
    return sum(prices, Decimal(0)) * power_kw * SLOT_HOURS / KWH_PER_MWH


def planning_order(devices: Iterable[Device], day: date, tz: ZoneInfo) -> list[Device]:
    """Least flexible first: smallest slack (window slots minus needed slots), then the
    largest load, then the name for a stable order."""

    def slack(device: Device) -> int:
        start, end = window_bounds(device, day, tz)
        return (end - start) // SLOT - device.slots_needed

    return sorted(devices, key=lambda d: (slack(d), -d.power_kw, d.name))


def plan_day(
    devices: Sequence[Device],
    slots: Iterable[PricePoint],
    day: date,
    tz: ZoneInfo,
    power_cap_kw: Decimal | None = None,
    existing_load: Mapping[datetime, Decimal] | None = None,
    existing_baseline_load: Mapping[datetime, Decimal] | None = None,
) -> DayPlan:
    """Plan one day. `slots` are 15-minute grid prices (see prices.to_grid).

    `existing_load` is power already planned by the previous day's plan: windows of two
    days can overlap in the evening (Saturday's 16:00-20:00 and Sunday's 18:00-07:00).
    """
    price_at = {s.start: s.price for s in slots}
    load: dict[datetime, Decimal] = dict(existing_load or {})
    base_load: dict[datetime, Decimal] = dict(existing_baseline_load or {})
    results: dict[str, DevicePlan] = {}

    def fits(at: datetime, used: Mapping[datetime, Decimal], power: Decimal) -> bool:
        return power_cap_kw is None or used.get(at, Decimal(0)) + power <= power_cap_kw

    for device in planning_order(devices, day, tz):
        w_start, w_end = window_bounds(device, day, tz)
        starts = slot_starts(w_start, w_end)
        missing = [t for t in starts if t not in price_at]
        if missing:
            results[device.name] = DevicePlan(device, w_start, w_end, problem=NO_PRICES)
            continue
        if len(starts) < device.slots_needed:  # e.g. a night window on the spring DST day
            results[device.name] = DevicePlan(device, w_start, w_end, problem=TOO_SHORT)
            continue

        prices = [price_at[t] for t in starts]
        chosen = choose(device, prices, [fits(t, load, device.power_kw) for t in starts])
        naive = earliest_block(
            [fits(t, base_load, device.power_kw) for t in starts], device.slots_needed
        )
        if chosen is None or naive is None:
            results[device.name] = DevicePlan(device, w_start, w_end, problem=OVER_CAP)
            continue

        for i in chosen:
            load[starts[i]] = load.get(starts[i], Decimal(0)) + device.power_kw
        for i in naive:
            base_load[starts[i]] = base_load.get(starts[i], Decimal(0)) + device.power_kw
        results[device.name] = DevicePlan(
            device,
            w_start,
            w_end,
            blocks=to_blocks([starts[i] for i in chosen]),
            baseline=to_blocks([starts[i] for i in naive]),
            cost=energy_cost((prices[i] for i in chosen), device.power_kw),
            baseline_cost=energy_cost((prices[i] for i in naive), device.power_kw),
        )

    h_start, h_end = horizon(devices, day, tz)
    in_horizon = tuple(
        PricePoint(t, 15, price_at[t]) for t in slot_starts(h_start, h_end) if t in price_at
    )
    return DayPlan(
        day=day,
        tz=tz,
        devices=tuple(results[d.name] for d in devices),  # in devices.yaml order
        slots=in_horizon,
        horizon_start=h_start,
        horizon_end=h_end,
        power_cap_kw=power_cap_kw,
        load=load,
        baseline_load=base_load,
    )


def peak_load(load: Mapping[datetime, Decimal]) -> Decimal:
    return max(load.values(), default=Decimal(0))


def fallback_plan(
    devices: Sequence[Device], day: date, tz: ZoneInfo, power_cap_kw: Decimal | None = None
) -> DayPlan:
    """Without prices: every device starts when its window opens, still under the cap.

    Used to switch plugs when the day-ahead prices never arrived, so the water still gets
    hot. Costs are unknown, so they stay None.
    """
    start, end = horizon(devices, day, tz)
    flat = [PricePoint(t, 15, Decimal(0)) for t in slot_starts(start, end)]
    plan = plan_day(devices, flat, day, tz, power_cap_kw)
    items = tuple(
        replace(d, blocks=d.baseline, cost=None, baseline_cost=None) for d in plan.devices
    )
    return replace(plan, devices=items, slots=())
