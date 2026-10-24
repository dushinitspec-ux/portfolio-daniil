"""Replay past days: what would the plan have cost against the naive schedule?

Days are planned in order, each one counting the load the previous day's plan left in the
evening (exactly what the live service does). A day without complete prices is skipped and
reported, never filled in.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.devices import SiteConfig, format_minutes
from app.messages import money, percent
from app.planner import DayPlan, horizon, plan_day
from app.prices import PricePoint, is_complete


@dataclass
class DeviceTotals:
    name: str
    energy_kwh: Decimal
    days: int = 0
    cost: Decimal = Decimal(0)
    baseline_cost: Decimal = Decimal(0)

    @property
    def saving(self) -> Decimal:
        return self.baseline_cost - self.cost

    def per_day(self, value: Decimal) -> Decimal | None:
        return value / self.days if self.days else None

    @property
    def saving_percent(self) -> Decimal | None:
        return self.saving / self.baseline_cost * 100 if self.baseline_cost > 0 else None


@dataclass
class BacktestResult:
    days: list[date]
    skipped: list[date]
    devices: list[DeviceTotals]
    unplanned: dict[str, int] = field(default_factory=dict)  # device -> days without a plan

    @property
    def cost(self) -> Decimal:
        return sum((d.cost for d in self.devices), Decimal(0))

    @property
    def baseline_cost(self) -> Decimal:
        return sum((d.baseline_cost for d in self.devices), Decimal(0))

    @property
    def saving(self) -> Decimal:
        return self.baseline_cost - self.cost

    @property
    def saving_percent(self) -> Decimal | None:
        return self.saving / self.baseline_cost * 100 if self.baseline_cost > 0 else None

    def per_day(self, value: Decimal) -> Decimal | None:
        return value / len(self.days) if self.days else None


def complete_days(
    site: SiteConfig, grid: Sequence[PricePoint], tz: ZoneInfo, count: int
) -> list[date]:
    """The last `count` days whose whole planning horizon has prices, oldest first."""
    if not grid:
        return []
    last = grid[-1].start.astimezone(tz).date()
    first = grid[0].start.astimezone(tz).date()
    days: list[date] = []
    day = last
    while day >= first and len(days) < count:
        start, end = horizon(site.devices, day, tz)
        if is_complete([s for s in grid if start <= s.start < end], start, end):
            days.append(day)
        day -= timedelta(days=1)
    return sorted(days)


def run_backtest(
    site: SiteConfig, grid: Sequence[PricePoint], tz: ZoneInfo, days: Sequence[date]
) -> BacktestResult:
    totals = {d.name: DeviceTotals(d.name, d.energy_kwh) for d in site.devices}
    result = BacktestResult(days=[], skipped=[], devices=list(totals.values()))
    cap = site.power_cap_kw
    previous: DayPlan | None = None
    for day in sorted(days):
        if previous is None or previous.day != day - timedelta(days=1):
            previous = plan_day(site.devices, grid, day - timedelta(days=1), tz, cap)
        plan = plan_day(
            site.devices,
            grid,
            day,
            tz,
            cap,
            existing_load=previous.load,
            existing_baseline_load=previous.baseline_load,
        )
        previous = plan
        if plan.missing_prices:
            result.skipped.append(day)
            continue
        result.days.append(day)
        for item in plan.devices:
            if item.cost is None or item.baseline_cost is None:
                result.unplanned[item.device.name] = result.unplanned.get(item.device.name, 0) + 1
                continue
            device_totals = totals[item.device.name]
            device_totals.days += 1
            device_totals.cost += item.cost
            device_totals.baseline_cost += item.baseline_cost
    return result


def format_backtest(
    result: BacktestResult, site: SiteConfig, bidding_zone: str, resolution: str, attribution: str
) -> str:
    if not result.days:
        return "No day with complete prices in the data; nothing to replay."
    first, last = result.days[0], result.days[-1]
    cap = f"power cap {site.power_cap_kw.normalize():f} kW" if site.power_cap_kw else "no cap"
    lines = [
        f"Backtest: {bidding_zone} day-ahead prices, {len(result.days)} days "
        f"({first} to {last}), {resolution} prices",
        f"Devices: {site.site}, {cap}. Baseline: every device starts when its window opens.",
        "",
        f"{'Device':<22}{'kWh/day':>9}{'baseline/day':>14}{'planned/day':>13}"
        f"{'saving/day':>12}{'saving':>9}",
    ]
    for d in result.devices:
        lines.append(
            f"{d.name[:21]:<22}{d.energy_kwh.normalize():>9f}"
            f"{money(d.per_day(d.baseline_cost)):>14}{money(d.per_day(d.cost)):>13}"
            f"{money(d.per_day(d.saving)):>12}{percent(d.saving_percent):>9}"
        )
    lines.append(
        f"{'All devices':<22}{'':>9}{money(result.per_day(result.baseline_cost)):>14}"
        f"{money(result.per_day(result.cost)):>13}{money(result.per_day(result.saving)):>12}"
        f"{percent(result.saving_percent):>9}"
    )
    lines.append("")
    lines.append(
        f"Over {len(result.days)} days: {money(result.cost)} instead of "
        f"{money(result.baseline_cost)}, saving {money(result.saving)} "
        f"({percent(result.saving_percent)})."
    )
    for name, count in result.unplanned.items():
        lines.append(f"{name}: no plan on {count} day(s) (power cap or a short DST night).")
    if result.skipped:
        lines.append(f"Skipped (prices incomplete): {', '.join(map(str, result.skipped))}")
    lines.append(
        "Spot price only: grid fees, taxes and the supplier margin are the same in every "
        "hour and are not included."
    )
    if attribution:
        lines.append(attribution)
    return "\n".join(lines)


def describe_devices(site: SiteConfig) -> str:
    return "; ".join(
        f"{d.name} {d.power_kw.normalize():f} kW × {format_minutes(d.run_time)}"
        for d in site.devices
    )
