"""Find Annex II allergens in a recipe with the curated dictionary.

For every ingredient line the matcher:
1. folds the text (app/text.py) and runs every dictionary pattern over it;
2. keeps the longest matches that do not overlap, so "peanut butter" wins over "butter"
   and "buckwheat" over "wheat";
3. turns them into allergen hits, Annex II exclusion notes and "known, no allergen" words;
4. reports every word it does not know.

An ingredient's status is FOUND (allergens found, every word known), NONE (every word
known, none of the 14) or CHECK (a person has to look: an unknown word, a word that only
*usually* means an allergen, an ambiguous word, or a "free-from" claim).
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from pydantic import BaseModel, Field

from app.dictionary import FREE_FROM_NOTE, Entry, Kind, all_entries
from app.i18n import Language
from app.text import LETTERS, WORD_RE, Ingredient, fold, fold_with_map, parse_ingredients

_LEFT = rf"(?<![{LETTERS}0-9])"
_RIGHT = rf"(?![{LETTERS}0-9])"
_GAP = r"[\s\-]*"

# Endings a short Turkish word may take ("süt" -> "sütü", "sütlü", "sütsüz").
_TR_SHORT_SUFFIXES = (
    "(?:"
    + "|".join(
        (
            *("u", "i", "a", "e", "lu", "li", "la", "le", "da", "de", "ta", "te"),
            *("dan", "den", "tan", "ten", "nu", "ni", "nun", "nin", "yla", "yle", "lar", "ler"),
            *("suz", "siz", "yu", "yi", "ya", "ye", "dur", "dir", "luk", "lik"),
        )
    )
    + ")?"
)
_TR_SOFTEN = {"k": "g", "p": "b", "t": "d"}
_TR_WITHOUT = ("siz", "suz")  # folded -sız/-siz/-suz/-süz: "without"
# Longest first: inside a compound there is no word boundary to force backtracking, so
# "(?:e|er)" would stop at "geriebene" + "r".
_DE_ENDINGS = "(?:ern|en|er|es|e|n|s)?"
_VOWELS = set("aeiouаеиоуыэюя")


def _word(word: str, language: Language, last: bool, exact: bool) -> str:
    escaped = re.escape(word)
    if exact:
        return escaped
    if language is Language.EN:
        if not last:
            return escaped
        if len(word) > 2 and word.endswith("y") and word[-2] not in _VOWELS:
            return re.escape(word[:-1]) + "(?:y|ies)"
        return escaped + "(?:s|es)?"
    if language is Language.DE:
        return escaped + _DE_ENDINGS
    if language is Language.RU:
        return escaped + "[а-я]{0,6}"
    # Turkish
    stem = escaped
    vowels = sum(ch in _VOWELS for ch in word)
    if word[-1] in _TR_SOFTEN and vowels >= 2:
        stem = f"(?:{escaped}|{re.escape(word[:-1] + _TR_SOFTEN[word[-1]])})"
    suffix = "[a-z]{0,10}" if len(word) >= 4 else _TR_SHORT_SUFFIXES
    return stem + (f"(?P<sfx>{suffix})" if last else suffix)


def build_regex(phrase: str, language: Language) -> str:
    """Regex for one dictionary phrase, run against folded text. See app/dictionary.py."""
    exact = phrase.startswith("=")
    never_compound = phrase.startswith("!")
    at_word_end = phrase.endswith("~")
    core = fold(phrase.strip().strip("=!~").strip())
    words = [w for w in re.split(r"[\s\-]+", core) if w]
    compound = (
        language is Language.DE
        and len(words) == 1
        and len(core) >= 4
        and not exact
        and not never_compound
    )
    if compound:
        # Inside a compound there are no word boundaries, but the word can still take an
        # ending: "gehackt" -> "gehackte", "frisch" -> "frische".
        return re.escape(words[0]) + _DE_ENDINGS
    body = _GAP.join(
        _word(w, language, last=i == len(words) - 1, exact=exact) for i, w in enumerate(words)
    )
    return ("" if at_word_end else _LEFT) + body + _RIGHT


@dataclass(frozen=True)
class Pattern:
    regex: re.Pattern[str]
    entry: Entry
    phrase: str  # as written in the dictionary, without markers
    language: Language
    weight: int  # length of the folded phrase: breaks ties between equal spans


_KIND_ORDER = {Kind.PRODUCT: 0, Kind.WORD: 1, Kind.EXCLUSION: 2, Kind.SAFE: 3}


@cache
def patterns() -> tuple[Pattern, ...]:
    compiled = []
    for entry in all_entries():
        for language, phrase in entry.phrases:
            regex = re.compile(build_regex(phrase, language))
            clean = phrase.strip().strip("=!~").strip()
            compiled.append(Pattern(regex, entry, clean, language, len(fold(clean))))
    return tuple(compiled)


# "Free-from" claims: matched before the allergen word inside them, never removing anything.
_ALLERGEN_WORDS_EN = (
    "gluten|lactose|dairy|milk|eggs?|nuts?|peanuts?|soy|soya|sesame|wheat|celery|mustard|"
    "sulphites?|sulfites?|fish|shellfish|allergens?"
)
_FREE_FROM = tuple(
    re.compile(p)
    for p in (
        rf"{_LEFT}(?:{_ALLERGEN_WORDS_EN}){_GAP}free{_RIGHT}",
        rf"{_LEFT}(?:free from|without|non|no){_GAP}(?:{_ALLERGEN_WORDS_EN}){_RIGHT}",
        rf"{_LEFT}(?:gluten|laktose|lactose|milch|ei|eier|nuss|nusse|erdnuss|soja|sesam|"
        rf"weizen|sellerie|senf){_GAP}frei[a-z]*{_RIGHT}",
        rf"{_LEFT}ohne{_GAP}(?:gluten|laktose|lactose|milch|eier?|nusse?|erdnusse?|soja|"
        rf"sesam|weizen|sellerie|senf){_RIGHT}",
        rf"{_LEFT}без{_GAP}(?:глютен|лактоз|молок|молочн|яиц|яйц|орех|арахис|сои|соев|"
        rf"кунжут|пшениц|рыб|сельдере|горчиц)[а-я]*{_RIGHT}",
    )
)


class Status(StrEnum):
    FOUND = "found"  # allergens found, every word known
    NONE = "none"  # every word known, none of the 14 allergens
    CHECK = "check"  # a person has to look at it


class Hit(BaseModel):
    allergen: int
    certain: bool  # False: the word only usually or possibly means this allergen
    found: str  # the text as written in the recipe
    term: str  # the dictionary phrase that matched
    language: Language
    note: str = ""  # what the dictionary says about this product


class IngredientResult(BaseModel):
    text: str
    parent: str | None = None  # "pesto" for the "cashews" in "pesto (basil, cashews)"
    status: Status
    hits: list[Hit] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)  # words not in the dictionary
    free_from: bool = False  # the line has a "-free" / "без" / "-sız" claim

    @property
    def label(self) -> str:
        return f"{self.parent} › {self.text}" if self.parent else self.text

    @property
    def allergens(self) -> set[int]:
        return {h.allergen for h in self.hits}

    @property
    def certain(self) -> set[int]:
        return {h.allergen for h in self.hits if h.certain}

    @property
    def uncertain(self) -> set[int]:
        return self.allergens - self.certain

    @property
    def all_notes(self) -> list[str]:
        """Notes of the matched products, then exclusion and free-from notes."""
        return _dedupe([h.note for h in self.hits if h.note] + self.notes)


class Analysis(BaseModel):
    items: list[IngredientResult] = Field(default_factory=list)

    @property
    def allergens(self) -> set[int]:
        """Everything the dictionary found or suspects: what the chef starts from."""
        return set().union(*(i.allergens for i in self.items)) if self.items else set()

    @property
    def certain(self) -> set[int]:
        return set().union(*(i.certain for i in self.items)) if self.items else set()

    @property
    def to_check(self) -> list[IngredientResult]:
        return [i for i in self.items if i.status is Status.CHECK]

    @property
    def unknown_words(self) -> list[str]:
        return [w for i in self.items for w in i.unknown]


@dataclass
class _Candidate:
    start: int
    end: int
    weight: int
    pattern: Pattern | None  # None: a free-from claim
    without: bool = False  # Turkish "-sız": the word means "without" the allergen


def _candidates(folded: str) -> list[_Candidate]:
    found: list[_Candidate] = []
    for pattern in patterns():
        for m in pattern.regex.finditer(folded):
            if m.end() == m.start():
                continue
            suffix = (m.groupdict().get("sfx") or "") if pattern.language is Language.TR else ""
            without = suffix.startswith(_TR_WITHOUT) and pattern.entry.kind in (
                Kind.WORD,
                Kind.PRODUCT,
            )
            found.append(_Candidate(m.start(), m.end(), pattern.weight, pattern, without))
    for regex in _FREE_FROM:
        for m in regex.finditer(folded):
            found.append(_Candidate(m.start(), m.end(), m.end() - m.start(), None))
    return found


def _select(candidates: list[_Candidate]) -> list[list[_Candidate]]:
    """Longest non-overlapping matches. Returns groups: the same word listed under two
    groups (German "Pudding": milk, maybe gluten) is one span with several entries."""

    def order(c: _Candidate) -> tuple[int, int, int, int]:
        kind = _KIND_ORDER[c.pattern.entry.kind] if c.pattern else -1
        return (-(c.end - c.start), -c.weight, kind, c.start)

    ranked = sorted(candidates, key=order)
    taken: list[list[_Candidate]] = []
    occupied: set[int] = set()
    for cand in ranked:
        span = set(range(cand.start, cand.end))
        if span & occupied:
            for group in taken:  # same span and same phrase length: merge
                head = group[0]
                if (head.start, head.end, head.weight) == (cand.start, cand.end, cand.weight):
                    group.append(cand)
                    break
            continue
        occupied |= span
        taken.append([cand])
    return sorted(taken, key=lambda g: g[0].start)


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def analyse_text(text: str) -> IngredientResult:
    """Analyse one ingredient line (without its bracketed parts)."""
    folded, index = fold_with_map(text)
    nfc = unicodedata.normalize("NFC", text)  # what `index` points into

    def as_written(start: int, end: int) -> str:
        return nfc[index[start] : index[end - 1] + 1]

    hits: list[Hit] = []
    notes: list[str] = []
    free_from = False
    strong: list[tuple[int, int]] = []  # spans that make a partly matched word "known"
    covered: set[int] = set()

    for group in _select(_candidates(folded)):
        head = group[0]
        covered |= set(range(head.start, head.end))
        allergen_entries = [
            c for c in group if c.pattern and c.pattern.entry.kind in (Kind.WORD, Kind.PRODUCT)
        ]
        if head.pattern is None or any(c.without for c in allergen_entries):
            free_from = True
            strong.append((head.start, head.end))
            word = as_written(head.start, head.end)
            if head.pattern is None:
                notes.append(f"'{word}': {FREE_FROM_NOTE}")
            else:
                notes.append(f"'{word}' means 'without {head.pattern.phrase}'. {FREE_FROM_NOTE}")
            continue
        if allergen_entries:
            strong.append((head.start, head.end))
            found = as_written(head.start, head.end)
            # The same word can be listed under several languages ("parmesan" is EN, TR
            # and DE): one hit per allergen, certain if any entry says so.
            merged: dict[int, Hit] = {}
            for cand in allergen_entries:
                assert cand.pattern is not None
                entry = cand.pattern.entry
                pairs = [(n, True) for n in entry.contains] + [(n, False) for n in entry.maybe]
                for number, certain in pairs:
                    known = merged.get(number)
                    if known and (known.certain or not certain):
                        continue
                    merged[number] = Hit(
                        allergen=number,
                        certain=certain,
                        found=found,
                        term=cand.pattern.phrase,
                        language=cand.pattern.language,
                        note=entry.note,
                    )
            hits.extend(merged.values())
            continue
        if head.pattern and head.pattern.entry.kind is Kind.EXCLUSION:
            strong.append((head.start, head.end))
            notes.append(f"{as_written(head.start, head.end)}: {head.pattern.entry.note}")

    unknown: list[str] = []
    for m in WORD_RE.finditer(folded):
        letters = set(range(m.start(), m.end()))
        if letters <= covered:
            continue
        partly_strong = any(s < m.end() and e > m.start() for s, e in strong)
        if partly_strong or len(m.group()) < 3:
            continue
        unknown.append(as_written(m.start(), m.end()))
    # Words under three letters are skipped as filler ("of", "g", "и"), but a line in which
    # nothing at all was recognised must not pass as "none of the 14": "XO" (sauce with
    # dried shrimp and scallops), or text garbled to "f?st?k" by a wrong encoding.
    if not covered and not unknown and WORD_RE.search(folded):
        unknown.append(nfc.strip())
    for token in re.findall(r"[^\s,;]+", nfc):
        if ("?" in token or "�" in token) and any(ch.isalpha() for ch in token):
            if token not in unknown:
                unknown.append(token)
            notes.append(GARBLED_NOTE)

    result = IngredientResult(
        text=text.strip(),
        status=Status.NONE,
        hits=hits,
        notes=_dedupe(notes),
        unknown=_dedupe(unknown),
        free_from=free_from,
    )
    result.status = _status(result)
    return result


def _status(result: IngredientResult) -> Status:
    if result.unknown or result.free_from or result.uncertain:
        return Status.CHECK
    return Status.FOUND if result.hits else Status.NONE


PARTS_NOTE = "Allergens are taken from the ingredients listed in brackets."
GARBLED_NOTE = (
    "A question mark inside a word usually means the text was garbled by a wrong "
    "encoding (for example 'f?st?k' for 'fıstık'): retype it."
)


def _analyse_item(item: Ingredient, parent: str | None) -> list[IngredientResult]:
    result = analyse_text(item.text)
    result.parent = parent
    if not item.parts:
        return [result]
    # The listed parts say what this product is made of, so its "usually contains" guesses
    # and its unknown words give way to them. What its name says for sure is kept.
    result.hits = [h for h in result.hits if h.certain]
    result.unknown = []
    result.notes = [*result.notes, PARTS_NOTE]
    result.status = _status(result)
    path = f"{parent} › {item.text}" if parent else item.text
    results = [result]
    for part in item.parts:
        results.extend(_analyse_item(part, path))
    return results


def analyse(recipe: str) -> Analysis:
    """Analyse a whole recipe: 'spaghetti, egg yolk, pecorino, guanciale'."""
    items: list[IngredientResult] = []
    for ingredient in parse_ingredients(recipe):
        items.extend(_analyse_item(ingredient, None))
    return Analysis(items=items)
