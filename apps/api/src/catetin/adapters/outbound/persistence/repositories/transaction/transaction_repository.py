from typing import Any, cast

from sqlalchemy import Table, case, delete, desc, func, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from catetin.domain.models import (
    DayTotal,
    ItemTotal,
    ParsedTransaction,
    Summary,
    Transaction,
)
from catetin.domain.ports.clock import ClockPort

from ...models import TransactionRow
from .mappers import (
    transaction_from_core_row,
    transaction_row_from_parsed,
    transaction_to_domain,
    transaction_values_from_parsed,
)

# The raw `Table` behind the mapped entity, for the handful of queries that
# must bypass the session-wide soft-delete `with_loader_criteria`. Declarative
# types `__table__` as the broader `FromClause`, which `delete()` will not
# accept, so the narrowing happens once here rather than at each call site.
_transactions = cast(Table, TransactionRow.__table__)


class SqlAlchemyTransactionRepository:
    def __init__(self, session: AsyncSession, clock: ClockPort) -> None:
        self._session = session
        self._clock = clock

    async def add(
        self, user_id: int, parsed: ParsedTransaction, *, excluded_from_report: bool = False
    ) -> Transaction:
        occurred_at = int(self._clock.now().timestamp())
        row = transaction_row_from_parsed(
            user_id, parsed, occurred_at, excluded_from_report=excluded_from_report
        )
        self._session.add(row)
        await self._session.flush()
        return transaction_to_domain(row)

    async def batch_add(
        self, user_id: int, parsed: list[ParsedTransaction]
    ) -> list[Transaction]:
        """One `executemany` INSERT for the whole batch instead of N round trips.

        SQLite/aiosqlite doesn't reliably support RETURNING with executemany, so
        the inserted rows are re-fetched by id afterward. Safe because the writer
        engine's single-connection pool holds this session's transaction exclusively
        until commit — no other write can land between the insert and the select.
        """
        if not parsed:
            return []
        occurred_at = int(self._clock.now().timestamp())
        values = [transaction_values_from_parsed(user_id, p, occurred_at) for p in parsed]
        await self._session.execute(insert(TransactionRow), values)
        await self._session.flush()

        stmt = (
            select(TransactionRow)
            .where(TransactionRow.user_id == user_id, TransactionRow.occurred_at == occurred_at)
            .order_by(desc(TransactionRow.id))
            .limit(len(values))
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [transaction_to_domain(row) for row in reversed(rows)]

    async def get(self, user_id: int, transaction_id: int) -> Transaction | None:
        stmt = select(TransactionRow).where(
            TransactionRow.user_id == user_id, TransactionRow.id == transaction_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return transaction_to_domain(row) if row is not None else None

    async def list_recent(self, user_id: int, limit: int = 20) -> list[Transaction]:
        # id as tiebreaker: created_at has 1-second resolution, so two inserts
        # in the same second would otherwise sort in an undefined order.
        stmt = (
            select(TransactionRow)
            .where(TransactionRow.user_id == user_id)
            .order_by(desc(TransactionRow.created_at), desc(TransactionRow.id))
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [transaction_to_domain(row) for row in rows]

    async def list_page(self, user_id: int, offset: int, limit: int) -> list[Transaction]:
        """One window of `list_recent`'s ordering, for `/list` pagination.

        Same ORDER BY as `list_recent` — an OFFSET is only meaningful against a
        total order, so the `id` tiebreaker matters more here than there: with
        two rows sharing a `created_at` second, an unstable sort could show one
        of them on both page 1 and page 2 and the other on neither.
        """
        stmt = (
            select(TransactionRow)
            .where(TransactionRow.user_id == user_id)
            .order_by(desc(TransactionRow.created_at), desc(TransactionRow.id))
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [transaction_to_domain(row) for row in rows]

    async def count_active_for_user(self, user_id: int) -> int:
        """How many rows `/list` can page through — soft-deleted ones excluded,
        so the page count matches what the windows actually contain.

        Not `count_for_user`: that one counts `/batal`'d rows too, because
        `/hapusakun` is about to erase those as well.
        """
        stmt = select(func.count()).select_from(TransactionRow).where(
            TransactionRow.user_id == user_id,
            TransactionRow.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def soft_delete_last(self, user_id: int) -> Transaction | None:
        stmt = (
            select(TransactionRow)
            .where(TransactionRow.user_id == user_id)
            .order_by(desc(TransactionRow.created_at), desc(TransactionRow.id))
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        row.deleted_at = int(self._clock.now().timestamp())
        await self._session.flush()
        return transaction_to_domain(row)

    async def summarize_range(self, user_id: int, start_date: str, end_date: str) -> Summary:
        stmt = select(
            TransactionRow.kind,
            func.count().label("n"),
            func.sum(TransactionRow.total_amount).label("total"),
        ).where(
            TransactionRow.user_id == user_id,
            TransactionRow.occurred_on >= start_date,
            TransactionRow.occurred_on <= end_date,
            TransactionRow.deleted_at.is_(None),
            TransactionRow.excluded_from_report == 0,
        ).group_by(TransactionRow.kind)
        rows = (await self._session.execute(stmt)).all()

        income = expense = count = 0
        for kind, n, total in rows:
            count += n
            if kind == "sale":
                income += total
            else:
                expense += total
        return Summary(income=income, expense=expense, profit=income - expense, count=count)

    async def daily_totals(
        self, user_id: int, start_date: str, end_date: str
    ) -> list[DayTotal]:
        income_expr = func.sum(
            case((TransactionRow.kind == "sale", TransactionRow.total_amount), else_=0)
        )
        expense_expr = func.sum(
            case((TransactionRow.kind == "expense", TransactionRow.total_amount), else_=0)
        )
        stmt = (
            select(
                TransactionRow.occurred_on,
                income_expr.label("income"),
                expense_expr.label("expense"),
            )
            .where(
                TransactionRow.user_id == user_id,
                TransactionRow.occurred_on >= start_date,
                TransactionRow.occurred_on <= end_date,
                TransactionRow.deleted_at.is_(None),
                TransactionRow.excluded_from_report == 0,
            )
            .group_by(TransactionRow.occurred_on)
            .order_by(TransactionRow.occurred_on)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            DayTotal(date=day, income=income, expense=expense, profit=income - expense)
            for day, income, expense in rows
        ]

    async def top_items(self, user_id: int, kind: str, limit: int = 10) -> list[ItemTotal]:
        stmt = (
            select(
                TransactionRow.item,
                TransactionRow.kind,
                func.sum(TransactionRow.total_amount).label("total"),
            )
            .where(
                TransactionRow.user_id == user_id,
                TransactionRow.kind == kind,
                TransactionRow.deleted_at.is_(None),
                TransactionRow.excluded_from_report == 0,
            )
            .group_by(TransactionRow.item, TransactionRow.kind)
            .order_by(desc("total"))
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [ItemTotal(item=item, kind=kind, total=total) for item, kind, total in rows]

    async def list_flagged(
        self, user_id: int, start_date: str, end_date: str
    ) -> list[Transaction]:
        stmt = (
            select(TransactionRow)
            .where(
                TransactionRow.user_id == user_id,
                TransactionRow.occurred_on >= start_date,
                TransactionRow.occurred_on <= end_date,
                TransactionRow.flagged == 1,
                TransactionRow.excluded_from_report == 0,
            )
            .order_by(TransactionRow.occurred_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [transaction_to_domain(row) for row in rows]

    async def exclude_flagged(self, user_id: int, start_date: str, end_date: str) -> int:
        stmt = (
            update(TransactionRow)
            .where(
                TransactionRow.user_id == user_id,
                TransactionRow.occurred_on >= start_date,
                TransactionRow.occurred_on <= end_date,
                TransactionRow.flagged == 1,
                TransactionRow.excluded_from_report == 0,
                TransactionRow.deleted_at.is_(None),
            )
            .values(excluded_from_report=1)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()

        return cast("int", cast(CursorResult[Any], result).rowcount)

    async def list_in_period(
        self, user_id: int, start_date: str, end_date: str
    ) -> list[Transaction]:
        """Full audit-trail listing (FR-5 §B) — includes soft-deleted rows
        (shown with their own "Batal" status), so this deliberately selects
        the raw `Table` rather than the mapped entity to bypass the
        session-wide soft-delete `with_loader_criteria`."""
        table = _transactions
        stmt = (
            select(table)
            .where(
                table.c.user_id == user_id,
                table.c.occurred_on >= start_date,
                table.c.occurred_on <= end_date,
                table.c.excluded_from_report == 0,
            )
            .order_by(table.c.occurred_at)
        )
        rows = (await self._session.execute(stmt)).all()
        return [transaction_from_core_row(row) for row in rows]

    async def count_for_user(self, user_id: int) -> int:
        """Every row this user owns, soft-deleted and excluded ones included:
        the number `/hapusakun` promises to erase. Counts the raw `Table` so
        the session-wide soft-delete criteria cannot hide `/batal`'d rows and
        under-report what is about to go."""
        table = _transactions
        stmt = select(func.count()).select_from(table).where(table.c.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one()

    async def purge_user(self, user_id: int) -> int:
        """Hard-delete every row this user owns, `raw_text` and all (G5/US-12).

        Deliberately a Core `delete()` against the raw `Table`, not an ORM
        select-then-delete: the session installs a `deleted_at IS NULL`
        `with_loader_criteria` on selects, so an ORM round trip would skip
        already-soft-deleted rows and orphan every `/batal`'d transaction
        forever. Soft delete is not erasure; this is.
        """
        table = _transactions
        result = await self._session.execute(delete(table).where(table.c.user_id == user_id))
        return cast("int", cast(CursorResult[Any], result).rowcount)

    async def count_by_occurred_on(self, occurred_on: str) -> int:
        """Instance-wide (all users) count for ops stats — not user-scoped."""
        stmt = select(func.count()).select_from(TransactionRow).where(
            TransactionRow.occurred_on == occurred_on,
            TransactionRow.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def count_created_since(self, since_at: int) -> int:
        """Instance-wide (all users) count for ops stats — not user-scoped."""
        stmt = select(func.count()).select_from(TransactionRow).where(
            TransactionRow.created_at >= since_at,
            TransactionRow.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one()
