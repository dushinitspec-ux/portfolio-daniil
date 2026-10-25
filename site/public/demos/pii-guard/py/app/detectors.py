"""Find personal data in free text.

Each finder proposes candidates with a loose pattern and keeps only those that pass the
real check in validators.py (checksum, registry length, calendar date, numbering plan).
Detector.detect() runs them in PRIORITY order and blanks out what each one claims before
the next one runs.
"""

import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import date
from pathlib import Path

import phonenumbers
from phonenumbers import Leniency, PhoneNumberMatcher

from app.entities import PRIORITY, Entity, EntityType
from app.validators import (
    IBAN_LENGTHS,
    VAT_FORMATS,
    birth_date,
    card_is_valid,
    compact,
    email_is_valid,
    iban_is_valid,
    ipv4_is_valid,
)

# --- E-mail --------------------------------------------------------------------------

_EMAIL = re.compile(
    r"(?<![\w.%+-])"
    r"[A-Za-z0-9_%+-](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9_%+-])?"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}"
    r"(?![\w-])"
)


def find_emails(text: str) -> Iterator[Entity]:
    for m in _EMAIL.finditer(text):
        if email_is_valid(m.group()):
            yield Entity(EntityType.EMAIL, m.start(), m.end(), m.group(), m.group().lower())


# --- IBAN ----------------------------------------------------------------------------

_IBAN_START = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}")
_ALNUM_RUN = re.compile(r"[A-Za-z0-9]+")
_SPACES = " \u00a0"  # a space or a no-break space between the groups


def find_ibans(text: str) -> Iterator[Entity]:
    """IBANs in electronic form (DE89370400440532013000) or print form (groups of four).

    The registry length for the country says exactly how many characters to collect, so
    a word right after the IBAN ("... 0130 00 BIC") is never swallowed into it.
    """
    for m in _IBAN_START.finditer(text):
        expected = IBAN_LENGTHS.get(m.group()[:2].upper())
        if expected is None:
            continue
        collected, pos = len(m.group()), m.end()
        while collected < expected:
            if pos < len(text) and text[pos] in _SPACES:
                pos += 1
            run = _ALNUM_RUN.match(text, pos)
            if run is None or collected + len(run.group()) > expected:
                break
            collected += len(run.group())
            pos = run.end()
        if collected != expected or (pos < len(text) and text[pos].isalnum()):
            continue
        raw = text[m.start() : pos]
        if iban_is_valid(raw):
            yield Entity(EntityType.IBAN, m.start(), pos, raw, compact(raw))


# --- Runs of digit groups (cards, phone numbers) -------------------------------------


def _best_split[T](
    groups: Sequence[tuple[int, int]],
    accepts: Sequence[Callable[[int, int], T | None]],
    max_groups: int,
) -> list[tuple[int, int, T]]:
    """Split a run of digit groups into values so that as many groups as possible are covered.

    A run can hold more than one value, or a value with a stray number in front
    ("ref 12 4111 1111 1111 1111", "2026-114 0151 23456789"). Taking the longest match
    from the left is not enough: in "+49 30 12345678 0151 23456789" the first four groups
    are a valid Berlin number on their own, and the leftover "23456789" would leak. So
    every slice of whole groups is checked and the best split of the whole run is chosen
    (dynamic programming over the groups).

    `accepts` are checks from strict to loose. Covering more groups always wins, because an
    uncovered group may be part of a number and leak. Between splits that cover the same
    groups, the one with fewer slices from a looser check wins.
    """
    n = len(groups)
    # best[i] = (score, slices) for groups[i:]
    best: list[tuple[int, list[tuple[int, int, T]]]] = [(0, [])] * (n + 1)
    for i in range(n - 1, -1, -1):
        choice = best[i + 1]  # leave group i uncovered
        for j in range(i, min(n, i + max_groups)):
            for level, accept in enumerate(accepts):
                result = accept(groups[i][0], groups[j][1])
                if result is None:
                    continue
                score = 4 * (j - i + 1) - 3 * level + best[j + 1][0]
                if score > choice[0]:
                    choice = (score, [(groups[i][0], groups[j][1], result), *best[j + 1][1]])
                break
        best[i] = choice
    return best[0][1]


