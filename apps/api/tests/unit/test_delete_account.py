"""`/hapusakun` at the use-case level (UU PDP right to erasure).

The properties worth pinning down here are the ones a future refactor could
quietly break: that erasure reaches *every* table rather than the two obvious
ones, that it reaches soft-deleted rows (a `/batal`'d transaction is exactly
the row a user most wants gone), that it does not touch the neighbours, and
that what survives is an audit row nobody can trace back to a person.

Real SQL atomicity and the Core-delete-vs-loader-criteria behaviour are
covered against actual SQLite in `tests/integration/test_repositories.py`.
"""

from datetime import UTC, date, datetime

import orjson
import pytest

from catetin.application.delete_account import DeleteAccount
from catetin.application.manage_transactions import ManageTransactions
from catetin.application.onboarding import Onboarding
from catetin.domain.errors import NotFound
from catetin.domain.models import ParsedTransaction
from tests.fakes.fake_repositories import FakeUnitOfWork
from tests.fakes.frozen_clock import FrozenClock

TODAY = date(2026, 8, 15)
NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


@pytest.fixture
def uow(clock: FrozenClock) -> FakeUnitOfWork:
    return FakeUnitOfWork(clock)


@pytest.fixture
def delete_account(uow: FakeUnitOfWork, clock: FrozenClock) -> DeleteAccount:
    return DeleteAccount(uow, clock)


def _parsed(item: str, total_amount: int = 10_000) -> ParsedTransaction:
    return ParsedTransaction(
        kind="sale",
        item=item,
        qty=1,
        unit_amount=None,
        total_amount=total_amount,
        occurred_on=TODAY,
        confidence=1.0,
        raw_text=f"jual {item}",
    )


def _update_payload(telegram_id: str, text: str) -> bytes:
    """A webhook body shaped like the ones `inbox` actually stores."""
    return orjson.dumps(
        {
            "update_id": 1,
            "message": {
                "message_id": 7,
                "from": {"id": int(telegram_id), "is_bot": False, "first_name": "Budi"},
                "chat": {"id": int(telegram_id), "type": "private"},
                "text": text,
            },
        }
    )


async def _populate(uow: FakeUnitOfWork, telegram_id: str, update_id: int) -> int:
    """One user with a row in every table `/hapusakun` has to reach."""
    user = await Onboarding(uow).get_or_create_user("telegram", telegram_id, "Budi")
    async with uow as u:
        await u.transactions.add(user.id, _parsed("Kopi"))
        await u.transactions.add(user.id, _parsed("Teh"))
        await u.parse_failures.add(user.id, "laris manis hari ini", "no_amount")
        await u.inbox.add_if_new(update_id, _update_payload(telegram_id, "jual kopi 10rb"))
        u._rate_limits[(user.id, "pdf")] = 3
    return user.id


async def test_preview_counts_every_transaction_including_soft_deleted(
    uow: FakeUnitOfWork, delete_account: DeleteAccount
) -> None:
    """The prompt says "SEMUA", so the number on it must not be the `/lapor`
    number — a `/batal`'d row is erased too and has to be counted."""
    user_id = await _populate(uow, "9001", 100)
    await ManageTransactions(uow).cancel_last(user_id)

    assert await delete_account.preview(user_id) == 2


async def test_execute_erases_every_table_and_reports_the_counts(
    uow: FakeUnitOfWork, delete_account: DeleteAccount
) -> None:
    user_id = await _populate(uow, "9001", 100)

    summary = await delete_account.execute(user_id)

    assert summary.transactions == 2
    assert summary.parse_failures == 1
    assert summary.inbox == 1
    assert summary.rate_limits == 1
    assert summary.users == 1
    assert summary.total == 6

    async with uow as u:
        assert await u.users.get_by_id(user_id) is None
        assert await u.transactions.count_for_user(user_id) == 0
        assert u._parse_failures == []
        assert u._inbox == {}
        assert u._rate_limits == {}


async def test_execute_erases_soft_deleted_rows_too(
    uow: FakeUnitOfWork, delete_account: DeleteAccount
) -> None:
    """Soft delete is not erasure. If the purge inherited the `deleted_at IS
    NULL` criteria it would orphan every `/batal`'d row forever."""
    user_id = await _populate(uow, "9001", 100)
    await ManageTransactions(uow).cancel_last(user_id)

    summary = await delete_account.execute(user_id)

    assert summary.transactions == 2
    async with uow as u:
        assert u._transactions == []


async def test_execute_leaves_other_users_untouched(
    uow: FakeUnitOfWork, delete_account: DeleteAccount
) -> None:
    """G5/US-12 cross-user isolation, on the one path that deletes for real."""
    victim = await _populate(uow, "9001", 100)
    bystander = await _populate(uow, "9002", 200)

    await delete_account.execute(victim)

    async with uow as u:
        assert await u.users.get_by_id(bystander) is not None
        assert await u.transactions.count_for_user(bystander) == 2
        assert [f.user_id for f in u._parse_failures] == [bystander]
        assert list(u._inbox) == [200]
        assert list(u._rate_limits) == [(bystander, "pdf")]


async def test_deletion_log_records_the_purge_without_identifying_anyone(
    uow: FakeUnitOfWork, delete_account: DeleteAccount
) -> None:
    """The audit row is the only thing that survives, so it has to prove the
    erasure happened while being useless for re-identifying who asked."""
    user_id = await _populate(uow, "9001", 100)

    summary = await delete_account.execute(user_id)

    async with uow as u:
        assert await u.deletion_log.count_total() == 1
        platform, rows_deleted, deleted_at = u._deletion_log[0]

    assert platform == "telegram"
    assert rows_deleted == summary.total
    assert deleted_at == int(NOW.timestamp())
    # Nothing that points back at the person: the platform user id ("9001")
    # and the display name are the two handles that could, and neither is
    # anywhere in the row. The table's *shape* is pinned separately, by
    # `test_deletion_log_carries_no_identifying_columns`.
    assert "9001" not in repr(u._deletion_log)
    assert "Budi" not in repr(u._deletion_log)


async def test_execute_on_unknown_user_raises_and_writes_no_audit_row(
    uow: FakeUnitOfWork, delete_account: DeleteAccount
) -> None:
    with pytest.raises(NotFound):
        await delete_account.execute(4242)

    async with uow as u:
        assert await u.deletion_log.count_total() == 0


async def test_second_purge_of_the_same_user_is_a_no_op(
    uow: FakeUnitOfWork, delete_account: DeleteAccount
) -> None:
    """A replayed confirmation tap must not write a second `deletion_log` row
    and make one erasure request look like two."""
    user_id = await _populate(uow, "9001", 100)
    await delete_account.execute(user_id)

    with pytest.raises(NotFound):
        await delete_account.execute(user_id)

    async with uow as u:
        assert await u.deletion_log.count_total() == 1
