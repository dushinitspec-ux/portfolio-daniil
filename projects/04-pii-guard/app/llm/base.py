"""What an LLM backend must do for the gateway, and the instructions it gets."""

from collections.abc import Sequence
from typing import Protocol

from app.guard import Message


class LLMError(Exception):
    """The provider failed or declined. The gateway answers 502 and logs the decision."""


class LLMClient(Protocol):
    name: str

    async def complete(self, system: str, messages: Sequence[Message]) -> str: ...


SYSTEM_PROMPT = """\
You are an assistant used by staff of a company. Before a message reaches you, a privacy \
gateway replaces personal data in it with placeholders such as <EMAIL_1>, <PHONE_2>, \
<IBAN_1> or <NAME_1>. The gateway puts the real values back into your answer before the \
user reads it.

Rules for placeholders:
- When you refer to a value, write its placeholder exactly as it appears, including the \
angle brackets, for example <EMAIL_1>. You may use a placeholder as often as you need.
- Never guess, invent or ask for the real values, and never create new placeholders.
- Treat each placeholder as the real value it stands for: <EMAIL_1> is an e-mail address, \
<NAME_1> is a person's name, and so on.
"""
