"""Session-scoped access to `rate_limits`, for the parts of the purge that
must join the same writer transaction as everything else.

`SqliteRateLimiter` next door owns its own sessions on purpose (a rate-limit
check must commit independently of whatever the caller is doing). `/hapusakun`
needs the opposite: the rate-limit rows have to disappear in the *same*
transaction as the transactions, inbox and users rows, or a mid-purge failure
would leave a half-erased account behind. Hence a second, tiny repository on
the UnitOfWork's session rather than a `purge_user` bolted onto the limiter.
"""

from typing import cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import RateLimitRow


class SqlAlchemyRateLimitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def purge_user(self, user_id: int) -> int:
        stmt = delete(RateLimitRow).where(RateLimitRow.user_id == user_id)
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount
