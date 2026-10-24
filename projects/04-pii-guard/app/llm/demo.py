"""Offline stand-in for an LLM, so the whole round trip runs with no API key.

It is deterministic: the same masked input always gives the same answer. It quotes one
sentence of the last user message (the first one that holds a placeholder) and drafts a
reply that uses every placeholder it was given, so a placeholder often appears twice and
restoring the real values is visible on the page. It never sees a real value.
"""

import re
from collections.abc import Sequence

from app.entities import EntityType
from app.guard import Message
from app.masking import PLACEHOLDER

DISCLAIMER = "Demo model: offline, no LLM was called. This answer follows fixed rules."

# One sentence per type for the drafted reply. {p} is the placeholder.
REPLY_LINES: dict[EntityType, str] = {
    EntityType.EMAIL: "We will send the confirmation to {p}.",
    EntityType.PHONE: "If anything is unclear, we will call you at {p}.",
    EntityType.IBAN: "The refund will be paid to the account {p}.",
    EntityType.CARD: "The card {p} will not be charged again.",
    EntityType.VAT_ID: "The corrected invoice will show the VAT ID {p}.",
    EntityType.IPV4: "We will check the server logs for requests from {p}.",
    EntityType.DATE_OF_BIRTH: "We have noted the date of birth {p}.",
    EntityType.NAME: "{p} is copied on this reply.",
}

QUOTE_CHARS = 160


def quote_sentence(text: str) -> str:
    """The first sentence with a placeholder in it (or the first sentence), shortened."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    sentence = next((s for s in sentences if PLACEHOLDER.search(s)), sentences[0])
    if len(sentence) > QUOTE_CHARS:
        sentence = sentence[: QUOTE_CHARS - 1].rstrip() + "…"
    return sentence


class DemoLLM:
    name = "demo (offline)"

    async def complete(self, system: str, messages: Sequence[Message]) -> str:
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        tokens: list[tuple[str, EntityType]] = []
        for message in messages:
            for m in PLACEHOLDER.finditer(message.content):
                token, kind = f"<{m.group(1).upper()}_{m.group(2)}>", EntityType(m.group(1).upper())
                if (token, kind) not in tokens:
                    tokens.append((token, kind))

        lines = [DISCLAIMER, "", f'From your message: "{quote_sentence(last)}"', ""]
        if not tokens:
            lines.append("It reached me without any personal data, so there was nothing to mask.")
            return "\n".join(lines)

        names = [t for t, kind in tokens if kind is EntityType.NAME]
        lines.append("Draft reply:")
        lines.append(f"Dear {names[0]}," if names else "Hello,")
        lines.append("thank you for your message.")
        for token, kind in tokens:
            if names and token == names[0]:
                continue
            lines.append(REPLY_LINES[kind].format(p=token))
        return "\n".join(lines)
