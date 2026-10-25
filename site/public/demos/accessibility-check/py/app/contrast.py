"""CSS colour parsing and the WCAG 2.2 contrast ratio.

Relative luminance follows the WCAG 2.2 definition (sRGB, threshold 0.04045):
https://www.w3.org/TR/WCAG22/#dfn-relative-luminance
Contrast ratio = (L1 + 0.05) / (L2 + 0.05), L1 being the lighter colour.
"""

import colorsys
import math
import re
from dataclasses import dataclass

NORMAL_TEXT_MIN = 4.5
LARGE_TEXT_MIN = 3.0
# "Large scale" text in WCAG: at least 18 pt, or 14 pt bold. 1 pt = 4/3 px in CSS.
LARGE_PX = 24.0
LARGE_BOLD_PX = 14 * 4 / 3


@dataclass(frozen=True)
class RGBA:
    r: int
    g: int
    b: int
    a: float = 1.0

    @property
    def hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @property
    def opaque(self) -> bool:
        return self.a >= 1.0

    def over(self, backdrop: "RGBA") -> "RGBA":
        """Alpha-composite this colour over an opaque backdrop."""
        a = self.a
        return RGBA(
            round(self.r * a + backdrop.r * (1 - a)),
            round(self.g * a + backdrop.g * (1 - a)),
            round(self.b * a + backdrop.b * (1 - a)),
        )


def _channel(value_8bit: int) -> float:
    c = value_8bit / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: RGBA) -> float:
    return 0.2126 * _channel(color.r) + 0.7152 * _channel(color.g) + 0.0722 * _channel(color.b)


def contrast_ratio(a: RGBA, b: RGBA) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


THRESHOLDS = (LARGE_TEXT_MIN, NORMAL_TEXT_MIN, 7.0)


def format_ratio(ratio: float) -> str:
    """Round to two decimals (#777 on white is 4.4776 -> "4.48:1"), but never round a failing
    value up to a threshold: 4.497 is shown as "4.49:1", not as a passing-looking "4.50:1".
    The pass/fail decision always uses the unrounded ratio."""
    shown = round(ratio, 2)
    if any(ratio < threshold <= shown for threshold in THRESHOLDS):
        shown = math.floor(ratio * 100) / 100
    return f"{shown:.2f}:1"


def is_large_text(font_size_px: float | None, bold: bool) -> bool:
    if font_size_px is None:
        return False
    return font_size_px >= LARGE_PX or (bold and font_size_px >= LARGE_BOLD_PX)


def required_ratio(large: bool) -> float:
    return LARGE_TEXT_MIN if large else NORMAL_TEXT_MIN


