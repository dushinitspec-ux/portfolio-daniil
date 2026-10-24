"""Report data. Everything is a pydantic model, so the JSON export is the stored format."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    HIGH = "high"  # blocks some customers from using the page
    MEDIUM = "medium"  # makes the page hard to use for some customers
    LOW = "low"  # worth fixing, small impact on its own

    @property
    def rank(self) -> int:
        return {"high": 0, "medium": 1, "low": 2}[self.value]


class CheckStatus(StrEnum):
    FAIL = "fail"
    WARNING = "warning"  # advisory rule found something, or a likely problem needs a human look
    PASS = "pass"
    NOT_APPLICABLE = "n/a"

    @property
    def rank(self) -> int:
        return {"fail": 0, "warning": 1, "pass": 2, "n/a": 3}[self.value]


class ScanStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Issue(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    snippet: str = ""
    # Identical problems on one page (the same colour pair, say) are reported once.
    count: int = 1


class PageReport(BaseModel):
    url: str
    final_url: str
    status_code: int | None = None
    content_type: str = ""
    title: str | None = None
    redirects: list[str] = Field(default_factory=list)
    elapsed_ms: int = 0
    error: str | None = None
    duplicate_of: str | None = None  # same HTML as this page, not analysed twice
    analysed: bool = False
    issues: list[Issue] = Field(default_factory=list)
    checks: dict[str, CheckStatus] = Field(default_factory=dict)

    @property
    def issue_count(self) -> int:
        return sum(i.count for i in self.issues)


class SkippedUrl(BaseModel):
    url: str
    reason: str


class RuleSummary(BaseModel):
    rule_id: str
    title: str
    criteria: list[str]
    severity: Severity
    advisory: bool
    fix: str
    status: CheckStatus
    issues: int
    pages_affected: int
    pages_checked: int


class CriterionSummary(BaseModel):
    number: str
    name: str
    level: str
    obsolete: bool
    status: CheckStatus
    rule_ids: list[str]
    issues: int
    pages_affected: int


class Summary(BaseModel):
    pages_requested: int = 0
    pages_analysed: int = 0
    rules: list[RuleSummary] = Field(default_factory=list)
    criteria: list[CriterionSummary] = Field(default_factory=list)
    checks: dict[CheckStatus, int] = Field(default_factory=dict)
    issues_by_severity: dict[Severity, int] = Field(default_factory=dict)


class Action(BaseModel):
    title: str
    why: str
    how: str


class Explanation(BaseModel):
    summary: str
    actions: list[Action]
    language: str = "English"
    source: str  # "fixed texts" or the Claude model name
    note: str = ""


class ScanOptions(BaseModel):
    max_pages: int
    concurrency: int
    delay_s: float


class ScanReport(BaseModel):
    id: int | None = None
    start_url: str
    origin: str = ""
    sample: str | None = None  # "broken" / "fixed" for the bundled demo pages
    status: ScanStatus = ScanStatus.RUNNING
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    duration_s: float | None = None
    options: ScanOptions
    robots: str = ""
    pages: list[PageReport] = Field(default_factory=list)
    skipped: list[SkippedUrl] = Field(default_factory=list)
    skipped_total: int = 0
    summary: Summary = Field(default_factory=Summary)
    explanation: Explanation | None = None
    tool_version: str = ""
    standard: str = "WCAG 2.2, levels A and AA (static HTML checks only)"
