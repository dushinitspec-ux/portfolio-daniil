"""Shared pieces for the rules: WCAG criteria, the Rule type, and a parsed page with
helpers for the questions every rule asks (is this hidden? what is its accessible name?).
"""

import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from app.models import Issue, Severity

UNDERSTANDING = "https://www.w3.org/WAI/WCAG22/Understanding/"


@dataclass(frozen=True)
class Criterion:
    number: str
    name: str
    level: str
    slug: str
    obsolete: bool = False

    @property
    def url(self) -> str:
        return UNDERSTANDING + self.slug

    @property
    def label(self) -> str:
        return f"{self.number} {self.name} ({self.level})"


CRITERIA: dict[str, Criterion] = {
    c.number: c
    for c in [
        Criterion("1.1.1", "Non-text Content", "A", "non-text-content"),
        Criterion("1.3.1", "Info and Relationships", "A", "info-and-relationships"),
        Criterion("1.4.2", "Audio Control", "A", "audio-control"),
        Criterion("1.4.3", "Contrast (Minimum)", "AA", "contrast-minimum"),
        Criterion("1.4.4", "Resize Text", "AA", "resize-text"),
        Criterion("2.4.1", "Bypass Blocks", "A", "bypass-blocks"),
        Criterion("2.4.2", "Page Titled", "A", "page-titled"),
        Criterion("2.4.4", "Link Purpose (In Context)", "A", "link-purpose-in-context"),
        Criterion("3.1.1", "Language of Page", "A", "language-of-page"),
        Criterion("3.3.2", "Labels or Instructions", "A", "labels-or-instructions"),
        Criterion("4.1.2", "Name, Role, Value", "A", "name-role-value"),
        # Removed from WCAG 2.2 ("obsolete and removed"); kept only to explain why
        # duplicate ids are reported as a best practice and not as a failure.
        Criterion("4.1.1", "Parsing", "removed in 2.2", "parsing", obsolete=True),
    ]
}


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    criteria: tuple[str, ...]
    severity: Severity  # default severity; single findings may be lower
    fix: str  # one line: what to change
    owner_text: str  # plain-language "why it matters", used by the offline explainer
    check: Callable[["Page"], "Outcome"]
    advisory: bool = False  # True: best practice or heuristic, reported as a warning


@dataclass
class Outcome:
    """What a rule found on one page. `checked` = how many elements it looked at;
    0 means the rule did not apply (no images on the page, say)."""

    checked: int = 0
    issues: list[Issue] = field(default_factory=list)


HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
WHITESPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


def snippet(tag: Tag, limit: int = 160) -> str:
    """The start tag only, with long attribute values shortened: enough to find the element."""
    parts = [tag.name]
    for name, value in tag.attrs.items():
        text = " ".join(value) if isinstance(value, list) else str(value)
        if len(text) > 60:
            text = text[:57] + "..."
        parts.append(f'{name}="{text}"' if text else name)
    result = "<" + " ".join(parts) + ">"
    return result if len(result) <= limit else result[: limit - 4] + "...>"


def attr(tag: Tag, name: str) -> str | None:
    value = tag.get(name)
    if value is None:
        return None
    return " ".join(value) if isinstance(value, list) else str(value)


class Page:
    """One parsed HTML page plus lookups shared by all rules."""

    def __init__(self, html: str | BeautifulSoup, url: str = "") -> None:
        self.soup = html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "lxml")
        self.url = url
        self.ids: dict[str, list[Tag]] = defaultdict(list)
        self.labels_for: dict[str, list[Tag]] = defaultdict(list)
        for tag in self.soup.find_all(True):
            if (tag_id := attr(tag, "id")) is not None:
                self.ids[tag_id].append(tag)
            if tag.name == "label" and (target := attr(tag, "for")):
                self.labels_for[target].append(tag)

    @property
    def html_tag(self) -> Tag | None:
        tag = self.soup.find("html")
        return tag if isinstance(tag, Tag) else None

    def elements(self, *names: str) -> Iterator[Tag]:
        for tag in self.soup.find_all(list(names)):
            if isinstance(tag, Tag):
                yield tag

    def is_hidden(self, tag: Tag) -> bool:
        """Hidden from everyone or from assistive technology, judged from the markup only."""
        node: Tag | None = tag
        while node is not None and node.name not in ("[document]", "html"):
            if node.has_attr("hidden") or attr(node, "aria-hidden") == "true":
                return True
            if HIDDEN_STYLE.search(attr(node, "style") or ""):
                return True
            if node.name == "input" and (attr(node, "type") or "").lower() == "hidden":
                return True
            if node.name in ("template", "noscript"):
                return True
            node = node.parent if isinstance(node.parent, Tag) else None
        return False

    def text_content(self, tag: Tag) -> str:
        """Visible text of an element as a screen reader would read it: text nodes, image
        alt texts and aria-labels of children, skipping aria-hidden parts."""
        pieces: list[str] = []

        def walk(node: Tag) -> None:
            for child in node.children:
                if isinstance(child, Comment):
                    continue
                if isinstance(child, NavigableString):
                    pieces.append(str(child))
                elif isinstance(child, Tag):
                    if child.name in ("script", "style", "template", "select", "textarea"):
                        continue
                    if attr(child, "aria-hidden") == "true" or child.has_attr("hidden"):
                        continue
                    if label := clean(attr(child, "aria-label") or ""):
                        pieces.append(f" {label} ")
                    elif child.name in ("img", "area") or (
                        child.name == "input" and attr(child, "type") == "image"
                    ):
                        pieces.append(f" {attr(child, 'alt') or ''} ")
                    else:
                        walk(child)

        walk(tag)
        return clean("".join(pieces))

    def labelledby_text(self, tag: Tag) -> str:
        ids = (attr(tag, "aria-labelledby") or "").split()
        texts = [self.text_content(self.ids[i][0]) for i in ids if self.ids.get(i)]
        return clean(" ".join(texts))

    def accessible_name(self, tag: Tag, *, from_content: bool) -> str:
        """A simplified version of the W3C accessible name computation: aria-labelledby,
        aria-label, the element's own label source, its content (for links, buttons and
        headings), then the title attribute. Placeholders are deliberately ignored."""
        if name := self.labelledby_text(tag):
            return name
        if name := clean(attr(tag, "aria-label") or ""):
            return name
        is_image = tag.name in ("img", "area") or (
            tag.name == "input" and (attr(tag, "type") or "").lower() == "image"
        )
        if is_image and (name := clean(attr(tag, "alt") or "")):
            return name
        is_field = tag.name in ("input", "select", "textarea", "meter", "progress", "output")
        if is_field and (name := self.label_text(tag)):
            return name
        if from_content and (name := self.text_content(tag)):
            return name
        return clean(attr(tag, "title") or "")

    def label_text(self, control: Tag) -> str:
        texts = []
        control_id = attr(control, "id")
        # <label for> belongs to the first element with that id only, as in browsers.
        if control_id is not None and self.ids[control_id][0] is control:
            texts += [self.text_content(label) for label in self.labels_for.get(control_id, [])]
        wrapper = control.find_parent("label")
        if isinstance(wrapper, Tag):
            texts.append(self.text_content(wrapper))
        return clean(" ".join(texts))
