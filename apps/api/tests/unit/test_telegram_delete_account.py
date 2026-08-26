"""`/hapusakun` at the handler level — the confirmation keyboard and its
nonce, TTL and replay rules.

This is the only button in the bot that destroys data, so the tests that
matter are the ones asserting a purge did *not* happen: a stale keyboard, a
replayed tap, someone else's nonce. Handlers run directly against fakes; PTB's
`Application` is never built.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from telegram import Update
from telegram import User as TelegramUser

from catetin.adapters.inbound.telegram.handlers import (
    DELETE_CANCEL,
    DELETE_DONE_MESSAGE,
    DELETE_DOWNLOAD_PREFIX,
    DELETE_EXPIRED_MESSAGE,
    DELETE_NONCE_TTL_SECONDS,
    DELETE_PREFIX,
    TelegramDeps,
    on_callback,
    on_cancel,
    on_delete_account,
)
from catetin.application.delete_account import DeleteAccount
from catetin.application.generate_report import GenerateReport
from catetin.application.manage_transactions import ManageTransactions
from catetin.application.onboarding import Onboarding
from catetin.domain.models import ParsedTransaction
from tests.fakes.fake_messaging import FakeMessaging
from tests.fakes.fake_repositories import (
    FakeRateLimiter,
    FakeReportRenderer,
    FakeUnitOfWork,
)
from tests.fakes.frozen_clock import FrozenClock

TELEGRAM_ID = 12345678
TODAY = date(2026, 8, 15)


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
def renderer() -> FakeReportRenderer:
    return FakeReportRenderer()


@pytest.fixture
def deps(
    uow: FakeUnitOfWork,
    messaging: FakeMessaging,
    clock: FrozenClock,
    renderer: FakeReportRenderer,
) -> TelegramDeps:
    return TelegramDeps(
        onboarding=Onboarding(uow),
        record_transactions=cast(Any, None),
        manage_transactions=ManageTransactions(uow),
        summarize=cast(Any, None),
        generate_report=GenerateReport(uow, FakeRateLimiter(), renderer),
        delete_account=DeleteAccount(uow, clock),
        messaging=messaging,
        clock=clock,
        default_timezone="Asia/Jakarta",
    )


class _FakeContext:
    def __init__(self, deps: TelegramDeps) -> None:
        self.application = SimpleNamespace(bot_data={"deps": deps})
        self.args: list[str] | None = None


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


def _parsed(item: str) -> ParsedTransaction:
    return ParsedTransaction(
        kind="sale",
        item=item,
        qty=1,
        unit_amount=None,
        total_amount=10_000,
        occurred_on=TODAY,
        confidence=1.0,
        raw_text=f"jual {item}",
    )


async def _seed_user(deps: TelegramDeps, uow: FakeUnitOfWork, n_transactions: int = 2) -> int:
    user = await deps.onboarding.get_or_create_user("telegram", str(TELEGRAM_ID), "Rina")
    async with uow as u:
        for i in range(n_transactions):
            await u.transactions.add(user.id, _parsed(f"Kopi {i}"))
    return user.id


async def _open_keyboard(deps: TelegramDeps) -> str:
    """Run `/hapusakun` and return the confirm button's callback payload."""
    await on_delete_account(_message_update("/hapusakun"), cast(Any, _FakeContext(deps)))
    buttons = {label: data for label, data in deps.messaging.actions[-1].buttons}
    return next(d for d in buttons.values() if d.startswith(DELETE_PREFIX))


# --- the prompt ------------------------------------------------------------


