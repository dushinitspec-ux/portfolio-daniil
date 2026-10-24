"""Texts: the daily Telegram plan and the formatting shared with the web page.

Plain text, no Markdown, so a device name with "_" or "*" cannot break the message.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from app.devices import format_minutes
from app.planner import Block, DayPlan, DevicePlan
from app.prices import day_bounds

CENT = Decimal("0.01")


def cents(value: Decimal) -> Decimal:
    """Round to cents; -0.004 becomes 0.00, not "-0.00"."""
    rounded = value.quantize(CENT, ROUND_HALF_UP)
    return abs(rounded) if rounded == 0 else rounded


def money(value: Decimal | None) -> str:
    return "—" if value is None else f"{cents(value):.2f} €"


def ct_per_kwh(eur_per_mwh: Decimal, places: int = 1) -> str:
    """EUR/MWh -> ct/kWh text (divide by 10), never "-0.0"."""
    rounded = (eur_per_mwh / 10).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)
    return f"{abs(rounded) if rounded == 0 else rounded:.{places}f}"


def percent(value: Decimal | None) -> str:
    return "—" if value is None else f"{value.quantize(Decimal('0.1'), ROUND_HALF_UP):.1f} %"


def kw(value: Decimal) -> str:
    return f"{value.normalize():f} kW"


def is_ambiguous(at: datetime, tz: ZoneInfo) -> bool:
    """True for a wall-clock time that happens twice (02:00-03:00 when clocks go back)."""
    local = at.astimezone(tz).replace(tzinfo=None)
    return (
        local.replace(tzinfo=tz, fold=0).utcoffset() != local.replace(tzinfo=tz, fold=1).utcoffset()
    )


def clock(at: datetime, tz: ZoneInfo) -> str:
    """'02:15', or '02:15 CEST' when that wall-clock time happens twice that night."""
    local = at.astimezone(tz)
    text = local.strftime("%H:%M")
    return f"{text} {local.tzname()}" if is_ambiguous(at, tz) else text


def blocks_text(blocks: Iterable[Block], tz: ZoneInfo) -> str:
    return ", ".join(f"{clock(b.start, tz)}–{clock(b.end, tz)}" for b in blocks)


def dst_note(plan: DayPlan) -> str | None:
    """Explain a 23- or 25-hour day, and a night window that crosses the change."""
    start, end = day_bounds(plan.day, plan.tz)
    hours = round((end - start) / timedelta(hours=1))
    if hours == 25:
        return "Clocks go back tonight: this day has 25 hours, 02:00–03:00 happens twice."
    if hours == 23:
        return "Clocks go forward tonight: this day has 23 hours, there is no 02:00–03:00."
    return None


def day_title(plan: DayPlan) -> str:
    return f"{plan.day:%A} {plan.day.day} {plan.day:%b %Y}"


def device_lines(item: DevicePlan, tz: ZoneInfo) -> list[str]:
    d = item.device
    head = f"{d.name} · {kw(d.power_kw)} · {format_minutes(d.run_time)}"
    if not item.planned:
        return [head, f"  not planned: {item.problem}"]
    saving = cents(item.saving or Decimal(0))
    return [
        head,
        f"  {blocks_text(item.blocks, tz)}",
        f"  {money(item.cost)} instead of {money(item.baseline_cost)}"
        + (f", saves {money(saving)}" if saving > 0 else ""),
    ]


def format_plan(plan: DayPlan, bidding_zone: str, attribution: str = "") -> str:
    lines = [f"⚡ Plan for {day_title(plan)} · {bidding_zone} day-ahead"]
    if note := dst_note(plan):
        lines.append(note)
    for item in plan.devices:
        lines.append("")
        lines.extend(device_lines(item, plan.tz))

    lines.append("")
    if plan.planned:
        lines.append(
            f"Expected cost {money(plan.cost)} instead of {money(plan.baseline_cost)} "
            "if every device started when its window opens."
        )
        lines.append(f"Saving {money(plan.saving)} ({percent(plan.saving_percent)}).")
    else:
        lines.append("Nothing could be planned: prices for this day are not published yet.")
    lines.append("Spot price only; grid fees and taxes are the same in every hour.")
    if attribution:
        lines.append(attribution)
    return "\n".join(lines)


def format_not_published(day_text: str, bidding_zone: str) -> str:
    return (
        f"⚠️ Day-ahead prices for {day_text} ({bidding_zone}) are still not published. "
        "Devices with Shelly plugs fall back to starting when their window opens."
    )
