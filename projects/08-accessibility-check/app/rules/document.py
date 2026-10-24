"""Rules about the page as a whole: title, language, zoom, headings, landmarks, ids."""

import re

from bs4 import Tag

from app.models import Issue, Severity
from app.rules.base import Outcome, Page, attr, clean, snippet

# --- 2.4.2 Page titled ----------------------------------------------------------------


def page_title(page: Page) -> str | None:
    """Text of the document <title>, ignoring <title> elements inside inline SVG."""
    for tag in page.soup.find_all("title"):
        if isinstance(tag, Tag) and tag.find_parent("svg") is None:
            return clean(tag.get_text())
    return None


def check_page_title(page: Page) -> Outcome:
    out = Outcome(checked=1)
    title = page_title(page)
    if title is None:
        message = "The page has no <title>, so browser tabs and screen readers show no name."
    elif not title:
        message = "The page <title> is empty."
    else:
        return out
    out.issues.append(Issue(rule_id="page-title", severity=Severity.HIGH, message=message))
    return out


# --- 3.1.1 Language of page -----------------------------------------------------------

# BCP 47 shape: "en", "de-DE", "zh-Hant-TW". "en_US" or "english" are not valid.
LANG_TAG = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{1,8})*$")


def check_html_lang(page: Page) -> Outcome:
    out = Outcome(checked=1)
    html = page.html_tag
    lang = clean(attr(html, "lang") or "") if html else ""
    if not lang:
        out.issues.append(
            Issue(
                rule_id="html-lang",
                severity=Severity.HIGH,
                message="<html> has no lang attribute, so screen readers may read the page "
                "with the wrong language's pronunciation.",
                snippet=snippet(html) if html else "",
            )
        )
    elif not LANG_TAG.match(lang):
        out.issues.append(
            Issue(
                rule_id="html-lang",
                severity=Severity.MEDIUM,
                message=f'lang="{lang}" is not a valid language code (use e.g. "en", "de" '
                'or "en-GB").',
                snippet=snippet(html) if html else "",
            )
        )
    return out


# --- 1.4.4 Resize text: zoom must not be blocked --------------------------------------


def _viewport_settings(content: str) -> dict[str, str]:
    settings = {}
    for part in re.split(r"[,;]", content):
        if "=" in part:
            key, value = part.split("=", 1)
            settings[key.strip().lower()] = value.strip().lower()
    return settings


def check_meta_viewport(page: Page) -> Outcome:
    out = Outcome()
    for meta in page.soup.find_all("meta", attrs={"name": re.compile("^viewport$", re.I)}):
        if not isinstance(meta, Tag):
            continue
        out.checked += 1
        settings = _viewport_settings(attr(meta, "content") or "")
        scalable = settings.get("user-scalable", "")
        if scalable in ("no", "0") or abs(_number(scalable, 1)) < 1:
            out.issues.append(
                Issue(
                    rule_id="meta-viewport",
                    severity=Severity.HIGH,
                    message="The viewport sets user-scalable=no, which blocks pinch-zoom in "
                    "many mobile browsers.",
                    snippet=snippet(meta),
                )
            )
        elif _number(settings.get("maximum-scale", ""), 10) < 2:
            out.issues.append(
                Issue(
                    rule_id="meta-viewport",
                    severity=Severity.MEDIUM,
                    message=f"The viewport limits zoom to maximum-scale="
                    f"{settings['maximum-scale']}; text must be zoomable to 200 %.",
                    snippet=snippet(meta),
                )
            )
    return out


def _number(value: str, default: float) -> float:
    try:
        return float(value)
    except ValueError:
        return default


# --- 1.3.1 Headings (advisory) ----------------------------------------------------------

HEADING = re.compile(r"^h[1-6]$")


def _headings(page: Page) -> list[tuple[int, Tag]]:
    found = []
    for tag in page.soup.find_all(True):
        if not isinstance(tag, Tag) or page.is_hidden(tag):
            continue
        if HEADING.match(tag.name):
            level = int(tag.name[1])
        elif attr(tag, "role") == "heading" and (attr(tag, "aria-level") or "").isdigit():
            level = int(attr(tag, "aria-level") or "2")
        else:
            continue
        found.append((level, tag))
    return found


