"""Text helpers: a language-neutral search form of ingredient text, and recipe parsing.

Kitchens type recipes with and without diacritics ("süt" / "sut", "Müsli" / "Musli",
"ёлка" / "елка"), so both the dictionary and the recipe are compared in a folded form:
lower case, Latin diacritics removed, Turkish dotless "ı" and dotted "İ" turned into "i",
"ß" into "ss", Cyrillic "ё" into "е". Cyrillic letters are otherwise kept as they are.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

_FOLD = str.maketrans(
    {
        "ä": "a",
        "à": "a",
        "á": "a",
        "â": "a",
        "ã": "a",
        "å": "a",
        "æ": "ae",
        "ç": "c",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "ğ": "g",
        "ı": "i",
        "í": "i",
        "ì": "i",
        "î": "i",
        "ï": "i",
        "ñ": "n",
        "ö": "o",
        "ó": "o",
        "ò": "o",
        "ô": "o",
        "õ": "o",
        "ø": "o",
        "œ": "oe",
        "ş": "s",
        "ß": "ss",
        "ü": "u",
        "ú": "u",
        "ù": "u",
        "û": "u",
        "ÿ": "y",
        "ё": "е",
        "̇": "",  # combining dot above, left over from a decomposed "İ"
        "’": "'",
    }
)

# Letters of the folded alphabet: what a "word" is made of.
LETTERS = "a-zа-я"
WORD_RE = re.compile(rf"[{LETTERS}]+")


def fold(text: str) -> str:
    """Search form of a text: 'Süzme YOĞURT, İrmik' -> 'suzme yogurt, irmik'."""
    return fold_with_map(text)[0]


def fold_with_map(text: str) -> tuple[str, list[int]]:
    """Fold `text` and return, for every folded character, its index in the NFC text.

    Folding can change the length ("ß" -> "ss"), so the map is what lets the UI show the
    matched word exactly as the chef typed it ("fındığı", not "findigi").
    """
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    index: list[int] = []
    for i, char in enumerate(text):
        # "İ".lower() is "i" + a combining dot, so map it before lowering.
        folded = "i" if char == "İ" else char.lower().translate(_FOLD)
        out.append(folded)
        index.extend([i] * len(folded))
    return "".join(out), index


@dataclass
class Ingredient:
    """One recipe line. `parts` holds what was written in brackets after it."""

    text: str
    parts: list["Ingredient"] = field(default_factory=list)


_SEPARATORS = ",;\n•·"
_OPEN = "(["
_CLOSE = ")]"


def parse_ingredients(recipe: str) -> list[Ingredient]:
    """'pesto (basil, cashews), egg yolk; salt' -> pesto[basil, cashews], egg yolk, salt.

    Commas, semicolons, new lines and bullets separate ingredients. Text in round or square
    brackets after an ingredient lists what it is made of; brackets can be nested. Missing
    closing brackets are tolerated: the rest of the line is treated as the inside.
    """
    items, _ = _parse(recipe, 0, depth=0)
    return items


def _parse(text: str, pos: int, depth: int) -> tuple[list[Ingredient], int]:
    items: list[Ingredient] = []
    buffer: list[str] = []
    parts: list[Ingredient] = []

    def flush() -> None:
        name = " ".join("".join(buffer).split()).strip(" .:-–—*")
        if name or parts:
            items.append(Ingredient(name or "?", list(parts)))
        buffer.clear()
        parts.clear()

    while pos < len(text):
        char = text[pos]
        if char in _OPEN:
            inner, pos = _parse(text, pos + 1, depth + 1)
            parts.extend(inner)
            continue
        if char in _CLOSE:
            if depth > 0:
                flush()
                return items, pos + 1
            pos += 1  # a stray closing bracket at the top level
            continue
        if char in _SEPARATORS:
            flush()
        else:
            buffer.append(char)
        pos += 1
    flush()
    return items, pos


def canonical_recipe(items: list[Ingredient]) -> str:
    """Order-, case- and spacing-independent form of a recipe, used to detect changes."""

    def canon(item: Ingredient) -> str:
        name = " ".join(fold(item.text).split())
        if item.parts:
            name += "(" + ",".join(sorted(canon(p) for p in item.parts)) + ")"
        return name

    return "|".join(sorted(canon(i) for i in items))


def recipe_hash(recipe: str) -> str:
    """Two recipes get the same hash only if they list the same ingredients.

    Reordering lines, changing letter case or spacing, or typing without diacritics does
    not change it; adding, removing or renaming an ingredient does.
    """
    canonical = canonical_recipe(parse_ingredients(recipe))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
