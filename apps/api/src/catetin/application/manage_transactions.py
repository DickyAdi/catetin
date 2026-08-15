"""ManageTransactions — `/list` and `/batal`.

`/batal` twice in a row removes the next-most-recent row, not a no-op: the
first call soft-deletes the latest transaction, which the structural
soft-delete filter (`with_loader_criteria`, installed on the session)
then excludes from every subsequent query — including the second call's
own "most recent" lookup. No extra bookkeeping is needed here for that.
"""

from __future__ import annotations

from ..domain.models import Transaction
from ..domain.ports.repositories import UnitOfWork

DEFAULT_LIST_LIMIT = 10


class ManageTransactions:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def list_recent(
        self, user_id: int, limit: int = DEFAULT_LIST_LIMIT
    ) -> list[Transaction]:
        async with self._uow as uow:
            return await uow.transactions.list_recent(user_id, limit)

    async def cancel_last(self, user_id: int) -> Transaction | None:
        async with self._uow as uow:
            removed = await uow.transactions.soft_delete_last(user_id)
            await uow.commit()
            return removed
