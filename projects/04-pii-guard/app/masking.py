"""Replace personal data with numbered placeholders, and put it back into the answer.

A Vault lives for one request and only in memory. It is never logged, stored or returned
by the API: the audit log and the responses only ever see placeholders and counts.
"""

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.entities import Entity, EntityType

# Built from the real type names, so names with digits (IPV4) and underscores
# (DATE_OF_BIRTH) both work. Tolerant on purpose: models sometimes write "<email_1>" or
# "< EMAIL_1 >".
_TYPE_NAMES = "|".join(sorted((t.value for t in EntityType), key=len, reverse=True))
PLACEHOLDER = re.compile(rf"<\s*({_TYPE_NAMES})_(\d+)\s*>", re.IGNORECASE)


def placeholder(entity_type: EntityType, number: int) -> str:
    return f"<{entity_type.value}_{number}>"


class Vault:
    """Placeholder <-> original value for one request. The same value gets the same number."""

    def __init__(self, texts: Iterable[str] = ()) -> None:
        self._by_key: dict[tuple[EntityType, str], str] = {}
        self._original: dict[str, str] = {}
        self._types: dict[str, EntityType] = {}
        self._next: Counter[EntityType] = Counter()
        # A text may already contain something like "<EMAIL_1>" (a template, a pasted
        # answer). New placeholders skip those numbers, so restoring never confuses them.
        self._reserved = {
            (m.group(1).upper(), int(m.group(2))) for t in texts for m in PLACEHOLDER.finditer(t)
        }

    def __repr__(self) -> str:  # never show the values
        return f"Vault({len(self._original)} placeholders)"

    def placeholder_for(self, entity: Entity) -> str:
        key = (entity.type, entity.canonical)
        if key not in self._by_key:
            number = self._next[entity.type] + 1
            while (entity.type.value, number) in self._reserved:
                number += 1
            self._next[entity.type] = number
            token = placeholder(entity.type, number)
            self._by_key[key] = token
            self._original[token] = entity.value
            self._types[token] = entity.type
        return self._by_key[key]

    def token_for(self, entity: Entity) -> str | None:
        """The placeholder already given to this value, without creating a new one."""
        return self._by_key.get((entity.type, entity.canonical))

    def original(self, token: str) -> str | None:
        return self._original.get(token)

    def type_of(self, token: str) -> EntityType | None:
        return self._types.get(token)

    @property
    def originals(self) -> list[str]:
        return list(self._original.values())

    def __len__(self) -> int:
        return len(self._original)


def mask(text: str, entities: Sequence[Entity], vault: Vault) -> str:
    """Replace each entity span with its placeholder. Entities must not overlap."""
    parts: list[str] = []
    last = 0
    for entity in sorted(entities, key=lambda e: e.start):
        parts.append(text[last : entity.start])
        parts.append(vault.placeholder_for(entity))
        last = entity.end
    parts.append(text[last:])
    return "".join(parts)


@dataclass(frozen=True)
class Segment:
    """A piece of text for the web page: plain, or one restored/masked value."""

    text: str
    kind: EntityType | None = None
    token: str | None = None  # the placeholder this piece came from / stands for


def _normalise(match: re.Match[str]) -> str:
    return f"<{match.group(1).upper()}_{int(match.group(2))}>"


def restore_segments(text: str, vault: Vault) -> list[Segment]:
    """Split an answer into plain text and restored values.

    Every occurrence of a placeholder is restored, however often the model repeats it.
    A placeholder the model invented (<EMAIL_7> when there was no seventh e-mail) is left
    as it is: guessing a value for it would put wrong data in front of the user.
    """
    segments: list[Segment] = []
    last = 0
    for m in PLACEHOLDER.finditer(text):
        token = _normalise(m)
        value = vault.original(token)
        if value is None:
            continue
        if m.start() > last:
            segments.append(Segment(text[last : m.start()]))
        segments.append(Segment(value, vault.type_of(token), token))
        last = m.end()
    if last < len(text):
        segments.append(Segment(text[last:]))
    return segments


def restore(text: str, vault: Vault) -> str:
    return "".join(s.text for s in restore_segments(text, vault))


def unknown_placeholders(text: str, vault: Vault) -> list[str]:
    """Placeholders in the answer that the gateway never created."""
    return [
        _normalise(m) for m in PLACEHOLDER.finditer(text) if vault.original(_normalise(m)) is None
    ]


def placeholder_segments(text: str) -> list[Segment]:
    """Split masked text so the page can highlight the placeholders."""
    segments: list[Segment] = []
    last = 0
    for m in PLACEHOLDER.finditer(text):
        if m.start() > last:
            segments.append(Segment(text[last : m.start()]))
        kind = EntityType.__members__.get(m.group(1).upper())
        segments.append(Segment(m.group(), kind, m.group()))
        last = m.end()
    if last < len(text):
        segments.append(Segment(text[last:]))
    return segments


def contains_value(text: str, value: str) -> bool:
    """True if value appears in text as a separate token (not inside a longer word)."""
    pattern = r"\s+".join(re.escape(part) for part in value.split())
    return re.search(rf"(?<!\w){pattern}(?!\w)", text) is not None
