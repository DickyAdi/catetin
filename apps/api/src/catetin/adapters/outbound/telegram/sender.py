"""TelegramSender — implements `MessagingPort` over the shared PTB `Bot`
instance (constructed once, in `composition.py`, and injected here and into
the inbound `Application`).

The port is keyed on our internal `user_id`, not a Telegram chat id, so every
send resolves the user's `platform_user_id` (the chat id, for a private
chat) via a reader `UnitOfWork` first.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any

from catetin.domain.ports.repositories import UnitOfWork
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, RetryAfter, TelegramError

_logger = logging.getLogger("catetin.telegram.sender")

_CHUNK_SIZE = 4096


def chunk_text(text: str, size: int = _CHUNK_SIZE) -> list[str]:
    """Split on line boundaries, never mid-token, per the M1 reply rules."""
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > size:
        split_at = remaining.rfind("\n", 0, size)
        if split_at <= 0:
            split_at = size
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


class TelegramSender:
    def __init__(self, bot: Bot, reader_uow_factory: Callable[[], UnitOfWork]) -> None:
        self._bot = bot
        self._reader_uow_factory = reader_uow_factory

    async def _resolve_chat_id(self, user_id: int) -> int | None:
        async with self._reader_uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
        if user is None or user.blocked_at is not None:
            return None
        return int(user.platform_user_id)

    async def _send(
        self, chat_id: int, coro_factory: Callable[[], Coroutine[Any, Any, Any]]
    ) -> None:
        try:
            await coro_factory()
        except RetryAfter as exc:
            retry_after = exc.retry_after
            seconds = (
                retry_after.total_seconds()
                if isinstance(retry_after, timedelta)
                else float(retry_after)
            )
            await asyncio.sleep(seconds)
            try:
                await coro_factory()
            except TelegramError:
                _logger.exception("failed to deliver to chat %s after retry", chat_id)
        except Forbidden:
            _logger.info("user blocked the bot; chat_id=%s", chat_id)
        except TelegramError:
            _logger.exception("failed to deliver to chat %s", chat_id)

    async def send_text(self, user_id: int, text: str) -> None:
        chat_id = await self._resolve_chat_id(user_id)
        if chat_id is None:
            return
        for chunk in chunk_text(text):
            await self._send(chat_id, lambda c=chunk: self._bot.send_message(chat_id, c))  # type: ignore[misc]

    async def send_document(
        self, user_id: int, filename: str, content: bytes, caption: str | None = None
    ) -> None:
        chat_id = await self._resolve_chat_id(user_id)
        if chat_id is None:
            return
        await self._send(
            chat_id,
            lambda: self._bot.send_document(
                chat_id, content, filename=filename, caption=caption
            ),
        )

    async def ask_choice(self, user_id: int, prompt: str, options: list[str]) -> None:
        chat_id = await self._resolve_chat_id(user_id)
        if chat_id is None:
            return
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(opt, callback_data=f"choice:{opt}") for opt in options]]
        )
        await self._send(
            chat_id, lambda: self._bot.send_message(chat_id, prompt, reply_markup=keyboard)
        )
