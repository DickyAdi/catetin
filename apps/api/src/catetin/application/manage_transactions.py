"""ManageTransactions — `/list` and `/batal`.

`/batal` twice in a row removes the next-most-recent row, not a no-op: the
first call soft-deletes the latest transaction, which the structural
soft-delete filter (`with_loader_criteria`, installed on the session)
then excludes from every subsequent query — including the second call's
own "most recent" lookup. No extra bookkeeping is needed here for that.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.models import Transaction
from ..domain.ports.repositories import UnitOfWork

DEFAULT_LIST_LIMIT = 10


@dataclass(frozen=True, slots=True)
class TransactionPage:
    """One `/list` window plus what the caller needs to draw navigation.

    `offset` is the *effective* offset, which is not always the one asked for:
    see `list_page` for the two ways a requested offset gets adjusted.
    """

    items: list[Transaction]
    total: int
    offset: int
    page_size: int


class ManageTransactions:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def list_recent(
        self, user_id: int, limit: int = DEFAULT_LIST_LIMIT
    ) -> list[Transaction]:
        async with self._uow as uow:
            return await uow.transactions.list_recent(user_id, limit)

    async def list_page(
        self, user_id: int, offset: int = 0, limit: int = DEFAULT_LIST_LIMIT
    ) -> TransactionPage:
        """A page of recent transactions, with the total for "page 2/3".

        The requested offset is normalised twice, because `/list`'s buttons are
        stateless and long-lived — an old keyboard can be tapped at any time:

          - snapped down to a page boundary, so the page number the caller
            renders always describes the rows it got;
          - clamped to the last page when it points past the end, which is what
            a keyboard from before a `/batal` (or `/hapusakun`) does.

        Both counts come from the same `UnitOfWork`, hence the same reader
        transaction: a page and a total that disagree would render "1-10 dari 4".
        """
        limit = max(1, limit)
        async with self._uow as uow:
            total = await uow.transactions.count_active_for_user(user_id)
            offset = max(0, offset) // limit * limit
            if total > 0 and offset >= total:
                offset = (total - 1) // limit * limit
            items = await uow.transactions.list_page(user_id, offset, limit)
            return TransactionPage(items=items, total=total, offset=offset, page_size=limit)

    async def cancel_last(self, user_id: int) -> Transaction | None:
        async with self._uow as uow:
            removed = await uow.transactions.soft_delete_last(user_id)
            await uow.commit()
            return removed
