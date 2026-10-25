"""Rules about content inside the page: images, links, buttons, frames, media, colours."""

import re
from collections import Counter
from urllib.parse import parse_qs, urlsplit

from bs4 import NavigableString, Tag

from app.contrast import (
    RGBA,
    background_color,
    contrast_ratio,
    font_size_px,
    format_ratio,
    is_bold,
    is_large_text,
    parse_color,
    parse_style,
    required_ratio,
)
from app.models import Issue, Severity
from app.rules.base import Outcome, Page, attr, clean, snippet

# --- 1.1.1 Non-text content ------------------------------------------------------------

# "IMG_2041.jpg", "hero-banner.webp", "DSC00012": a file name, not a description.
FILENAME_ALT = re.compile(
    r"^[\w\-. ]*\.(jpe?g|png|gif|webp|avif|svg|bmp|tiff?)$|^(img|dsc|image|photo)[_\-]?\d+$",
    re.IGNORECASE,
)


def check_image_alt(page: Page) -> Outcome:
    out = Outcome()
    for img in page.elements("img", "input"):
        if img.name == "input" and (attr(img, "type") or "").lower() != "image":
            continue
        if page.is_hidden(img) or attr(img, "role") in ("presentation", "none"):
            continue
        out.checked += 1
        alt = attr(img, "alt")
        if alt is None:
            if page.accessible_name(img, from_content=False):
                continue  # named by aria-label, aria-labelledby or title instead
            what = "Image button" if img.name == "input" else "Image"
            out.issues.append(
                Issue(
                    rule_id="image-alt",
                    severity=Severity.HIGH,
                    message=f"{what} has no alt attribute, so screen readers cannot describe it.",
                    snippet=snippet(img),
                )
            )
        elif FILENAME_ALT.match(alt.strip()):
            out.issues.append(
                Issue(
                    rule_id="image-alt",
                    severity=Severity.MEDIUM,
                    message=f'The alt text "{alt.strip()}" is a file name, not a description.',
                    snippet=snippet(img),
                )
            )
        elif img.name == "input" and not alt.strip():
            out.issues.append(
                Issue(
                    rule_id="image-alt",
                    severity=Severity.HIGH,
                    message="Image button has an empty alt, so the button has no name.",
                    snippet=snippet(img),
                )
            )
    return out


# --- 2.4.4 Link purpose and 4.1.2 names of links and buttons ----------------------------

# Link texts that say nothing about the target when read on their own. Matched after
# lower-casing and stripping punctuation and arrows.
VAGUE_LINK_TEXTS: dict[str, set[str]] = {
    "en": {"click here", "click", "here", "read more", "more", "learn more", "details",
           "more info", "more information", "link", "this", "go", "continue", "see more"},
    "de": {"hier", "hier klicken", "klicken sie hier", "mehr", "weiter", "weiterlesen",
           "mehr erfahren", "mehr lesen", "details", "mehr infos", "link"},
    "ru": {"здесь", "тут", "сюда", "нажмите здесь", "нажмите", "подробнее", "далее",
           "читать далее", "читать дальше", "ещё", "еще", "ссылка", "узнать больше", "тык"},
    "tr": {"buraya tıklayın", "buraya tıkla", "tıklayın", "tıkla", "burada", "buraya",
           "devamı", "devamını oku", "daha fazla", "detaylar", "detay", "incele"},
    "fr": {"cliquez ici", "ici", "en savoir plus", "lire la suite", "plus", "suite"},
    "es": {"haga clic aquí", "haz clic aquí", "aquí", "leer más", "más", "ver más"},
}  # fmt: skip
VAGUE_LOOKUP = {text: lang for lang, texts in VAGUE_LINK_TEXTS.items() for text in texts}
_PUNCTUATION = re.compile(r"[\s.,:;!?…»«›‹→←>\-–—()\[\]\"'“”„]+")


def normalize_link_text(text: str) -> str:
    return _PUNCTUATION.sub(" ", text.lower()).strip()


def _links(page: Page) -> list[Tag]:
    return [
        tag
        for tag in page.elements("a", "area")
        if tag.has_attr("href") and not page.is_hidden(tag)
    ]


def check_link_name(page: Page) -> Outcome:
    links = _links(page)
    out = Outcome(checked=len(links))
    for link in links:
        if not page.accessible_name(link, from_content=link.name == "a"):
            has_image = link.find("img") is not None or link.find("svg") is not None
            out.issues.append(
                Issue(
                    rule_id="link-name",
                    severity=Severity.HIGH,
                    message=(
                        "Link has no text: it contains only an image or icon without a text "
                        "alternative."
                        if has_image
                        else 'Link has no text, so a screen reader announces only "link".'
                    ),
                    snippet=snippet(link),
                )
            )
    return out


def check_link_purpose(page: Page) -> Outcome:
    links = _links(page)
    out = Outcome(checked=len(links))
    vague: Counter[str] = Counter()
    examples: dict[str, Tag] = {}
    for link in links:
        name = page.accessible_name(link, from_content=link.name == "a")
        key = normalize_link_text(name)
        if key in VAGUE_LOOKUP:
            vague[name] += 1
            examples.setdefault(name, link)
    for name, count in vague.items():
        times = f" ({count} links)" if count > 1 else ""
        out.issues.append(
            Issue(
                rule_id="link-purpose",
                severity=Severity.MEDIUM,
                message=(
                    f'Link text "{name}"{times} does not say where the link goes. It passes '
                    "only if the surrounding sentence makes the target clear."
                ),
                snippet=snippet(examples[name]),
                count=count,
            )
        )
    return out


BUTTON_INPUT_TYPES = {"button", "submit", "reset"}


