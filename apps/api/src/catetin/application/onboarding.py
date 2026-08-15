"""Onboarding — `get_or_create_user`, `/start` copy, `/digest`, `/zona`.

All user-facing copy is Indonesian, second person `kamu`, no English product
jargon (per Modules M1-M2's reply formatting rules).
"""

from __future__ import annotations

from zoneinfo import available_timezones

from ..domain.errors import DomainValidationError
from ..domain.models import User
from ..domain.ports.repositories import UnitOfWork

_START_MESSAGE = """\
Halo! 👋 Aku CatetIn, bot pencatatan keuangan buat usahamu.

Coba kirim salah satu contoh ini:
• "jual ayam geprek 50rb"
• "beli tepung 20rb"
• "jual nasi goreng 25rb, es jeruk 8rb"

Ketik /bantuan buat lihat semua perintah.

Data transaksimu cuma dipakai buat mencatat usahamu — baca kebijakan \
privasi di catetin.id/privasi."""


class Onboarding:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def get_or_create_user(
        self, platform: str, platform_user_id: str, display_name: str | None = None
    ) -> User:
        """Idempotent: used by `/start` and by any first message."""
        async with self._uow as uow:
            existing = await uow.users.get_by_platform_identity(platform, platform_user_id)
            if existing is not None:
                return existing
            created = await uow.users.create(platform, platform_user_id, display_name)
            await uow.commit()
            return created

    def start_message(self) -> str:
        return _START_MESSAGE

    async def toggle_digest(self, user_id: int, enabled: bool) -> User:
        async with self._uow as uow:
            updated = await uow.users.set_digest_enabled(user_id, enabled)
            await uow.commit()
            return updated

    async def set_timezone(self, user_id: int, tz: str) -> User:
        if tz not in available_timezones():
            raise DomainValidationError(f"unknown timezone: {tz}")
        async with self._uow as uow:
            updated = await uow.users.set_timezone(user_id, tz)
            await uow.commit()
            return updated
