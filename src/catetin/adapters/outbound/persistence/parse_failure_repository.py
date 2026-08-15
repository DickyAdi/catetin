from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catetin.domain.models import ParseFailure

from .mappers import parse_failure_to_domain
from .orm import ParseFailureRow


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
