"""Turns a stored report into what the templates show (shared by the page and the export)."""

from dataclasses import dataclass
from typing import Any

from app.explain import LANGUAGES, LIMITS_NOTE
from app.models import CheckStatus, Issue, PageReport, RuleSummary, ScanReport
from app.rules import CRITERIA, RULES, Criterion
from app.samples import SAMPLES

MAX_EXAMPLES_PER_RULE = 25

STATUS_LABELS = {
    CheckStatus.FAIL: "Fail",
    CheckStatus.WARNING: "Warning",
    CheckStatus.PASS: "Pass",
    CheckStatus.NOT_APPLICABLE: "Not applicable",
}

# What static HTML checks cannot see. Shown on every report, in the README and the export.
NOT_CHECKED = [
    "Colour contrast as rendered: only colours written inline in the HTML are checked, not "
    "colours from stylesheets, images or hover and focus states.",
    "Keyboard use: whether every menu, pop-up and form works without a mouse, and whether "
    "focus gets trapped anywhere.",
    "Focus order, visible focus, and focus hidden behind sticky headers (2.4.3, 2.4.7, 2.4.11).",
    "How screen readers actually announce the page, and dynamic content added by JavaScript.",
    "Whether alt texts, labels and headings are meaningful: only whether they exist.",
    "Captions and transcripts for video and audio, text in images, reflow at 320 px, motion.",
    "PDFs and other documents linked from the site.",
]


@dataclass(frozen=True)
class Example:
    page: PageReport
    issue: Issue


@dataclass(frozen=True)
class RuleGroup:
    summary: RuleSummary
    criteria: list[Criterion]
    examples: list[Example]
    more: int


def status_label(status: CheckStatus) -> str:
    return STATUS_LABELS[status]


def status_class(status: CheckStatus) -> str:
    return {"n/a": "na"}.get(status.value, status.value)


def short_url(url: str, origin: str) -> str:
    if origin and url.startswith(origin):
        return url[len(origin) :] or "/"
    return url


def report_view(report: ScanReport) -> dict[str, Any]:
    groups = []
    for rule_summary in report.summary.rules:
        if rule_summary.status not in (CheckStatus.FAIL, CheckStatus.WARNING):
            continue
        examples = [
            Example(page, issue)
            for page in report.pages
            for issue in page.issues
            if issue.rule_id == rule_summary.rule_id
        ]
        groups.append(
            RuleGroup(
                summary=rule_summary,
                criteria=[CRITERIA[c] for c in rule_summary.criteria],
                examples=examples[:MAX_EXAMPLES_PER_RULE],
                more=max(len(examples) - MAX_EXAMPLES_PER_RULE, 0),
            )
        )
    passed = [r for r in report.summary.rules if r.status is CheckStatus.PASS]
    not_applicable = [r for r in report.summary.rules if r.status is CheckStatus.NOT_APPLICABLE]
    checks = report.summary.checks
    return {
        "report": report,
        "groups": groups,
        "passed": passed,
        "not_applicable": not_applicable,
        "criteria": report.summary.criteria,
        "criteria_info": CRITERIA,
        "rules_info": RULES,
        "failed_count": checks.get(CheckStatus.FAIL, 0),
        "warning_count": checks.get(CheckStatus.WARNING, 0),
        "pass_count": checks.get(CheckStatus.PASS, 0),
        "na_count": checks.get(CheckStatus.NOT_APPLICABLE, 0),
        "not_checked": NOT_CHECKED,
        "limits_note": LIMITS_NOTE,
        "languages": LANGUAGES,
        "sample_name": SAMPLES.get(report.sample or ""),
        "status_label": status_label,
        "status_class": status_class,
        "short_url": lambda url: short_url(url, report.origin),
    }
