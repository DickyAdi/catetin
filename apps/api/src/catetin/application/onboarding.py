"""Onboarding — `get_or_create_user`, the `/start` flow, `/digest`, `/zona`.

All user-facing copy is Indonesian, second person `kamu`, no English product
jargon (per Modules M1-M2's reply formatting rules).
"""

from __future__ import annotations

import re
from zoneinfo import available_timezones

from ..domain.errors import DomainValidationError
from ..domain.models import User
from ..domain.ports.repositories import UnitOfWork

# A business name is echoed back into chat replies and into the PDF report, so
# it is an untrusted string that reaches two renderers. Rather than escape it
# per sink, the accepted alphabet is narrowed at the door: letters, digits,
# spaces, `-` and `_`. That drops every character markup, control sequences and
# SQL-ish payloads need (`<`, `&`, `;`, `/`, quotes, newlines) while still
# covering how UMKM actually write their names ("Warung Mbok Rina", "Toko-ABC_1").
_BUSINESS_NAME_RE = re.compile(r"^[A-Za-z0-9 _\-]+$")
MAX_BUSINESS_NAME_LEN = 64


def validate_business_name(raw: str) -> str | None:
    """Return the cleaned name, or None if it is not acceptable.

    Pure and sync on purpose: the Telegram handler has to validate a typed name
    *before* anything is written (the user still has to confirm it), so this
    cannot be folded into the persisting method below.
    """
    name = raw.strip()
    if not name or len(name) > MAX_BUSINESS_NAME_LEN:
        return None
    if not _BUSINESS_NAME_RE.fullmatch(name):
        return None
    return name


_GUIDE_MESSAGE = """\
Kirim transaksimu pakai bahasa sehari-hari:
• "jual ayam geprek 50rb"
• "beli tepung 20rb"
• "jual nasi goreng 25rb, es jeruk 8rb"

Perintah yang ada:
• /hariini — untung-rugi hari ini
• /minggu — ringkasan 7 hari
• /lapor — laporan PDF
• /list — 10 transaksi terakhir
• /batal — batalkan transaksi terakhir
• /digest on|off — ringkasan otomatis tiap malam
• /zona — atur zona waktu

Zona waktumu sekarang {timezone} (dipakai buat nentuin "hari ini"). \
Kalau beda, ketik /zona lalu pilih zonamu.

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

    def guide_message(self, timezone: str) -> str:
        """The "here is what I can do" copy, sent once setup is finished.

        It used to be the whole of `/start`, back when there was no signup at
        all. `/start` now runs the two-step name + timezone flow and this is
        the closing message, so the timezone line it ends on states a value the
        user has just chosen rather than one guessed for them."""
        return _GUIDE_MESSAGE.format(timezone=timezone)

    async def set_business_name(self, user_id: int, name: str) -> User:
        """Persist a business name. Re-validates: the handler validated before
        showing the confirm button, but the button payload is user-controlled
        and this method is the last gate before the value is stored."""
        cleaned = validate_business_name(name)
        if cleaned is None:
            raise DomainValidationError(f"invalid business name: {name!r}")
        async with self._uow as uow:
            updated = await uow.users.set_business_name(user_id, cleaned)
            await uow.commit()
            return updated

    async def complete_onboarding(self, user_id: int) -> User:
        async with self._uow as uow:
            updated = await uow.users.set_onboarded(user_id)
            await uow.commit()
            return updated

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
