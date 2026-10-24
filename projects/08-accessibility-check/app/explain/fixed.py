"""Offline explainer: hand-written texts per rule, no API key and no network.

The texts live next to each rule in app/rules/__init__.py (owner_text and fix), so a new
rule cannot be added without its plain-language explanation.
"""

from app.explain.base import LANGUAGES, LIMITS_NOTE
from app.models import Action, CheckStatus, Explanation, ScanReport, Severity
from app.rules import RULES


class FixedTextExplainer:
    async def explain(self, report: ScanReport, language: str = "en") -> Explanation:
        summary = report.summary
        failing = [r for r in summary.rules if r.status is CheckStatus.FAIL]
        warned = [r for r in summary.rules if r.status is CheckStatus.WARNING]
        high = summary.issues_by_severity.get(Severity.HIGH, 0)
        pages = summary.pages_analysed
        page_word = "page" if pages == 1 else "pages"

        if not failing and not warned:
            text = (
                f"The automated checks found no problems on the {pages} {page_word} that were "
                "analysed. That is a good start, but these checks cover only part of WCAG."
            )
        else:
            parts = [f"The check looked at {pages} {page_word}."]
            if failing:
                parts.append(
                    f"{len(failing)} of the automated checks failed"
                    + (f", with {high} serious problems" if high else "")
                    + " that make the site hard or impossible to use for some customers."
                )
            if warned:
                parts.append(f"{len(warned)} more checks produced warnings worth a look.")
            parts.append("Start with the items at the top of this list.")
            text = " ".join(parts)

        actions = []
        for rule_summary in [*failing, *warned][:6]:
            rule = RULES[rule_summary.rule_id]
            checked = rule_summary.pages_checked
            where = (
                f" (found on {rule_summary.pages_affected} of {checked} "
                f"{'page' if checked == 1 else 'pages'})"
                if checked
                else ""
            )
            actions.append(Action(title=rule.title + where, why=rule.owner_text, how=rule.fix))

        note = LIMITS_NOTE
        if language != "en":
            note = (
                f"The fixed texts exist only in English; {LANGUAGES.get(language, language)} "
                "needs the Claude explainer (AI_PROVIDER=anthropic). " + note
            )
        return Explanation(
            summary=text, actions=actions, language="English", source="fixed texts", note=note
        )
