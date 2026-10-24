"""Every rule with at least one failing and one passing fixture."""

import pytest

from app.models import CheckStatus, PageReport, Severity
from app.rules import CRITERIA, RULES, Page, check_site, run_rules
from tests.conftest import check


def messages(rule_id: str, html: str) -> list[str]:
    return [i.message for i in check(rule_id, html).issues]


# --- registry ---------------------------------------------------------------------------


def test_every_rule_is_mapped_to_known_criteria_and_has_texts() -> None:
    for rule in RULES.values():
        assert rule.criteria and all(c in CRITERIA for c in rule.criteria), rule.id
        assert rule.fix and rule.owner_text and rule.title, rule.id


def test_parsing_criterion_is_marked_obsolete_in_wcag_22() -> None:
    assert CRITERIA["4.1.1"].obsolete
    assert RULES["duplicate-id"].advisory
    # Duplicates that break labels are reported under the criteria that still exist.
    assert RULES["duplicate-id-referenced"].criteria == ("1.3.1", "4.1.2")


def test_run_rules_gives_a_status_for_every_page_rule() -> None:
    page = Page('<html lang="en"><head><title>Shop</title></head><body><p>Hi</p></body></html>')
    issues, checks = run_rules(page)
    assert set(checks) == set(RULES) - {"page-title-unique"}
    assert checks["image-alt"] is CheckStatus.NOT_APPLICABLE
    assert checks["page-title"] is CheckStatus.PASS
    assert checks["bypass-blocks"] is CheckStatus.WARNING  # advisory rule -> warning
    assert all(i.rule_id in RULES for i in issues)


# --- 1.1.1 images -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "html",
    [
        '<img src="bag.jpg">',
        '<img src="bag.jpg" alt="IMG_2041.jpg">',
        '<img src="bag.jpg" alt="DSC00012">',
        '<input type="image" src="go.png">',
    ],
)
def test_image_alt_fails(html: str) -> None:
    assert check("image-alt", html).issues


@pytest.mark.parametrize(
    "html",
    [
        '<img src="bag.jpg" alt="Brown leather tote">',
        '<img src="line.png" alt="">',  # decorative
        '<img src="x.png" aria-hidden="true">',
        '<img src="x.png" role="presentation">',
        '<img src="x.png" aria-label="Logo of the shop">',
        '<input type="image" src="go.png" alt="Search">',
    ],
)
def test_image_alt_passes(html: str) -> None:
    outcome = check("image-alt", html)
    assert not outcome.issues


def test_missing_alt_is_high_and_filename_alt_is_medium() -> None:
    assert check("image-alt", '<img src="a.png">').issues[0].severity is Severity.HIGH
    assert check("image-alt", '<img src="a.png" alt="a.png">').issues[0].severity is Severity.MEDIUM


# --- forms ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "html",
    [
        '<input type="text" name="name">',
        '<input name="email">',
        "<select><option>A</option></select>",
        "<textarea></textarea>",
        '<label>Name</label><input id="n">',  # label not connected to the field
    ],
)
def test_form_label_fails(html: str) -> None:
    assert len(check("form-label", html).issues) == 1


@pytest.mark.parametrize(
    "html",
    [
        '<label for="n">Name</label><input id="n">',
        "<label>Name <input></label>",
        '<input aria-label="Search the shop">',
        '<span id="l">Phone</span><input aria-labelledby="l">',
        '<input type="hidden" name="csrf">',
        '<input type="submit">',
        '<input title="Quantity">',
    ],
)
def test_form_label_passes(html: str) -> None:
    assert not check("form-label", html).issues


def test_placeholder_only_is_a_separate_warning() -> None:
    html = '<input type="email" placeholder="Your e-mail">'
    assert not check("form-label", html).issues
    assert "placeholder" in messages("label-placeholder", html)[0]
    labelled = '<label for="e">E-mail</label><input id="e" placeholder="name@example.com">'
    assert not check("label-placeholder", labelled).issues


# --- document -----------------------------------------------------------------------------


def test_page_title() -> None:
    assert check("page-title", "<html><head></head><body></body></html>").issues
    assert check("page-title", "<html><head><title> </title></head></html>").issues
    assert not check("page-title", "<html><head><title>Contact – Shop</title></head></html>").issues
    svg_only = "<html><body><svg><title>Icon</title></svg></body></html>"
    assert check("page-title", svg_only).issues  # an SVG title is not the page title


@pytest.mark.parametrize(
    ("html_tag", "fails"),
    [
        ("<html>", True),
        ('<html lang="">', True),
        ('<html lang="en_US">', True),
        ('<html lang="english">', True),
        ('<html lang="en">', False),
        ('<html lang="de-DE">', False),
        ('<html lang="zh-Hant-TW">', False),
    ],
)
def test_html_lang(html_tag: str, fails: bool) -> None:
    html = f"<!doctype html>{html_tag}<head><title>T</title></head><body></body></html>"
    assert bool(check("html-lang", html).issues) is fails