async def test_hapusakun_asks_for_confirmation_with_the_row_count(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed_user(deps, uow, n_transactions=3)

    await on_delete_account(_message_update("/hapusakun"), cast(Any, _FakeContext(deps)))

    assert len(messaging.actions) == 1
    action = messaging.actions[0]
    assert "3 transaksi" in action.prompt
    assert "Tidak bisa dibatalkan" in action.prompt
    labels = [label for label, _ in action.buttons]
    assert labels == ["📄 Unduh data dulu", "✅ Hapus semua", "❌ Batal"]
    # Nothing is destroyed by merely asking.
    async with uow as u:
        assert await u.transactions.count_for_user(1) == 3


async def test_hapusakun_alone_deletes_nothing(
    deps: TelegramDeps, uow: FakeUnitOfWork
) -> None:
    user_id = await _seed_user(deps, uow)

    await on_delete_account(_message_update("/hapusakun"), cast(Any, _FakeContext(deps)))

    async with uow as u:
        assert await u.users.get_by_id(user_id) is not None
        assert await u.deletion_log.count_total() == 0


# --- confirming ------------------------------------------------------------


async def test_confirming_erases_the_account(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    user_id = await _seed_user(deps, uow)
    payload = await _open_keyboard(deps)

    await on_callback(cast(Any, _callback_update(payload)), cast(Any, _FakeContext(deps)))

    async with uow as u:
        assert await u.users.get_by_id(user_id) is None
        assert await u.transactions.count_for_user(user_id) == 0
        assert await u.deletion_log.count_total() == 1
    assert messaging.texts[-1].text == DELETE_DONE_MESSAGE


async def test_confirming_twice_purges_once(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """The replay case: the nonce is burned on the first tap, so a double-tap
    on a still-visible keyboard cannot write a second audit row (or explode
    against a user row that no longer exists)."""
    await _seed_user(deps, uow)
    payload = await _open_keyboard(deps)
    context = cast(Any, _FakeContext(deps))

    await on_callback(cast(Any, _callback_update(payload)), context)
    await on_callback(cast(Any, _callback_update(payload)), context)

    async with uow as u:
        assert await u.deletion_log.count_total() == 1
    assert messaging.texts[-1].text == DELETE_EXPIRED_MESSAGE


async def test_an_expired_keyboard_does_not_erase_anything(
    deps: TelegramDeps, uow: FakeUnitOfWork, clock: FrozenClock, messaging: FakeMessaging
) -> None:
    """The stale tap: an old keyboard scrolled back to tomorrow must be inert."""
    user_id = await _seed_user(deps, uow)
    payload = await _open_keyboard(deps)

    clock.advance(seconds=DELETE_NONCE_TTL_SECONDS + 1)
    await on_callback(cast(Any, _callback_update(payload)), cast(Any, _FakeContext(deps)))

    async with uow as u:
        assert await u.users.get_by_id(user_id) is not None
        assert await u.deletion_log.count_total() == 0
    assert messaging.texts[-1].text == DELETE_EXPIRED_MESSAGE


async def test_a_forged_nonce_does_not_erase_anything(
    deps: TelegramDeps, uow: FakeUnitOfWork, clock: FrozenClock
) -> None:
    user_id = await _seed_user(deps, uow)
    await _open_keyboard(deps)

    forged = f"{DELETE_PREFIX}deadbeefdeadbeef:{int(clock.now().timestamp())}"
    await on_callback(cast(Any, _callback_update(forged)), cast(Any, _FakeContext(deps)))

    async with uow as u:
        assert await u.users.get_by_id(user_id) is not None
        assert await u.deletion_log.count_total() == 0


async def test_a_tap_with_no_live_keyboard_does_not_erase_anything(
    deps: TelegramDeps, uow: FakeUnitOfWork, clock: FrozenClock
) -> None:
    """Fails closed after a restart: the pending-nonce dict is in-process, so
    a tap on a keyboard the process has forgotten reads as expired."""
    user_id = await _seed_user(deps, uow)
    payload = f"{DELETE_PREFIX}deadbeefdeadbeef:{int(clock.now().timestamp())}"

    await on_callback(cast(Any, _callback_update(payload)), cast(Any, _FakeContext(deps)))

    async with uow as u:
        assert await u.users.get_by_id(user_id) is not None


async def test_a_malformed_payload_does_not_erase_anything(
    deps: TelegramDeps, uow: FakeUnitOfWork
) -> None:
    user_id = await _seed_user(deps, uow)
    await _open_keyboard(deps)

    await on_callback(
        cast(Any, _callback_update(f"{DELETE_PREFIX}not-a-payload")),
        cast(Any, _FakeContext(deps)),
    )

    async with uow as u:
        assert await u.users.get_by_id(user_id) is not None


# --- backing out -----------------------------------------------------------


async def test_the_cancel_button_stands_the_keyboard_down(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    user_id = await _seed_user(deps, uow)
    payload = await _open_keyboard(deps)
    context = cast(Any, _FakeContext(deps))

    await on_callback(cast(Any, _callback_update(DELETE_CANCEL)), context)
    assert messaging.texts[-1].text == "Dibatalkan."

    # ...and the button it stood down is now inert.
    await on_callback(cast(Any, _callback_update(payload)), context)
    async with uow as u:
        assert await u.users.get_by_id(user_id) is not None
        assert await u.deletion_log.count_total() == 0


async def test_the_batal_command_also_stands_the_keyboard_down(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """`/batal` is the universal "no" in this bot: typing it while a delete
    keyboard is live must disarm it, not cancel the last transaction."""
    user_id = await _seed_user(deps, uow)
    payload = await _open_keyboard(deps)
    context = cast(Any, _FakeContext(deps))

    await on_cancel(_message_update("/batal"), context)

    assert messaging.texts[-1].text == "Dibatalkan."
    async with uow as u:
        # The transactions are intact — `/batal` did not fall through to
        # soft-deleting the last one.
        assert await u.transactions.count_for_user(user_id) == 2

    await on_callback(cast(Any, _callback_update(payload)), context)
    async with uow as u:
        assert await u.users.get_by_id(user_id) is not None


# --- "Unduh data dulu" -----------------------------------------------------


async def test_download_sends_a_pdf_and_re_arms_the_keyboard(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging, clock: FrozenClock
) -> None:
    """Taking your data out on the way to deleting it must not consume the
    confirmation, and must restart the clock — rendering a PDF can eat a good
    part of the 5 minutes."""
    user_id = await _seed_user(deps, uow)
    await on_delete_account(_message_update("/hapusakun"), cast(Any, _FakeContext(deps)))
    download = next(
        data
        for _, data in messaging.actions[-1].buttons
        if data.startswith(DELETE_DOWNLOAD_PREFIX)
    )

    clock.advance(seconds=DELETE_NONCE_TTL_SECONDS - 10)
    await on_callback(cast(Any, _callback_update(download)), cast(Any, _FakeContext(deps)))

    assert len(messaging.documents) == 1
    assert messaging.documents[0].filename.endswith(".pdf")
    # Nothing erased, and a fresh keyboard offered.
    async with uow as u:
        assert await u.users.get_by_id(user_id) is not None
    assert len(messaging.actions) == 2

    # The re-issued button works past the original deadline.
    clock.advance(seconds=20)
    confirm = next(
        data for _, data in messaging.actions[-1].buttons if data.startswith(DELETE_PREFIX)
    )
    await on_callback(cast(Any, _callback_update(confirm)), cast(Any, _FakeContext(deps)))

    async with uow as u:
        assert await u.users.get_by_id(user_id) is None
