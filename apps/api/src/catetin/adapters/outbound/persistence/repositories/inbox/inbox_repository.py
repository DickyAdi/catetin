from typing import cast

import orjson
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from catetin.domain.ports.clock import ClockPort

from ...models import InboxRow

# Update envelopes that carry a `from` object, i.e. the ones this bot ever
# stores. Anything else (channel posts, chat member updates) has no personal
# sender to match and is left alone.
_SENDER_CARRIERS = ("message", "edited_message", "callback_query")


def _sender_id(payload: bytes) -> str | None:
    """The Telegram user id inside a stored update, or None if unreadable.

    `inbox.payload` is the verbatim webhook body, so this is the only handle
    on "whose update is this" — the table has no `user_id` column (its PK is
    Telegram's own `update_id`, which is what makes replay idempotent).
    """
    try:
        update = orjson.loads(payload)
    except orjson.JSONDecodeError:
        return None
    if not isinstance(update, dict):
        return None
    for key in _SENDER_CARRIERS:
        envelope = update.get(key)
        if isinstance(envelope, dict):
            sender = envelope.get("from")
            if isinstance(sender, dict) and sender.get("id") is not None:
                return str(sender["id"])
    return None


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

    async def delete_processed_older_than(self, before_at: int) -> int:
        stmt = delete(InboxRow).where(
            InboxRow.processed_at.is_not(None), InboxRow.processed_at < before_at
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount

    async def purge_user(self, user_id: int, platform_user_id: str) -> int:
        """Hard-delete this user's raw webhook bodies — `/hapusakun`.

        Takes `platform_user_id` alongside `user_id` (which stays first, per
        G5/US-12) because the match lives inside the JSON payload, not in a
        column. Rows are decoded in Python rather than matched with a `LIKE`
        over the payload: a substring search for the id would also hit
        message ids, chat ids and amounts, and would delete other people's
        updates. The scan is bounded — `run_prune` keeps this table to 7 days.
        """
        rows = (await self._session.execute(select(InboxRow.update_id, InboxRow.payload))).all()
        doomed = [
            update_id
            for update_id, payload in rows
            if _sender_id(payload) == platform_user_id
        ]
        if not doomed:
            return 0
        stmt = delete(InboxRow).where(InboxRow.update_id.in_(doomed))
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount
