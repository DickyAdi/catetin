"""Writes the `deletion_log` audit row for `/hapusakun`.

Deliberately has no read-by-user method: nothing here is keyed to a person,
so there is nothing to look up on their behalf. `count_total` exists only so
ops can answer "how many erasure requests have we honored".
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import DeletionLogRow


class SqlAlchemyDeletionLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, platform: str, rows_deleted: int, deleted_at: int) -> None:
        self._session.add(
            DeletionLogRow(
                deleted_at=deleted_at, platform=platform, rows_deleted=rows_deleted
            )
        )
        await self._session.flush()

    async def count_total(self) -> int:
        stmt = select(func.count()).select_from(DeletionLogRow)
        return (await self._session.execute(stmt)).scalar_one()