# CSS Color Module Level 4 named colours.
NAMED_COLORS: dict[str, str] = {
    "aliceblue": "f0f8ff", "antiquewhite": "faebd7", "aqua": "00ffff",
    "aquamarine": "7fffd4", "azure": "f0ffff", "beige": "f5f5dc", "bisque": "ffe4c4",
    "black": "000000", "blanchedalmond": "ffebcd", "blue": "0000ff",
    "blueviolet": "8a2be2", "brown": "a52a2a", "burlywood": "deb887",
    "cadetblue": "5f9ea0", "chartreuse": "7fff00", "chocolate": "d2691e",
    "coral": "ff7f50", "cornflowerblue": "6495ed", "cornsilk": "fff8dc",
    "crimson": "dc143c", "cyan": "00ffff", "darkblue": "00008b", "darkcyan": "008b8b",
    "darkgoldenrod": "b8860b", "darkgray": "a9a9a9", "darkgreen": "006400",
    "darkgrey": "a9a9a9", "darkkhaki": "bdb76b", "darkmagenta": "8b008b",
    "darkolivegreen": "556b2f", "darkorange": "ff8c00", "darkorchid": "9932cc",
    "darkred": "8b0000", "darksalmon": "e9967a", "darkseagreen": "8fbc8f",
    "darkslateblue": "483d8b", "darkslategray": "2f4f4f", "darkslategrey": "2f4f4f",
    "darkturquoise": "00ced1", "darkviolet": "9400d3", "deeppink": "ff1493",
    "deepskyblue": "00bfff", "dimgray": "696969", "dimgrey": "696969",
    "dodgerblue": "1e90ff", "firebrick": "b22222", "floralwhite": "fffaf0",
    "forestgreen": "228b22", "fuchsia": "ff00ff", "gainsboro": "dcdcdc",
    "ghostwhite": "f8f8ff", "gold": "ffd700", "goldenrod": "daa520", "gray": "808080",
    "green": "008000", "greenyellow": "adff2f", "grey": "808080", "honeydew": "f0fff0",
    "hotpink": "ff69b4", "indianred": "cd5c5c", "indigo": "4b0082", "ivory": "fffff0",
    "khaki": "f0e68c", "lavender": "e6e6fa", "lavenderblush": "fff0f5",
    "lawngreen": "7cfc00", "lemonchiffon": "fffacd", "lightblue": "add8e6",
    "lightcoral": "f08080", "lightcyan": "e0ffff", "lightgoldenrodyellow": "fafad2",
    "lightgray": "d3d3d3", "lightgreen": "90ee90", "lightgrey": "d3d3d3",
    "lightpink": "ffb6c1", "lightsalmon": "ffa07a", "lightseagreen": "20b2aa",
    "lightskyblue": "87cefa", "lightslategray": "778899", "lightslategrey": "778899",
    "lightsteelblue": "b0c4de", "lightyellow": "ffffe0", "lime": "00ff00",
    "limegreen": "32cd32", "linen": "faf0e6", "magenta": "ff00ff", "maroon": "800000",
    "mediumaquamarine": "66cdaa", "mediumblue": "0000cd", "mediumorchid": "ba55d3",
    "mediumpurple": "9370db", "mediumseagreen": "3cb371", "mediumslateblue": "7b68ee",
    "mediumspringgreen": "00fa9a", "mediumturquoise": "48d1cc",
    "mediumvioletred": "c71585", "midnightblue": "191970", "mintcream": "f5fffa",
    "mistyrose": "ffe4e1", "moccasin": "ffe4b5", "navajowhite": "ffdead",
    "navy": "000080", "oldlace": "fdf5e6", "olive": "808000", "olivedrab": "6b8e23",
    "orange": "ffa500", "orangered": "ff4500", "orchid": "da70d6",
    "palegoldenrod": "eee8aa", "palegreen": "98fb98", "paleturquoise": "afeeee",
    "palevioletred": "db7093", "papayawhip": "ffefd5", "peachpuff": "ffdab9",
    "peru": "cd853f", "pink": "ffc0cb", "plum": "dda0dd", "powderblue": "b0e0e6",
    "purple": "800080", "rebeccapurple": "663399", "red": "ff0000",
    "rosybrown": "bc8f8f", "royalblue": "4169e1", "saddlebrown": "8b4513",
    "salmon": "fa8072", "sandybrown": "f4a460", "seagreen": "2e8b57",
    "seashell": "fff5ee", "sienna": "a0522d", "silver": "c0c0c0", "skyblue": "87ceeb",
    "slateblue": "6a5acd", "slategray": "708090", "slategrey": "708090", "snow": "fffafa",
    "springgreen": "00ff7f", "steelblue": "4682b4", "tan": "d2b48c", "teal": "008080",
    "thistle": "d8bfd8", "tomato": "ff6347", "turquoise": "40e0d0", "violet": "ee82ee",
    "wheat": "f5deb3", "white": "ffffff", "whitesmoke": "f5f5f5", "yellow": "ffff00",
    "yellowgreen": "9acd32",
}  # fmt: skip

_HEX = re.compile(r"#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})")
_FUNC = re.compile(r"(rgba?|hsla?)\(([^)]*)\)")


def _alpha(token: str | None) -> float:
    if token is None:
        return 1.0
    value = float(token[:-1]) / 100 if token.endswith("%") else float(token)
    return min(max(value, 0.0), 1.0)


