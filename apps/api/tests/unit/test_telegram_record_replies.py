"""`on_text` reply-shape tests — what a user actually sees after sending a
plain (non-command) message.

Handlers run directly against fakes, but the parser and `RecordTransactions`
are the real ones: the bugs these cover (QA round 2) all lived in the seam
between a `RecordIssue.reason` and the sentence rendered for it, so a fake
parser would have tested nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from telegram import Update

from catetin.adapters.inbound.telegram.handlers import (
    CHOICE_EXPENSE,
    CHOICE_OTHER,
    CHOICE_SALE,
    TelegramDeps,
    on_text,
)
from catetin.adapters.outbound.parsing.regex_parser import RegexParser
from catetin.adapters.outbound.parsing.segmenter import MAX_SEGMENTS
from catetin.application.onboarding import Onboarding
from catetin.application.record_transactions import RecordTransactions
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
    unused = cast(Any, None)
    return TelegramDeps(
        onboarding=Onboarding(uow),
        record_transactions=RecordTransactions(RegexParser(), uow),
        manage_transactions=unused,
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


async def _send(deps: TelegramDeps, text: str) -> None:
    await on_text(_message_update(text), cast(Any, _FakeContext(deps)))


def _only_text(messaging: FakeMessaging) -> str:
    assert len(messaging.texts) == 1
    return messaging.texts[0].text


# --- segment-cap truncation notice -----------------------------------------


async def test_truncation_notice_leads_the_reply(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    """QA round 2: 21+ segments recorded 20 and said nothing the user could
    find. The notice now opens the message, ahead of the confirmation list it
    explains — a message long enough to hit the cap gets a reply long enough
    to hide a footnote in."""
    text = "\n".join(f"jual item{i} {i + 1}0rb" for i in range(MAX_SEGMENTS + 5))

    await _send(deps, text)

    reply = _only_text(messaging)
    assert reply.startswith(
        f"Pesannya kepanjangan, cuma {MAX_SEGMENTS} transaksi pertama yang diproses."
    )
    assert f"Tercatat {MAX_SEGMENTS} transaksi:" in reply


async def test_truncation_notice_survives_a_batch_of_ambiguous_segments(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    """The case that made it invisible in practice: with no verb every segment
    is ambiguous, and 20 `ambiguous_kind` error lines used to push the notice
    off the bottom of the message."""
    text = "\n".join(f"item{i} {i + 1}0rb" for i in range(MAX_SEGMENTS + 5))

    await _send(deps, text)

    reply = _only_text(messaging)
    assert reply == (
        f"Pesannya kepanjangan, cuma {MAX_SEGMENTS} transaksi pertama yang diproses."
    )
    assert "ambiguous_kind" not in reply


async def test_no_truncation_notice_below_the_cap(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    text = "\n".join(f"jual item{i} {i + 1}0rb" for i in range(MAX_SEGMENTS))

    await _send(deps, text)

    assert "kepanjangan" not in _only_text(messaging)


# --- ambiguous kind: a question, not an error ------------------------------


async def test_ambiguous_kind_asks_the_three_button_keyboard(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    """US-08: no verb means the bot cannot tell sale from expense, so it asks
    — with exactly the three documented options."""
    await _send(deps, "ayam geprek 50rb")

    assert len(messaging.choices) == 1
    asked = messaging.choices[0]
    assert asked.options == [CHOICE_SALE, CHOICE_EXPENSE, CHOICE_OTHER]
    assert asked.options == ["Jual", "Beli", "Bukan Usaha"]
    assert "Ayam Geprek" in asked.prompt


async def test_ambiguous_kind_does_not_also_report_an_error(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    """It used to fall through to the catch-all and emit
    'Nggak bisa diproses: "..." (ambiguous_kind).' beside the keyboard,
    leaking an internal reason code and calling a question a failure."""
    await _send(deps, "ayam geprek 50rb")

    assert messaging.texts == []
    assert len(messaging.choices) == 1


# --- flagged: a note, never a popup ----------------------------------------


async def test_flagged_but_unambiguous_gets_a_suffix_and_a_note_only(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    """FR-1: the high-signal flag is metadata. It never rejects and never asks,
    so a flagged row with a clear verb is recorded with a warning suffix and a
    closing note, and no keyboard of any kind."""
    await _send(deps, "dapet duit 50k")

    reply = _only_text(messaging)
    assert "⚠️" in reply
    assert "Ada yang kelihatannya bukan pemasukan usaha" in reply
    assert "Pas /lapor nanti kamu bisa keluarkan dari laporan." in reply
    assert messaging.choices == []
    assert messaging.actions == []


async def test_unflagged_transaction_gets_no_warning_at_all(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    await _send(deps, "jual ayam geprek 50rb")

    reply = _only_text(messaging)
    assert "⚠️" not in reply
    assert messaging.choices == []
    assert messaging.actions == []


# --- unparseable segments still report --------------------------------------


async def test_segment_without_an_amount_still_reports(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    """Suppressing `ambiguous_kind` must not suppress the real failures."""
    await _send(deps, "jual ayam geprek 50rb\njual es teh")

    reply = _only_text(messaging)
    assert "Nggak ketemu nominalnya" in reply
    assert "jual es teh" in reply