def _groups(run: re.Match[str], pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    return [(g.start() + run.start(), g.end() + run.start()) for g in pattern.finditer(run.group())]


# --- Payment cards -------------------------------------------------------------------


# Digit groups separated by a single space or hyphen: "4111 1111 1111 1111", "3782-822463-10005".
# Not after "+": "+49 30 ..." is a phone number.
_DIGIT_GROUPS = re.compile(r"(?<![\w+-])\d+(?:[ -]\d+)*(?![\w])")
_DIGITS = re.compile(r"\d+")


def _card_grouping_ok(lengths: Sequence[int]) -> bool:
    """Cards are printed in one block, in fours, or 4-6-5 / 4-6-4 (Amex, Diners).

    Without this rule two phone numbers in a row ("49 30 12345678 0151") passed as a
    Visa number one time in ten, just because the Luhn digit happened to fit.
    """
    if len(lengths) == 1:
        return True
    if list(lengths) in ([4, 6, 5], [4, 6, 4]):
        return True
    return all(n == 4 for n in lengths[:-1]) and 1 <= lengths[-1] <= 4


def find_cards(text: str) -> Iterator[Entity]:
    """Card numbers: a real issuer prefix and length, a valid Luhn digit, a real grouping."""

    def accept(start: int, end: int) -> str | None:
        parts = _DIGITS.findall(text, start, end)
        digits = "".join(parts)
        if card_is_valid(digits) and _card_grouping_ok([len(p) for p in parts]):
            return digits
        return None

    for run in _DIGIT_GROUPS.finditer(text):
        for start, end, digits in _best_split(_groups(run, _DIGITS), [accept], max_groups=5):
            yield Entity(EntityType.CARD, start, end, text[start:end], digits)


# --- EU VAT IDs ----------------------------------------------------------------------

_VAT_START = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(sorted(VAT_FORMATS)) + r")(?=[ ]?[0-9A-Z+*])"
)
# Group 1 is the separator before a block (none before the first one), group 2 the block.
_VAT_FIRST_GROUP = re.compile(r"()([0-9A-Z+*]+)")
_VAT_GROUP = re.compile(r"([ .])([0-9A-Z+*]+)")
_MAX_VAT_GROUPS = 6


def find_vat_ids(text: str) -> Iterator[Entity]:
    """EU VAT IDs: an uppercase country prefix and that country's VIES format.

    Written forms vary ("DE123456789", "DE 123 456 789", "DK12 34 56 78"), so the groups
    after the prefix are joined, longest combination first, until one fits the format.
    """
    for m in _VAT_START.finditer(text):
        country = m.group(1)
        pos = m.end() + (1 if text[m.end()] == " " else 0)
        groups: list[re.Match[str]] = []
        while len(groups) < _MAX_VAT_GROUPS:
            g = _VAT_GROUP.match(text, pos) if groups else _VAT_FIRST_GROUP.match(text, pos)
            if g is None:
                break
            groups.append(g)
            pos = g.end()
        for k in range(len(groups), 0, -1):
            body = "".join(g.group(2) for g in groups[:k])
            end = groups[k - 1].end()
            if end < len(text) and text[end].isalnum():
                continue
            if VAT_FORMATS[country].fullmatch(body):
                yield Entity(
                    EntityType.VAT_ID, m.start(), end, text[m.start() : end], country + body
                )
                break


# --- IPv4 ----------------------------------------------------------------------------

# Not part of a longer dotted number such as a version "1.2.3.4.5".
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?!\.?\d)")


def find_ipv4(text: str) -> Iterator[Entity]:
    for m in _IPV4.finditer(text):
        if ipv4_is_valid(m.group()):
            yield Entity(EntityType.IPV4, m.start(), m.end(), m.group(), m.group())


