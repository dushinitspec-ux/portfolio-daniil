from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.devices import DeviceConfigError, load_site, parse_clock, parse_duration, parse_window
from tests.conftest import ROOT, make_device, site_with


@pytest.mark.parametrize(
    ("text", "minutes"), [("3h", 180), ("45min", 45), ("1h30min", 90), ("1h 15min", 75), (90, 90)]
)
def test_durations(text: str | int, minutes: int) -> None:
    assert parse_duration(text) == minutes


@pytest.mark.parametrize("text", ["", "2", "20min", "1.5h", 0, -15, True])
def test_bad_durations(text: str | int) -> None:
    with pytest.raises(ValueError):
        parse_duration(text)


def test_clock_times() -> None:
    assert parse_clock("06:30") == 390
    assert parse_clock("24:00") == 1440
    for bad in ("6:30", "06:10", "25:00", "noon"):
        with pytest.raises(ValueError):
            parse_clock(bad)


def test_window_crossing_midnight_starts_the_day_before() -> None:
    spec = parse_window("22:00-07:00")
    assert (spec.start_day_offset, spec.start_minute, spec.end_minute) == (-1, 1320, 1860)
    assert spec.minutes == 9 * 60


def test_window_until_midnight_stays_on_the_same_day() -> None:
    assert parse_window("18:00-24:00") == parse_window("18:00-00:00")
    assert parse_window("18:00-00:00").start_day_offset == 0
    assert parse_window("00:00-00:00").minutes == 24 * 60


def test_latest_finish_cuts_the_window() -> None:
    assert parse_window("22:00-07:00", "06:00").end_minute == 1440 + 360
    assert parse_window("09:00-18:00", "17:00").end_minute == 17 * 60
    with pytest.raises(ValueError, match="outside the window"):
        parse_window("09:00-18:00", "08:00")


def test_power_from_yaml_float_is_exact() -> None:
    assert make_device(power_kw=1.1).power_kw == Decimal("1.1")


@pytest.mark.parametrize(
    "fields",
    [
        {"run_time": "10h", "window": "22:00-07:00"},  # longer than the window
        {"run_time": "3h", "window": "22:00-07:00", "latest_finish": "00:30"},
        {"run_time": "1h", "min_block": "2h"},
        {"window": "22:00"},
        {"power_kw": 0},
        {"shelly": {"host": "-c 1 evil"}},
    ],
)
def test_invalid_devices(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_device(**fields)


def test_site_rejects_duplicate_names_and_loads_above_the_cap() -> None:
    with pytest.raises(ValidationError, match="unique"):
        site_with(make_device(name="A"), make_device(name="A"))
    with pytest.raises(ValidationError, match="power_cap_kw"):
        site_with(make_device(power_kw=20), cap="18")


def test_shipped_devices_yaml_is_valid() -> None:
    site = load_site(ROOT / "devices.yaml")
    assert site.power_cap_kw == Decimal(18)
    assert [d.name for d in site.devices][:2] == ["Hot-water boiler", "EV charger"]
    assert all(d.shelly is None or d.shelly.host.startswith("192.0.2.") for d in site.devices)


def test_bad_yaml_gives_a_readable_error(tmp_path: Path) -> None:
    path = tmp_path / "devices.yaml"
    path.write_text("devices:\n  - name: Boiler\n    power_kw: 6\n", encoding="utf-8")
    with pytest.raises(DeviceConfigError, match="has errors"):
        load_site(path)
