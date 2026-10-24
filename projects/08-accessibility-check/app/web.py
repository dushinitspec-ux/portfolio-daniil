"""Web UI (server-rendered HTML) and a small JSON API."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import __version__
from app.export import render_html, render_json
from app.models import ScanReport, ScanStatus
from app.rules import RULES
from app.samples import SAMPLES, sample_routes
from app.service import ScanService
from app.urls import InvalidURL, TargetNotAllowed
from app.views import report_view

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")


class ScanRequest(BaseModel):
    url: str
    max_pages: int | None = Field(default=None, ge=1, le=200)


def create_app(service: ScanService) -> FastAPI:
    app = FastAPI(title="Accessibility Check", version=__version__)
    # The demo shop and robots.txt, also used by the in-process demo crawl.
    for route in sample_routes():
        app.router.routes.append(route)

    async def index_context(error: str | None = None, url: str = "") -> dict[str, Any]:
        samples = {name: await service.repo.latest_sample(name) for name in SAMPLES}
        return {
            "recent": await service.repo.recent(15),
            "demo": service.settings.demo_mode,
            "samples": SAMPLES,
            "sample_reports": samples,
            "max_pages": service.settings.max_pages,
            "rule_count": len(RULES),
            "error": error,
            "url": url,
        }

    async def load(report_id: int) -> ScanReport:
        report = await service.repo.get(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return report

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "index.html", await index_context())

    @app.post("/scan", response_model=None)
    async def scan(
        request: Request,
        url: Annotated[str, Form()],
        max_pages: Annotated[int | None, Form(ge=1, le=200)] = None,
    ) -> Response:
        try:
            report_id = await service.start(url, max_pages)
        except (InvalidURL, TargetNotAllowed) as exc:
            context = await index_context(error=str(exc), url=url)
            return TEMPLATES.TemplateResponse(request, "index.html", context, status_code=400)
        return RedirectResponse(f"/reports/{report_id}", status_code=303)

    @app.post("/demo/{name}")
    async def scan_sample(name: str) -> RedirectResponse:
        if name not in SAMPLES:
            raise HTTPException(status_code=404, detail="Unknown sample")
        report_id = await service.start_sample(name)
        return RedirectResponse(f"/reports/{report_id}", status_code=303)

    @app.get("/reports/{report_id}", response_class=HTMLResponse)
    async def report_page(request: Request, report_id: int) -> HTMLResponse:
        report = await load(report_id)
        if report.status is ScanStatus.RUNNING:
            row = await service.repo.get_row(report_id)
            context = {"report": report, "pages_done": row.pages if row else 0}
            return TEMPLATES.TemplateResponse(request, "running.html", context)
        context = report_view(report)
        if report.sample:
            other = "fixed" if report.sample == "broken" else "broken"
            context["other_sample"] = (other, await service.repo.latest_sample(other))
        return TEMPLATES.TemplateResponse(request, "report.html", context)

    def download(report_id: int, extension: str) -> dict[str, str]:
        name = f"accessibility-report-{report_id}.{extension}"
        return {"Content-Disposition": f'attachment; filename="{name}"'}

    @app.get("/reports/{report_id}/export.json")
    async def export_json(report_id: int) -> Response:
        report = await load(report_id)
        return Response(
            render_json(report), media_type="application/json", headers=download(report_id, "json")
        )

    @app.get("/reports/{report_id}/export.html", response_class=HTMLResponse)
    async def export_html(report_id: int) -> HTMLResponse:
        report = await load(report_id)
        return HTMLResponse(render_html(report), headers=download(report_id, "html"))

    @app.post("/reports/{report_id}/explain")
    async def explain(report_id: int, language: Annotated[str, Form()] = "en") -> RedirectResponse:
        await load(report_id)
        await service.explain(report_id, language)
        return RedirectResponse(f"/reports/{report_id}#explanation", status_code=303)

    @app.post("/api/scans", status_code=202)
    async def api_start(body: ScanRequest) -> dict[str, Any]:
        try:
            report_id = await service.start(body.url, body.max_pages)
        except (InvalidURL, TargetNotAllowed) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"id": report_id, "status": "running", "report": f"/api/scans/{report_id}"}

    @app.get("/api/scans/{report_id}")
    async def api_report(report_id: int) -> JSONResponse:
        report = await load(report_id)
        return JSONResponse(report.model_dump(mode="json"))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