# --- Dates of birth ------------------------------------------------------------------

# Only dates close to one of these words: a bare date is usually an invoice or a meeting.
_BIRTH_WORDS = re.compile(
    r"\bborn\b|\bdate of birth\b|\bdob\b|\bd\.o\.b\.|\bbirthday\b"
    r"|\bgeb\.|\bgeboren\b|\bgeburtsdatum\b|\bgeburtstag\b"
    r"|\bdoğum\b|\bdoğdu\b"
    r"|\bродил(?:ся|ась)\b|\bдата рождения\b|\bд\.\s?р\."
    r"|\bnée? le\b|\bdate de naissance\b",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"(?<![\d.])(?:(?P<d>\d{1,2})[./-](?P<m>\d{1,2})[./-](?P<y>\d{4})"
    r"|(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2}))(?![\d])"
)
_LOOK_BACK = 40


def find_dates_of_birth(text: str, today: date | None = None) -> Iterator[Entity]:
    today = today or date.today()
    for m in _DATE.finditer(text):
        if m.group("iy"):
            born = birth_date(int(m.group("id")), int(m.group("im")), int(m.group("iy")), today)
        else:
            d, mo, y = int(m.group("d")), int(m.group("m")), int(m.group("y"))
            # Day first (EU), then month first (US) when the day-first reading is impossible.
            born = birth_date(d, mo, y, today) or birth_date(mo, d, y, today)
        if born is None:
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        before = text[max(line_start, m.start() - _LOOK_BACK) : m.start()]
        if _BIRTH_WORDS.search(before):
            yield Entity(EntityType.DATE_OF_BIRTH, m.start(), m.end(), m.group(), born.isoformat())


# --- Phone numbers -------------------------------------------------------------------


# Groups of digits as people write phone numbers: "+49", "(0)30", "(030)", "12345678",
# separated by one space, hyphen, dot or slash.
_PHONE_GROUP = r"[+(]?\d[\d()]*"
_PHONE_RUN = re.compile(rf"(?<![\w+]){_PHONE_GROUP}(?:[ \-./]{_PHONE_GROUP})*")
_PHONE_GROUPS = re.compile(_PHONE_GROUP)
_MAX_PHONE_GROUPS = 7  # "+49 (0) 30 123 456 78" is about as many as anyone uses


def _whole_match(
    candidate: str, regions: Sequence[str], leniency: Leniency
) -> phonenumbers.PhoneNumber | None:
    """The number if the whole candidate is one phone number in one of the regions."""
    for region in regions:
        for match in PhoneNumberMatcher(candidate, region, leniency=leniency):
            if match.start == 0 and match.end == len(candidate):
                return match.number
    return None


def find_phones(text: str, regions: Sequence[str]) -> Iterator[Entity]:
    """Phone numbers, validated against libphonenumber's numbering plans.

    First choice: a number that is VALID (assigned range, correct trunk prefix, not a
    date). Then, only for international numbers ("+49 ...", "0049 ..."), one that is
    POSSIBLE: an unassigned number is still somebody's number tomorrow, and missing it
    leaks it. PhoneNumberMatcher alone gives up on a whole run of digits when the run is
    not one number, so "2026-114 0151 23456789" or two numbers in a row came out with no
    phone number at all; that is why the run is split with _best_split().
    """

    def plausible(start: int, end: int) -> bool:
        # E.164 allows at most 15 digits, plus a "00" exit code; fewer than 5 is no number.
        return 5 <= sum(c.isdigit() for c in text[start:end]) <= 17

    def valid(start: int, end: int) -> phonenumbers.PhoneNumber | None:
        if not plausible(start, end):
            return None
        return _whole_match(text[start:end], regions, Leniency.VALID)

    def possible(start: int, end: int) -> phonenumbers.PhoneNumber | None:
        if not text.startswith(("+", "00"), start) or not plausible(start, end):
            return None
        return _whole_match(text[start:end], regions, Leniency.POSSIBLE)

    for run in _PHONE_RUN.finditer(text):
        groups = _groups(run, _PHONE_GROUPS)
        for start, end, number in _best_split(groups, [valid, possible], _MAX_PHONE_GROUPS):
            e164 = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
            yield Entity(EntityType.PHONE, start, end, text[start:end], e164)


