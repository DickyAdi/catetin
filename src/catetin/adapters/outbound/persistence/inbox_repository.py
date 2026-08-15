from typing import cast

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from catetin.domain.ports.clock import ClockPort

from .orm import InboxRow


class SqlAlchemyInboxRepository:
    def __init__(self, session: AsyncSession, clock: ClockPort) -> None:
        self._session = session
        self._clock = clock

    async def add_if_new(self, update_id: int, payload: bytes) -> bool:
        stmt = (
            sqlite_insert(InboxRow)
            .values(update_id=update_id, payload=payload)
            .on_conflict_do_nothing(index_elements=[InboxRow.update_id])
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount != 0

    async def mark_processed(self, update_id: int) -> None:
        row = await self._session.get(InboxRow, update_id)
        if row is not None:
            row.processed_at = int(self._clock.now().timestamp())
            await self._session.flush()

    async def list_unprocessed(self) -> list[tuple[int, bytes]]:
        stmt = (
            select(InboxRow.update_id, InboxRow.payload)
            .where(InboxRow.processed_at.is_(None))
            .order_by(InboxRow.received_at)
        )
        rows = (await self._session.execute(stmt)).all()
        return [(update_id, payload) for update_id, payload in rows]

    async def count_unprocessed(self) -> int:
        stmt = select(func.count()).select_from(InboxRow).where(InboxRow.processed_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one()
