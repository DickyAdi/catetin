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
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError

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


def _keyboard(buttons: list[tuple[str, str]] | None) -> InlineKeyboardMarkup | None:
    """One row of (label, callback_data), or None for "no keyboard at all".

    The None is load-bearing on the edit path: PTB omits a None `reply_markup`
    from the request, and an `editMessageText` without one is what strips a
    keyboard off a message.
    """
    if not buttons:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=data) for label, data in buttons]]
    )


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
        keyboard = _keyboard([(opt, f"choice:{opt}") for opt in options])
        await self._send(
            chat_id, lambda: self._bot.send_message(chat_id, prompt, reply_markup=keyboard)
        )

    async def ask_action(self, user_id: int, prompt: str, buttons: list[tuple[str, str]]) -> None:
        chat_id = await self._resolve_chat_id(user_id)
        if chat_id is None:
            return
        await self._send(
            chat_id,
            lambda: self._bot.send_message(
                chat_id, prompt, reply_markup=_keyboard(buttons)
            ),
        )

    async def update_message(
        self,
        user_id: int,
        message_id: int,
        text: str,
        buttons: list[tuple[str, str]] | None = None,
    ) -> None:
        """`editMessageText` — the same message, new text and new keyboard.

        Omitting `reply_markup` is how Telegram removes an inline keyboard, so
        `buttons=None` needs no special call: `_keyboard` returns None and PTB
        drops the field from the request.

        No `chunk_text` here, deliberately. Splitting an edit is meaningless —
        the extra chunks would have nowhere to go but new messages, which is
        the thing the caller asked not to happen.
        """
        chat_id = await self._resolve_chat_id(user_id)
        if chat_id is None:
            return

        async def edit() -> None:
            try:
                await self._bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=_keyboard(buttons),
                )
            except BadRequest as exc:
                # Telegram rejects an edit that would change nothing. It means
                # the screen already says what we wanted it to say, so it is
                # the intended state arriving early (a double tap), not a
                # failure worth a stack trace.
                if "not modified" not in str(exc).lower():
                    raise
                _logger.debug("edit was a no-op for chat %s message %s", chat_id, message_id)

        await self._send(chat_id, edit)
