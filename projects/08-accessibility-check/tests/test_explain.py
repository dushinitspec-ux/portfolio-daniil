"""The shop-owner summary: fixed texts, and Claude with a fake SDK client."""

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.config import AIProvider, Settings
from app.crawler import CrawlOptions
from app.db import Repository
from app.explain import ExplainError, FixedTextExplainer, create_explainer
from app.explain.anthropic_client import FALLBACK_BETA, ClaudeExplainer
from app.explain.base import build_user_prompt, findings_digest
from app.models import ScanReport
from app.samples import sample_transport
from app.scanner import run_scan
from app.service import ScanService


async def sample_report(name: str = "broken") -> ScanReport:
    async with httpx.AsyncClient(transport=sample_transport()) as client:
        return await run_scan(
            f"http://127.0.0.1:8108/samples/{name}/",
            client=client,
            options=CrawlOptions(delay_s=0),
            sample=name,
        )


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def fake_client(text: str | None, stop_reason: str = "end_turn") -> Any:
    content = [] if text is None else [SimpleNamespace(type="text", text=text)]
    response = SimpleNamespace(content=content, stop_reason=stop_reason, model="claude-opus-5-5")
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(response)))


REPLY = json.dumps(
    {
        "summary": "Blind customers cannot buy on two pages.",
        "actions": [{"title": f"Step {i}", "why": "why", "how": "how"} for i in range(8)],
    }
)


async def test_fixed_texts_put_failures_first_and_keep_the_limits_note() -> None:
    explanation = await FixedTextExplainer().explain(await sample_report(), "en")
    assert explanation.source == "fixed texts"
    assert len(explanation.actions) == 6
    assert explanation.actions[0].title.startswith("Images without a text alternative")
    assert "found on 3 of 4 pages" in explanation.actions[0].title
    assert "does not mean the site is accessible" in explanation.note


async def test_fixed_texts_for_a_clean_site_and_other_languages() -> None:
    explanation = await FixedTextExplainer().explain(await sample_report("fixed"), "de")
    assert "found no problems" in explanation.summary
    assert explanation.actions == []
    assert "only in English" in explanation.note


async def test_claude_request_and_reply() -> None:
    client = fake_client(REPLY)
    explanation = await ClaudeExplainer(client, "claude-opus-5-5", "medium").explain(
        await sample_report(), "ru"
    )

    call = client.beta.messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"]["type"] == "json_schema"
    prompt = call["messages"][0]["content"]
    assert "Write the summary in Russian" in prompt
    assert "<findings>" in prompt and "image-alt" in prompt
    assert 'Never say that the site is "compliant"' in call["system"]
    assert explanation.summary.startswith("Blind customers")
    assert len(explanation.actions) == 6  # capped
    assert explanation.source == "Claude (claude-opus-5-5)"


@pytest.mark.parametrize(
    ("text", "stop_reason", "error"),
    [
        (None, "refusal", "declined"),
        ("{", "max_tokens", "cut off"),
        ("not json", "end_turn", "unexpected reply format"),
        (None, "end_turn", "no text"),
    ],
)
async def test_claude_failures_raise_explain_error(
    text: str | None, stop_reason: str, error: str
) -> None:
    explainer = ClaudeExplainer(fake_client(text, stop_reason), "claude-opus-5-5", "medium")
    with pytest.raises(ExplainError, match=error):
        await explainer.explain(await sample_report(), "en")


async def test_service_falls_back_to_fixed_texts(settings: Settings) -> None:
    repo = await Repository.connect(":memory:")
    explainer = ClaudeExplainer(fake_client(None, "refusal"), "claude-opus-5-5", "medium")
    service = ScanService(settings, repo, explainer)
    report = await service.scan_sample_now("broken")

    explanation = await service.explain(report.id or 0, "tr")
    await repo.close()

    assert explanation.source == "fixed texts"
    assert explanation.note.startswith("Claude was not available")


def test_prompt_contains_findings_but_no_page_html() -> None:
    report = ScanReport.model_validate_json(
        '{"start_url": "https://s.test/", "created_at": "2026-10-24T10:00:00Z",'
        ' "options": {"max_pages": 1, "concurrency": 1, "delay_s": 0}}'
    )
    assert findings_digest(report) == []
    prompt = build_user_prompt(report, "en")
    assert "Write the summary in English" in prompt and "<html" not in prompt


def test_demo_mode_never_uses_the_api(settings: Settings) -> None:
    demo = settings.model_copy(update={"demo_mode": True, "ai_provider": AIProvider.ANTHROPIC})
    assert isinstance(create_explainer(demo), FixedTextExplainer)
    real = settings.model_copy(update={"ai_provider": AIProvider.ANTHROPIC})
    assert isinstance(create_explainer(real), ClaudeExplainer)
