"""In-browser demo (Pyodide): plan a day with the real planner on the bundled real prices.

The prices are the project's fixture: DE-LU day-ahead prices downloaded once from the
Energy-Charts API (fixtures/energy-charts-de-lu.json, CC BY 4.0 from Bundesnetzagentur |
SMARD.de), parsed by the same code as a live answer. The devices come from devices.yaml, or
from the visitor's edits checked by the same pydantic model. A day is planned the way the
app plans it (service.PlanService.plan, backtest.run_backtest): the previous day first, so
the load it leaves in the evening counts against the power cap.

Nothing is drawn here: the page draws the chart from the numbers this module returns.
Money is sent as text with two decimals (exact Decimal arithmetic stays in Python); prices
are also sent as floats, for drawing only.
"""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.backtest import complete_days
from app.devices import SiteConfig, format_minutes, load_site
from app.fixtures import Fixture, load_fixture
from app.messages import blocks_text, cents, clock, ct_per_kwh, dst_note, format_plan
from app.planner import (
    NO_PRICES,
    OVER_CAP,
    TOO_SHORT,
    Block,
    DayPlan,
    peak_load,
    plan_day,
    planning_order,
)
from app.prices import PricePoint, day_bounds, day_hours, resolution_label, to_grid

ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "fixtures" / "energy-charts-de-lu.json"  # config.DEFAULT_FIXTURE
DEVICES = ROOT / "devices.yaml"
# The default of Settings.timezone; app/config.py itself needs pydantic-settings.
TIMEZONE = "Europe/Berlin"
PROBLEMS = {NO_PRICES: "no_prices", TOO_SHORT: "too_short", OVER_CAP: "over_cap"}
DEVICE_FIELDS = (
    "name",
    "power_kw",
    "run_time",
    "window",
    "latest_finish",
    "contiguous",
    "min_block",
)


@dataclass(frozen=True)
class Data:
    fixture: Fixture
    grid: list[PricePoint]
    site: SiteConfig
    tz: ZoneInfo
    days: list[date]


@cache
def data() -> Data:
    fixture = load_fixture(FIXTURE)
    grid = to_grid(fixture.prices.points)
    site = load_site(DEVICES)
    tz = ZoneInfo(TIMEZONE)
    return Data(fixture, grid, site, tz, complete_days(site, grid, tz, 10_000))


def _number(value: Decimal | None) -> str | None:
    return None if value is None else f"{value.normalize():f}"


def _money(value: Decimal | None) -> str | None:
    return None if value is None else f"{cents(value):.2f}"


def attribution(d: Data) -> str:
    """As PlanService.attribution words it."""
    prices = d.fixture.prices
    return f"Prices: {prices.license_info} — via {prices.source}"


def site_json(site: SiteConfig) -> dict[str, Any]:
    return {
        "site": site.site,
        "power_cap_kw": _number(site.power_cap_kw),
        "devices": [
            {
                "name": dev.name,
                "power_kw": _number(dev.power_kw),
                "run_time": dev.run_time,
                "window": dev.window,
                "latest_finish": dev.latest_finish,
                "contiguous": dev.contiguous,
                "min_block": dev.min_block,
            }
            for dev in site.devices
        ],
    }


def init() -> dict[str, Any]:
    """The price data (with its licence), the days that can be planned and the devices."""
    d = data()
    fx = d.fixture
    return {
        "bidding_zone": fx.bidding_zone,
        "timezone": TIMEZONE,
        "source": fx.prices.source,
        "license": fx.prices.license_info,
        "request": fx.request,
        "downloaded_at": fx.downloaded_at.isoformat(),
        "resolution": resolution_label(fx.prices.points),
        "attribution": attribution(d),
        "days": [{"day": day.isoformat(), "hours": day_hours(day, d.tz)} for day in d.days],
        "site": site_json(d.site),
    }


def _site_from(raw: dict[str, Any] | None) -> SiteConfig:
    """The visitor's devices and cap, checked by the app's own model (devices.SiteConfig)."""
    base = data().site
    if raw is None:
        return base
    devices = [{k: item.get(k) for k in DEVICE_FIELDS} for item in raw.get("devices", [])]
    cap = raw.get("power_cap_kw")
    return SiteConfig.model_validate(
        {
            "site": base.site,
            "power_cap_kw": None if cap in (None, "") else str(cap),
            "devices": devices,
        }
    )


