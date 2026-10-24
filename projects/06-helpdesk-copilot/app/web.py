"""Web page for the IT person (tickets, "Try a question") and a small JSON API."""

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from pydantic import BaseModel, Field

from app.copilot import Copilot, Reply
from app.db import Requester, Status, Ticket
from app.messages import AI_NOTICE
from app.triage import Priority

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
_CITATION = re.compile(r"\[(\d{1,2})\]")


def with_citation_links(text: str) -> Markup:
    """Escape the answer, then turn [2] into a link to source 2."""
    escaped = str(escape(text))
    return Markup(_CITATION.sub(r'<a class="cite" href="#src-\1">\1</a>', escaped))


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    name: str = Field(default="API user", max_length=100)


class TicketIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    name: str = Field(default="API user", max_length=100)


class StatusIn(BaseModel):
    status: Status


def ticket_json(ticket: Ticket) -> dict[str, Any]:
    return {
        "id": ticket.id,
        "created_at": ticket.created_at.isoformat(),
        "status": ticket.status.value,
        "priority": ticket.triage.priority.value,
        "category": ticket.triage.category.value,
        "summary": ticket.triage.summary,
        "question": ticket.question,
        "requester": ticket.requester.name,
        "channel": ticket.requester.channel,
        "why_ticket": ticket.route_reason,
        "priority_reason": ticket.triage.reason,
        "triaged_by": ticket.triage.by,
    }


def reply_json(reply: Reply) -> dict[str, Any]:
    decision = reply.decision
    return {
        "answered": reply.answered,
        "answer": decision.answer,
        "sources": [
            {"number": s.number, "id": s.section.id, "title": s.label} for s in decision.sources
        ],
        "ticket": ticket_json(reply.ticket) if reply.ticket else None,
        "why_ticket": decision.ticket_reason or None,
        "coverage": round(decision.retrieval.coverage, 3),
        "question_id": reply.question_id,
    }


def create_app(copilot: Copilot, tz: ZoneInfo, company: str, demo: bool = False) -> FastAPI:
    app = FastAPI(title="Helpdesk Copilot", version="0.1.0")
    repo = copilot.repo

    def local(value: datetime) -> str:
        return value.astimezone(tz).strftime("%d %b, %H:%M")

    TEMPLATES.env.filters["local"] = local
    TEMPLATES.env.filters["cite"] = with_citation_links
    common = {"company": company, "demo": demo, "llm": copilot.llm.name}

    @app.get("/", response_class=HTMLResponse)
    async def tickets_page(request: Request, status: str = "open") -> HTMLResponse:
        if status == "open":
            tickets = [t for t in await repo.list_tickets() if t.status is not Status.CLOSED]
        elif status == "all":
            tickets = await repo.list_tickets()
        else:
            tickets = await repo.list_tickets(Status(status) if status in Status else None)
        stats = await repo.stats()
        return TEMPLATES.TemplateResponse(
            request,
            "tickets.html",
            {
                **common,
                "page": "tickets",
                "tickets": tickets,
                "stats": stats,
                "status": status,
                "priorities": list(Priority),
                "Status": Status,
            },
        )

    @app.get("/try", response_class=HTMLResponse)
    async def try_page(request: Request, q: str = "") -> HTMLResponse:
        question = q.strip()[:2000]
        reply = await copilot.preview(question) if question else None
        return TEMPLATES.TemplateResponse(
            request,
            "try.html",
            {
                **common,
                "page": "try",
                "q": question,
                "reply": reply,
                "ai_notice": AI_NOTICE.format(company=company),
                "min_coverage": copilot.retriever.min_coverage,
            },
        )

    @app.post("/tickets/{ticket_id}/status")
    async def change_status(
        ticket_id: int, status: Annotated[Status, Form()], back: Annotated[str, Form()] = "open"
    ) -> RedirectResponse:
        if not await repo.set_ticket_status(ticket_id, status):
            raise HTTPException(404, "ticket not found")
        back = back if back in {"open", "all", *Status} else "open"
        return RedirectResponse(f"/?status={back}#t{ticket_id}", status_code=303)

    # JSON API

    @app.post("/api/ask")
    async def api_ask(body: AskIn) -> dict[str, Any]:
        return reply_json(await copilot.ask(body.question, Requester(body.name, "api")))

    @app.get("/api/tickets")
    async def api_tickets(status: Status | None = None) -> list[dict[str, Any]]:
        return [ticket_json(t) for t in await repo.list_tickets(status)]

    @app.post("/api/tickets", status_code=201)
    async def api_create_ticket(body: TicketIn) -> dict[str, Any]:
        return ticket_json(await copilot.open_ticket(body.text, Requester(body.name, "api")))

    @app.patch("/api/tickets/{ticket_id}")
    async def api_update_ticket(ticket_id: int, body: StatusIn) -> dict[str, Any]:
        if not await repo.set_ticket_status(ticket_id, body.status):
            raise HTTPException(404, "ticket not found")
        ticket = await repo.get_ticket(ticket_id)
        assert ticket is not None
        return ticket_json(ticket)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
