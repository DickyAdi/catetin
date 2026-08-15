from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catetin.domain.errors import NotFound
from catetin.domain.models import User
from catetin.domain.ports.clock import ClockPort

from .mappers import user_to_domain
from .orm import UserRow


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession, clock: ClockPort) -> None:
        self._session = session
        self._clock = clock

    async def get_by_id(self, user_id: int) -> User | None:
        row = await self._session.get(UserRow, user_id)
        return user_to_domain(row) if row is not None else None

    async def get_by_platform_identity(
        self, platform: str, platform_user_id: str
    ) -> User | None:
        stmt = select(UserRow).where(
            UserRow.platform == platform, UserRow.platform_user_id == platform_user_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return user_to_domain(row) if row is not None else None

    async def create(
        self, platform: str, platform_user_id: str, display_name: str | None = None
    ) -> User:
        row = UserRow(
            platform=platform, platform_user_id=platform_user_id, display_name=display_name
        )
        self._session.add(row)
        await self._session.flush()
        return user_to_domain(row)

    async def set_digest_enabled(self, user_id: int, enabled: bool) -> User:
        row = await self._session.get(UserRow, user_id)
        if row is None:
            raise NotFound(f"user {user_id} not found")
        row.digest_enabled = int(enabled)
        await self._session.flush()
        return user_to_domain(row)

    async def mark_blocked(self, user_id: int) -> User:
        row = await self._session.get(UserRow, user_id)
        if row is None:
            raise NotFound(f"user {user_id} not found")
        row.blocked_at = int(self._clock.now().timestamp())
        await self._session.flush()
        return user_to_domain(row)
