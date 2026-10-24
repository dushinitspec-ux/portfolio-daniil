import pytest

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
    relative_luminance,
)

WHITE = RGBA(255, 255, 255)
BLACK = RGBA(0, 0, 0)


def ratio(fg: str, bg: str) -> float:
    a, b = parse_color(fg), parse_color(bg)
    assert a is not None and b is not None
    return contrast_ratio(a, b)


def test_777_on_white_is_4_48_and_fails_aa() -> None:
    value = ratio("#777", "#fff")
    assert format_ratio(value) == "4.48:1"
    assert value < 4.5


def test_767676_on_white_is_the_lightest_grey_that_passes() -> None:
    assert format_ratio(ratio("#767676", "#ffffff")) == "4.54:1"
    assert ratio("#777777", "#ffffff") < 4.5 <= ratio("#767676", "#ffffff")


def test_black_on_white_is_21_and_same_colour_is_1() -> None:
    assert contrast_ratio(BLACK, WHITE) == pytest.approx(21.0)
    assert contrast_ratio(WHITE, WHITE) == pytest.approx(1.0)


def test_ratio_does_not_depend_on_the_order() -> None:
    assert ratio("#595959", "#fff") == pytest.approx(ratio("#fff", "#595959"))
    assert format_ratio(ratio("#595959", "#fff")) == "7.00:1"


def test_relative_luminance_uses_the_wcag_formula() -> None:
    assert relative_luminance(WHITE) == pytest.approx(1.0)
    assert relative_luminance(BLACK) == 0.0
    # Pure red: 0.2126 (only the red coefficient remains).
    assert relative_luminance(RGBA(255, 0, 0)) == pytest.approx(0.2126)
    # A channel at the linear/gamma threshold: 10/255 = 0.0392 <= 0.04045, linear part.
    assert relative_luminance(RGBA(10, 10, 10)) == pytest.approx(10 / 255 / 12.92)


def test_format_ratio_rounds_but_never_up_to_a_threshold() -> None:
    assert format_ratio(4.4776) == "4.48:1"
    assert format_ratio(4.4999) == "4.49:1"  # failing, so not shown as "4.50:1"
    assert format_ratio(2.996) == "2.99:1"
    assert format_ratio(4.5) == "4.50:1"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#abc", RGBA(0xAA, 0xBB, 0xCC)),
        ("#AABBCC", RGBA(0xAA, 0xBB, 0xCC)),
        ("rgb(255, 0, 0)", RGBA(255, 0, 0)),
        ("rgb(255 0 0)", RGBA(255, 0, 0)),
        ("rgb(100%, 0%, 0%)", RGBA(255, 0, 0)),
        ("rgba(0, 0, 0, 0.5)", RGBA(0, 0, 0, 0.5)),
        ("rgb(0 0 0 / 50%)", RGBA(0, 0, 0, 0.5)),
        ("#ff000080", RGBA(255, 0, 0, 128 / 255)),
        ("rebeccapurple", RGBA(0x66, 0x33, 0x99)),
        ("hsl(0, 100%, 50%)", RGBA(255, 0, 0)),
        ("white !important", WHITE),
    ],
)
def test_parse_color_formats(text: str, expected: RGBA) -> None:
    assert parse_color(text) == expected


@pytest.mark.parametrize(
    "text", ["currentColor", "inherit", "var(--brand)", "linear-gradient(#fff, #000)", "blue-ish"]
)
def test_colours_that_need_the_rendered_page_are_not_guessed(text: str) -> None:
    assert parse_color(text) is None


def test_semi_transparent_text_is_blended_over_the_background() -> None:
    blended = RGBA(0, 0, 0, 0.5).over(WHITE)
    assert blended == RGBA(128, 128, 128)


def test_background_shorthand() -> None:
    assert background_color(parse_style("background: #fff no-repeat")) == WHITE
    assert background_color(parse_style("background: url(bg.png) #fff")) is None
    assert background_color(parse_style("background-color: black; background: red")) == BLACK


def test_large_text_thresholds() -> None:
    assert is_large_text(24, bold=False)
    assert not is_large_text(23.9, bold=False)
    assert is_large_text(18.67, bold=True)  # 14 pt bold
    assert not is_large_text(18, bold=True)
    assert not is_large_text(None, bold=True)
    assert font_size_px(parse_style("font-size: 18pt")) == pytest.approx(24)
    assert font_size_px(parse_style("font-size: 2em")) is None


def test_bold_detection() -> None:
    assert is_bold(parse_style("font-weight: 700"), "span")
    assert is_bold({}, "h2")
    assert not is_bold(parse_style("font-weight: normal"), "h2")
    assert not is_bold({}, "p")
