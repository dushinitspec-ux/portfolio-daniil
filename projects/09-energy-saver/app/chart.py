"""The price chart as inline SVG: one column per 15 minutes, the planned ones highlighted,
and one row per device with its window, the plan and the baseline.

Server-side SVG instead of matplotlib: no heavy dependency, crisp at any size, it follows
the page's light/dark colours, and every column has a native tooltip (<title>).
The x axis is real time (UTC), labelled in local time, so a 25-hour day is wider and
shows 02:00 twice.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from html import escape
from math import ceil, floor, log10

from app.messages import blocks_text, clock, ct_per_kwh, money
from app.planner import DayPlan
from app.prices import SLOT

WIDTH = 960
LEFT = 150
RIGHT = 16
TOP = 18
PRICE_HEIGHT = 230
AXIS_GAP = 34
ROW = 30

STYLE = """
<style>
  .es-bg { fill: #fcfcfb; }
  .es-grid { stroke: #e1e0d9; stroke-width: 1; }
  .es-axis { stroke: #c3c2b7; stroke-width: 1; }
  .es-day { stroke: #898781; stroke-width: 1; }
  .es-text { fill: #52514e; font: 12px system-ui, -apple-system, "Segoe UI", sans-serif; }
  .es-label { fill: #0b0b0b; font: 600 12px system-ui, -apple-system, "Segoe UI", sans-serif; }
  .es-bar { fill: #c9c8c0; }
  .es-on { fill: #2a78d6; }
  .es-window { fill: #efeee9; }
  .es-plan { fill: #2a78d6; }
  .es-base { fill: #eb6834; }
  @media (prefers-color-scheme: dark) {
    .es-bg { fill: #1a1a19; }
    .es-grid { stroke: #2c2c2a; }
    .es-axis { stroke: #383835; }
    .es-text { fill: #c3c2b7; }
    .es-label { fill: #f0efec; }
    .es-bar { fill: #4a4a46; }
    .es-on, .es-plan { fill: #3987e5; }
    .es-window { fill: #262624; }
    .es-base { fill: #d95926; }
  }
</style>
"""


def nice_step(span: float, target_ticks: int = 5) -> float:
    raw = span / max(target_ticks, 1)
    magnitude = 10 ** floor(log10(raw)) if raw > 0 else 1
    for factor in (1, 2, 2.5, 5, 10):
        if raw <= factor * magnitude:
            return factor * magnitude
    return 10 * magnitude


def ct_value(eur_per_mwh: Decimal) -> float:
    """EUR/MWh -> ct/kWh as a float, for drawing only (money stays Decimal)."""
    return float(eur_per_mwh) / 10


def render_svg(plan: DayPlan) -> str:
    tz = plan.tz
    start, end = plan.horizon_start, plan.horizon_end
    plot_w = WIDTH - LEFT - RIGHT
    total = (end - start) / timedelta(minutes=1)

    def x(at: datetime) -> float:
        return LEFT + plot_w * ((at - start) / timedelta(minutes=1)) / total

    values = [ct_value(s.price) for s in plan.slots] or [0.0]
    # Below a hundredth of a cent counts as zero: -0.01 EUR/MWh should not add a whole
    # empty band of negative axis.
    low, high = round(min(values), 2), round(max(values), 2)
    step = nice_step(max(high, 0) - min(low, 0) or 1)
    y_min = floor(low / step) * step if low < 0 else 0.0
    y_max = max(step, ceil(high / step) * step)

    def y(value: float) -> float:
        return TOP + PRICE_HEIGHT * (y_max - value) / (y_max - y_min)

    rows_top = TOP + PRICE_HEIGHT + AXIS_GAP
    height = rows_top + ROW * len(plan.devices) + 8
    on_slots = {
        b.start + i * SLOT
        for d in plan.devices
        for b in d.blocks
        for i in range((b.end - b.start) // SLOT)
    }

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" '
        f'role="img" aria-labelledby="es-title es-desc" class="es-chart">',
        f'<title id="es-title">Day-ahead prices and plan for {plan.day.isoformat()}</title>',
        '<desc id="es-desc">Columns: spot price per 15 minutes in ct/kWh, planned slots '
        "highlighted. Rows: each device's window, planned runs and the baseline.</desc>",
        STYLE,
        f'<rect class="es-bg" x="0" y="0" width="{WIDTH}" height="{height}"/>',
    ]

    # Horizontal gridlines and price labels
    tick = y_min
    while tick <= y_max + 1e-9:
        ty = y(tick)
        cls = "es-axis" if abs(tick) < 1e-9 else "es-grid"
        out.append(
            f'<line class="{cls}" x1="{LEFT}" x2="{WIDTH - RIGHT}" y1="{ty:.1f}" y2="{ty:.1f}"/>'
        )
        out.append(
            f'<text class="es-text" x="{LEFT - 8}" y="{ty + 4:.1f}" '
            f'text-anchor="end">{tick:g}</text>'
        )
        tick += step
    out.append(
        f'<text class="es-text" x="{LEFT - 8}" y="{TOP - 6}" text-anchor="end">ct/kWh</text>'
    )

    # Price columns, one per 15 minutes
    slot_w = plot_w * 15 / total
    gap = 2 if slot_w >= 6 else 1
    zero = y(0)
    for slot in plan.slots:
        value = ct_value(slot.price)
        top, bottom = (y(value), zero) if value >= 0 else (zero, y(value))
        cls = "es-on" if slot.start in on_slots else "es-bar"
        label = (
            f"{clock(slot.start, tz)}–{clock(slot.end, tz)}: "
            f"{ct_per_kwh(slot.price, 2)} ct/kWh ({slot.price} €/MWh)"
        )
        out.append(
            f'<rect class="{cls}" x="{x(slot.start) + gap / 2:.1f}" y="{top:.1f}" '
            f'width="{max(slot_w - gap, 1):.1f}" height="{max(bottom - top, 0.5):.1f}">'
            f"<title>{escape(label)}</title></rect>"
        )

    # Time axis: every 3 hours of local time, and a line at each local midnight
    axis_y = TOP + PRICE_HEIGHT
    at = start
    while at <= end:
        local = at.astimezone(tz)
        if local.minute == 0 and local.hour % 3 == 0:
            tx = x(at)
            out.append(
                f'<line class="es-axis" x1="{tx:.1f}" x2="{tx:.1f}" y1="{axis_y}" '
                f'y2="{axis_y + 5}"/>'
            )
            # The first and last labels sit inside the plot instead of overflowing it.
            anchor = "start" if at == start else "end" if at == end else "middle"
            out.append(
                f'<text class="es-text" x="{tx:.1f}" y="{axis_y + 18}" '
                f'text-anchor="{anchor}">{local:%H:%M}</text>'
            )
        if local.hour == 0 and local.minute == 0 and start < at < end:
            tx = x(at)
            # Two pieces, so the line does not run through the hour labels.
            for y1, y2 in ((TOP - 4, axis_y), (rows_top - 8, height - 4)):
                out.append(
                    f'<line class="es-day" x1="{tx:.1f}" x2="{tx:.1f}" y1="{y1}" y2="{y2}"/>'
                )
            out.append(
                f'<text class="es-label" x="{tx + 4:.1f}" y="{TOP + 8}">{local:%a %d %b}</text>'
            )
        at += SLOT

    # One row per device: window band, planned runs, baseline underneath
    for row, item in enumerate(plan.devices):
        top = rows_top + row * ROW
        name = escape(item.device.name)
        out.append(
            f'<text class="es-label" x="{LEFT - 8}" y="{top + 14}" text-anchor="end">{name}</text>'
        )
        wx1, wx2 = x(max(item.window_start, start)), x(min(item.window_end, end))
        out.append(
            f'<rect class="es-window" x="{wx1:.1f}" y="{top}" width="{wx2 - wx1:.1f}" '
            f'height="22" rx="3"><title>{name}: window '
            f"{escape(item.device.window_label)}</title></rect>"
        )
        if not item.planned:
            out.append(
                f'<text class="es-text" x="{wx1 + 6:.1f}" y="{top + 15}">'
                f"not planned: {escape(item.problem or '')}</text>"
            )
            continue
        for block in item.blocks:
            bx1, bx2 = x(block.start), x(block.end)
            out.append(
                f'<rect class="es-plan" x="{bx1:.1f}" y="{top + 3}" '
                f'width="{max(bx2 - bx1 - 1, 1):.1f}" height="11" rx="2"><title>{name}: '
                f"{escape(blocks_text([block], tz))}</title></rect>"
            )
        for block in item.baseline:
            bx1, bx2 = x(block.start), x(block.end)
            out.append(
                f'<rect class="es-base" x="{bx1:.1f}" y="{top + 16}" '
                f'width="{max(bx2 - bx1 - 1, 1):.1f}" height="4" rx="1"><title>{name} '
                f"baseline: {escape(blocks_text([block], tz))}, "
                f"{escape(money(item.baseline_cost))}</title></rect>"
            )

    out.append("</svg>")
    return "\n".join(out)
