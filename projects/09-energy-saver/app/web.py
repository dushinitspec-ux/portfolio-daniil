"""The plan page (server-rendered HTML with an inline SVG chart) and a JSON API."""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.chart import render_svg
from app.devices import format_minutes
from app.messages import blocks_text, ct_per_kwh, day_title, dst_note, kw, money, percent
from app.planner import DayPlan, peak_load
from app.prices import day_bounds
from app.scheduler import preview_switching
from app.service import PlanService
from app.shelly import ShellyController

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")


@dataclass(frozen=True)
class Row:
    name: str
    power: str
    run_time: str
    window: str
    mode: str
    planned: str
    baseline: str
    cost: str
    baseline_cost: str
    saving: str
    problem: str | None
    shelly: str


def rows(plan: DayPlan) -> list[Row]:
    result = []
    for item in plan.devices:
        d = item.device
        result.append(
            Row(
                name=d.name,
                power=kw(d.power_kw),
                run_time=format_minutes(d.run_time),
                window=d.window_label,
                mode=d.mode_label,
                planned=blocks_text(item.blocks, plan.tz),
                baseline=blocks_text(item.baseline, plan.tz),
                cost=money(item.cost),
                baseline_cost=money(item.baseline_cost),
                saving=money(item.saving),
                problem=item.problem,
                shelly=d.shelly.host if d.shelly else "",
            )
        )
    return result


def price_stats(plan: DayPlan) -> tuple[str, str]:
    """Lowest and highest price of the day itself (not of the evening before)."""
    start, end = day_bounds(plan.day, plan.tz)
    day_slots = [s for s in plan.slots if start <= s.start < end]
    if not day_slots:
        return "—", "—"
    low = min(day_slots, key=lambda s: s.price)
    high = max(day_slots, key=lambda s: s.price)
    return ct_per_kwh(low.price), ct_per_kwh(high.price)


def create_app(
    service: PlanService,
    bidding_zone: str,
    demo: bool = False,
    controller: ShellyController | None = None,
) -> FastAPI:
    app = FastAPI(title="Energy Saver", version="0.1.0")

    async def resolve(day: date | None) -> date:
        if day is None:
            return await service.default_day()
        if day > service.today() + timedelta(days=1):
            raise HTTPException(404, "Day-ahead prices exist at most for tomorrow.")
        return day

    async def view(day: date) -> dict[str, Any]:
        plan = await service.plan(day)
        cached = await service.cached_days()
        last = service.today() + timedelta(days=1)
        if demo and cached:
            last = min(last, cached[1])
        low, high = price_stats(plan)
        return {
            "plan": plan,
            "title": day_title(plan),
            "rows": rows(plan),
            "chart": Markup(render_svg(plan)),
            "dst_note": dst_note(plan),
            "cost": money(plan.cost),
            "baseline_cost": money(plan.baseline_cost),
            "saving": money(plan.saving),
            "saving_percent": percent(plan.saving_percent),
            "low": low,
            "high": high,
            "hours": f"{plan.hours:g}",
            "cap": kw(plan.power_cap_kw) if plan.power_cap_kw else None,
            "peak": kw(peak_load(plan.load)) if plan.load else None,
            "prev_day": day - timedelta(days=1),
            "next_day": day + timedelta(days=1) if day < last else None,
            "attribution": await service.attribution(),
            "bidding_zone": bidding_zone,
            "site": service.site.site,
            "demo": demo,
            "shelly_mode": "dry run" if controller is None or controller.dry_run else "live",
            "switching": await preview_switching(
                plan, ShellyController(None, service.site.devices, dry_run=True)
            ),
        }

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, day: date | None = None) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "index.html", await view(await resolve(day)))

    @app.get("/chart.svg")
    async def chart(day: date | None = None) -> Response:
        plan = await service.plan(await resolve(day))
        return Response(render_svg(plan), media_type="image/svg+xml")

    @app.get("/api/plan")
    async def api_plan(day: date | None = None) -> dict[str, Any]:
        plan = await service.plan(await resolve(day))
        return {
            "day": plan.day.isoformat(),
            "bidding_zone": bidding_zone,
            "timezone": str(plan.tz),
            "hours": plan.hours,
            "cost_eur": str(plan.cost),
            "baseline_cost_eur": str(plan.baseline_cost),
            "saving_eur": str(plan.saving),
            "saving_percent": None
            if plan.saving_percent is None
            else round(float(plan.saving_percent), 2),
            "devices": [
                {
                    "name": item.device.name,
                    "problem": item.problem,
                    "blocks": [
                        {"start": b.start.isoformat(), "end": b.end.isoformat()}
                        for b in item.blocks
                    ],
                    "baseline": [
                        {"start": b.start.isoformat(), "end": b.end.isoformat()}
                        for b in item.baseline
                    ],
                    "cost_eur": None if item.cost is None else str(item.cost),
                    "baseline_cost_eur": None
                    if item.baseline_cost is None
                    else str(item.baseline_cost),
                }
                for item in plan.devices
            ],
            "attribution": await service.attribution(),
        }

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
