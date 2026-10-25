"""The rule registry and the code that runs every rule on a page."""

from collections import defaultdict

from app.models import CheckStatus, Issue, PageReport, Severity
from app.rules import content, document, forms
from app.rules.base import CRITERIA, Criterion, Outcome, Page, Rule

__all__ = ["CRITERIA", "RULES", "Criterion", "Page", "Rule", "check_site", "run_rules"]

RULES: dict[str, Rule] = {
    r.id: r
    for r in [
        Rule(
            id="image-alt",
            title="Images without a text alternative",
            criteria=("1.1.1",),
            severity=Severity.HIGH,
            fix='Add an alt attribute that describes each image; use alt="" for purely '
            "decorative images.",
            owner_text="Blind customers use screen readers that read the page aloud. For a "
            'photo without a description they hear only "image" or a file name, so they '
            "cannot tell which product it shows.",
            check=content.check_image_alt,
        ),
        Rule(
            id="form-label",
            title="Form fields without a label",
            criteria=("1.3.1", "4.1.2"),
            severity=Severity.HIGH,
            fix="Give every field a visible <label for=...>, or at least an aria-label.",
            owner_text='Without a label, a screen reader announces only "edit text". The '
            "customer has to guess whether to type a name, an e-mail or a phone number, and "
            "many give up on the order or the booking.",
            check=forms.check_form_labels,
        ),
        Rule(
            id="label-placeholder",
            title="Fields labelled only by a placeholder",
            criteria=("3.3.2",),
            severity=Severity.MEDIUM,
            fix="Add a visible label above the field; keep the placeholder only as an example.",
            owner_text="The grey hint text inside a field disappears as soon as someone starts "
            "typing. People who are interrupted or have memory difficulties no longer see "
            "what the field was for.",
            check=forms.check_placeholder_only,
            advisory=True,
        ),
        Rule(
            id="page-title",
            title="Missing or empty page title",
            criteria=("2.4.2",),
            severity=Severity.HIGH,
            fix="Give each page a <title> that names the page and the shop, e.g. "
            '"Contact – Sample Shop".',
            owner_text="The page title is the first thing a screen reader says and the text on "
            "the browser tab. Without it, customers with many tabs open cannot find your "
            "shop again.",
            check=document.check_page_title,
        ),
        Rule(
            id="page-title-unique",
            title="Several pages share the same title",
            criteria=("2.4.2",),
            severity=Severity.LOW,
            fix="Make each title describe its own page: product, category, contact, etc.",
            owner_text="When every page has the same title, customers who rely on the title to "
            "know where they are cannot tell the product page from the contact page.",
            check=lambda page: Outcome(),  # site-level, see check_site()
            advisory=True,
        ),
        Rule(
            id="html-lang",
            title="Page language not declared",
            criteria=("3.1.1",),
            severity=Severity.HIGH,
            fix='Set the language on the <html> element, e.g. <html lang="en"> or lang="de".',
            owner_text="Screen readers choose the voice and pronunciation from the declared "
            "language. Without it a German page may be read with English pronunciation and "
            "become hard to understand.",
            check=document.check_html_lang,
        ),
        Rule(
            id="heading-structure",
            title="Heading structure",
            criteria=("1.3.1",),
            severity=Severity.LOW,
            fix="Start each page with one <h1> and do not skip levels (h2 then h3, not h2 "
            "then h4).",
            owner_text="Many screen reader users jump from heading to heading to scan a page, "
            "the way sighted visitors skim. A missing main heading or skipped levels make "
            "the page feel incomplete.",
            check=document.check_headings,
            advisory=True,
        ),
        Rule(
            id="link-purpose",
            title='Vague link texts ("click here", "mehr", "подробнее")',
            criteria=("2.4.4",),
            severity=Severity.MEDIUM,
            fix='Write what the link opens: "Shipping costs" instead of "click here", or add '
            "an aria-label.",
            owner_text="Screen reader users often list all links on a page. A list of ten "
            '"read more" links tells them nothing about where each one leads.',
            check=content.check_link_purpose,
            advisory=True,
        ),
        Rule(
            id="link-name",
            title="Links without text",
            criteria=("2.4.4", "4.1.2"),
            severity=Severity.HIGH,
            fix='Add text to icon links, e.g. alt text on the image or aria-label="Shopping cart".',
            owner_text="An icon link such as a cart or a social media logo with no text is "
            'announced only as "link". The customer cannot know it leads to the cart.',
            check=content.check_link_name,
        ),
        Rule(
            id="button-name",
            title="Buttons without text",
            criteria=("4.1.2",),
            severity=Severity.HIGH,
            fix='Put text inside the button or add aria-label="Add to cart" to icon buttons.',
            owner_text="Icon buttons (a magnifier, a basket, an X) with no text are announced as "
            'just "button". Screen reader users cannot search, buy or close a pop-up.',
            check=content.check_button_name,
        ),
        Rule(
            id="frame-title",
            title="Embedded frames without a title",
            criteria=("4.1.2",),
            severity=Severity.MEDIUM,
            fix='Add a title to every <iframe>, e.g. title="Map: how to find our shop".',
            owner_text="Maps, videos and booking widgets are embedded as frames. Without a "
            "title a screen reader cannot say what the embedded box is.",
            check=content.check_iframe_title,
        ),
        Rule(
            id="duplicate-id",
            title="Duplicate ids",
            criteria=("4.1.1",),
            severity=Severity.LOW,
            fix="Make every id unique on the page.",
            owner_text="Two elements with the same internal name (id) confuse scripts and "
            "in-page links. WCAG 2.2 no longer counts this as a failure on its own, so it is "
            "listed as a best practice.",
            check=document.check_duplicate_ids,
            advisory=True,
        ),
        Rule(
            id="duplicate-id-referenced",
            title="Labels point to a duplicate id",
            criteria=("1.3.1", "4.1.2"),
            severity=Severity.MEDIUM,
            fix="Make the id unique, so <label for> and aria-labelledby point to one element.",
            owner_text="When a label points to an id that appears twice, the screen reader may "
            "read the label for the wrong field or not at all.",
            check=document.check_duplicate_referenced_ids,
        ),
        Rule(
            id="meta-viewport",
            title="Zoom is blocked on mobile",
            criteria=("1.4.4",),
            severity=Severity.HIGH,
            fix="Remove user-scalable=no and maximum-scale from the viewport meta tag.",
            owner_text="Many older customers and people with low vision zoom in with two "
            "fingers to read prices and small print. Blocking zoom stops them on the phone.",
            check=document.check_meta_viewport,
        ),
        Rule(
            id="bypass-blocks",
            title="No way to skip the menu",
            criteria=("2.4.1",),
            severity=Severity.MEDIUM,
            fix='Wrap the main content in <main> and add a "Skip to content" link as the first '
            "link on the page.",
            owner_text="People who use only the keyboard have to press Tab through the whole "
            "menu on every page before reaching the products. A skip link and a main area "
            "let them jump straight to the content.",
            check=document.check_bypass,
            advisory=True,
        ),
        Rule(
            id="color-contrast",
            title="Low text contrast (inline colours)",
            criteria=("1.4.3",),
            severity=Severity.HIGH,
            fix="Darken the text or lighten the background until the ratio is at least 4.5:1 "
            "(3:1 for large text).",
            owner_text="Light grey text on white is hard to read for people with weaker "
            "eyesight, and for everyone on a phone in sunlight.",
            check=content.check_inline_contrast,
        ),
        Rule(
            id="autoplay-audio",
            title="Media that plays by itself",
            criteria=("1.4.2",),
            severity=Severity.MEDIUM,
            fix="Do not autoplay sound: remove autoplay, or add muted and visible controls.",
            owner_text="Sound that starts by itself drowns out the screen reader, so a blind "
            "visitor cannot hear the page until they find the stop button, which they cannot "
            "find without hearing the page.",
            check=content.check_autoplay,
            advisory=True,
        ),
    ]
}


