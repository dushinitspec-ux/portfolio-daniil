from collections.abc import AsyncIterator
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.copilot import Copilot
from app.db import Repository
from app.demo import SAMPLE_QUESTIONS, seed
from app.evaluate import run as run_eval
from app.knowledge import Document
from app.llm.demo import DemoLLM, plain
from app.retrieval import Retriever
from app.web import create_app, with_citation_links
from tests.conftest import PROJECT_ROOT


@pytest.fixture
def demo_copilot(retriever: Retriever, repo: Repository) -> Copilot:
    return Copilot(retriever, DemoLLM(), repo, top_k=4)


@pytest.fixture
async def client(demo_copilot: Copilot) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(demo_copilot, ZoneInfo("Europe/Berlin"), "Sample Office", demo=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_demo_seed_runs_the_real_pipeline(demo_copilot: Copilot, repo: Repository) -> None:
    created = await seed(demo_copilot)

    stats = await repo.stats()
    assert stats.questions == len(SAMPLE_QUESTIONS)
    assert stats.tickets == created >= 6
    assert stats.solved >= 3
    tickets = await repo.list_tickets()
    assert tickets[0].triage.priority.value == "P1"  # open work, most urgent first
    assert tickets[-1].status.value == "closed"


async def test_tickets_page(client: httpx.AsyncClient, demo_copilot: Copilot) -> None:
    await seed(demo_copilot)
    html = (await client.get("/")).text

    assert "IT tickets" in html
    assert "demo mode" in html
    assert "The whole office has no internet" in html
    assert "Can you order a new office chair" not in html  # closed, not in the open view
    assert "Can you order a new office chair" in (await client.get("/?status=all")).text


async def test_status_change_redirects_back(client: httpx.AsyncClient, repo: Repository) -> None:
    resp = await client.post("/api/tickets", json={"text": "Printer is jammed", "name": "Max"})
    ticket_id = resp.json()["id"]

    resp = await client.post(f"/tickets/{ticket_id}/status", data={"status": "closed"})
    assert resp.status_code == 303
    ticket = await repo.get_ticket(ticket_id)
    assert ticket is not None and ticket.status.value == "closed"
    assert (await client.post("/tickets/999/status", data={"status": "closed"})).status_code == 404


async def test_try_page_shows_answer_sources_and_retrieval(
    client: httpx.AsyncClient, repo: Repository
) -> None:
    html = (await client.get("/try", params={"q": "How do I connect to the VPN from home?"})).text

    assert "Answered from 1 source" in html
    assert 'href="#src-1"' in html
    assert "VPN for remote work" in html
    assert "AI-generated answer" in html
    assert "BM25 top 4" in html
    assert (await repo.stats()).questions == 0  # the preview saves nothing


async def test_api_ask_and_tickets(client: httpx.AsyncClient) -> None:
    answered = (await client.post("/api/ask", json={"question": "Where is the toner?"})).json()
    assert answered["answered"]
    assert answered["sources"][0]["id"].startswith("printer#")

    ticket = (await client.post("/api/ask", json={"question": "The coffee machine leaks"})).json()
    assert not ticket["answered"]
    assert ticket["ticket"]["priority"] == "P3"

    tickets = (await client.get("/api/tickets", params={"status": "open"})).json()
    assert [t["summary"] for t in tickets] == ["The coffee machine leaks"]
    patched = await client.patch(f"/api/tickets/{tickets[0]['id']}", json={"status": "closed"})
    assert patched.json()["status"] == "closed"
    assert (await client.post("/api/ask", json={"question": ""})).status_code == 422


def test_answer_html_is_escaped_before_citation_links() -> None:
    html = str(with_citation_links("Use <b>this</b> [1]"))
    assert html == 'Use &lt;b&gt;this&lt;/b&gt; <a class="cite" href="#src-1">1</a>'


def test_plain_joins_wrapped_lines_but_keeps_lists() -> None:
    text = "Open **Settings** and\nclick `Add`.\n\n1. First step\n   continues here.\n2. Second"
    assert plain(text) == "Open Settings and click Add.\n\n1. First step continues here.\n2. Second"


async def test_eval_on_the_sample_set(documents: list[Document]) -> None:
    # A regression guard: the numbers in the README come from this command.
    report = await run_eval(
        documents,
        DemoLLM(),
        PROJECT_ROOT / "eval" / "questions.yaml",
        min_score=2.0,
        min_coverage=0.3,
        top_k=4,
        ablation=True,
    )
    assert "hit@1  29/30" in report
    assert "hit@3  30/30" in report
    assert "out-of-scope routed to a ticket    8/8" in report
    assert "BM25 on section text" in report


def test_eval_file_has_thirty_questions_with_existing_documents(
    documents: list[Document],
) -> None:
    import yaml

    data = yaml.safe_load(Path(PROJECT_ROOT / "eval" / "questions.yaml").read_text("utf-8"))
    ids = {d.id for d in documents}
    assert len(data["questions"]) == 30
    assert all(item["expected"] in ids for item in data["questions"] + data["holdout"])
