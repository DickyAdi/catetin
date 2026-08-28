"""`/list` pagination — the paged handler, its stateless `list:` callbacks,
and the guarantee that a page always fits in one Telegram message.

Two levels are exercised: `render_page`/`page_buttons` directly, where the
4096-character ceiling lives, and the handler end to end against fakes, where
what matters is that walking the keyboard shows every transaction exactly once
and that a tap on an old keyboard cannot crash or lie about the page count.

`/list` sends one message; every page after the first is an edit of it, so the
handler assertions below are mostly about `messaging.updates` — and about
`messaging.actions` staying at length 1 no matter how far the user walks.
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
    LIST_CLOSED,
    LIST_EMPTY,
    LIST_UNKNOWN_BUTTON,
    TelegramDeps,
    on_callback,
    on_list,
)
from catetin.adapters.inbound.telegram.list_view import (
    LIST_CLOSE,
    LIST_NOOP,
    LIST_PREFIX,
    SAFE_TEXT_LIMIT,
    TELEGRAM_TEXT_LIMIT,
    page_buttons,
    render_page,
)
from catetin.application.manage_transactions import (
    DEFAULT_LIST_LIMIT,
    ManageTransactions,
    TransactionPage,
)
from catetin.application.onboarding import Onboarding
from catetin.domain.models import ParsedTransaction, Transaction
from tests.fakes.fake_messaging import FakeMessaging
from tests.fakes.fake_repositories import FakeUnitOfWork
from tests.fakes.frozen_clock import FrozenClock

TELEGRAM_ID = 12345678
TODAY = date(2026, 8, 15)
# The message a `/list` keyboard sits on, i.e. the one every page edits.
LIST_MESSAGE_ID = 4242


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
    """Only `onboarding`/`manage_transactions`/`messaging` are reachable from
    `/list`; the rest stay unbuilt so a stray call fails loudly."""
    unused = cast(Any, None)
    return TelegramDeps(
        onboarding=Onboarding(uow),
        record_transactions=unused,
        manage_transactions=ManageTransactions(uow),
        summarize=unused,
        generate_report=unused,
        delete_account=unused,
        messaging=messaging,
        clock=clock,
        default_timezone="Asia/Jakarta",
    )


class _FakeContext:
    def __init__(self, deps: TelegramDeps) -> None:
        self.application = SimpleNamespace(bot_data={"deps": deps})
        self.args: list[str] | None = None


@dataclass
class _FakeMessage:
    message_id: int


@dataclass
class _FakeQuery:
    data: str
    # None models the one callback shape that has no message behind it (an
    # inline-mode keyboard); the handler must still answer the user somehow.
    message: _FakeMessage | None = None
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


def _callback_update(
    data: str, message_id: int | None = LIST_MESSAGE_ID
) -> _FakeCallbackUpdate:
    return _FakeCallbackUpdate(
        callback_query=_FakeQuery(
            data=data,
            message=None if message_id is None else _FakeMessage(message_id=message_id),
        ),
        effective_user=TelegramUser(id=TELEGRAM_ID, is_bot=False, first_name="Rina"),
    )


def _parsed(item: str, amount: int = 10_000) -> ParsedTransaction:
    return ParsedTransaction(
        kind="sale",
        item=item,
        qty=1,
        unit_amount=None,
        total_amount=amount,
        occurred_on=TODAY,
        confidence=1.0,
        raw_text=f"jual {item}",
    )


async def _seed(deps: TelegramDeps, uow: FakeUnitOfWork, n: int) -> int:
    """`n` transactions, oldest first — so `item-{n}` is the most recent and
    heads page 1."""
    user = await deps.onboarding.get_or_create_user("telegram", str(TELEGRAM_ID), "Rina")
    async with uow as u:
        for i in range(1, n + 1):
            await u.transactions.add(user.id, _parsed(f"item-{i}"))
        await u.commit()
    return user.id


async def _tap(
    deps: TelegramDeps, data: str, message_id: int | None = LIST_MESSAGE_ID
) -> None:
    await on_callback(
        cast(Any, _callback_update(data, message_id)), cast(Any, _FakeContext(deps))
    )


def _labels(buttons: list[tuple[str, str]]) -> list[str]:
    return [label for label, _ in buttons]


def _page(items: list[Transaction], total: int, offset: int) -> TransactionPage:
    return TransactionPage(
        items=items, total=total, offset=offset, page_size=DEFAULT_LIST_LIMIT
    )


def _transaction(tx_id: int, item: str, *, amount: int = 10_000) -> Transaction:
    return Transaction(
        id=tx_id,
        user_id=1,
        kind="sale",
        item=item,
        total_amount=amount,
        occurred_on=TODAY.isoformat(),
        occurred_at=1755225600,
        created_at=1755225600,
    )


# --- walking the keyboard ---------------------------------------------------


async def test_first_page_shows_ten_of_twentyfive_and_only_a_next_arrow(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 25)

    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    assert messaging.texts == []  # a paged list rides on the keyboard message
    assert len(messaging.actions) == 1
    shown = messaging.actions[0]
    assert shown.prompt.splitlines()[0] == "📋 Transaksi 1-10 dari 25"
    assert len(shown.prompt.splitlines()) == 11  # header + 10 rows
    assert _labels(shown.buttons) == ["Hal 1/3", "➡️", "✖️ Tutup"]
    assert shown.buttons[1][1] == f"{LIST_PREFIX}10"


async def test_next_shows_the_second_page_with_both_arrows(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 25)
    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    await _tap(deps, f"{LIST_PREFIX}10")

    shown = messaging.updates[-1]
    assert shown.text.splitlines()[0] == "📋 Transaksi 11-20 dari 25"
    assert shown.buttons is not None
    assert _labels(shown.buttons) == ["⬅️", "Hal 2/3", "➡️", "✖️ Tutup"]
    assert shown.buttons[0][1] == f"{LIST_PREFIX}0"
    assert shown.buttons[2][1] == f"{LIST_PREFIX}20"


async def test_next_edits_the_first_page_instead_of_sending_a_new_message(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """The point of edit-message paging: the chat keeps one `/list` message."""
    await _seed(deps, uow, 25)
    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    await _tap(deps, f"{LIST_PREFIX}10")

    assert len(messaging.actions) == 1  # still just the message `/list` sent
    assert messaging.texts == []
    assert [u.message_id for u in messaging.updates] == [LIST_MESSAGE_ID]


async def test_last_page_shows_the_remainder_with_no_next_arrow(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 25)
    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    await _tap(deps, f"{LIST_PREFIX}20")

    shown = messaging.updates[-1]
    lines = shown.text.splitlines()
    assert lines[0] == "📋 Transaksi 21-25 dari 25"
    assert len(lines) == 6  # header + the 5 remaining rows
    assert shown.buttons is not None
    assert _labels(shown.buttons) == ["⬅️", "Hal 3/3", "✖️ Tutup"]


async def test_walking_all_three_pages_shows_every_transaction_once(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """The whole point of the feature: 25 transactions, 3 taps, nothing
    skipped and nothing shown twice — all inside one message."""
    await _seed(deps, uow, 25)
    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))
    await _tap(deps, f"{LIST_PREFIX}10")
    await _tap(deps, f"{LIST_PREFIX}20")

    pages = [messaging.actions[0].prompt] + [u.text for u in messaging.updates]
    assert len(pages) == 3
    assert {u.message_id for u in messaging.updates} == {LIST_MESSAGE_ID}

    # Newest first: `item-25` heads page 1, `item-1` closes page 3.
    assert " item-25 " in pages[0] and " item-16 " in pages[0]
    assert " item-15 " in pages[1] and " item-6 " in pages[1]
    assert " item-5 " in pages[2] and " item-1 " in pages[2]

    body = [line for page in pages for line in page.splitlines()[1:]]
    assert len(body) == 25
    assert {line.split(".", 1)[0] for line in body} == {str(i) for i in range(1, 26)}


async def test_row_numbering_is_absolute_not_per_page(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 25)
    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    await _tap(deps, f"{LIST_PREFIX}10")

    first_row = messaging.updates[-1].text.splitlines()[1]
    assert first_row.startswith("11. ")


async def test_row_format_is_unchanged(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    user_id = await _seed(deps, uow, 1)
    async with uow as u:
        await u.transactions.add(user_id, _parsed("kopi", amount=1_500_000))
        await u.commit()

    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    rows = messaging.texts[0].text.splitlines()
    assert rows[1] == "1. [2] +Rp 1.500.000 kopi (2026-08-15)"


# --- the degenerate sizes ---------------------------------------------------


async def test_single_page_has_no_navigation_and_stays_plain_text(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, DEFAULT_LIST_LIMIT)

    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    assert messaging.actions == []  # no keyboard at all when there is one page
    assert len(messaging.texts) == 1
    assert messaging.texts[0].text.splitlines()[0] == "📋 Transaksi 1-10 dari 10"


async def test_empty_list_is_unchanged(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 0)

    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    assert [t.text for t in messaging.texts] == [LIST_EMPTY]
    assert messaging.actions == []


async def test_eleventh_transaction_turns_on_pagination(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 11)

    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    assert _labels(messaging.actions[0].buttons) == ["Hal 1/2", "➡️", "✖️ Tutup"]


# --- stale and unknown payloads ---------------------------------------------


async def test_offset_past_the_end_falls_back_to_the_last_page(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """A keyboard tapped after the rows behind it were cancelled: `list:200`
    must show the last page, not an empty one."""
    await _seed(deps, uow, 25)

    await _tap(deps, f"{LIST_PREFIX}200")

    shown = messaging.updates[-1]
    assert shown.text.splitlines()[0] == "📋 Transaksi 21-25 dari 25"
    assert shown.buttons is not None
    assert _labels(shown.buttons) == ["⬅️", "Hal 3/3", "✖️ Tutup"]


async def test_offset_past_the_end_of_an_emptied_list_says_so(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """Every row cancelled under a live keyboard: the page it was tapped from
    is replaced by the empty notice, and the arrows go with it."""
    await _seed(deps, uow, 0)

    await _tap(deps, f"{LIST_PREFIX}20")

    assert [(u.text, u.buttons) for u in messaging.updates] == [(LIST_EMPTY, None)]
    assert messaging.texts == []


async def test_a_shrunk_list_that_now_fits_one_page_loses_its_navigation(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """Down to 6 rows since the keyboard was drawn: the edit shows them all and
    keeps no buttons, because `page_buttons` offers none for a single page."""
    await _seed(deps, uow, 6)

    await _tap(deps, f"{LIST_PREFIX}10")

    shown = messaging.updates[-1]
    assert shown.text.splitlines()[0] == "📋 Transaksi 1-6 dari 6"
    assert shown.buttons is None


async def test_offset_between_pages_is_snapped_to_a_page_boundary(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """Nothing we send produces `list:7`, but if one arrives the page label and
    the rows under it still have to agree."""
    await _seed(deps, uow, 25)

    await _tap(deps, f"{LIST_PREFIX}7")

    shown = messaging.updates[-1]
    assert shown.text.splitlines()[0] == "📋 Transaksi 1-10 dari 25"
    assert shown.buttons is not None
    assert _labels(shown.buttons) == ["Hal 1/3", "➡️", "✖️ Tutup"]


async def test_negative_offset_lands_on_the_first_page(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 25)

    await _tap(deps, f"{LIST_PREFIX}-40")

    assert messaging.updates[-1].text.splitlines()[0] == "📋 Transaksi 1-10 dari 25"


async def test_unparseable_payload_is_answered_not_raised(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """A payload we cannot read is answered in a new message, not by editing:
    we do not know what page the message it came from is showing, so replacing
    its text would destroy a list the user can still read."""
    await _seed(deps, uow, 25)

    await _tap(deps, f"{LIST_PREFIX}halaman-dua")

    assert [t.text for t in messaging.texts] == [LIST_UNKNOWN_BUTTON]
    assert messaging.actions == []
    assert messaging.updates == []


async def test_page_indicator_tap_does_nothing(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 25)

    await _tap(deps, LIST_NOOP)

    assert messaging.texts == []
    assert messaging.actions == []
    assert messaging.updates == []


async def test_close_replaces_the_page_and_takes_the_keyboard_away(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """"✖️ Tutup" is the reason `update_message` exists: before it, closing
    could only apologise while the buttons stayed live in scrollback."""
    await _seed(deps, uow, 25)
    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    await _tap(deps, LIST_CLOSE)

    shown = messaging.updates[-1]
    assert (shown.message_id, shown.text, shown.buttons) == (
        LIST_MESSAGE_ID,
        LIST_CLOSED,
        None,
    )
    assert messaging.texts == []
    assert len(messaging.actions) == 1  # nothing new was sent to say it


async def test_close_on_an_unaddressable_message_still_acknowledges(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """No message behind the callback means no edit is possible; the user is
    told anyway rather than being left with a silent button."""
    await _seed(deps, uow, 25)

    await _tap(deps, LIST_CLOSE, message_id=None)

    assert [t.text for t in messaging.texts] == [LIST_CLOSED]
    assert messaging.updates == []


async def test_paging_an_unaddressable_message_falls_back_to_a_new_page(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 25)

    await _tap(deps, f"{LIST_PREFIX}10", message_id=None)

    assert messaging.updates == []
    assert messaging.actions[-1].prompt.splitlines()[0] == "📋 Transaksi 11-20 dari 25"


# --- the duplicate-tap guard ------------------------------------------------


async def test_tapping_the_same_arrow_twice_edits_once(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """Telegram would reject the second edit as "message is not modified"; the
    guard drops it here, before the page query."""
    await _seed(deps, uow, 25)
    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    await _tap(deps, f"{LIST_PREFIX}10")
    await _tap(deps, f"{LIST_PREFIX}10")

    assert len(messaging.updates) == 1


async def test_the_guard_does_not_block_paging_back_and_forth(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """It suppresses a repeat of the *current* page only — ⬅️ then ➡️ back to a
    page already seen is a real navigation and must redraw."""
    await _seed(deps, uow, 25)
    await on_list(_message_update("/list"), cast(Any, _FakeContext(deps)))

    await _tap(deps, f"{LIST_PREFIX}10")
    await _tap(deps, f"{LIST_PREFIX}0")
    await _tap(deps, f"{LIST_PREFIX}10")

    headers = [u.text.splitlines()[0] for u in messaging.updates]
    assert headers == [
        "📋 Transaksi 11-20 dari 25",
        "📋 Transaksi 1-10 dari 25",
        "📋 Transaksi 11-20 dari 25",
    ]


async def test_a_second_list_message_pages_independently(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """Two `/list` messages in one chat each edit themselves — the guard is
    keyed on the message, so the same offset on the other one is not a
    duplicate."""
    await _seed(deps, uow, 25)

    await _tap(deps, f"{LIST_PREFIX}10", message_id=LIST_MESSAGE_ID)
    await _tap(deps, f"{LIST_PREFIX}10", message_id=LIST_MESSAGE_ID + 1)

    assert [u.message_id for u in messaging.updates] == [
        LIST_MESSAGE_ID,
        LIST_MESSAGE_ID + 1,
    ]


async def test_closing_clears_the_guard_so_a_later_list_pages_normally(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _seed(deps, uow, 25)

    await _tap(deps, f"{LIST_PREFIX}10")
    await _tap(deps, LIST_CLOSE)
    await _tap(deps, f"{LIST_PREFIX}10")

    headers = [u.text.splitlines()[0] for u in messaging.updates]
    assert headers == [
        "📋 Transaksi 11-20 dari 25",
        LIST_CLOSED,
        "📋 Transaksi 11-20 dari 25",
    ]


async def test_callback_is_always_answered(
    deps: TelegramDeps, uow: FakeUnitOfWork
) -> None:
    """Telegram leaves a spinner on the button until the query is answered —
    including for the payloads that do nothing."""
    await _seed(deps, uow, 25)
    for data in (f"{LIST_PREFIX}10", LIST_NOOP, LIST_CLOSE, f"{LIST_PREFIX}x"):
        update = _callback_update(data)
        await on_callback(cast(Any, update), cast(Any, _FakeContext(deps)))
        assert update.callback_query.answered


# --- the 4096-character ceiling ---------------------------------------------


def test_a_full_page_of_maximum_length_items_fits_in_one_message() -> None:
    """Worst case at the parser's own cap: 10 rows of 80-character items.

    This is the case that must never need truncating — it is what a real user
    with verbose entries produces.
    """
    items = [_transaction(i, "x" * 80, amount=999_999_999) for i in range(1, 11)]
    text = render_page(_page(items, total=100, offset=0))

    assert len(text) < SAFE_TEXT_LIMIT
    assert "…" not in text


def test_a_page_of_pathologically_long_items_is_truncated_to_fit() -> None:
    """`Transaction.item` has no length cap of its own, so one absurd row (or
    ten) must cost the page its detail, never its delivery."""
    items = [_transaction(i, "y" * 5_000) for i in range(1, 11)]
    text = render_page(_page(items, total=100, offset=0))

    assert len(text) <= SAFE_TEXT_LIMIT < TELEGRAM_TEXT_LIMIT
    assert text.splitlines()[1].endswith("…")
    assert text.splitlines()[0] == "📋 Transaksi 1-10 dari 100"  # header survives


@pytest.mark.parametrize("item_length", [1, 40, 80, 200, 1_000, 20_000])
def test_no_page_size_and_item_length_combination_can_overflow(item_length: int) -> None:
    for count in (1, 2, 5, DEFAULT_LIST_LIMIT):
        items = [_transaction(i, "z" * item_length) for i in range(1, count + 1)]
        text = render_page(_page(items, total=1_000, offset=990))
        assert len(text) <= SAFE_TEXT_LIMIT


def test_excluded_rows_keep_their_marker_when_truncated() -> None:
    long_name = "w" * 5_000
    items = [_transaction(1, long_name)] + [
        _transaction(i, long_name) for i in range(2, 11)
    ]
    excluded = items[0].model_copy(update={"excluded_from_report": True})
    text = render_page(_page([excluded, *items[1:]], total=100, offset=0))

    assert text.splitlines()[1].startswith("1. 🚫 [1] ")


# --- buttons in isolation ---------------------------------------------------


def test_page_buttons_are_empty_for_a_single_page() -> None:
    items = [_transaction(i, "kopi") for i in range(1, 8)]
    assert page_buttons(_page(items, total=7, offset=0)) == []


def test_page_buttons_on_an_exact_multiple_have_no_trailing_empty_page() -> None:
    """20 transactions is 2 pages, not 3 — page 2 must not offer a next arrow
    onto nothing."""
    items = [_transaction(i, "kopi") for i in range(1, 11)]
    assert _labels(page_buttons(_page(items, total=20, offset=10))) == [
        "⬅️",
        "Hal 2/2",
        "✖️ Tutup",
    ]
