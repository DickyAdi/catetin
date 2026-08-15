"""ReplayInbox — startup replay of unprocessed `inbox` rows (M6 lifespan
step 6). Thin: the actual Telegram dispatch is Phase 6, so this only owns
the repository interaction and calls back into whatever the bot layer
supplies for re-dispatch.

If `dispatch` raises, the surrounding `UnitOfWork` rolls back and nothing is
marked processed — the row is retried on the next replay, giving
at-least-once delivery rather than losing an update on a crash mid-batch.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..domain.ports.repositories import UnitOfWork

ReplayCallback = Callable[[int, bytes], Awaitable[None]]


class ReplayInbox:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, dispatch: ReplayCallback) -> int:
        async with self._uow as uow:
            unprocessed = await uow.inbox.list_unprocessed()
            for update_id, payload in unprocessed:
                await dispatch(update_id, payload)
                await uow.inbox.mark_processed(update_id)
            await uow.commit()
        return len(unprocessed)
