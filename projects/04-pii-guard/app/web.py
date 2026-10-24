"""HTTP API (POST /v1/chat, POST /v1/mask, GET /v1/audit) and the demo web page."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, model_validator

from app.gateway import BlockedError, ChatResult, Gateway
from app.guard import Finding, LeakCheckError, Message, Prepared
from app.llm import LLMError
from app.masking import Segment, placeholder_segments
from app.policy import Action
from app.samples import DEFAULT_SAMPLE, SAMPLES, SAMPLES_BY_ID

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")

# --- API models ----------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _roles(self) -> "ChatRequest":
        if self.messages[0].role != "user" or self.messages[-1].role != "user":
            raise ValueError("the first and the last message must come from the user")
        return self


class EntityCount(BaseModel):
    type: str
    action: Literal["mask", "block", "allow"]
    count: int = Field(description="occurrences in the request")
    distinct: int = Field(description="different values; one placeholder each when masked")


class ChatResponse(BaseModel):
    decision: Literal["masked", "passed"]
    answer: str = Field(description="the model's answer with the real values put back")
    entities: list[EntityCount]
    sent_to_llm: list[ChatMessage] = Field(description="exactly what the model received")
    llm_answer: str = Field(description="the model's answer as written, with placeholders")
    unknown_placeholders: list[str]
    model: str
    latency_ms: int


class MaskRequest(BaseModel):
    text: str = Field(min_length=1)


class MaskResponse(BaseModel):
    decision: Literal["masked", "passed", "blocked"]
    masked: str | None = Field(description="null when the policy blocks the text")
    entities: list[EntityCount]


def _counts(findings: list[Finding]) -> list[EntityCount]:
    return [
        EntityCount(type=f.type, action=f.action, count=f.count, distinct=f.distinct)
        for f in findings
    ]


def _blocked_response(prepared: Prepared) -> JSONResponse:
    blocked = [f.type.value for f in prepared.findings if f.action is Action.BLOCK]
    return JSONResponse(
        status_code=422,
        content={
            "error": "blocked_by_policy",
            "message": f"The policy blocks {', '.join(blocked)}. Nothing was sent to the model.",
            "entities": [c.model_dump() for c in _counts(prepared.findings)],
        },
    )


# --- Web page view -------------------------------------------------------------------


@dataclass(frozen=True)
class Piece:
    """A piece of the original text: plain, or one detected value and what happens to it."""

    text: str
    kind: str | None = None
    action: str | None = None
    token: str | None = None


def original_pieces(prepared: Prepared) -> list[Piece]:
    text, found = prepared.original[0].content, prepared.entities[0]
    actions = {f.type: f.action.value for f in prepared.findings}
    pieces: list[Piece] = []
    last = 0
    for e in found:
        if e.start > last:
            pieces.append(Piece(text[last : e.start]))
        pieces.append(Piece(e.value, e.type.value, actions[e.type], prepared.vault.token_for(e)))
        last = e.end
    if last < len(text):
        pieces.append(Piece(text[last:]))
    return pieces


def result_view(
    prepared: Prepared | None, result: ChatResult | None, error: str | None
) -> dict[str, Any]:
    masked: list[Segment] = []
    if prepared and prepared.masked:
        masked = placeholder_segments(prepared.masked[0].content)
    return {
        "prepared": prepared,
        "original": original_pieces(prepared) if prepared else [],
        "masked": masked,
        "answer": result.answer_segments if result else [],
        "result": result,
        "error": error,
    }


# --- App -----------------------------------------------------------------------------


def create_app(gateway: Gateway, max_input_chars: int, demo: bool = False) -> FastAPI:
    app = FastAPI(title="PII Guard", version="0.1.0")
    policy = gateway.guard.policy

    def too_long(total: int) -> JSONResponse | None:
        if total <= max_input_chars:
            return None
        return JSONResponse(
            status_code=413,
            content={"error": "too_long", "message": f"limit is {max_input_chars} characters"},
        )

    @app.post("/v1/chat", response_model=ChatResponse, responses={422: {}, 413: {}, 502: {}})
    async def chat(body: ChatRequest) -> ChatResponse | Response:
        if error := too_long(sum(len(m.content) for m in body.messages)):
            return error
        messages = [Message(m.role, m.content) for m in body.messages]
        try:
            result = await gateway.chat(messages, source="api")
        except BlockedError as exc:
            return _blocked_response(exc.prepared)
        except LeakCheckError:
            return JSONResponse(
                status_code=500,
                content={"error": "leak_check_failed", "message": "Nothing was sent to the model."},
            )
        except LLMError as exc:
            return JSONResponse(
                status_code=502, content={"error": "llm_error", "message": str(exc)}
            )
        prepared = result.prepared
        return ChatResponse(
            decision="masked" if prepared.decision == "masked" else "passed",
            answer=result.answer,
            entities=_counts(prepared.findings),
            sent_to_llm=[ChatMessage(role=m.role, content=m.content) for m in prepared.masked],
            llm_answer=result.llm_answer,
            unknown_placeholders=result.unknown_placeholders,
            model=gateway.llm.name,
            latency_ms=result.latency_ms,
        )

    @app.post("/v1/mask", response_model=MaskResponse, responses={413: {}})
    async def mask_only(body: MaskRequest) -> MaskResponse | Response:
        """Dry run: what the model would receive. Nothing is sent and nothing is logged."""
        if error := too_long(len(body.text)):
            return error
        try:
            prepared = gateway.guard.prepare([Message("user", body.text)])
        except LeakCheckError:
            return JSONResponse(status_code=500, content={"error": "leak_check_failed"})
        return MaskResponse(
            decision=prepared.decision,
            masked=None if prepared.blocked else prepared.masked[0].content,
            entities=_counts(prepared.findings),
        )

    @app.get("/v1/audit")
    async def audit(limit: int = 50) -> list[dict[str, Any]]:
        entries = await gateway.audit.recent(max(1, min(limit, 500)))
        return [
            {
                "ts": e.ts.isoformat(),
                "source": e.source,
                "decision": e.decision,
                "entities": e.entities,
                "messages": e.messages,
                "model": e.model,
                "latency_ms": e.latency_ms,
            }
            for e in entries
        ]

    async def run_text(text: str) -> dict[str, Any]:
        if len(text) > max_input_chars:
            return result_view(None, None, f"The text is longer than {max_input_chars} characters.")
        try:
            result = await gateway.chat([Message("user", text)], source="web")
        except BlockedError as exc:
            return result_view(exc.prepared, None, None)
        except LeakCheckError:
            return result_view(None, None, "The leak check failed, nothing was sent to the model.")
        except LLMError as exc:
            return result_view(None, None, f"The model could not answer: {exc}.")
        return result_view(result.prepared, result, None)

    async def page(request: Request, text: str, view: dict[str, Any]) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                **view,
                "text": text,
                "samples": SAMPLES,
                "policy": policy.summary(),
                "audit": await gateway.audit.recent(8),
                "demo": demo,
                "model": gateway.llm.name,
                "max_chars": max_input_chars,
            },
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, sample: str | None = None) -> HTMLResponse:
        # ?sample=<id> runs one of the built-in fake texts. Real text is only ever POSTed,
        # so it never ends up in a URL or an access log.
        chosen = SAMPLES_BY_ID.get(sample or "")
        if chosen is None:
            return await page(request, DEFAULT_SAMPLE.text, result_view(None, None, None))
        return await page(request, chosen.text, await run_text(chosen.text))

    @app.post("/", response_class=HTMLResponse)
    async def index_post(request: Request, text: Annotated[str, Form()]) -> HTMLResponse:
        # Same page without JavaScript: the form posts here and gets the full page back.
        return await page(request, text, await run_text(text))

    @app.post("/ui/run", response_class=HTMLResponse)
    async def ui_run(request: Request, text: Annotated[str, Form()]) -> HTMLResponse:
        view = await run_text(text)
        return TEMPLATES.TemplateResponse(
            request, "_result.html", {**view, "audit": await gateway.audit.recent(8), "oob": True}
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
