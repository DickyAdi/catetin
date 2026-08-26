"""DeleteAccount — `/hapusakun`, the UU PDP right to erasure.

This is the one use case in the codebase that really destroys data. Every
other "delete" here is a soft delete (`/batal` sets `deleted_at` and the
session-wide loader criteria hide the row); erasure means the bytes go,
`raw_text` and all.

Two properties matter enough to spell out:

1. **One transaction.** Every table is purged inside a single `async with
   self._uow` block with one `commit()` at the end. The writer engine's
   `pool_size=1` pool is the lock, so nothing else can write in between, and
   an exception mid-purge rolls the whole thing back rather than leaving an
   account half-erased (a user row with orphaned transactions, or worse,
   transactions with no user).

2. **Core deletes, not ORM round trips.** See `purge_user` on each
   repository. An ORM select-then-delete would inherit the soft-delete
   criteria and silently skip every `/batal`'d row, orphaning exactly the
   data the user is most likely to want gone.

What survives on purpose: one `deletion_log` row, carrying a timestamp, the
platform, and a count. No user id, no chat text. It proves the request was
honored without keeping the person it was honored for.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.errors import NotFound
from ..domain.ports.clock import ClockPort
from ..domain.ports.repositories import UnitOfWork


@dataclass(frozen=True, slots=True)
class DeletionSummary:
    """Per-table counts of what was actually erased."""

    transactions: int
    parse_failures: int
    inbox: int
    rate_limits: int
    users: int

    @property
    def total(self) -> int:
        return (
            self.transactions
            + self.parse_failures
            + self.inbox
            + self.rate_limits
            + self.users
        )


class DeleteAccount:
    def __init__(self, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    async def preview(self, user_id: int) -> int:
        """How many transactions `execute()` would erase — the number shown on
        the confirmation keyboard. Counts soft-deleted and excluded rows too,
        because those are erased as well and the prompt says "SEMUA"."""
        async with self._uow as uow:
            return await uow.transactions.count_for_user(user_id)

    async def execute(self, user_id: int) -> DeletionSummary:
        async with self._uow as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise NotFound(f"user {user_id} not found")
            # Read the platform identity before anything is deleted: the
            # inbox purge needs the Telegram id to match payloads, and the
            # audit row needs the platform. Both are gone a few lines later.
            platform = user.platform
            platform_user_id = user.platform_user_id

            # Children first, users last: if this ever runs with
            # `PRAGMA foreign_keys=ON`, deleting the parent first would either
            # cascade (making the counts below lie) or fail outright.
            transactions = await uow.transactions.purge_user(user_id)
            parse_failures = await uow.parse_failures.purge_user(user_id)
            inbox = await uow.inbox.purge_user(user_id, platform_user_id)
            rate_limits = await uow.rate_limits.purge_user(user_id)
            users = await uow.users.hard_delete(user_id)

            summary = DeletionSummary(
                transactions=transactions,
                parse_failures=parse_failures,
                inbox=inbox,
                rate_limits=rate_limits,
                users=users,
            )
            await uow.deletion_log.add(
                platform, summary.total, int(self._clock.now().timestamp())
            )
            await uow.commit()

        return summary
