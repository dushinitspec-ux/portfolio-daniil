"""HTTP API: sensors push readings here; people can also look at status and charts."""

import secrets
from datetime import datetime
from typing import Annotated

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field

from app.alerts import EventKind, SensorState
from app.config import Settings
from app.models import SENSOR_ID_PATTERN, LimitIn, ReadingIn
from app.service import FridgeService, FutureReadingError, SensorNotFoundError

SensorId = Annotated[str, Path(pattern=SENSOR_ID_PATTERN)]
Hours = Annotated[int, Query(ge=1, le=168, description="How many hours back")]


class ReadingOut(BaseModel):
    sensor_id: str
    state: SensorState
    stored: bool = Field(description="False if this exact reading was already received")
    event: EventKind | None = None


class BatchOut(BaseModel):
    received: int
    stored: int
    events: int


class SensorOut(BaseModel):
    sensor_id: str
    limit: float
    state: SensorState
    last_temperature: float | None
    last_seen_at: datetime | None
    stale: bool


class PointOut(BaseModel):
    ts: datetime
    temperature: float


class HistoryOut(BaseModel):
    sensor_id: str
    limit: float
    points: list[PointOut]


class SummaryOut(BaseModel):
    sensor_id: str
    limit: float
    readings: int
    min_c: float | None
    avg_c: float | None
    max_c: float | None
    minutes_above_limit: float
    incidents: int


class ReportOut(BaseModel):
    since: datetime
    until: datetime
    sensors: list[SummaryOut]


def create_app(service: FridgeService, settings: Settings) -> FastAPI:
    app = FastAPI(
        title="Fridge Alert Bot",
        version="0.1.0",
        description="Receives fridge temperature readings and raises Telegram alerts.",
    )

    def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if settings.api_key and not secrets.compare_digest(x_api_key or "", settings.api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")

    protected = [Depends(require_api_key)]

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/readings", status_code=201, dependencies=protected)
    async def post_reading(reading: ReadingIn) -> ReadingOut:
        try:
            result = await service.ingest(reading)
        except FutureReadingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ReadingOut(
            sensor_id=result.sensor_id,
            state=result.state,
            stored=result.stored,
            event=result.event.kind if result.event else None,
        )

    @app.post("/readings/batch", status_code=201, dependencies=protected)
    async def post_batch(readings: Annotated[list[ReadingIn], Body(max_length=10_000)]) -> BatchOut:
        try:
            results = await service.ingest_many(readings)
        except FutureReadingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return BatchOut(
            received=len(results),
            stored=sum(r.stored for r in results),
            events=sum(r.event is not None for r in results),
        )

    @app.get("/sensors")
    async def list_sensors() -> list[SensorOut]:
        return [
            SensorOut(
                sensor_id=s.sensor.sensor_id,
                limit=s.sensor.limit,
                state=s.sensor.alert.state,
                last_temperature=s.sensor.last_temperature,
                last_seen_at=s.sensor.last_seen_at,
                stale=s.stale,
            )
            for s in await service.statuses()
        ]

    @app.put("/sensors/{sensor_id}/limit", dependencies=protected)
    async def put_limit(sensor_id: SensorId, body: LimitIn) -> dict[str, float | str]:
        sensor = await service.set_limit(sensor_id, body.limit)
        return {"sensor_id": sensor.sensor_id, "limit": sensor.limit}

    @app.get("/sensors/{sensor_id}/history")
    async def get_history(sensor_id: SensorId, hours: Hours = 24) -> HistoryOut:
        try:
            sensor, points = await service.history(sensor_id, hours)
        except SensorNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Unknown sensor") from exc
        return HistoryOut(
            sensor_id=sensor.sensor_id,
            limit=sensor.limit,
            points=[PointOut(ts=p.ts, temperature=p.temperature) for p in points],
        )

    @app.get("/sensors/{sensor_id}/chart.png", response_class=Response)
    async def get_chart(sensor_id: SensorId, hours: Hours = 24) -> Response:
        try:
            png = await service.history_chart(sensor_id, hours)
        except SensorNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Unknown sensor") from exc
        return Response(content=png, media_type="image/png")

    @app.get("/report")
    async def get_report(hours: Hours = 24) -> ReportOut:
        report = await service.report(hours)
        return ReportOut(
            since=report.since,
            until=report.until,
            sensors=[
                SummaryOut(
                    sensor_id=s.sensor_id,
                    limit=s.limit,
                    readings=s.readings,
                    min_c=s.min_c,
                    avg_c=None if s.avg_c is None else round(s.avg_c, 2),
                    max_c=s.max_c,
                    minutes_above_limit=round(s.time_above.total_seconds() / 60, 1),
                    incidents=s.incidents,
                )
                for s in report.sensors
            ],
        )

    return app
