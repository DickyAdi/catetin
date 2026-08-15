from types import TracebackType
from typing import Protocol, Self

from ..models import (
    DayTotal,
    ItemTotal,
    ParsedTransaction,
    ParseFailure,
    Summary,
    Transaction,
    User,
)


class UserRepository(Protocol):
    async def get_by_id(self, user_id: int) -> User | None: ...

    async def get_by_platform_identity(
        self, platform: str, platform_user_id: str
    ) -> User | None: ...

    async def create(
        self, platform: str, platform_user_id: str, display_name: str | None = None
    ) -> User: ...

    async def set_digest_enabled(self, user_id: int, enabled: bool) -> User: ...

    async def set_timezone(self, user_id: int, tz: str) -> User: ...

    async def mark_blocked(self, user_id: int) -> User: ...

    async def count_total(self) -> int: ...  # instance-wide, for ops stats

    async def list_digest_enabled(self) -> list[User]: ...  # instance-wide, for the nightly digest


class TransactionRepository(Protocol):
    async def add(self, user_id: int, parsed: ParsedTransaction) -> Transaction: ...

    async def batch_add(
        self, user_id: int, parsed: list[ParsedTransaction]
    ) -> list[Transaction]: ...

    async def get(self, user_id: int, transaction_id: int) -> Transaction | None: ...

    async def list_recent(self, user_id: int, limit: int = 20) -> list[Transaction]: ...

    async def soft_delete_last(self, user_id: int) -> Transaction | None: ...

    async def summarize_range(self, user_id: int, start_date: str, end_date: str) -> Summary: ...

    async def daily_totals(
        self, user_id: int, start_date: str, end_date: str
    ) -> list[DayTotal]: ...

    async def top_items(self, user_id: int, kind: str, limit: int = 10) -> list[ItemTotal]: ...

    # instance-wide (all users), for ops stats
    async def count_by_occurred_on(self, occurred_on: str) -> int: ...

    async def count_created_since(self, since_at: int) -> int: ...


class InboxRepository(Protocol):
    async def add_if_new(self, update_id: int, payload: bytes) -> bool: ...  # False if duplicate

    async def mark_processed(self, update_id: int) -> None: ...

    async def list_unprocessed(self) -> list[tuple[int, bytes]]: ...

    async def count_unprocessed(self) -> int: ...  # for ops stats

    async def delete_processed_older_than(self, before_at: int) -> int: ...  # returns rows deleted


class ParseFailureRepository(Protocol):
    async def add(self, user_id: int | None, raw_text: str, reason: str) -> ParseFailure: ...

    async def list_recent(self, limit: int = 50) -> list[ParseFailure]: ...

    async def count_since(self, since_at: int) -> int: ...  # for ops stats

    async def delete_older_than(self, before_at: int) -> int: ...  # returns rows deleted


class RateLimiterPort(Protocol):
    async def check_and_increment(
        self, user_id: int, bucket: str, limit: int, window_seconds: int
    ) -> bool: ...  # True if the call is allowed, False if the limit was hit


class UnitOfWork(Protocol):
    users: UserRepository
    transactions: TransactionRepository
    inbox: InboxRepository
    parse_failures: ParseFailureRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
