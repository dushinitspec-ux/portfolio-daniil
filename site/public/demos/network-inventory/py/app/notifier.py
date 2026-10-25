"""Where alerts go: a Telegram chat, or the console when no bot is configured."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    # Only a type here (main.py creates the Bot), so the scan pipeline imports without aiogram.
    from aiogram import Bot


class Notifier(Protocol):
    async def send(self, text: str) -> None: ...


class ConsoleNotifier:
    async def send(self, text: str) -> None:
        print(f"\n----- alert -----\n{text}\n-----------------", flush=True)


class TelegramNotifier:
    def __init__(self, bot: "Bot", chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        # Telegram's limit is 4096 characters; the alert is already capped per section.
        await self._bot.send_message(self._chat_id, text[:4096])
