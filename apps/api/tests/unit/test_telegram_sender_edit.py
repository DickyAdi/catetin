"""`TelegramSender.update_message` — the Bot API call it actually makes.

The interesting behaviour is not in the handler: it is that Telegram removes
an inline keyboard by *omitting* `reply_markup` from `editMessageText`, so
"take the buttons away" and "leave the buttons alone" are the same call with a
different argument, and getting it backwards silently strands a live keyboard.

A stub `Bot` records the kwargs rather than a real one being patched, because
what is under test is the arguments, not PTB's HTTP layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from telegram import Bot, InlineKeyboardMarkup
from telegram.error import BadRequest, TelegramError

from catetin.adapters.outbound.telegram.sender import TelegramSender
from catetin.domain.models import User
from catetin.domain.ports.repositories import UnitOfWork
from tests.fakes.fake_repositories import FakeUnitOfWork
from tests.fakes.frozen_clock import FrozenClock

CHAT_ID = 12345678
MESSAGE_ID = 4242


class _StubBot:
    """Records `edit_message_text` kwargs; optionally fails the first call."""

    def __init__(self, error: TelegramError | None = None) -> None:
        self.edits: list[dict[str, Any]] = []
        self._error = error

    async def edit_message_text(self, text: str, **kwargs: Any) -> None:
        self.edits.append({"text": text, **kwargs})
        if self._error is not None:
            raise self._error


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork(FrozenClock(datetime(2026, 8, 15, 12, 0, tzinfo=UTC)))


@pytest.fixture
async def user(uow: FakeUnitOfWork) -> User:
    async with uow as u:
        created = await u.users.create("telegram", str(CHAT_ID), "Rina")
        await u.commit()
    return created


def _sender(uow: FakeUnitOfWork, bot: _StubBot) -> TelegramSender:
    return TelegramSender(cast(Bot, bot), lambda: cast(UnitOfWork, uow))


async def test_buttons_are_sent_as_a_single_keyboard_row(
    uow: FakeUnitOfWork, user: User
) -> None:
    bot = _StubBot()

    await _sender(uow, bot).update_message(
        user.id, MESSAGE_ID, "Hal 2", [("⬅️", "list:0"), ("➡️", "list:20")]
    )

    (edit,) = bot.edits
    assert (edit["text"], edit["chat_id"], edit["message_id"]) == (
        "Hal 2",
        CHAT_ID,
        MESSAGE_ID,
    )
    markup = edit["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    row = markup.inline_keyboard[0]
    assert [(b.text, b.callback_data) for b in row] == [
        ("⬅️", "list:0"),
        ("➡️", "list:20"),
    ]


@pytest.mark.parametrize("buttons", [None, []])
async def test_no_buttons_omits_reply_markup_which_is_what_strips_a_keyboard(
    uow: FakeUnitOfWork, user: User, buttons: list[tuple[str, str]] | None
) -> None:
    """`None` and `[]` mean the same thing to the port, and both have to reach
    Telegram as "no keyboard" rather than as an empty one."""
    bot = _StubBot()

    await _sender(uow, bot).update_message(user.id, MESSAGE_ID, "Oke, ditutup.", buttons)

    assert bot.edits[0]["reply_markup"] is None


async def test_an_unmodified_edit_is_swallowed(uow: FakeUnitOfWork, user: User) -> None:
    """A double tap that raced past the handler's guard: Telegram rejects the
    edit because the screen already says this, which is not a failure."""
    bot = _StubBot(BadRequest("Message is not modified: specified new message content"))

    await _sender(uow, bot).update_message(user.id, MESSAGE_ID, "Hal 2")

    assert len(bot.edits) == 1  # one attempt, no retry, no raise


async def test_a_message_too_old_to_edit_is_logged_not_raised(
    uow: FakeUnitOfWork, user: User
) -> None:
    """Best-effort like every other send: the caller has nothing to do about a
    message that is gone, and a handler must not die over one."""
    bot = _StubBot(BadRequest("Message to edit not found"))

    await _sender(uow, bot).update_message(user.id, MESSAGE_ID, "Hal 2")

    assert len(bot.edits) == 1


async def test_a_blocked_user_is_not_edited_at_all(
    uow: FakeUnitOfWork, user: User
) -> None:
    async with uow as u:
        await u.users.mark_blocked(user.id)
        await u.commit()
    bot = _StubBot()

    await _sender(uow, bot).update_message(user.id, MESSAGE_ID, "Hal 2")

    assert bot.edits == []
