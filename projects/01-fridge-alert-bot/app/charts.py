"""PNG temperature charts for /history.

Uses the object-oriented Matplotlib API (Figure + Agg canvas) instead of pyplot:
pyplot keeps global state and is not safe to call from worker threads.
"""

from io import BytesIO
from zoneinfo import ZoneInfo

from matplotlib.dates import DateFormatter
from matplotlib.figure import Figure

from app.models import Point


def render_history_png(
    sensor_id: str, points: list[Point], limit: float, tz: ZoneInfo, hours: int
) -> bytes:
    fig = Figure(figsize=(8, 4), dpi=120)
    ax = fig.subplots()

    if points:
        times = [p.ts.astimezone(tz) for p in points]
        temps = [p.temperature for p in points]
        ax.plot(times, temps, color="#1f6feb", linewidth=1.6, label="Temperature")
        ax.fill_between(
            times,
            temps,
            limit,
            where=[t > limit for t in temps],
            color="#d1242f",
            alpha=0.25,
            interpolate=True,
            label="Above limit",
        )
        ax.xaxis.set_major_formatter(DateFormatter("%H:%M", tz=tz))
    else:
        ax.text(
            0.5,
            0.5,
            "No readings in this period",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=12,
            color="#57606a",
        )

    ax.axhline(limit, color="#d1242f", linestyle="--", linewidth=1.2, label=f"Limit {limit:.1f} °C")
    ax.set_title(f"{sensor_id} — last {hours} h")
    ax.set_ylabel("°C")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()

    buffer = BytesIO()
    fig.savefig(buffer, format="png")
    return buffer.getvalue()
