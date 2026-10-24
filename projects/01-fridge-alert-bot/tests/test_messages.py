from datetime import timedelta

from app.alerts import AlertState, SensorState
from app.messages import format_duration, format_status
from app.models import Sensor, SensorStatus


def test_format_duration() -> None:
    assert format_duration(timedelta(seconds=45)) == "45 s"
    assert format_duration(timedelta(minutes=6, seconds=59)) == "6 min"
    assert format_duration(timedelta(hours=2)) == "2 h"
    assert format_duration(timedelta(hours=1, minutes=20)) == "1 h 20 min"


def test_status_shows_icons() -> None:
    ok = Sensor("a", 5.0, AlertState(), last_temperature=3.0)
    alert = Sensor("b", 5.0, AlertState(SensorState.ALERT), last_temperature=9.0)
    text = format_status(
        [
            SensorStatus(ok, stale=False, age=timedelta(minutes=1)),
            SensorStatus(alert, stale=False, age=timedelta(seconds=10)),
            SensorStatus(ok, stale=True, age=timedelta(minutes=40)),
        ]
    )
    assert "🟢 a — 3.0 °C" in text
    assert "🔴 b — 9.0 °C" in text
    assert "⚪ a — 3.0 °C (limit 5.0) · no data for 40 min" in text


def test_status_escapes_html() -> None:
    sensor = Sensor("<b>", 5.0, AlertState())
    assert "&lt;b&gt;" in format_status([SensorStatus(sensor, stale=True, age=None)])
