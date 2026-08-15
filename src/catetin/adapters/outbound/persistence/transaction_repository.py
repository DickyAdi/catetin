from sqlalchemy import case, desc, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from catetin.domain.models import (
    DayTotal,
    ItemTotal,
    ParsedTransaction,
    Summary,
    Transaction,
)
from catetin.domain.ports.clock import ClockPort

from .mappers import (
    transaction_row_from_parsed,
    transaction_to_domain,
    transaction_values_from_parsed,
)
from .orm import TransactionRow


class SqlAlchemyTransactionRepository:
    def __init__(self, session: AsyncSession, clock: ClockPort) -> None:
        self._session = session
        self._clock = clock

    async def add(self, user_id: int, parsed: ParsedTransaction) -> Transaction:
        occurred_at = int(self._clock.now().timestamp())
        row = transaction_row_from_parsed(user_id, parsed, occurred_at)
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
            )
            .group_by(TransactionRow.item, TransactionRow.kind)
            .order_by(desc("total"))
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [ItemTotal(item=item, kind=kind, total=total) for item, kind, total in rows]

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