def _rgb_component(token: str) -> int:
    value = float(token[:-1]) * 2.55 if token.endswith("%") else float(token)
    return round(min(max(value, 0.0), 255.0))


def _split_args(args: str) -> tuple[list[str], str | None]:
    """Both "10, 20, 30, 0.5" and "10 20 30 / 50%" syntaxes."""
    args = args.strip()
    alpha = None
    if "/" in args:
        args, alpha = (part.strip() for part in args.split("/", 1))
    parts = [p for p in re.split(r"[\s,]+", args) if p]
    if alpha is None and len(parts) == 4:
        alpha = parts.pop()
    return parts, alpha


def parse_color(value: str) -> RGBA | None:
    """Parse one CSS colour. Returns None for anything that cannot be resolved statically
    (currentColor, inherit, var(--x), gradients, unknown words)."""
    text = value.strip().lower().removesuffix("!important").strip()
    if text in NAMED_COLORS:
        h = NAMED_COLORS[text]
        return RGBA(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    if text == "transparent":
        return RGBA(0, 0, 0, 0.0)
    if match := _HEX.fullmatch(text):
        h = match.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h)
        alpha = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return RGBA(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)
    if match := _FUNC.fullmatch(text):
        kind, args = match.groups()
        try:
            parts, alpha = _split_args(args)
            if len(parts) != 3:
                return None
            if kind.startswith("rgb"):
                r, g, b = (_rgb_component(p) for p in parts)
                return RGBA(r, g, b, _alpha(alpha))
            hue = float(parts[0].removesuffix("deg")) % 360 / 360
            sat = float(parts[1].removesuffix("%")) / 100
            light = float(parts[2].removesuffix("%")) / 100
            r_f, g_f, b_f = colorsys.hls_to_rgb(hue, light, sat)
            return RGBA(round(r_f * 255), round(g_f * 255), round(b_f * 255), _alpha(alpha))
        except ValueError:
            return None
    return None


def parse_style(style: str) -> dict[str, str]:
    """Inline `style` attribute -> {property: value}, lower-cased, last declaration wins."""
    declarations: dict[str, str] = {}
    for part in style.split(";"):
        if ":" not in part:
            continue
        name, value = part.split(":", 1)
        name, value = name.strip().lower(), value.strip()
        if name and value:
            declarations[name] = value
    return declarations


def _tokens(value: str) -> list[str]:
    """Split a shorthand value on spaces that are not inside parentheses."""
    tokens, depth, current = [], 0, ""
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if current:
                tokens.append(current)
            current = ""
        else:
            current += ch
    if current:
        tokens.append(current)
    return tokens


def background_color(declarations: dict[str, str]) -> RGBA | None:
    """The background colour from background-color or the `background` shorthand.
    A background image or gradient makes the real backdrop unknown, so it returns None."""
    if "background-color" in declarations:
        return parse_color(declarations["background-color"])
    shorthand = declarations.get("background", "").lower()
    if not shorthand or "url(" in shorthand or "gradient(" in shorthand:
        return None
    for token in _tokens(shorthand.removesuffix("!important")):
        if color := parse_color(token.rstrip(",")):
            return color
    return None


def font_size_px(declarations: dict[str, str]) -> float | None:
    value = declarations.get("font-size", "").lower().removesuffix("!important").strip()
    if match := re.fullmatch(r"(\d+(?:\.\d+)?)(px|pt)", value):
        number = float(match.group(1))
        return number if match.group(2) == "px" else number * 4 / 3
    return None


def is_bold(declarations: dict[str, str], tag_name: str) -> bool:
    weight = declarations.get("font-weight", "").lower().removesuffix("!important").strip()
    if weight in ("bold", "bolder"):
        return True
    if weight.isdigit():
        return int(weight) >= 700
    if weight:  # "normal", "lighter", ...
        return False
    # Bold by default in every browser's built-in stylesheet.
    return tag_name in ("b", "strong", "th", "h1", "h2", "h3", "h4", "h5", "h6")
