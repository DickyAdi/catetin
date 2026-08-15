"""SqliteRateLimiter -> RateLimiterPort, backed by the WITHOUT ROWID rate_limits table.

Accessed only through RateLimiterPort; a future RedisRateLimiter is ~30 LOC
plus a config change, not a rewrite of the callers.
"""

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catetin.domain.ports.clock import ClockPort

from ...models import RateLimitRow


class SqliteRateLimiter:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: ClockPort
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def check_and_increment(
        self, user_id: int, bucket: str, limit: int, window_seconds: int
    ) -> bool:
        now = int(self._clock.now().timestamp())
        window_start = (now // window_seconds) * window_seconds

        stmt = (
            sqlite_insert(RateLimitRow)
            .values(user_id=user_id, bucket=bucket, window_start=window_start, count=1)
            .on_conflict_do_update(
                index_elements=[
                    RateLimitRow.user_id,
                    RateLimitRow.bucket,
                    RateLimitRow.window_start,
                ],
                set_={"count": RateLimitRow.count + 1},
            )
            .returning(RateLimitRow.count)
        )
        async with self._session_factory() as session:
            count = (await session.execute(stmt)).scalar_one()
            await session.commit()
        return count <= limit
