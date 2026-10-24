"""Rules about form fields."""

from bs4 import Tag

from app.models import Issue, Severity
from app.rules.base import Outcome, Page, attr, clean, snippet

# Input types that are buttons or invisible, so they need no <label>.
NO_LABEL_TYPES = {"hidden", "submit", "reset", "button", "image"}


def _fields(page: Page) -> list[Tag]:
    fields: list[Tag] = []
    for tag in page.elements("input", "select", "textarea"):
        if tag.name == "input" and (attr(tag, "type") or "text").lower() in NO_LABEL_TYPES:
            continue
        if page.is_hidden(tag):
            continue
        fields.append(tag)
    return fields


INPUT_NAMES = {"checkbox": "Checkbox", "radio": "Radio button", "range": "Slider"}


def _describe(tag: Tag) -> str:
    if tag.name == "input":
        kind = (attr(tag, "type") or "text").lower()
        return INPUT_NAMES.get(kind, f"{kind.capitalize()} field")
    return {"select": "Drop-down list", "textarea": "Text area"}[tag.name]


def check_form_labels(page: Page) -> Outcome:
    """A field with no accessible name at all fails 1.3.1 and 4.1.2."""
    fields = _fields(page)
    out = Outcome(checked=len(fields))
    for tag in fields:
        if page.accessible_name(tag, from_content=False):
            continue
        if clean(attr(tag, "placeholder") or ""):
            continue  # reported by the placeholder rule instead
        out.issues.append(
            Issue(
                rule_id="form-label",
                severity=Severity.HIGH,
                message=f"{_describe(tag)} has no label, so screen readers announce it "
                "without saying what to enter.",
                snippet=snippet(tag),
            )
        )
    return out


def check_placeholder_only(page: Page) -> Outcome:
    """Placeholder as the only label: browsers expose it as the name, but it disappears
    as soon as the visitor starts typing and is usually low-contrast grey."""
    fields = [f for f in _fields(page) if clean(attr(f, "placeholder") or "")]
    out = Outcome(checked=len(fields))
    for tag in fields:
        if page.accessible_name(tag, from_content=False):
            continue
        out.issues.append(
            Issue(
                rule_id="label-placeholder",
                severity=Severity.MEDIUM,
                message=(
                    f"{_describe(tag)} is labelled only by its placeholder "
                    f'"{clean(attr(tag, "placeholder") or "")}", which disappears while typing.'
                ),
                snippet=snippet(tag),
            )
        )
    return out
