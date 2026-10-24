from datetime import timedelta

from app.models import Incident, Point
from app.report import summarize, time_above_limit
from tests.conftest import T0


def points(*pairs: tuple[float, float]) -> list[Point]:
    return [Point(T0 + timedelta(minutes=m), t) for m, t in pairs]


def test_time_above_limit_sums_intervals() -> None:
    data = points((0, 3.0), (1, 6.0), (2, 6.0), (3, 4.0), (4, 6.0), (5, 3.0))
    assert time_above_limit(data, 5.0, until=T0 + timedelta(minutes=6)) == timedelta(minutes=3)


def test_gap_in_data_is_capped() -> None:
    # The sensor went silent for two hours while warm: count at most 10 minutes of that.
    data = points((0, 6.0), (120, 3.0))
    assert time_above_limit(data, 5.0, until=T0 + timedelta(hours=3)) == timedelta(minutes=10)


def test_last_reading_counts_until_end_of_period() -> None:
    data = points((0, 3.0), (10, 7.0))
    assert time_above_limit(data, 5.0, until=T0 + timedelta(minutes=14)) == timedelta(minutes=4)


def test_summarize() -> None:
    data = points((0, 2.0), (1, 4.0), (2, 6.0))
    incidents = [
        Incident("fridge-1", T0, T0, None, 9.0, 5.0),
        Incident("other", T0, T0, None, 9.0, 5.0),
    ]
    summary = summarize("fridge-1", 5.0, data, incidents, until=T0 + timedelta(minutes=3))
    assert (summary.min_c, summary.avg_c, summary.max_c) == (2.0, 4.0, 6.0)
    assert summary.incidents == 1
    assert summary.readings == 3


def test_summarize_without_data() -> None:
    summary = summarize("fridge-1", 5.0, [], [], until=T0)
    assert summary.min_c is None
    assert summary.time_above == timedelta()
