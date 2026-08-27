"""`/zona` handler tests — the inline-keyboard zone picker, its stateless
`tz:` callback, and the still-supported `/zona <tz>` argument path.

Handlers are exercised directly against fakes: PTB's `Application` is never
built, so `context` is a stub carrying only what `_deps` reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from telegram import Update
from telegram import User as TelegramUser

from catetin.adapters.inbound.telegram.handlers import (
    TZ_OPTIONS,
    TZ_PREFIX,
    TelegramDeps,
    on_callback,
    on_timezone,
)
from catetin.application.onboarding import Onboarding
from tests.fakes.fake_messaging import FakeMessaging
from tests.fakes.fake_repositories import FakeUnitOfWork
from tests.fakes.frozen_clock import FrozenClock

TELEGRAM_ID = 12345678


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 8, 15, 12, 0, tzinfo=UTC))


@pytest.fixture
def uow(clock: FrozenClock) -> FakeUnitOfWork:
    return FakeUnitOfWork(clock)


@pytest.fixture
def messaging() -> FakeMessaging:
    return FakeMessaging()


@pytest.fixture
def deps(
    uow: FakeUnitOfWork, messaging: FakeMessaging, clock: FrozenClock
) -> TelegramDeps:
    """Only `onboarding`/`messaging`/`clock` are reachable from `/zona`; the
    other use cases stay unbuilt so a stray call fails loudly."""
    unused = cast(Any, None)
    return TelegramDeps(
        onboarding=Onboarding(uow),
        record_transactions=unused,
        manage_transactions=unused,
        summarize=unused,
        generate_report=unused,
        delete_account=unused,
        messaging=messaging,
        clock=clock,
        default_timezone="Asia/Jakarta",
    )


class _FakeContext:
    def __init__(self, deps: TelegramDeps, args: list[str] | None = None) -> None:
        self.application = SimpleNamespace(bot_data={"deps": deps})
        self.args = args


@dataclass
class _FakeQuery:
    data: str
    answered: bool = False

    async def answer(self) -> None:
        self.answered = True


@dataclass
class _FakeCallbackUpdate:
    callback_query: _FakeQuery
    effective_user: TelegramUser


def _message_update(text: str) -> Update:
    return Update.de_json(
        {
            "update_id": 1,
            "message": {
                "message_id": 42,
                "from": {"id": TELEGRAM_ID, "is_bot": False, "first_name": "Rina"},
                "chat": {"id": TELEGRAM_ID, "type": "private"},
                "date": 1755225600,
                "text": text,
            },
        },
        bot=None,
    )


def _callback_update(data: str) -> _FakeCallbackUpdate:
    return _FakeCallbackUpdate(
        callback_query=_FakeQuery(data=data),
        effective_user=TelegramUser(id=TELEGRAM_ID, is_bot=False, first_name="Rina"),
    )


async def _current_timezone(uow: FakeUnitOfWork) -> str:
    async with uow as open_uow:
        user = await open_uow.users.get_by_platform_identity("telegram", str(TELEGRAM_ID))
    assert user is not None
    return user.timezone


# --- bare `/zona` -----------------------------------------------------------


async def test_bare_zona_shows_current_timezone_and_zone_buttons(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    """TC-003 + TC-005: one message answers both "what is it now?" and
    "how do I change it?" — no free text to mistype."""
    await on_timezone(_message_update("/zona"), cast(Any, _FakeContext(deps)))

    assert messaging.texts == []  # the prompt rides on the keyboard, not a bare text
    assert len(messaging.actions) == 1
    asked = messaging.actions[0]
    assert "Asia/Jakarta" in asked.prompt  # the current zone, guessed at signup
    assert "Pilih zona waktumu:" in asked.prompt
    assert asked.buttons == [
        ("WIB", "tz:Asia/Jakarta"),
        ("WITA", "tz:Asia/Makassar"),
        ("WIT", "tz:Asia/Jayapura"),
    ]


async def test_bare_zona_reflects_a_previously_changed_timezone(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    await on_timezone(
        _message_update("/zona Asia/Jayapura"),
        cast(Any, _FakeContext(deps, args=["Asia/Jayapura"])),
    )
    await on_timezone(_message_update("/zona"), cast(Any, _FakeContext(deps)))

    assert "Asia/Jayapura" in messaging.actions[0].prompt


def test_tz_options_cover_the_three_indonesian_zones() -> None:
    assert TZ_OPTIONS == (
        ("WIB", "Asia/Jakarta"),
        ("WITA", "Asia/Makassar"),
        ("WIT", "Asia/Jayapura"),
    )


# --- `/zona <tz>` (unchanged, backward compatible) --------------------------


async def test_zona_with_argument_still_sets_the_timezone(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await on_timezone(
        _message_update("/zona Asia/Makassar"),
        cast(Any, _FakeContext(deps, args=["Asia/Makassar"])),
    )

    assert await _current_timezone(uow) == "Asia/Makassar"
    assert messaging.texts[-1].text == "Zona waktu diset ke Asia/Makassar."
    assert messaging.actions == []


async def test_zona_with_unknown_argument_is_rejected(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await on_timezone(
        _message_update("/zona Asia/Ngawi"),
        cast(Any, _FakeContext(deps, args=["Asia/Ngawi"])),
    )

    assert await _current_timezone(uow) == "Asia/Jakarta"
    assert messaging.texts[-1].text == "Zona waktu tidak dikenal: Asia/Ngawi"


# --- `tz:` callback ---------------------------------------------------------


@pytest.mark.parametrize(("label", "tz"), TZ_OPTIONS)
async def test_tz_callback_sets_timezone_and_confirms(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging, label: str, tz: str
) -> None:
    # Seed the user, then tap the button — as a real session would.
    await on_timezone(_message_update("/zona"), cast(Any, _FakeContext(deps)))

    update = _callback_update(f"{TZ_PREFIX}{tz}")
    await on_callback(cast(Any, update), cast(Any, _FakeContext(deps)))

    assert update.callback_query.answered is True
    assert await _current_timezone(uow) == tz
    assert messaging.texts[-1].text == f"Zona waktu diset ke {tz}."


async def test_tz_callback_works_without_any_pending_state(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """Unlike `choice:`, the zone tap carries its payload — a restart that
    empties `pending_choices` must not turn it into "sesi kedaluwarsa"."""
    assert deps.pending_choices == {}

    await on_callback(
        cast(Any, _callback_update("tz:Asia/Makassar")), cast(Any, _FakeContext(deps))
    )

    assert await _current_timezone(uow) == "Asia/Makassar"
    assert messaging.texts[-1].text == "Zona waktu diset ke Asia/Makassar."
    assert deps.pending_choices == {}


async def test_unknown_tz_callback_is_handled_gracefully(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await on_callback(
        cast(Any, _callback_update("tz:Asia/Unknown")), cast(Any, _FakeContext(deps))
    )

    assert await _current_timezone(uow) == "Asia/Jakarta"
    assert messaging.texts[-1].text == "Zona waktu tidak dikenal: Asia/Unknown"


async def test_tz_callback_does_not_consume_a_pending_choice(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """The two callback mechanisms are independent: an open ambiguous-kind
    question must survive a zone change."""
    await on_timezone(_message_update("/zona"), cast(Any, _FakeContext(deps)))
    user_id = 1
    deps.pending_choices[user_id] = [cast(Any, object())]

    await on_callback(
        cast(Any, _callback_update("tz:Asia/Jayapura")), cast(Any, _FakeContext(deps))
    )

    assert await _current_timezone(uow) == "Asia/Jayapura"
    assert len(deps.pending_choices[user_id]) == 1
