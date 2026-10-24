"""Telegram message texts (HTML parse mode)."""

from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from app.alerts import AlertEvent, EventKind, SensorState
from app.models import SensorStatus
from app.report import Report

STATE_ICONS = {SensorState.OK: "🟢", SensorState.PENDING: "🟡", SensorState.ALERT: "🔴"}
STALE_ICON = "⚪"


def format_duration(value: timedelta) -> str:
    seconds = int(value.total_seconds())
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


def _clock(value: datetime, tz: ZoneInfo) -> str:
    return value.astimezone(tz).strftime("%H:%M")


def format_event(event: AlertEvent, tz: ZoneInfo) -> str:
    name = escape(event.sensor_id)
    if event.kind is EventKind.ALERT:
        return (
            f"🚨 <b>Fridge alert: {name}</b>\n"
            f"Temperature: <b>{event.temperature:.1f} °C</b> (limit {event.limit:.1f} °C)\n"
            f"Above the limit for {format_duration(event.duration)} "
            f"(since {_clock(event.breach_started_at, tz)}).\n"
            "Check the door, the seal and the compressor."
        )
    return (
        f"✅ <b>Back to normal: {name}</b>\n"
        f"Temperature: {event.temperature:.1f} °C (limit {event.limit:.1f} °C)\n"
        f"The incident lasted {format_duration(event.duration)}, "
        f"peak {event.peak_temperature:.1f} °C."
    )


def format_status(statuses: list[SensorStatus]) -> str:
    if not statuses:
        return "No sensors yet. They appear automatically after the first reading."
    lines = ["<b>Fridge status</b>"]
    for item in statuses:
        sensor = item.sensor
        name = escape(sensor.sensor_id)
        if sensor.last_temperature is None or item.age is None:
            lines.append(f"{STALE_ICON} {name} — no data yet (limit {sensor.limit:.1f} °C)")
            continue
        icon = STALE_ICON if item.stale else STATE_ICONS[sensor.alert.state]
        note = (
            f"no data for {format_duration(item.age)}"
            if item.stale
            else f"{format_duration(item.age)} ago"
        )
        lines.append(
            f"{icon} {name} — {sensor.last_temperature:.1f} °C (limit {sensor.limit:.1f}) · {note}"
        )
    lines.append("\n🟢 ok · 🟡 above limit, waiting · 🔴 alert · ⚪ no data")
    return "\n".join(lines)


def format_report(report: Report, tz: ZoneInfo) -> str:
    period = (
        f"{report.since.astimezone(tz):%d %b %H:%M} - {report.until.astimezone(tz):%d %b %H:%M}"
    )
    lines = [f"📋 <b>Daily report</b>\n{period}"]
    if not report.sensors:
        lines.append("\nNo sensors yet.")
    for s in report.sensors:
        name = escape(s.sensor_id)
        if not s.readings or s.min_c is None or s.avg_c is None or s.max_c is None:
            lines.append(f"\n<b>{name}</b>: no readings in this period")
            continue
        flag = "⚠️ " if s.incidents else ""
        lines.append(
            f"\n{flag}<b>{name}</b> (limit {s.limit:.1f} °C)\n"
            f"min {s.min_c:.1f} · avg {s.avg_c:.1f} · max {s.max_c:.1f} °C\n"
            f"above limit: {format_duration(s.time_above)} · incidents: {s.incidents}"
        )
    return "\n".join(lines)