def _errors(exc: ValidationError) -> list[dict[str, Any]]:
    out = []
    for error in exc.errors():
        loc = error["loc"]
        device = (
            loc[1] if len(loc) > 1 and loc[0] == "devices" and isinstance(loc[1], int) else None
        )
        field = str(loc[-1]) if loc and isinstance(loc[-1], str) and loc[-1] != "devices" else None
        message = str(error["msg"]).removeprefix("Value error, ")
        out.append({"device": device, "field": field, "message": message})
    return out


class _Axis:
    """Positions on the chart: slot indexes of the plan's price slots (the horizon)."""

    def __init__(self, slots: tuple[PricePoint, ...]) -> None:
        self.starts = [s.start for s in slots]

    def at(self, moment: datetime) -> int:
        return bisect_left(self.starts, moment)

    def blocks(self, blocks: tuple[Block, ...], tz: ZoneInfo) -> list[dict[str, Any]]:
        return [
            {"from": self.at(b.start), "to": self.at(b.end), "text": blocks_text((b,), tz)}
            for b in blocks
        ]


def _ticks(plan: DayPlan) -> list[dict[str, Any]]:
    """Every local full hour of the horizon, labelled as the app labels times (a repeated
    hour on the autumn DST night gets its zone name)."""
    ticks = []
    for i, slot in enumerate(plan.slots):
        local = slot.start.astimezone(plan.tz)
        if local.minute == 0:
            ticks.append(
                {
                    "i": i,
                    "hour": local.hour,
                    "label": clock(slot.start, plan.tz),
                    "date": local.date().isoformat(),
                }
            )
    return ticks


def _percent(value: Decimal | None) -> str | None:
    return None if value is None else f"{value.quantize(Decimal('0.1'), ROUND_HALF_UP):.1f}"


def plan(day: str, site: dict[str, Any] | None = None) -> dict[str, Any]:
    """Plan `day` (YYYY-MM-DD) for devices.yaml, or for the visitor's devices and cap."""
    d = data()
    try:
        config = _site_from(site)
    except ValidationError as exc:
        return {"ok": False, "errors": _errors(exc)}
    the_day = date.fromisoformat(day)
    tz, devices, cap = d.tz, config.devices, config.power_cap_kw

    previous = plan_day(devices, d.grid, the_day - timedelta(days=1), tz, cap)
    result = plan_day(
        devices,
        d.grid,
        the_day,
        tz,
        cap,
        existing_load=previous.load,
        existing_baseline_load=previous.baseline_load,
    )

    axis = _Axis(result.slots)
    order = [dev.name for dev in planning_order(devices, the_day, tz)]
    day_start, day_end = day_bounds(the_day, tz)
    in_horizon = [s.start for s in result.slots]
    items = []
    for item in result.devices:
        dev = item.device
        items.append(
            {
                "name": dev.name,
                "power_kw": _number(dev.power_kw),
                "run_time": dev.run_time,
                "run_label": format_minutes(dev.run_time),
                "energy_kwh": _number(dev.energy_kwh),
                "contiguous": dev.contiguous,
                "min_block": dev.min_block,
                "window": [axis.at(item.window_start), axis.at(item.window_end)],
                "window_text": [clock(item.window_start, tz), clock(item.window_end, tz)],
                "order": order.index(dev.name),
                "planned": item.planned,
                "problem": PROBLEMS.get(item.problem or "", item.problem),
                "blocks": axis.blocks(item.blocks, tz),
                "baseline": axis.blocks(item.baseline, tz),
                "cost": _money(item.cost),
                "baseline_cost": _money(item.baseline_cost),
                "saving": _money(item.saving),
            }
        )

    return {
        "ok": True,
        "day": the_day.isoformat(),
        "hours": result.hours,
        "dst_note": dst_note(result),
        "power_cap_kw": _number(cap),
        "slots": [
            {
                "t": s.start.astimezone(UTC).isoformat(),
                "label": clock(s.start, tz),
                "price": float(s.price),
                "ct": ct_per_kwh(s.price, 2),
            }
            for s in result.slots
        ],
        "day_range": [axis.at(day_start), axis.at(day_end)],
        "ticks": _ticks(result),
        "devices": items,
        "order": order,
        "totals": {
            "cost": _money(result.cost),
            "baseline": _money(result.baseline_cost),
            "saving": _money(result.saving),
            "percent": _percent(result.saving_percent),
            "planned": len(result.planned),
            "devices": len(result.devices),
        },
        "peak_kw": _number(peak_load({t: result.load.get(t, Decimal(0)) for t in in_horizon})),
        "baseline_peak_kw": _number(
            peak_load({t: result.baseline_load.get(t, Decimal(0)) for t in in_horizon})
        ),
        "message": format_plan(result, d.fixture.bidding_zone, attribution(d)),
    }
