"""Aggregation: per-page results -> a summary per rule and per WCAG success criterion."""

from collections import Counter

from app.models import (
    CheckStatus,
    CriterionSummary,
    PageReport,
    RuleSummary,
    Severity,
    Summary,
)
from app.rules import CRITERIA, RULES


def _worst(statuses: list[CheckStatus]) -> CheckStatus:
    return min(statuses, key=lambda s: s.rank) if statuses else CheckStatus.NOT_APPLICABLE


def summarize(pages: list[PageReport]) -> Summary:
    analysed = [p for p in pages if p.analysed]
    rules: list[RuleSummary] = []
    for rule in RULES.values():
        statuses = [p.checks[rule.id] for p in analysed if rule.id in p.checks]
        issues = sum(i.count for p in analysed for i in p.issues if i.rule_id == rule.id)
        affected = sum(1 for p in analysed if any(i.rule_id == rule.id for i in p.issues))
        rules.append(
            RuleSummary(
                rule_id=rule.id,
                title=rule.title,
                criteria=list(rule.criteria),
                severity=rule.severity,
                advisory=rule.advisory,
                fix=rule.fix,
                status=_worst(statuses),
                issues=issues,
                pages_affected=affected,
                pages_checked=sum(1 for s in statuses if s is not CheckStatus.NOT_APPLICABLE),
            )
        )

    criteria: list[CriterionSummary] = []
    for number, criterion in CRITERIA.items():
        mapped = [r for r in rules if number in r.criteria]
        affected_pages = {
            p.url for p in analysed for i in p.issues if number in RULES[i.rule_id].criteria
        }
        criteria.append(
            CriterionSummary(
                number=number,
                name=criterion.name,
                level=criterion.level,
                obsolete=criterion.obsolete,
                status=_worst([r.status for r in mapped]),
                rule_ids=[r.rule_id for r in mapped],
                issues=sum(r.issues for r in mapped),
                pages_affected=len(affected_pages),
            )
        )
    criteria.sort(key=lambda c: (c.obsolete, [int(x) for x in c.number.split(".")]))

    rules.sort(key=lambda r: (r.status.rank, r.severity.rank, -r.issues))
    severity = Counter(i.severity for p in analysed for i in p.issues for _ in range(i.count))
    return Summary(
        pages_requested=len(pages),
        pages_analysed=len(analysed),
        rules=rules,
        criteria=criteria,
        checks={s: sum(1 for r in rules if r.status is s) for s in CheckStatus},
        issues_by_severity={s: severity.get(s, 0) for s in Severity},
    )
