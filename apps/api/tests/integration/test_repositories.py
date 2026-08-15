"""Repository behavior against a real migrated SQLite database.

Uses the SqlAlchemyUnitOfWork end-to-end rather than instantiating repos
directly, since that's how production code drives them and it exercises the
soft-delete `with_loader_criteria` filter installed on the session.
"""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catetin.adapters.outbound.persistence.repositories.rate_limit.rate_limiter import (
    SqliteRateLimiter,
)
from catetin.adapters.outbound.persistence.uow import SqlAlchemyUnitOfWork
from catetin.domain.models import ParsedTransaction
from tests.fakes.frozen_clock import FrozenClock


def _parsed(
    item: str = "kopi",
    total_amount: int = 15_000,
    kind: str = "sale",
    occurred_on: date = date(2026, 8, 15),
) -> ParsedTransaction:
    return ParsedTransaction(
        kind=kind,
        item=item,
        qty=1,
        unit_amount=total_amount,
        total_amount=total_amount,
        occurred_on=occurred_on,
        confidence=1.0,
        raw_text=f"{item} {total_amount}",
    )


@pytest.fixture
def uow(
    sessionmaker: async_sessionmaker[AsyncSession], clock: FrozenClock
) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(sessionmaker, clock)


async def test_user_create_get_by_id_and_platform_identity(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    async with uow as u:
        created = await u.users.create("telegram", "1001", display_name="Budi")
        await u.commit()

    async with uow as u:
        by_id = await u.users.get_by_id(created.id)
        by_platform = await u.users.get_by_platform_identity("telegram", "1001")

    assert by_id is not None
    assert by_id.id == created.id
    assert by_id.display_name == "Budi"
    assert by_platform is not None
    assert by_platform.id == created.id


async def test_user_get_by_id_missing_returns_none(uow: SqlAlchemyUnitOfWork) -> None:
    async with uow as u:
        assert await u.users.get_by_id(999) is None
        assert await u.users.get_by_platform_identity("telegram", "nope") is None


async def test_transaction_batch_create_and_list_recent(uow: SqlAlchemyUnitOfWork) -> None:
    async with uow as u:
        user = await u.users.create("telegram", "2001")
        for item in ("kopi", "teh", "roti"):
            await u.transactions.add(user.id, _parsed(item=item))
        await u.commit()

    async with uow as u:
        recent = await u.transactions.list_recent(user.id)

    assert {t.item for t in recent} == {"kopi", "teh", "roti"}
    assert all(t.user_id == user.id for t in recent)


async def test_transaction_batch_add_inserts_all_in_one_go_with_ids_populated(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    async with uow as u:
        user = await u.users.create("telegram", "2005")
        parsed = [_parsed(item="kopi"), _parsed(item="teh"), _parsed(item="roti")]
        recorded = await u.transactions.batch_add(user.id, parsed)
        await u.commit()

    assert [t.item for t in recorded] == ["kopi", "teh", "roti"]
    assert all(t.id is not None for t in recorded)
    assert len({t.id for t in recorded}) == 3
    assert all(t.user_id == user.id for t in recorded)

    async with uow as u:
        recent = await u.transactions.list_recent(user.id)
    assert {t.item for t in recent} == {"kopi", "teh", "roti"}


async def test_transaction_batch_add_empty_list_returns_empty(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    async with uow as u:
        user = await u.users.create("telegram", "2006")
        recorded = await u.transactions.batch_add(user.id, [])
        await u.commit()

    assert recorded == []


async def test_summarize_range_aggregates_by_kind(uow: SqlAlchemyUnitOfWork) -> None:
    async with uow as u:
        user = await u.users.create("telegram", "3001")
        await u.transactions.add(user.id, _parsed(kind="sale", total_amount=50_000))
        await u.transactions.add(user.id, _parsed(kind="sale", total_amount=30_000))
        await u.transactions.add(user.id, _parsed(kind="expense", total_amount=20_000))
        await u.commit()

    async with uow as u:
        summary = await u.transactions.summarize_range(user.id, "2026-08-01", "2026-08-31")

    assert summary.income == 80_000
    assert summary.expense == 20_000
    assert summary.profit == 60_000
    assert summary.count == 3


async def test_soft_delete_last_excludes_from_default_queries(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    async with uow as u:
        user = await u.users.create("telegram", "4001")
        await u.transactions.add(user.id, _parsed(item="pertama"))
        await u.transactions.add(user.id, _parsed(item="terakhir"))
        await u.commit()

    async with uow as u:
        deleted = await u.transactions.soft_delete_last(user.id)
        await u.commit()

    assert deleted is not None
    assert deleted.item == "terakhir"
    assert deleted.deleted_at is not None

    async with uow as u:
        remaining = await u.transactions.list_recent(user.id)
        summary = await u.transactions.summarize_range(user.id, "2026-08-01", "2026-08-31")

    assert [t.item for t in remaining] == ["pertama"]
    assert summary.count == 1


async def test_cross_user_isolation(uow: SqlAlchemyUnitOfWork) -> None:
    async with uow as u:
        user_a = await u.users.create("telegram", "5001")
        user_b = await u.users.create("telegram", "5002")
        await u.transactions.add(user_a.id, _parsed(item="milik-a"))
        await u.transactions.add(user_b.id, _parsed(item="milik-b"))
        await u.commit()

    async with uow as u:
        a_txns = await u.transactions.list_recent(user_a.id)
        b_txns = await u.transactions.list_recent(user_b.id)
        a_summary = await u.transactions.summarize_range(user_a.id, "2026-08-01", "2026-08-31")

    assert [t.item for t in a_txns] == ["milik-a"]
    assert [t.item for t in b_txns] == ["milik-b"]
    assert a_summary.count == 1


async def test_inbox_add_if_new_is_idempotent(uow: SqlAlchemyUnitOfWork) -> None:
    async with uow as u:
        first = await u.inbox.add_if_new(42, b'{"foo": 1}')
        second = await u.inbox.add_if_new(42, b'{"foo": 1}')
        await u.commit()

    assert first is True
    assert second is False

    async with uow as u:
        unprocessed = await u.inbox.list_unprocessed()

    assert [update_id for update_id, _ in unprocessed] == [42]


async def test_ops_stats_count_methods(uow: SqlAlchemyUnitOfWork, clock: FrozenClock) -> None:
    """The repo-layer counts that back GET /ops/api/stats (instance-wide, not
    user-scoped)."""
    async with uow as u:
        user_a = await u.users.create("telegram", "6001")
        user_b = await u.users.create("telegram", "6002")
        await u.transactions.add(user_a.id, _parsed(occurred_on=date(2026, 8, 15)))
        await u.transactions.add(user_b.id, _parsed(occurred_on=date(2026, 8, 15)))
        await u.transactions.add(user_a.id, _parsed(occurred_on=date(2026, 8, 10)))
        await u.parse_failures.add(user_a.id, "gak jelas", "no_amount")
        await u.inbox.add_if_new(1, b"{}")
        await u.inbox.mark_processed(1)
        await u.inbox.add_if_new(2, b"{}")
        await u.commit()

    since_all = int(clock.now().timestamp()) - 3600

    async with uow as u:
        assert await u.users.count_total() == 2
        assert await u.transactions.count_by_occurred_on("2026-08-15") == 2
        assert await u.transactions.count_created_since(since_all) == 3
        assert await u.parse_failures.count_since(since_all) == 1
        assert await u.inbox.count_unprocessed() == 1


async def test_inbox_mark_processed_removes_from_unprocessed(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    async with uow as u:
        await u.inbox.add_if_new(7, b"{}")
        await u.commit()

    async with uow as u:
        await u.inbox.mark_processed(7)
        await u.commit()

    async with uow as u:
        unprocessed = await u.inbox.list_unprocessed()

    assert unprocessed == []


async def test_rate_limiter_allows_until_limit_then_blocks(
    sessionmaker: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    uow: SqlAlchemyUnitOfWork,
) -> None:
    async with uow as u:
        user = await u.users.create("telegram", "6001")
        await u.commit()

    limiter = SqliteRateLimiter(sessionmaker, clock)

    results = [
        await limiter.check_and_increment(user.id, "pdf", limit=3, window_seconds=3600)
        for _ in range(4)
    ]

    assert results == [True, True, True, False]


async def test_rate_limiter_buckets_are_independent(
    sessionmaker: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    uow: SqlAlchemyUnitOfWork,
) -> None:
    async with uow as u:
        user = await u.users.create("telegram", "6002")
        await u.commit()

    limiter = SqliteRateLimiter(sessionmaker, clock)

    assert await limiter.check_and_increment(user.id, "pdf", limit=1, window_seconds=3600)
    assert not await limiter.check_and_increment(user.id, "pdf", limit=1, window_seconds=3600)
    assert await limiter.check_and_increment(user.id, "digest", limit=1, window_seconds=3600)
