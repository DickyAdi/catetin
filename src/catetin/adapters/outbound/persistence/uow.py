"""Thin UnitOfWork: the SQLAlchemy AsyncSession plus begin()/commit()/rollback().

Not a class hierarchy — one concrete class wrapping one AsyncSession, per the
design docs. The soft-delete filter (`deleted_at IS NULL` on `transactions`)
is installed structurally on the session via `with_loader_criteria`, rather
than repeated per query.
"""

from types import TracebackType
from typing import Self

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import with_loader_criteria

from catetin.domain.ports.clock import ClockPort

from .inbox_repository import SqlAlchemyInboxRepository
from .orm import TransactionRow
from .parse_failure_repository import SqlAlchemyParseFailureRepository
from .transaction_repository import SqlAlchemyTransactionRepository
from .user_repository import SqlAlchemyUserRepository


def _install_soft_delete_filter(session: AsyncSession) -> None:
    @event.listens_for(session.sync_session, "do_orm_execute")
    def _add_criteria(execute_state: object) -> None:
        if (
            execute_state.is_select  # type: ignore[attr-defined]
            and not execute_state.is_column_load  # type: ignore[attr-defined]
            and not execute_state.is_relationship_load  # type: ignore[attr-defined]
        ):
            execute_state.statement = execute_state.statement.options(  # type: ignore[attr-defined]
                with_loader_criteria(TransactionRow, lambda cls: cls.deleted_at.is_(None))
            )


class SqlAlchemyUnitOfWork:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: ClockPort
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self.session: AsyncSession

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        _install_soft_delete_filter(self.session)
        self.users = SqlAlchemyUserRepository(self.session, self._clock)
        self.transactions = SqlAlchemyTransactionRepository(self.session, self._clock)
        self.inbox = SqlAlchemyInboxRepository(self.session, self._clock)
        self.parse_failures = SqlAlchemyParseFailureRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def begin(self) -> None:
        await self.session.begin()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
