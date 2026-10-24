"""The web UI and the JSON API, driven through httpx.ASGITransport."""

from collections.abc import AsyncIterator

import httpx
import pytest

from app.config import Settings
from app.db import Repository
from app.explain import FixedTextExplainer
from app.models import CheckStatus, ScanReport, ScanStatus
from app.rules import Page, run_rules
from app.service import ScanService
from app.web import create_app
from tests.conftest import FakeSite, links


@pytest.fixture
async def service(settings: Settings, site: FakeSite) -> AsyncIterator[ScanService]:
    site.routes["https://shop.test/robots.txt"] = (200, {}, "User-agent: *\nDisallow:\n")
    site.page("https://shop.test/", links("/contact"))
    site.page("https://shop.test/contact", '<html><body><input name="q"></body></html>')
    repo = await Repository.connect(settings.database_path)
    yield ScanService(settings, repo, FixedTextExplainer(), transport=site.transport)
    await repo.close()


@pytest.fixture
async def client(service: ScanService) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def finished_report(service: ScanService, client: httpx.AsyncClient, path: str) -> str:
    await service.wait()
    return (await client.get(path)).text


async def test_index_page(client: httpx.AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert '<label for="url">Website address</label>' in resp.text
    assert "Sample Shop, broken version" in resp.text
    assert "not proof of accessibility" in resp.text


async def test_scan_form_redirects_to_the_report(
    client: httpx.AsyncClient, service: ScanService
) -> None:
    resp = await client.post("/scan", data={"url": "https://shop.test/", "max_pages": "5"})
    assert resp.status_code == 303
    location = resp.headers["location"]

    html = await finished_report(service, client, location)

    assert "By WCAG 2.2 success criterion" in html
    assert "Form fields without a label" in html
    assert "Not checked automatically" in html
    report = await service.repo.get(int(location.rsplit("/", 1)[1]))
    assert report is not None and report.status is ScanStatus.DONE
    assert report.options.max_pages == 5


async def test_running_report_page_refreshes_itself(
    client: httpx.AsyncClient, service: ScanService
) -> None:
    report_id = await service.start("https://shop.test/")
    html = (await client.get(f"/reports/{report_id}")).text
    assert 'http-equiv="refresh"' in html
    await service.wait()
    assert 'http-equiv="refresh"' not in (await client.get(f"/reports/{report_id}")).text


async def test_invalid_url_shows_an_error(client: httpx.AsyncClient) -> None:
    resp = await client.post("/scan", data={"url": "ftp://shop.test/"})
    assert resp.status_code == 400
    assert "Only http:// and https://" in resp.text


async def test_private_targets_are_refused_without_a_test_transport(settings: Settings) -> None:
    repo = await Repository.connect(":memory:")
    service = ScanService(settings, repo, FixedTextExplainer())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)), base_url="http://test"
    ) as c:
        resp = await c.post("/scan", data={"url": "http://192.168.1.1/"})
        api = await c.post("/api/scans", json={"url": "http://127.0.0.1:22/"})
    await repo.close()
    assert resp.status_code == 400 and "private or local address" in resp.text
    assert api.status_code == 422


async def test_demo_sample_scan_works_offline(
    client: httpx.AsyncClient, service: ScanService
) -> None:
    resp = await client.post("/demo/broken")
    assert resp.status_code == 303
    html = await finished_report(service, client, resp.headers["location"])
    assert "Sample Shop, broken version" in html
    assert "Images without a text alternative" in html
    assert (await client.post("/demo/unknown")).status_code == 404


async def test_sample_pages_and_robots_are_served(client: httpx.AsyncClient) -> None:
    assert "Disallow: /samples/broken/private/" in (await client.get("/robots.txt")).text
    page = await client.get("/samples/fixed/")
    assert page.status_code == 200 and "Skip to content" in page.text


async def test_exports(client: httpx.AsyncClient, service: ScanService) -> None:
    report_id = await service.start("https://shop.test/")
    await service.wait()

    json_resp = await client.get(f"/reports/{report_id}/export.json")
    html_resp = await client.get(f"/reports/{report_id}/export.html")

    assert "attachment" in json_resp.headers["content-disposition"]
    report = ScanReport.model_validate_json(json_resp.text)
    assert report.summary.pages_analysed == 2
    assert html_resp.headers["content-disposition"].endswith('.html"')
    assert "<style>" in html_resp.text and "<script" not in html_resp.text
    assert "https://shop.test" in html_resp.text


async def test_explain_for_a_shop_owner(client: httpx.AsyncClient, service: ScanService) -> None:
    report_id = await service.start("https://shop.test/")
    await service.wait()

    resp = await client.post(f"/reports/{report_id}/explain", data={"language": "en"})
    assert resp.status_code == 303
    html = (await client.get(f"/reports/{report_id}")).text

    assert "written by fixed texts" in html
    assert "edit text" in html  # the plain-language text of the form-label rule


async def test_api_start_and_poll(client: httpx.AsyncClient, service: ScanService) -> None:
    resp = await client.post("/api/scans", json={"url": "shop.test", "max_pages": 1})
    assert resp.status_code == 202
    await service.wait()
    data = (await client.get(resp.json()["report"])).json()
    assert data["status"] == "done"
    assert data["summary"]["pages_requested"] == 1


async def test_unknown_report_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/reports/999")).status_code == 404
    assert (await client.get("/api/scans/999")).status_code == 404
    assert (await client.get("/healthz")).json() == {"status": "ok"}


async def test_the_ui_passes_its_own_checks(
    client: httpx.AsyncClient, service: ScanService
) -> None:
    await service.start_sample("broken")
    await service.wait()
    pages = [
        (await client.get(path)).text for path in ["/", "/reports/1", "/reports/1/export.html"]
    ]
    for html in pages:
        _, checks = run_rules(Page(html))
        failed = [rule for rule, status in checks.items() if status is not CheckStatus.PASS
                  and status is not CheckStatus.NOT_APPLICABLE]  # fmt: skip
        assert failed == []