@pytest.mark.parametrize(
    ("content", "severity"),
    [
        ("width=device-width, initial-scale=1, user-scalable=no", Severity.HIGH),
        ("width=device-width, user-scalable=0", Severity.HIGH),
        ("width=device-width, initial-scale=1, maximum-scale=1", Severity.MEDIUM),
        ("width=device-width, initial-scale=1", None),
        ("width=device-width, maximum-scale=5", None),
    ],
)
def test_meta_viewport(content: str, severity: Severity | None) -> None:
    html = f'<html lang="en"><head><meta name="viewport" content="{content}"></head></html>'
    issues = check("meta-viewport", html).issues
    assert (issues[0].severity if issues else None) is severity


def test_meta_viewport_not_applicable_without_the_tag() -> None:
    assert check("meta-viewport", "<p>x</p>").checked == 0


def test_headings() -> None:
    assert "no <h1>" in messages("heading-structure", "<h2>Products</h2>")[0]
    skipped = messages("heading-structure", "<h1>Shop</h1><h2>Bags</h2><h4>Tote</h4>")
    assert skipped == [
        "Heading level jumps from h2 to h4; screen reader users may think a section is missing."
    ]
    assert "empty" in messages("heading-structure", "<h1>Shop</h1><h2> </h2>")[0]
    assert not check(
        "heading-structure", "<h1>Shop</h1><h2>Bags</h2><h3>Tote</h3><h2>Info</h2>"
    ).issues


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<nav><a href='/'>Home</a></nav><div>Products</div>", "No <main> landmark and no skip"),
        ("<a href='#content'>Skip</a><main>Hi</main>", "does not exist"),
        ("<a href='#c'>Skip</a><div id='c'>Hi</div>", "No <main> landmark. The skip link"),
    ],
)
def test_bypass_blocks_warnings(html: str, expected: str) -> None:
    assert expected in messages("bypass-blocks", html)[0]


@pytest.mark.parametrize(
    "html",
    [
        "<main><h1>Hi</h1></main>",
        "<div role='main'>Hi</div>",
        "<a href='#main'>Skip to content</a><main id='main'>Hi</main>",
    ],
)
def test_bypass_blocks_passes(html: str) -> None:
    assert not check("bypass-blocks", html).issues


def test_duplicate_ids_split_by_whether_a_label_points_to_them() -> None:
    plain = '<div id="product">A</div><div id="product">B</div>'
    assert check("duplicate-id", plain).issues[0].severity is Severity.LOW
    assert not check("duplicate-id-referenced", plain).issues

    referenced = '<label for="email">E-mail</label><input id="email"><input id="email">'
    assert not check("duplicate-id", referenced).issues
    assert check("duplicate-id-referenced", referenced).issues[0].severity is Severity.MEDIUM
    assert not check("duplicate-id", '<div id="a"></div><div id="b"></div>').issues


def test_label_for_belongs_to_the_first_element_with_the_id() -> None:
    html = '<label for="email">E-mail</label><input id="email"><input id="email">'
    issues = check("form-label", html).issues
    assert len(issues) == 1  # the second field gets no label, like in a browser


# --- links and buttons --------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", ["Click here", "read more", "Mehr", "hier klicken", "Подробнее", "здесь",
             "Devamını oku", "buraya tıklayın", "En savoir plus", "Leer más", "More »"]
)  # fmt: skip
def test_vague_link_texts_in_several_languages(text: str) -> None:
    assert check("link-purpose", f'<a href="/x">{text}</a>').issues


@pytest.mark.parametrize(
    "html",
    [
        '<a href="/shipping">Shipping costs</a>',
        '<a href="/x" aria-label="Read more about the leather tote">Read more</a>',
        '<a href="/x">Подробнее о доставке</a>',
        "<a>Read more</a>",  # no href: not a link
    ],
)
def test_descriptive_links_pass(html: str) -> None:
    assert not check("link-purpose", html).issues


def test_repeated_vague_links_are_reported_once_with_a_count() -> None:
    issues = check("link-purpose", '<a href="/a">Read more</a>' * 3).issues
    assert len(issues) == 1 and issues[0].count == 3


@pytest.mark.parametrize(
    "html",
    [
        '<a href="/cart"></a>',
        '<a href="/cart"><img src="cart.svg"></a>',
        '<a href="/cart"><img src="cart.svg" alt=""></a>',
        '<a href="/ig"><svg viewBox="0 0 2 2"><rect/></svg></a>',
        '<a href="/x"><span aria-hidden="true">→</span></a>',
    ],
)
def test_link_name_fails(html: str) -> None:
    assert check("link-name", html).issues


