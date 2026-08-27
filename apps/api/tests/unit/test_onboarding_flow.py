"""The `/start` state machine — name, then timezone, then done.

Handlers are exercised directly against fakes (same approach as
`test_telegram_handlers.py`): PTB's `Application` is never built, so `context`
is a stub carrying only what `_deps` reads.

The through-line of these tests is that setup owns the conversation while it is
open: a message typed mid-flow is a business name, not a transaction, and the
`has_onboarded` flag only flips at the very last step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from telegram import Update
from telegram import User as TelegramUser

from catetin.adapters.inbound.telegram.handlers import (
    ASK_NAME,
    ASK_TIMEZONE,
    INVALID_NAME,
    NOT_ONBOARDED,
    OB_CANCEL,
    OB_REDO,
    OB_SAVE,
    OB_SKIP_REDO,
    ONBOARDING_CANCELLED,
    ONBOARDING_DONE,
    ONBOARDING_EXPIRED,
    REDO_DECLINED,
    REDO_PROMPT,
    OnboardingState,
    TelegramDeps,
    on_callback,
    on_cancel,
    on_report,
    on_start,
    on_text,
)
from catetin.application.onboarding import MAX_BUSINESS_NAME_LEN, Onboarding
from catetin.domain.models import User
from tests.fakes.fake_messaging import FakeMessaging
from tests.fakes.fake_repositories import FakeUnitOfWork
from tests.fakes.frozen_clock import FrozenClock

TELEGRAM_ID = 12345678
USER_ID = 1  # FakeUserRepository hands out ids from 1
BUSINESS_NAME = "Warung Mbok Rina"


# --- doubles ----------------------------------------------------------------


@dataclass
class _SpyRecordTransactions:
    """Records calls so "onboarding did not parse this as a transaction" can be
    asserted positively instead of by an incidental crash."""

    calls: list[tuple[int, str]] = field(default_factory=list)

    async def execute(self, user_id: int, text: str, today: date) -> Any:
        self.calls.append((user_id, text))
        return SimpleNamespace(recorded=[], issues=[], ambiguous=[])


@dataclass
class _StubGenerateReport:
    calls: list[int] = field(default_factory=list)

    async def execute(
        self, user_id: int, start: date, end: date, *, period_label: str
    ) -> Any:
        self.calls.append(user_id)
        return SimpleNamespace(pdf_bytes=b"%PDF-fake")


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 8, 26, 12, 0, tzinfo=UTC))


@pytest.fixture
def uow(clock: FrozenClock) -> FakeUnitOfWork:
    return FakeUnitOfWork(clock)


@pytest.fixture
def messaging() -> FakeMessaging:
    return FakeMessaging()


@pytest.fixture
def recorder() -> _SpyRecordTransactions:
    return _SpyRecordTransactions()


@pytest.fixture
def reporter() -> _StubGenerateReport:
    return _StubGenerateReport()


@pytest.fixture
def deps(
    uow: FakeUnitOfWork,
    messaging: FakeMessaging,
    clock: FrozenClock,
    recorder: _SpyRecordTransactions,
    reporter: _StubGenerateReport,
) -> TelegramDeps:
    unused = cast(Any, None)
    return TelegramDeps(
        onboarding=Onboarding(uow),
        record_transactions=cast(Any, recorder),
        manage_transactions=unused,
        summarize=unused,
        generate_report=cast(Any, reporter),
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


async def _send(handler: Any, deps: TelegramDeps, text: str) -> None:
    await handler(_message_update(text), cast(Any, _FakeContext(deps)))


async def _tap(deps: TelegramDeps, data: str) -> None:
    await on_callback(cast(Any, _callback_update(data)), cast(Any, _FakeContext(deps)))


async def _current_user(uow: FakeUnitOfWork) -> User:
    async with uow as open_uow:
        user = await open_uow.users.get_by_platform_identity("telegram", str(TELEGRAM_ID))
    assert user is not None
    return user


async def _complete_onboarding(deps: TelegramDeps, name: str = BUSINESS_NAME) -> None:
    await _send(on_start, deps, "/start")
    await _send(on_text, deps, name)
    await _tap(deps, OB_SAVE)
    await _tap(deps, "tz:Asia/Jakarta")


# --- the happy path ---------------------------------------------------------


async def test_full_start_flow_saves_name_timezone_and_marks_onboarded(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _send(on_start, deps, "/start")
    assert ASK_NAME in messaging.texts[-1].text
    assert deps.onboarding_pending[USER_ID].step == "awaiting_name"
    assert (await _current_user(uow)).has_onboarded is False

    await _send(on_text, deps, BUSINESS_NAME)
    preview = messaging.actions[-1]
    assert preview.prompt == f"Simpan sebagai '{BUSINESS_NAME}'?"
    assert preview.buttons == [("✅ Simpan", OB_SAVE), ("❌ Batal", OB_CANCEL)]
    # Nothing is written until the user agrees.
    assert (await _current_user(uow)).business_name is None
    assert deps.onboarding_pending[USER_ID] == OnboardingState(
        step="confirming_name", proposed_name=BUSINESS_NAME
    )

    await _tap(deps, OB_SAVE)
    assert (await _current_user(uow)).business_name == BUSINESS_NAME
    zones = messaging.actions[-1]
    assert zones.prompt == ASK_TIMEZONE
    assert zones.buttons == [
        ("WIB", "tz:Asia/Jakarta"),
        ("WITA", "tz:Asia/Makassar"),
        ("WIT", "tz:Asia/Jayapura"),
    ]
    assert deps.onboarding_pending[USER_ID].step == "awaiting_timezone"
    assert (await _current_user(uow)).has_onboarded is False  # not yet

    await _tap(deps, "tz:Asia/Makassar")
    user = await _current_user(uow)
    assert user.timezone == "Asia/Makassar"
    assert user.has_onboarded is True
    assert user.business_name == BUSINESS_NAME
    assert deps.onboarding_pending == {}
    assert messaging.texts[-2].text == ONBOARDING_DONE
    assert "/lapor" in messaging.texts[-1].text  # the command guide closes it out


async def test_finishing_setup_does_not_send_the_bare_zone_confirmation(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    """The zone tap is step 2 of setup, so it answers with "Siap!" — the
    stand-alone `/zona` acknowledgement would read as a non-sequitur here."""
    await _complete_onboarding(deps)

    assert not any("Zona waktu diset ke" in sent.text for sent in messaging.texts)


async def test_zone_tap_outside_setup_keeps_its_own_reply(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    """...and the reverse: once setup is done, `/zona` behaves exactly as before."""
    await _complete_onboarding(deps)

    await _tap(deps, "tz:Asia/Jayapura")

    assert messaging.texts[-1].text == "Zona waktu diset ke Asia/Jayapura."
    assert (await _current_user(uow)).timezone == "Asia/Jayapura"


# --- name validation, through the handler -----------------------------------


@pytest.mark.parametrize(
    "bad_name",
    [
        "<script>alert(1)</script>",
        "a\nb",
        "a" * (MAX_BUSINESS_NAME_LEN + 1),
        "   ",
        "a;DROP TABLE users",
    ],
)
async def test_invalid_name_is_rejected_and_re_asked(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging, bad_name: str
) -> None:
    await _send(on_start, deps, "/start")
    await _send(on_text, deps, bad_name)

    assert messaging.texts[-1].text == INVALID_NAME
    assert messaging.actions == []  # no confirm button for a name we won't store
    assert deps.onboarding_pending[USER_ID].step == "awaiting_name"
    assert (await _current_user(uow)).business_name is None


async def test_a_valid_name_after_a_rejected_one_still_works(
    deps: TelegramDeps, uow: FakeUnitOfWork
) -> None:
    await _send(on_start, deps, "/start")
    await _send(on_text, deps, "<script>")
    await _send(on_text, deps, BUSINESS_NAME)
    await _tap(deps, OB_SAVE)

    assert (await _current_user(uow)).business_name == BUSINESS_NAME


async def test_cancel_button_re_asks_without_leaving_the_flow(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _send(on_start, deps, "/start")
    await _send(on_text, deps, BUSINESS_NAME)

    await _tap(deps, OB_CANCEL)

    assert messaging.texts[-1].text == ASK_NAME
    assert deps.onboarding_pending[USER_ID].step == "awaiting_name"
    assert (await _current_user(uow)).business_name is None

    await _send(on_text, deps, "Toko-ABC_1")
    await _tap(deps, OB_SAVE)
    assert (await _current_user(uow)).business_name == "Toko-ABC_1"


async def test_retyping_at_the_confirm_step_proposes_the_new_name(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    await _send(on_start, deps, "/start")
    await _send(on_text, deps, BUSINESS_NAME)

    await _send(on_text, deps, "Toko-ABC_1")

    assert messaging.actions[-1].prompt == "Simpan sebagai 'Toko-ABC_1'?"
    assert deps.onboarding_pending[USER_ID].proposed_name == "Toko-ABC_1"


# --- setup owns the conversation --------------------------------------------


async def test_text_during_setup_is_not_parsed_as_a_transaction(
    deps: TelegramDeps, recorder: _SpyRecordTransactions, messaging: FakeMessaging
) -> None:
    """The bug this prevents: "Warung Mbok Rina" reaching the parser and
    bouncing back as "nggak ketemu nominalnya"."""
    await _send(on_start, deps, "/start")

    await _send(on_text, deps, BUSINESS_NAME)

    assert recorder.calls == []
    assert messaging.actions[-1].prompt == f"Simpan sebagai '{BUSINESS_NAME}'?"


async def test_a_transaction_shaped_message_during_setup_is_read_as_a_name(
    deps: TelegramDeps, recorder: _SpyRecordTransactions
) -> None:
    await _send(on_start, deps, "/start")

    await _send(on_text, deps, "jual ayam geprek 50rb")

    assert recorder.calls == []
    assert deps.onboarding_pending[USER_ID].proposed_name == "jual ayam geprek 50rb"


async def test_text_at_the_timezone_step_re_offers_the_keyboard(
    deps: TelegramDeps, recorder: _SpyRecordTransactions, messaging: FakeMessaging
) -> None:
    await _send(on_start, deps, "/start")
    await _send(on_text, deps, BUSINESS_NAME)
    await _tap(deps, OB_SAVE)

    await _send(on_text, deps, "WIB")  # typed instead of tapped

    assert recorder.calls == []
    assert messaging.actions[-1].prompt == ASK_TIMEZONE
    assert deps.onboarding_pending[USER_ID].step == "awaiting_timezone"


async def test_text_after_setup_is_parsed_normally(
    deps: TelegramDeps, recorder: _SpyRecordTransactions
) -> None:
    await _complete_onboarding(deps)

    await _send(on_text, deps, "jual ayam geprek 50rb")

    assert recorder.calls == [(USER_ID, "jual ayam geprek 50rb")]


# --- /batal -----------------------------------------------------------------


async def test_batal_cancels_a_pending_setup(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _send(on_start, deps, "/start")

    await _send(on_cancel, deps, "/batal")

    assert messaging.texts[-1].text == ONBOARDING_CANCELLED
    assert deps.onboarding_pending == {}
    assert (await _current_user(uow)).has_onboarded is False


async def test_batal_after_setup_falls_through_to_transaction_cancel(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    await _complete_onboarding(deps)

    canceller = SimpleNamespace(calls=[])

    async def cancel_last(user_id: int) -> None:
        """Returns None — "no transaction to cancel", the fall-through path."""
        canceller.calls.append(user_id)

    deps.manage_transactions = cast(Any, SimpleNamespace(cancel_last=cancel_last))

    await _send(on_cancel, deps, "/batal")

    assert canceller.calls == [USER_ID]
    assert messaging.texts[-1].text == "Belum ada transaksi buat dibatalkan."


# --- re-running setup -------------------------------------------------------


async def test_start_when_already_onboarded_asks_before_redoing(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    await _complete_onboarding(deps)

    await _send(on_start, deps, "/start")

    prompt = messaging.actions[-1]
    assert prompt.prompt == REDO_PROMPT
    assert prompt.buttons == [("✅ Ulangi", OB_REDO), ("❌ Gak usah", OB_SKIP_REDO)]
    assert deps.onboarding_pending == {}  # nothing is pending until they choose


async def test_declining_the_redo_leaves_everything_alone(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _complete_onboarding(deps)
    await _send(on_start, deps, "/start")

    await _tap(deps, OB_SKIP_REDO)

    assert messaging.texts[-1].text == REDO_DECLINED
    assert deps.onboarding_pending == {}
    user = await _current_user(uow)
    assert user.has_onboarded is True
    assert user.business_name == BUSINESS_NAME


async def test_accepting_the_redo_runs_the_flow_again(
    deps: TelegramDeps, uow: FakeUnitOfWork, messaging: FakeMessaging
) -> None:
    await _complete_onboarding(deps)
    await _send(on_start, deps, "/start")

    await _tap(deps, OB_REDO)
    assert messaging.texts[-1].text == ASK_NAME
    assert deps.onboarding_pending[USER_ID].step == "awaiting_name"

    await _send(on_text, deps, "Toko-ABC_1")
    await _tap(deps, OB_SAVE)
    await _tap(deps, "tz:Asia/Jayapura")

    user = await _current_user(uow)
    assert user.business_name == "Toko-ABC_1"
    assert user.timezone == "Asia/Jayapura"
    assert user.has_onboarded is True


async def test_an_abandoned_redo_does_not_un_onboard_the_user(
    deps: TelegramDeps, uow: FakeUnitOfWork
) -> None:
    """`has_onboarded` stays True for the whole redo — walking away mid-way
    must not demote a working account back behind the `/lapor` gate."""
    await _complete_onboarding(deps)
    await _send(on_start, deps, "/start")
    await _tap(deps, OB_REDO)

    assert (await _current_user(uow)).has_onboarded is True

    await _send(on_cancel, deps, "/batal")

    user = await _current_user(uow)
    assert user.has_onboarded is True
    assert user.business_name == BUSINESS_NAME  # the old name survives


async def test_confirm_without_pending_state_reports_an_expired_session(
    deps: TelegramDeps, messaging: FakeMessaging
) -> None:
    """A tap on a keyboard left over from before a restart."""
    await _tap(deps, OB_SAVE)

    assert messaging.texts[-1].text == ONBOARDING_EXPIRED


# --- the /lapor gate --------------------------------------------------------


async def test_lapor_is_gated_before_setup(
    deps: TelegramDeps, messaging: FakeMessaging, reporter: _StubGenerateReport
) -> None:
    await _send(on_report, deps, "/lapor")

    assert messaging.texts[-1].text == NOT_ONBOARDED
    assert messaging.documents == []
    assert reporter.calls == []


async def test_lapor_works_once_onboarded(
    deps: TelegramDeps, messaging: FakeMessaging, reporter: _StubGenerateReport
) -> None:
    await _complete_onboarding(deps)

    await _send(on_report, deps, "/lapor")

    assert reporter.calls == [USER_ID]
    assert messaging.documents[-1].content == b"%PDF-fake"


async def test_lapor_is_still_gated_mid_setup(
    deps: TelegramDeps, messaging: FakeMessaging, reporter: _StubGenerateReport
) -> None:
    await _send(on_start, deps, "/start")
    await _send(on_text, deps, BUSINESS_NAME)
    await _tap(deps, OB_SAVE)  # name saved, timezone still open

    await _send(on_report, deps, "/lapor")

    assert messaging.texts[-1].text == NOT_ONBOARDED
    assert reporter.calls == []
