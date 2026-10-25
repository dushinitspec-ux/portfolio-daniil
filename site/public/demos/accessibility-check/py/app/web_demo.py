"""Entry point of the in-browser demo (Pyodide): JSON in, JSON out.

The rules, the report aggregation, the robots.txt parser, the link extraction and the
contrast maths are the project's own modules. What differs from a real scan is only the
transport: a browser page cannot crawl other sites (cross-origin requests are blocked), so the
bundled "Sample Shop" pages are read from files. The small loop below follows links the way
app.crawler does (same origin, robots.txt obeyed, "/" and "/index.html" counted once, a
missing page is a 404); tests/test_web_demo.py checks it reports exactly what a real crawl of
the same pages reports.

Nothing here imports httpx, FastAPI, the database or the Anthropic SDK.
"""

import hashlib
import re
from collections import deque
from pathlib import Path
from typing import Any

from app.contrast import (
    LARGE_TEXT_MIN,
    NORMAL_TEXT_MIN,
    contrast_ratio,
    format_ratio,
    is_large_text,
    parse_color,
)
from app.links import extract_links, parse_html
from app.models import PageReport, SkippedUrl
from app.report import summarize
from app.robots import Robots
from app.rules import CRITERIA, RULES, Page, check_site, run_rules
from app.rules.document import page_title
from app.urls import normalize, same_origin

SAMPLE_DIR = Path(__file__).parent / "sample_site"
SAMPLES = {
    "broken": "Sample Shop, broken version",
    "fixed": "Sample Shop, fixed version",
}
# The sample pages are served by the web app at /samples/<name>/; any host name works here
# because nothing is fetched. It is only shown in the report.
BASE_URL = "https://sample-shop.example"
PRODUCT_TOKEN = "AccessibilityCheckBot"  # app.crawler.CrawlOptions().product_token
MAX_PAGES = 20
HTML_TYPE = "text/html; charset=utf-8"
MAX_PASTED_BYTES = 500_000
# WCAG 1.4.6 Contrast (Enhanced), level AAA. The project's rules check levels A and AA only;
# the contrast checker shows AAA for comparison.
AAA_NORMAL_MIN = 7.0
AAA_LARGE_MIN = 4.5
CONTRAST_COLORS = re.compile(r"Text (#[0-9a-f]{6}) on (#[0-9a-f]{6})")


def _read(url: str) -> tuple[int, bytes | None]:
    """What the web app's /samples/ route would answer for this URL: (status, HTML body)."""
    path = normalize(url).split("/", 3)[3] if url.count("/") >= 3 else ""
    if not path.startswith("samples/"):
        return 404, None
    relative = path.removeprefix("samples/").split("?", 1)[0]
    if relative.endswith("/") or not relative:
        relative += "index.html"
    file = (SAMPLE_DIR / relative).resolve()
    if SAMPLE_DIR.resolve() not in file.parents or file.suffix != ".html" or not file.is_file():
        return 404, None
    return 200, file.read_bytes()


def _analyse(body: bytes, url: str) -> tuple[str | None, list[Any], dict[str, Any]]:
    """As app.scanner.analyse(): parse, run every page rule, read the title."""
    page = Page(parse_html(body, HTML_TYPE), url)
    issues, checks = run_rules(page)
    return page_title(page), issues, checks


def crawl_sample(name: str) -> tuple[list[PageReport], list[SkippedUrl], str]:
    if name not in SAMPLES:
        raise ValueError(f"unknown sample {name!r}")
    start = normalize(f"{BASE_URL}/samples/{name}/")
    robots = Robots.parse((SAMPLE_DIR / "robots.txt").read_text(encoding="utf-8"))
    robots.status = "robots.txt found and obeyed"
    seen = {start: 0}
    queue = deque([start])
    hashes: dict[str, str] = {}
    pages: list[PageReport] = []
    skipped: list[SkippedUrl] = []
    requested = 0
    while queue:
        url = queue.popleft()
        if not robots.allowed(url, PRODUCT_TOKEN):
            skipped.append(SkippedUrl(url=url, reason="blocked by robots.txt"))
            continue
        if requested >= MAX_PAGES:
            skipped.append(SkippedUrl(url=url, reason=f"page limit ({MAX_PAGES}) reached"))
            continue
        requested += 1
        status, body = _read(url)
        page = PageReport(
            url=url,
            final_url=url,
            status_code=status,
            content_type="text/html" if body is not None else "text/plain",
        )
        if body is not None:
            digest = hashlib.sha256(body).hexdigest()
            if digest in hashes:
                page.duplicate_of = hashes[digest]
            else:
                hashes[digest] = url
                for link in extract_links(parse_html(body, HTML_TYPE), url):
                    if same_origin(link, start) and link not in seen:
                        seen[link] = len(seen)
                        queue.append(link)
                page.title, page.issues, page.checks = _analyse(body, url)
                page.analysed = True
        pages.append(page)
    check_site(pages)
    return pages, skipped, robots.status