def check_button_name(page: Page) -> Outcome:
    out = Outcome()
    candidates = list(page.elements("button", "input")) + [
        tag for tag in page.soup.find_all(attrs={"role": "button"}) if isinstance(tag, Tag)
    ]
    seen: set[int] = set()
    for tag in candidates:
        if id(tag) in seen or page.is_hidden(tag):
            continue
        seen.add(id(tag))
        input_type = (attr(tag, "type") or "").lower()
        if tag.name == "input" and input_type not in BUTTON_INPUT_TYPES:
            continue
        out.checked += 1
        if tag.name == "input":
            # Browsers name empty submit and reset buttons "Submit" / "Reset" themselves.
            name = page.accessible_name(tag, from_content=False) or clean(attr(tag, "value") or "")
            if not name and input_type in ("submit", "reset"):
                continue
        else:
            name = page.accessible_name(tag, from_content=True)
        if not name:
            out.issues.append(
                Issue(
                    rule_id="button-name",
                    severity=Severity.HIGH,
                    message="Button has no text or label, so its purpose is not announced.",
                    snippet=snippet(tag),
                )
            )
    return out


def check_iframe_title(page: Page) -> Outcome:
    out = Outcome()
    for frame in page.elements("iframe", "frame"):
        if page.is_hidden(frame):
            continue
        out.checked += 1
        if not page.accessible_name(frame, from_content=False):
            out.issues.append(
                Issue(
                    rule_id="frame-title",
                    severity=Severity.MEDIUM,
                    message="Embedded frame has no title, so users cannot tell what it contains.",
                    snippet=snippet(frame),
                )
            )
    return out


# --- 1.4.2 Audio control (heuristic) --------------------------------------------------

AUTOPLAY_PARAMS = ("autoplay", "auto_play")
MUTE_PARAMS = ("mute", "muted")


def check_autoplay(page: Page) -> Outcome:
    out = Outcome()
    for media in page.elements("audio", "video"):
        out.checked += 1
        if media.has_attr("autoplay") and not media.has_attr("muted"):
            controls = "" if media.has_attr("controls") else " and has no controls"
            out.issues.append(
                Issue(
                    rule_id="autoplay-audio",
                    severity=Severity.MEDIUM,
                    message=(
                        f"<{media.name}> starts playing by itself, is not muted{controls}. "
                        "If it has sound for more than 3 seconds, visitors need a way to "
                        "stop it."
                    ),
                    snippet=snippet(media),
                )
            )
    for frame in page.elements("iframe"):
        src = attr(frame, "src") or ""
        params = {k.lower(): v for k, v in parse_qs(urlsplit(src).query).items()}
        if not any(p in params for p in AUTOPLAY_PARAMS):
            continue
        out.checked += 1
        autoplay = any(params.get(p, ["0"])[0] in ("1", "true") for p in AUTOPLAY_PARAMS)
        muted = any(params.get(p, ["0"])[0] in ("1", "true") for p in MUTE_PARAMS)
        if autoplay and not muted:
            out.issues.append(
                Issue(
                    rule_id="autoplay-audio",
                    severity=Severity.LOW,
                    message="Embedded player is set to autoplay without mute.",
                    snippet=snippet(frame),
                )
            )
    return out


# --- 1.4.3 Contrast, only where both colours are in inline styles ---------------------


def _own_text(tag: Tag) -> str:
    return clean(" ".join(str(c) for c in tag.children if isinstance(c, NavigableString)))


def _inline_background(tag: Tag) -> tuple[RGBA | None, bool]:
    """(colour, found). Walks up to the nearest element whose inline style sets a
    background. found=False: no inline background anywhere, so the backdrop is unknown."""
    node: Tag | None = tag
    while isinstance(node, Tag) and node.name != "[document]":
        declarations = parse_style(attr(node, "style") or "")
        if "background" in declarations or "background-color" in declarations:
            return background_color(declarations), True
        node = node.parent if isinstance(node.parent, Tag) else None
    return None, False


def check_inline_contrast(page: Page) -> Outcome:
    out = Outcome()
    failures: dict[tuple[str, str, bool], list[Tag]] = {}
    ratios: dict[tuple[str, str, bool], float] = {}
    for tag in page.soup.find_all(style=True):
        if not isinstance(tag, Tag) or page.is_hidden(tag) or not _own_text(tag):
            continue
        declarations = parse_style(attr(tag, "style") or "")
        if "color" not in declarations:
            continue
        foreground = parse_color(declarations["color"])
        background, found = _inline_background(tag)
        if foreground is None or not found or background is None or not background.opaque:
            continue  # cannot be judged without the rendered page
        if not foreground.opaque:
            foreground = foreground.over(background)
        out.checked += 1
        large = is_large_text(font_size_px(declarations), is_bold(declarations, tag.name))
        ratio = contrast_ratio(foreground, background)
        if ratio < required_ratio(large):
            key = (foreground.hex, background.hex, large)
            failures.setdefault(key, []).append(tag)
            ratios[key] = ratio
    for (fg, bg, large), tags in failures.items():
        need = "3:1 for large text" if large else "4.5:1 for normal-size text"
        size_note = "" if large else " (3:1 would be enough if the text is large)"
        times = f" on {len(tags)} elements" if len(tags) > 1 else ""
        out.issues.append(
            Issue(
                rule_id="color-contrast",
                severity=Severity.HIGH if ratios[(fg, bg, large)] < 3 else Severity.MEDIUM,
                message=(
                    f"Text {fg} on {bg} has a contrast of {format_ratio(ratios[(fg, bg, large)])}"
                    f"{times}; WCAG needs {need}{size_note}."
                ),
                snippet=snippet(tags[0]),
                count=len(tags),
            )
        )
    return out
