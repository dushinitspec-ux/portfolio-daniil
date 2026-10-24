"""The bundled demo website: a deliberately broken "Sample Shop" and its fixed version.

The pages are served by the web app at /samples/broken/ and /samples/fixed/. Demo scans do
not go over the network: the crawler talks to this small ASGI app in-process through
httpx.ASGITransport, so the demo works offline and needs no running server.
"""

from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

SAMPLE_DIR = Path(__file__).parent / "sample_site"
SAMPLES = {
    "broken": "Sample Shop, broken version",
    "fixed": "Sample Shop, fixed version",
}
ROBOTS_TXT = (SAMPLE_DIR / "robots.txt").read_text(encoding="utf-8")


def sample_url(name: str, base_url: str) -> str:
    if name not in SAMPLES:
        raise KeyError(name)
    return f"{base_url.rstrip('/')}/samples/{name}/"


async def robots_txt(request: Request) -> PlainTextResponse:
    return PlainTextResponse(ROBOTS_TXT)


def sample_routes() -> list[Route | Mount]:
    return [
        Route("/robots.txt", robots_txt),
        Mount("/samples", StaticFiles(directory=SAMPLE_DIR, html=True), name="samples"),
    ]


def sample_transport() -> httpx.AsyncBaseTransport:
    return httpx.ASGITransport(app=Starlette(routes=sample_routes()))