def _status(rule: Rule, outcome: Outcome) -> CheckStatus:
    if outcome.issues:
        return CheckStatus.WARNING if rule.advisory else CheckStatus.FAIL
    return CheckStatus.PASS if outcome.checked else CheckStatus.NOT_APPLICABLE


def run_rules(page: Page) -> tuple[list[Issue], dict[str, CheckStatus]]:
    """Every page rule on one page: the issues and a pass/fail/n/a status per rule."""
    issues: list[Issue] = []
    checks: dict[str, CheckStatus] = {}
    for rule in RULES.values():
        if rule.id == "page-title-unique":
            continue
        outcome = rule.check(page)
        issues.extend(outcome.issues)
        checks[rule.id] = _status(rule, outcome)
    issues.sort(key=lambda i: i.severity.rank)
    return issues, checks


def check_site(pages: list[PageReport]) -> None:
    """Rules that need all pages at once. Adds issues to the pages in place."""
    analysed = [p for p in pages if p.analysed]
    by_title: dict[str, list[PageReport]] = defaultdict(list)
    for page in analysed:
        if page.title:
            by_title[page.title.casefold()].append(page)
    for page in analysed:
        if not page.title or len(analysed) < 2:
            page.checks["page-title-unique"] = CheckStatus.NOT_APPLICABLE
            continue
        same = by_title[page.title.casefold()]
        if len(same) > 1:
            page.issues.append(
                Issue(
                    rule_id="page-title-unique",
                    severity=Severity.LOW,
                    message=f'The title "{page.title}" is used on {len(same)} pages.',
                )
            )
            page.checks["page-title-unique"] = CheckStatus.WARNING
        else:
            page.checks["page-title-unique"] = CheckStatus.PASS