# --- Names ---------------------------------------------------------------------------


def compile_names(names: Iterable[str]) -> re.Pattern[str] | None:
    """One pattern for a list of known names, longest first, whole words, case-sensitive."""
    unique = sorted({n.strip() for n in names if n.strip()}, key=len, reverse=True)
    if not unique:
        return None
    # "Anna  Schmidt" or a line break between the parts is still the same name.
    alternatives = "|".join(r"\s+".join(re.escape(part) for part in n.split()) for n in unique)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)")


def find_names(text: str, pattern: re.Pattern[str] | None) -> Iterator[Entity]:
    if pattern is None:
        return
    for m in pattern.finditer(text):
        canonical = " ".join(m.group().split()).casefold()
        yield Entity(EntityType.NAME, m.start(), m.end(), m.group(), canonical)


def load_names(path: Path | None) -> list[str]:
    """Names file: one name per line, '#' starts a comment."""
    if path is None:
        return []
    lines = (line.split("#", 1)[0].strip() for line in path.read_text("utf-8").splitlines())
    return [line for line in lines if line]


# --- All together --------------------------------------------------------------------


def resolve_overlaps(candidates: Iterable[Entity]) -> list[Entity]:
    """Keep the highest-priority candidate where several overlap, then the longest."""
    rank = {t: i for i, t in enumerate(PRIORITY)}
    ordered = sorted(candidates, key=lambda e: (rank[e.type], -(e.end - e.start), e.start))
    kept: list[Entity] = []
    for candidate in ordered:
        if not any(candidate.overlaps(k) for k in kept):
            kept.append(candidate)
    return sorted(kept, key=lambda e: e.start)


class Detector:
    def __init__(
        self,
        phone_regions: Sequence[str] = ("DE",),
        names: Iterable[str] = (),
        today: date | None = None,
    ) -> None:
        self.phone_regions = [r.upper() for r in phone_regions]
        self._names = compile_names(names)
        self._today = today

    def _finders(self) -> dict[EntityType, Callable[[str], Iterable[Entity]]]:
        return {
            EntityType.IBAN: find_ibans,
            EntityType.CARD: find_cards,
            EntityType.EMAIL: find_emails,
            EntityType.VAT_ID: find_vat_ids,
            EntityType.IPV4: find_ipv4,
            EntityType.DATE_OF_BIRTH: lambda t: find_dates_of_birth(t, self._today),
            EntityType.PHONE: lambda t: find_phones(t, self.phone_regions),
            EntityType.NAME: lambda t: find_names(t, self._names),
        }

    def detect(self, text: str) -> list[Entity]:
        """Run the finders in PRIORITY order on a working copy of the text.

        Whatever one finder claims is blanked out before the next one runs. A phone number
        right after an IBAN is then still found on its own, instead of a phone candidate
        that reaches into the IBAN being thrown away as a whole, number included.
        """
        finders = self._finders()
        working = text
        kept: list[Entity] = []
        for entity_type in PRIORITY:
            found = resolve_overlaps(finders[entity_type](working))
            kept.extend(found)
            working = _blank_out(working, found)
        return sorted(kept, key=lambda e: e.start)


# Not a letter, digit or separator, so it ends any candidate; same length keeps offsets.
_BLANK = "#"


def _blank_out(text: str, entities: Sequence[Entity]) -> str:
    if not entities:
        return text
    chars = list(text)
    for e in entities:
        chars[e.start : e.end] = _BLANK * (e.end - e.start)
    return "".join(chars)