def _path(url: str | None) -> str | None:
    if url is None:
        return None
    return "/" + url.split("/", 3)[3] if url.count("/") >= 3 else url


def _report(pages: list[PageReport], skipped: list[SkippedUrl]) -> dict[str, Any]:
    summary = summarize(pages)
    data = summary.model_dump(mode="json")
    for criterion in data["criteria"]:
        criterion["url"] = CRITERIA[criterion["number"]].url
    page_list = []
    for page in pages:
        issues = []
        for issue in page.issues:
            item = issue.model_dump(mode="json")
            if issue.rule_id == "color-contrast" and (m := CONTRAST_COLORS.search(issue.message)):
                item["colors"] = [m.group(1), m.group(2)]
            issues.append(item)
        page_list.append(
            {
                "url": page.url,
                "path": _path(page.url),
                "status": page.status_code,
                "analysed": page.analysed,
                "duplicate_of": _path(page.duplicate_of),
                "title": page.title,
                "issues": issues,
                "issue_count": page.issue_count,
            }
        )
    return {
        "pages": page_list,
        "skipped": [{"url": s.url, "path": _path(s.url), "reason": s.reason} for s in skipped],
        "summary": data,
        "rules_info": {
            rule.id: {
                "title": rule.title,
                "criteria": list(rule.criteria),
                "fix": rule.fix,
                "why": rule.owner_text,
                "advisory": rule.advisory,
            }
            for rule in RULES.values()
        },
    }


def samples() -> dict[str, str]:
    return dict(SAMPLES)


def scan_sample(name: str) -> dict[str, Any]:
    """Scan the bundled Sample Shop ("broken" or "fixed") with the project's rules."""
    pages, skipped, robots = crawl_sample(name)
    return {
        "sample": name,
        "label": SAMPLES[name],
        "start_url": normalize(f"{BASE_URL}/samples/{name}/"),
        "robots": robots,
        **_report(pages, skipped),
    }


def check_html(html: str) -> dict[str, Any]:
    """Run every page rule on one pasted HTML document."""
    body = html.encode("utf-8")
    if len(body) > MAX_PASTED_BYTES:
        raise ValueError(f"the HTML is larger than {MAX_PASTED_BYTES // 1000} KB")
    url = f"{BASE_URL}/pasted.html"
    page = PageReport(url=url, final_url=url, status_code=200, content_type="text/html")
    page.title, page.issues, page.checks = _analyse(body, url)
    page.analysed = True
    check_site([page])
    return {"sample": None, "label": "pasted HTML", "bytes": len(body), **_report([page], [])}


def contrast(
    foreground: str, background: str, font_px: float = 16, bold: bool = False
) -> dict[str, Any]:
    """WCAG contrast of two CSS colours, with the project's own parser and maths."""
    fg, bg = parse_color(foreground), parse_color(background)
    if fg is None or bg is None:
        return {"error": "foreground" if fg is None else "background"}
    if not bg.opaque:
        return {"error": "background-alpha"}
    shown_fg = fg if fg.opaque else fg.over(bg)  # as the color-contrast rule does
    ratio = contrast_ratio(shown_fg, bg)
    large = is_large_text(float(font_px), bool(bold))
    levels = [
        ("AA", "normal", NORMAL_TEXT_MIN),
        ("AA", "large", LARGE_TEXT_MIN),
        ("AAA", "normal", AAA_NORMAL_MIN),
        ("AAA", "large", AAA_LARGE_MIN),
    ]
    return {
        "foreground": shown_fg.hex,
        "background": bg.hex,
        "blended": not fg.opaque,
        "ratio": round(ratio, 4),
        "shown": format_ratio(ratio),
        "large": large,
        "checks": [
            {"level": level, "text": size, "need": need, "pass": ratio >= need}
            for level, size, need in levels
        ],
    }
