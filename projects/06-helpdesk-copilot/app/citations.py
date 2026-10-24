"""Numbered sources and the [1], [2] citations that point to them.

The LLM sees the retrieved sections as [1]..[k]. Its answer must cite them by number. Before
an answer is shown, every citation is checked: unknown numbers are removed, and an answer
left without any valid citation is not shown at all (the question becomes a ticket).
"""

import re
from dataclasses import dataclass

from app.knowledge import Section

# [1], [2][3] and [1, 2] are all accepted.
CITATION = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")


@dataclass(frozen=True)
class Source:
    number: int
    section: Section

    @property
    def label(self) -> str:
        return self.section.label


@dataclass(frozen=True)
class CitationCheck:
    text: str  # the answer with unknown citations removed
    cited: list[Source]  # sources the answer cites, in the order of first citation
    unknown: list[int]  # numbers that were not in the source list

    @property
    def grounded(self) -> bool:
        return bool(self.cited)


def number_sources(sections: list[Section]) -> list[Source]:
    return [Source(i, section) for i, section in enumerate(sections, start=1)]


def cited_numbers(text: str) -> list[int]:
    """Citation numbers in order of first appearance, without duplicates."""
    numbers: list[int] = []
    for match in CITATION.finditer(text):
        for part in match.group(1).split(","):
            number = int(part)
            if number not in numbers:
                numbers.append(number)
    return numbers


def check_citations(text: str, sources: list[Source]) -> CitationCheck:
    by_number = {s.number: s for s in sources}
    numbers = cited_numbers(text)
    unknown = [n for n in numbers if n not in by_number]

    def keep_known(match: re.Match[str]) -> str:
        known = [p.strip() for p in match.group(1).split(",") if int(p) in by_number]
        return "".join(f"[{n}]" for n in known)

    cleaned = CITATION.sub(keep_known, text) if unknown else text
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", re.sub(r"[ \t]{2,}", " ", cleaned)).strip()
    cited = [by_number[n] for n in numbers if n in by_number]
    return CitationCheck(cleaned, cited, unknown)


def format_sources(sources: list[Source]) -> str:
    """The source list shown under an answer: "[1] VPN for remote work › ..."."""
    return "\n".join(f"[{s.number}] {s.label}" for s in sources)