@pytest.mark.parametrize(
    "html",
    [
        '<a href="/cart">Cart</a>',
        '<a href="/cart"><img src="cart.svg" alt="Shopping cart"></a>',
        '<a href="/cart" aria-label="Shopping cart"><svg></svg></a>',
        '<a href="/ig"><svg><title>Instagram</title></svg></a>',
        '<a href="/x" title="Our Instagram page"><i class="icon"></i></a>',
    ],
)
def test_link_name_passes(html: str) -> None:
    assert not check("link-name", html).issues


@pytest.mark.parametrize(
    "html",
    [
        "<button></button>",
        '<button><svg viewBox="0 0 1 1"></svg></button>',
        '<input type="button">',
        '<input type="button" value=" ">',
        '<div role="button"></div>',
    ],
)
def test_button_name_fails(html: str) -> None:
    assert len(check("button-name", html).issues) == 1


@pytest.mark.parametrize(
    "html",
    [
        "<button>Add to cart</button>",
        '<button aria-label="Close"><svg></svg></button>',
        '<input type="submit">',  # browsers call it "Submit"
        '<input type="button" value="Send">',
        '<div role="button">Menu</div>',
        "<button hidden></button>",
    ],
)
def test_button_name_passes(html: str) -> None:
    assert not check("button-name", html).issues


def test_iframe_title() -> None:
    assert check("frame-title", '<iframe src="map.html"></iframe>').issues
    assert not check(
        "frame-title", '<iframe src="m.html" title="Map: find our shop"></iframe>'
    ).issues
    assert check("frame-title", '<iframe src="t.html" aria-hidden="true"></iframe>').checked == 0


# --- media and contrast -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "flagged"),
    [
        ('<video src="a.mp4" autoplay></video>', True),
        ('<audio src="a.mp3" autoplay controls></audio>', True),
        ('<video src="a.mp4" autoplay muted loop></video>', False),
        ('<video src="a.mp4" controls></video>', False),
        ('<iframe title="v" src="https://player.test/v?autoplay=1"></iframe>', True),
        ('<iframe title="v" src="https://player.test/v?autoplay=1&amp;mute=1"></iframe>', False),
    ],
)
def test_autoplay(html: str, flagged: bool) -> None:
    assert bool(check("autoplay-audio", html).issues) is flagged


def test_contrast_fails_for_777_on_white() -> None:
    issues = check("color-contrast", '<p style="color:#777;background:#fff">Price</p>').issues
    assert len(issues) == 1
    assert "4.48:1" in issues[0].message and "4.5:1" in issues[0].message


def test_contrast_passes_and_uses_large_text_threshold() -> None:
    assert not check("color-contrast", '<p style="color:#595959;background:#fff">OK</p>').issues
    # #949494 on white is 3.03:1: fails for normal text, passes for 24px text.
    assert check("color-contrast", '<p style="color:#949494;background:#fff">Small</p>').issues
    big = '<p style="color:#949494;background:#fff;font-size:24px">Big</p>'
    assert not check("color-contrast", big).issues


def test_contrast_takes_the_background_from_an_inline_ancestor() -> None:
    html = '<div style="background-color:#000"><span style="color:#333">Dark on black</span></div>'
    issues = check("color-contrast", html).issues
    assert issues and issues[0].severity is Severity.HIGH  # below 3:1


def test_contrast_is_not_guessed_without_an_inline_background() -> None:
    outcome = check("color-contrast", '<p style="color:#aaa">Unknown backdrop</p>')
    assert outcome.checked == 0 and not outcome.issues
    gradient = '<p style="color:#aaa;background:linear-gradient(#fff,#000)">x</p>'
    assert check("color-contrast", gradient).checked == 0


def test_identical_colour_pairs_are_reported_once() -> None:
    html = '<p style="color:#aaa;background:#fff">a</p>' * 3
    issues = check("color-contrast", html).issues
    assert len(issues) == 1 and issues[0].count == 3


# --- site-level ----------------------------------------------------------------------------


def test_duplicate_titles_across_pages() -> None:
    pages = [
        PageReport(url=f"https://shop.test/{n}", final_url="", title=t, analysed=True)
        for n, t in [("a", "Shop"), ("b", "shop"), ("c", "Contact – Shop")]
    ]
    check_site(pages)
    assert [p.checks["page-title-unique"] for p in pages] == [
        CheckStatus.WARNING,
        CheckStatus.WARNING,
        CheckStatus.PASS,
    ]
    assert "used on 2 pages" in pages[0].issues[0].message
