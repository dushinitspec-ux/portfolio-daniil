import asyncio
from datetime import timedelta

import pytest

from app.alerts import EventKind, SensorState
from app.config import Settings
from app.db import Repository
from app.service import FridgeService, FutureReadingError
from tests.conftest import T0, FakeClock, RecordingNotifier, reading


async def test_first_reading_creates_sensor_with_default_limit(service: FridgeService) -> None:
    await service.ingest(reading(0, 3.0, sensor_id="new-fridge"))
    sensor = await service.get_sensor("new-fridge")
    assert sensor.limit == 5.0
    assert sensor.last_temperature == 3.0


async def test_full_incident_sends_alert_and_recovery(
    service: FridgeService, notifier: RecordingNotifier, repo: Repository
) -> None:
    for minute, temp in [(0, 3.0), (1, 6.0), (3, 7.0), (6, 8.5), (9, 6.0), (12, 4.0)]:
        await service.ingest(reading(minute, temp))

    assert len(notifier.messages) == 2
    assert "Fridge alert: fridge-1" in notifier.messages[0]
    assert "8.5 °C" in notifier.messages[0]
    assert "Back to normal" in notifier.messages[1]
    assert "lasted 11 min" in notifier.messages[1]

    incidents = await repo.incidents(T0, T0 + timedelta(hours=1))
    assert len(incidents) == 1
    assert incidents[0].resolved_at == T0 + timedelta(minutes=12)
    assert incidents[0].peak_temperature == 8.5


async def test_duplicate_reading_is_ignored(service: FridgeService) -> None:
    first = await service.ingest(reading(0, 6.0))
    second = await service.ingest(reading(0, 6.0))
    assert first.stored is True
    assert second.stored is False


async def test_late_reading_does_not_move_state_backwards(
    service: FridgeService, notifier: RecordingNotifier
) -> None:
    await service.ingest(reading(0, 8.0))
    await service.ingest(reading(6, 8.0))
    late = await service.ingest(reading(3, 2.0))  # arrives after the 6-minute reading

    assert late.stored is True
    assert late.state is SensorState.ALERT
    assert len(notifier.messages) == 1  # no false "back to normal"


async def test_old_events_are_stored_but_not_notified(
    service: FridgeService, notifier: RecordingNotifier, repo: Repository, clock: FakeClock
) -> None:
    clock.now = T0 + timedelta(hours=3)  # a sensor uploads data that is 3 hours old
    results = await service.ingest_many([reading(m, 9.0) for m in range(0, 10)])

    assert [r.event.kind for r in results if r.event] == [EventKind.ALERT]
    assert notifier.messages == []
    assert len(await repo.incidents(T0, clock.now)) == 1


async def test_future_reading_is_rejected(service: FridgeService, clock: FakeClock) -> None:
    clock.now = T0
    with pytest.raises(FutureReadingError):
        await service.ingest(reading(10, 3.0))


async def test_notifier_failure_does_not_lose_readings(
    repo: Repository, settings: Settings, clock: FakeClock
) -> None:
    class BrokenNotifier:
        async def send(self, text: str) -> None:
            raise ConnectionError("Telegram is down")

    service = FridgeService(repo, BrokenNotifier(), settings, clock=clock)
    for minute in range(0, 7):
        result = await service.ingest(reading(minute, 9.0))
    assert result.state is SensorState.ALERT


async def test_concurrent_requests_send_one_alert(
    service: FridgeService, notifier: RecordingNotifier
) -> None:
    await service.ingest(reading(0, 9.0))
    await asyncio.gather(*(service.ingest(reading(m, 9.0)) for m in range(5, 15)))
    assert len(notifier.messages) == 1


async def test_set_limit_changes_alerting(
    service: FridgeService, notifier: RecordingNotifier
) -> None:
    await service.set_limit("fridge-1", 8.0)
    for minute in range(0, 10):
        await service.ingest(reading(minute, 7.0))
    assert notifier.messages == []


async def test_status_marks_silent_sensors_as_stale(
    service: FridgeService, clock: FakeClock
) -> None:
    clock.now = T0 + timedelta(minutes=30)
    await service.ingest(reading(0, 3.0, sensor_id="quiet"))
    await service.ingest(reading(25, 3.0, sensor_id="chatty"))
    statuses = {s.sensor.sensor_id: s for s in await service.statuses()}
    assert statuses["quiet"].stale is True  # 30 minutes without data
    assert statuses["chatty"].stale is False


async def test_report_counts_time_above_limit_and_incidents(service: FridgeService) -> None:
    await service.ingest_many([reading(m, 9.0 if 2 <= m < 12 else 3.0) for m in range(0, 20)])
    report = await service.report(hours=24)
    summary = report.sensors[0]
    assert summary.time_above == timedelta(minutes=10)
    assert summary.incidents == 1
    assert summary.max_c == 9.0
