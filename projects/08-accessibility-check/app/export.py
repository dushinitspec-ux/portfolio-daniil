"""Standalone exports of a report: one HTML file with inline CSS, and JSON."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import ScanReport
from app.views import report_view

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


def render_html(report: ScanReport) -> str:
    return _ENV.get_template("export.html").render(report_view(report))


def render_json(report: ScanReport) -> str:
    return report.model_dump_json(indent=2)
