"""Offline provider for demo mode: extractive answers and rule-based triage.

The answer is the best matching section itself, cited as [1]. It cannot rephrase or
translate, but it never says anything the knowledge base does not say.
"""

import re

from app.citations import Source
from app.llm.base import AnswerDraft
from app.triage import Triage, triage_by_rules

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s")


def plain(markdown: str) -> str:
    """Section text as it is shown in a chat: no Markdown emphasis, no hard line wraps.

    The knowledge base is wrapped at ~95 characters for editing. Lines of a paragraph are
    joined; a list item starts a new line; a blank line still separates paragraphs.
    """
    text = _CODE.sub(r"\1", _BOLD.sub(r"\1", markdown))
    lines: list[str] = []
    for raw in text.strip().splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
        elif lines and lines[-1] and not _LIST_ITEM.match(raw):
            lines[-1] += " " + line
        else:
            lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


class DemoLLM:
    name = "demo (extractive)"

    async def answer(self, question: str, sources: list[Source]) -> AnswerDraft:
        if not sources:
            return AnswerDraft(answered=False, answer="")
        best = sources[0]
        return AnswerDraft(answered=True, answer=f"{plain(best.section.text)} [{best.number}]")

    async def triage(self, text: str) -> Triage:
        return triage_by_rules(text)
