import random
from datetime import timedelta

from app.alerts import AlertRules, AlertState, EventKind, SensorState, evaluate
from app.simulation import FridgeModel, Mode, SensorProfile
from tests.conftest import T0

PROFILE = SensorProfile("kitchen-fridge-1", setpoint_c=3.5, limit_c=5.0)
STEP_S = 30


def simulate(model: FridgeModel, hours: float) -> tuple[list[EventKind], set[SensorState]]:
    """Run the model through the real alert rules and collect what happened."""
    state = AlertState()
    events: list[EventKind] = []
    seen_states: set[SensorState] = set()
    for i in range(int(hours * 3600 / STEP_S)):
        state, event = evaluate(
            state,
            sensor_id=PROFILE.sensor_id,
            temperature=model.step(STEP_S),
            at=T0 + timedelta(seconds=i * STEP_S),
            limit=PROFILE.limit_c,
            rules=AlertRules(),
        )
        seen_states.add(state.state)
        if event:
            events.append(event.kind)
    return events, seen_states


def test_same_seed_gives_same_data() -> None:
    a = FridgeModel(PROFILE, random.Random(1))
    b = FridgeModel(PROFILE, random.Random(1))
    assert [a.step(STEP_S) for _ in range(100)] == [b.step(STEP_S) for _ in range(100)]


def test_single_door_opening_does_not_alert() -> None:
    model = FridgeModel(PROFILE, random.Random(7), door_per_hour=0, failures_per_day=0)
    model.force_door(duration_s=120)  # the longest opening the simulator generates
    events, seen = simulate(model, hours=1)
    assert SensorState.PENDING in seen  # the door does push it over the limit...
    assert events == []  # ...but not long enough to wake anyone up


def test_busy_kitchen_rarely_raises_false_alarms() -> None:
    # Three openings an hour for a week, no real failures. Only openings stacked close
    # together may keep the fridge warm for 5 minutes; that should be rare.
    model = FridgeModel(PROFILE, random.Random(7), door_per_hour=3, failures_per_day=0)
    events, _ = simulate(model, hours=24 * 7)
    assert events.count(EventKind.ALERT) <= 2


def test_compressor_failure_alerts_and_recovers() -> None:
    model = FridgeModel(PROFILE, random.Random(7), door_per_hour=0, failures_per_day=0)
    model.force_failure(duration_s=30 * 60)
    events, _ = simulate(model, hours=2)
    assert events == [EventKind.ALERT, EventKind.RECOVERED]
    assert model.mode is Mode.NORMAL
