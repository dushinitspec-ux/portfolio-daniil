"""Business logic shared by the HTTP API and the Telegram bot."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from app.alerts import AlertEvent, AlertRules, EventKind, SensorState, evaluate
from app.charts import render_history_png
from app.config import Settings
from app.db import Repository
from app.messages import format_event, format_report
from app.models import Point, ReadingIn, Sensor, SensorStatus
from app.notifier import Notifier
from app.report import Report, summarize

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


class SensorNotFoundError(LookupError):
    pass


class FutureReadingError(ValueError):
    pass


# Sensor clocks drift; allow a little, reject readings from the future beyond that.
MAX_CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class IngestResult:
    sensor_id: str
    state: SensorState
    stored: bool
    event: AlertEvent | None


class FridgeService:
    def __init__(
        self,
        repo: Repository,
        notifier: Notifier,
        settings: Settings,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repo = repo
        self._notifier = notifier
        self._settings = settings
        self._clock = clock
        self._rules = AlertRules(
            delay=timedelta(minutes=settings.alert_delay_minutes),
            hysteresis=settings.recovery_hysteresis_c,
        )
        # One lock for the read-evaluate-write cycle: two concurrent requests for the
        # same sensor must not both see the old state and send the same alert twice.
        self._lock = asyncio.Lock()

    # Readings

    def _check_timestamps(self, readings: list[ReadingIn]) -> None:
        latest_allowed = self._clock() + MAX_CLOCK_SKEW
        for reading in readings:
            if reading.timestamp > latest_allowed:
                raise FutureReadingError(
                    f"{reading.sensor_id}: timestamp {reading.timestamp.isoformat()} "
                    "is in the future, check the sensor clock"
                )

    async def ingest(self, reading: ReadingIn) -> IngestResult:
        self._check_timestamps([reading])
        async with self._lock, self._repo.transaction():
            result = await self._ingest_unlocked(reading)
        if result.event:
            await self._notify(result.event)
        return result

    async def ingest_many(self, readings: list[ReadingIn]) -> list[IngestResult]:
        self._check_timestamps(readings)
        ordered = sorted(readings, key=lambda r: r.timestamp)
        async with self._lock, self._repo.transaction():
            results = [await self._ingest_unlocked(r) for r in ordered]
        for result in results:
            if result.event:
                await self._notify(result.event)
        return results

    async def _ingest_unlocked(self, reading: ReadingIn) -> IngestResult:
        sensor = await self._repo.get_sensor(reading.sensor_id)
        if sensor is None:
            sensor = await self._repo.create_sensor(
                reading.sensor_id, self._settings.default_limit_c
            )

        stored = await self._repo.add_reading(
            reading.sensor_id, reading.temperature, reading.timestamp
        )
        # Late or repeated readings go to history but must not move the state backwards.
        if not stored or (sensor.last_seen_at and reading.timestamp <= sensor.last_seen_at):
            return IngestResult(sensor.sensor_id, sensor.alert.state, stored, None)

        new_state, event = evaluate(
            sensor.alert,
            sensor_id=sensor.sensor_id,
            temperature=reading.temperature,
            at=reading.timestamp,
            limit=sensor.limit,
            rules=self._rules,
        )
        sensor = replace(
            sensor,
            alert=new_state,
            last_temperature=reading.temperature,
            last_seen_at=reading.timestamp,
        )
        await self._repo.save_sensor(sensor)
        if event:
            await self._record_incident(event)
        return IngestResult(sensor.sensor_id, new_state.state, stored, event)

    async def _record_incident(self, event: AlertEvent) -> None:
        if event.kind is EventKind.ALERT:
            await self._repo.open_incident(
                event.sensor_id,
                started_at=event.breach_started_at,
                alerted_at=event.at,
                peak_temperature=event.peak_temperature,
                limit=event.limit,
            )
        else:
            await self._repo.close_incident(event.sensor_id, event.at, event.peak_temperature)

    async def _notify(self, event: AlertEvent) -> None:
        age = self._clock() - event.at
        if age > timedelta(minutes=self._settings.alert_max_age_minutes):
            # Old data uploaded late (e.g. a sensor that was offline): keep the incident
            # in the history, but do not wake anyone up about something long finished.
            logger.info("Skipping notification for old %s event on %s", event.kind, event.sensor_id)
            return
        try:
            await self._notifier.send(format_event(event, self._settings.tz))
        except Exception:
            # A Telegram outage must never make the API reject sensor readings.
            logger.exception("Could not send %s notification for %s", event.kind, event.sensor_id)

    # Sensors

    async def statuses(self) -> list[SensorStatus]:
        now = self._clock()
        stale_after = timedelta(minutes=self._settings.stale_after_minutes)
        result = []
        for sensor in await self._repo.list_sensors():
            age = now - sensor.last_seen_at if sensor.last_seen_at else None
            result.append(SensorStatus(sensor, stale=age is None or age > stale_after, age=age))
        return result

    async def sensor_ids(self) -> list[str]:
        return [s.sensor_id for s in await self._repo.list_sensors()]

    async def get_sensor(self, sensor_id: str) -> Sensor:
        sensor = await self._repo.get_sensor(sensor_id)
        if sensor is None:
            raise SensorNotFoundError(sensor_id)
        return sensor

    async def set_limit(self, sensor_id: str, limit: float) -> Sensor:
        """Change a limit. Unknown sensors are created, so limits can be set up in advance."""
        async with self._lock, self._repo.transaction():
            sensor = await self._repo.get_sensor(sensor_id)
            if sensor is None:
                sensor = await self._repo.create_sensor(sensor_id, limit)
            else:
                sensor = replace(sensor, limit=limit)
                await self._repo.save_sensor(sensor)
        return sensor

    # History and reports

    async def history(self, sensor_id: str, hours: int) -> tuple[Sensor, list[Point]]:
        sensor = await self.get_sensor(sensor_id)
        now = self._clock()
        # Include readings a sensor with a fast clock sent "from the future" - we accepted them.
        points = await self._repo.readings(
            sensor_id, now - timedelta(hours=hours), now + MAX_CLOCK_SKEW
        )
        return sensor, points

    async def history_chart(self, sensor_id: str, hours: int) -> bytes:
        sensor, points = await self.history(sensor_id, hours)
        # Rendering takes ~100 ms of CPU; keep it off the event loop.
        return await asyncio.to_thread(
            render_history_png, sensor_id, points, sensor.limit, self._settings.tz, hours
        )

    async def report(self, hours: int = 24) -> Report:
        until = self._clock()
        since = until - timedelta(hours=hours)
        incidents = await self._repo.incidents(since, until)
        summaries = []
        for sensor in await self._repo.list_sensors():
            points = await self._repo.readings(sensor.sensor_id, since, until)
            summaries.append(summarize(sensor.sensor_id, sensor.limit, points, incidents, until))
        return Report(since=since, until=until, sensors=summaries)

    async def send_daily_report(self) -> None:
        report = await self.report()
        try:
            await self._notifier.send(format_report(report, self._settings.tz))
        except Exception:
            logger.exception("Could not send the daily report")
