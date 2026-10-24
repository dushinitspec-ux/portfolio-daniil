"""Where alerts go: a Telegram chat, or the console in demo mode."""

import logging
import re
from typing import Protocol

from aiogram import Bot

logger = logging.getLogger(__name__)

_TAG = re.compile(r"</?[a-z]+>")


class Notifier(Protocol):
    async def send(self, text: str) -> None: ...


class ConsoleNotifier:
    """Demo mode: print alerts instead of sending them."""

    async def send(self, text: str) -> None:
        print(
            f"\n----- notification -----\n{_TAG.sub('', text)}\n------------------------",
            flush=True,
        )


class TelegramNotifier:
    def __init__(self, bot: Bot, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        await self._bot.send_message(self._chat_id, text)
