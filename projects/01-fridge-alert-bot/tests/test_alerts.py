from datetime import timedelta

from app.alerts import AlertEvent, AlertRules, AlertState, EventKind, SensorState, evaluate
from tests.conftest import T0

RULES = AlertRules(delay=timedelta(minutes=5), hysteresis=0.5)


def run(
    readings: list[tuple[float, float]], limit: float = 5.0
) -> tuple[AlertState, list[AlertEvent]]:
    """Feed (minute, temperature) pairs through the state machine."""
    state = AlertState()
    events = []
    for minute, temp in readings:
        state, event = evaluate(
            state,
            sensor_id="fridge-1",
            temperature=temp,
            at=T0 + timedelta(minutes=minute),
            limit=limit,
            rules=RULES,
        )
        if event:
            events.append(event)
    return state, events


def test_normal_temperature_stays_ok() -> None:
    state, events = run([(0, 3.0), (1, 4.9), (2, 5.0)])
    assert state.state is SensorState.OK
    assert events == []


def test_short_spike_does_not_alert() -> None:
    # Someone opened the door for two minutes.
    state, events = run([(0, 3.0), (1, 7.5), (2, 6.0), (3, 4.0)])
    assert state.state is SensorState.OK
    assert events == []


def test_alert_after_delay() -> None:
    state, events = run([(0, 6.0), (2, 6.5), (4, 7.0), (5, 7.2)])
    assert state.state is SensorState.ALERT
    assert len(events) == 1
    assert events[0].kind is EventKind.ALERT
    assert events[0].duration == timedelta(minutes=5)
    assert events[0].peak_temperature == 7.2


def test_no_alert_just_before_delay() -> None:
    state, events = run([(0, 6.0), (4.9, 6.5)])
    assert state.state is SensorState.PENDING
    assert events == []


def test_alert_is_sent_once_per_incident() -> None:
    _, events = run([(m, 8.0) for m in range(0, 60)])
    assert [e.kind for e in events] == [EventKind.ALERT]


def test_recovery_needs_hysteresis() -> None:
    # 4.8 is below the limit but inside the 0.5 °C hysteresis band: still an alert.
    state, events = run([(0, 6.0), (5, 9.0), (10, 4.8)])
    assert state.state is SensorState.ALERT
    assert [e.kind for e in events] == [EventKind.ALERT]

    state, events = run([(0, 6.0), (5, 9.0), (10, 4.8), (12, 4.4)])
    assert state.state is SensorState.OK
    recovered = events[-1]
    assert recovered.kind is EventKind.RECOVERED
    assert recovered.duration == timedelta(minutes=12)
    assert recovered.peak_temperature == 9.0


def test_hovering_at_limit_does_not_spam() -> None:
    # After an alert the temperature wobbles around the limit for an hour.
    wobble = [(6 + m, 5.3 if m % 2 else 4.8) for m in range(60)]
    _, events = run([(0, 6.0), (5, 6.0), *wobble])
    assert [e.kind for e in events] == [EventKind.ALERT]


def test_pending_restarts_after_dip_below_limit() -> None:
    _, events = run([(0, 6.0), (3, 4.0), (4, 6.0), (8, 6.0)])
    assert events == []  # only 4 minutes since the second breach started
    _, events = run([(0, 6.0), (3, 4.0), (4, 6.0), (9, 6.0)])
    assert [e.kind for e in events] == [EventKind.ALERT]
    assert events[0].breach_started_at == T0 + timedelta(minutes=4)


def test_freezer_with_negative_temperatures() -> None:
    _, events = run([(0, -14.0), (3, -12.0), (6, -13.0), (10, -16.0)], limit=-15.0)
    assert [e.kind for e in events] == [EventKind.ALERT, EventKind.RECOVERED]
    assert events[1].peak_temperature == -12.0