def check_headings(page: Page) -> Outcome:
    headings = _headings(page)
    out = Outcome(checked=max(len(headings), 1))
    if not any(level == 1 for level, _ in headings):
        out.issues.append(
            Issue(
                rule_id="heading-structure",
                severity=Severity.LOW,
                message="The page has no <h1>, so there is no main heading to jump to.",
            )
        )
    previous = 0
    for level, tag in headings:
        if not page.text_content(tag):
            out.issues.append(
                Issue(
                    rule_id="heading-structure",
                    severity=Severity.MEDIUM,
                    message=f"An <h{level}> heading is empty.",
                    snippet=snippet(tag),
                )
            )
            continue
        if previous and level > previous + 1:
            out.issues.append(
                Issue(
                    rule_id="heading-structure",
                    severity=Severity.LOW,
                    message=f"Heading level jumps from h{previous} to h{level}; screen reader "
                    "users may think a section is missing.",
                    snippet=snippet(tag),
                )
            )
        previous = level
    return out


# --- 2.4.1 Bypass blocks (advisory) ---------------------------------------------------


def _skip_link(page: Page) -> Tag | None:
    """A same-page link among the first three links of the page."""
    for link in page.soup.find_all("a", href=True, limit=3):
        href = attr(link, "href") or ""
        if isinstance(link, Tag) and href.startswith("#") and len(href) > 1:
            return link
    return None


def check_bypass(page: Page) -> Outcome:
    out = Outcome(checked=1)
    main = page.soup.find("main") or page.soup.find(attrs={"role": "main"})
    skip = _skip_link(page)
    if skip is not None:
        target = (attr(skip, "href") or "")[1:]
        if not page.ids.get(target) and not page.soup.find("a", attrs={"name": target}):
            out.issues.append(
                Issue(
                    rule_id="bypass-blocks",
                    severity=Severity.MEDIUM,
                    message=f'The skip link points to "#{target}", which does not exist on '
                    "the page.",
                    snippet=snippet(skip),
                )
            )
            return out
    if main is None and skip is None:
        out.issues.append(
            Issue(
                rule_id="bypass-blocks",
                severity=Severity.MEDIUM,
                message="No <main> landmark and no skip link: keyboard and screen reader "
                "users must go through the whole menu on every page.",
            )
        )
    elif main is None:
        out.issues.append(
            Issue(
                rule_id="bypass-blocks",
                severity=Severity.LOW,
                message="No <main> landmark. The skip link helps keyboard users, but screen "
                "reader users cannot jump to the main content by landmark.",
            )
        )
    return out


# --- Duplicate ids ---------------------------------------------------------------------

REFERENCE_ATTRIBUTES = ("aria-labelledby", "aria-describedby", "aria-controls", "headers")


def _referenced_ids(page: Page) -> set[str]:
    referenced = set(page.labels_for)
    for name in REFERENCE_ATTRIBUTES:
        for tag in page.soup.find_all(attrs={name: True}):
            if isinstance(tag, Tag):
                referenced.update((attr(tag, name) or "").split())
    return referenced


def _duplicates(page: Page) -> dict[str, list[Tag]]:
    return {i: tags for i, tags in page.ids.items() if i and len(tags) > 1}


def check_duplicate_ids(page: Page) -> Outcome:
    """Best practice only: WCAG 2.2 removed 4.1.1 Parsing. Duplicates that a label or ARIA
    attribute points to are reported by the next rule instead, because those break names."""
    out = Outcome(checked=len(page.ids))
    referenced = _referenced_ids(page)
    for tag_id, tags in _duplicates(page).items():
        if tag_id in referenced:
            continue
        out.issues.append(
            Issue(
                rule_id="duplicate-id",
                severity=Severity.LOW,
                message=f'id="{tag_id}" is used {len(tags)} times. Not a WCAG 2.2 failure '
                "on its own, but scripts and in-page links may pick the wrong element.",
                snippet=snippet(tags[1]),
            )
        )
    return out


def check_duplicate_referenced_ids(page: Page) -> Outcome:
    referenced = _referenced_ids(page)
    out = Outcome(checked=len(referenced))
    for tag_id, tags in _duplicates(page).items():
        if tag_id not in referenced:
            continue
        out.issues.append(
            Issue(
                rule_id="duplicate-id-referenced",
                severity=Severity.MEDIUM,
                message=f'id="{tag_id}" is used {len(tags)} times and a label or ARIA '
                "attribute points to it, so the label may be read for the wrong element.",
                snippet=snippet(tags[1]),
            )
        )
    return out
