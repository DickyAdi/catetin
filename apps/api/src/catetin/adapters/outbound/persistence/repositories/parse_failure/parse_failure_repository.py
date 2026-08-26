from typing import cast

from sqlalchemy import delete, desc, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from catetin.domain.models import ParseFailure

from ...models import ParseFailureRow
from .mappers import parse_failure_to_domain


class SqlAlchemyParseFailureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_id: int | None, raw_text: str, reason: str) -> ParseFailure:
        row = ParseFailureRow(user_id=user_id, raw_text=raw_text, reason=reason)
        self._session.add(row)
        await self._session.flush()
        return parse_failure_to_domain(row)

    async def list_recent(self, limit: int = 50) -> list[ParseFailure]:
        stmt = select(ParseFailureRow).order_by(desc(ParseFailureRow.created_at)).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [parse_failure_to_domain(row) for row in rows]

    async def count_since(self, since_at: int) -> int:
        stmt = select(func.count()).select_from(ParseFailureRow).where(
            ParseFailureRow.created_at >= since_at
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def delete_older_than(self, before_at: int) -> int:
        stmt = delete(ParseFailureRow).where(ParseFailureRow.created_at < before_at)
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount

    async def purge_user(self, user_id: int) -> int:
        """Hard-delete this user's parse failures, including their `raw_text`
        (verbatim chat the parser could not read) — `/hapusakun` (G5/US-12)."""
        stmt = delete(ParseFailureRow).where(ParseFailureRow.user_id == user_id)
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount
