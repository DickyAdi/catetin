"""In-memory doubles for the repository ports and UnitOfWork.

Same shape as `SqlAlchemyUnitOfWork` and its repositories, minus SQLAlchemy:
every `async with FakeUnitOfWork(...)` block hands out fresh repository
wrappers that read/write the same shared in-memory store, mirroring how real
sessions all point at one database file. There is no rollback-on-exception
here — the real atomicity guarantees are already covered by
`tests/integration/test_repositories.py` against a real SQLite database.
"""

from __future__ import annotations

from types import TracebackType
from typing import Self, cast

from catetin.domain.errors import DomainValidationError
from catetin.domain.models import (
    DayTotal,
    ItemTotal,
    ParsedTransaction,
    ParseFailure,
    Summary,
    Transaction,
    User,
)
from catetin.domain.ports.clock import ClockPort


class FakeUserRepository:
    def __init__(self, clock: ClockPort, users: dict[int, User]) -> None:
        self._clock = clock
        self._users = users

    def _next_id(self) -> int:
        return max(self._users, default=0) + 1

    async def get_by_id(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    async def get_by_platform_identity(
        self, platform: str, platform_user_id: str
    ) -> User | None:
        for user in self._users.values():
            if user.platform == platform and user.platform_user_id == platform_user_id:
                return user
        return None

    async def create(
        self, platform: str, platform_user_id: str, display_name: str | None = None
    ) -> User:
        now = int(self._clock.now().timestamp())
        user = User(
            id=self._next_id(),
            platform=cast('str', platform),  # type: ignore[arg-type]
            platform_user_id=platform_user_id,
            display_name=display_name,
            created_at=now,
            updated_at=now,
        )
        self._users[user.id] = user
        return user

    async def set_digest_enabled(self, user_id: int, enabled: bool) -> User:
        updated = self._users[user_id].model_copy(update={"digest_enabled": enabled})
        self._users[user_id] = updated
        return updated

    async def set_timezone(self, user_id: int, tz: str) -> User:
        updated = self._users[user_id].model_copy(update={"timezone": tz})
        self._users[user_id] = updated
        return updated

    async def mark_blocked(self, user_id: int) -> User:
        updated = self._users[user_id].model_copy(
            update={"blocked_at": int(self._clock.now().timestamp())}
        )
        self._users[user_id] = updated
        return updated

    async def count_total(self) -> int:
        return len(self._users)

    async def list_digest_enabled(self) -> list[User]:
        return [
            u for u in self._users.values() if u.digest_enabled and u.blocked_at is None
        ]


class FakeTransactionRepository:
    def __init__(self, clock: ClockPort, rows: list[Transaction]) -> None:
        self._clock = clock
        self._rows = rows

    def _next_id(self) -> int:
        return max((t.id for t in self._rows), default=0) + 1

    def _live(self, user_id: int) -> list[Transaction]:
        return [t for t in self._rows if t.user_id == user_id and t.deleted_at is None]

    async def add(self, user_id: int, parsed: ParsedTransaction) -> Transaction:
        if parsed.kind is None:
            raise DomainValidationError(
                "cannot persist a ParsedTransaction with an ambiguous kind"
            )
        now = int(self._clock.now().timestamp())
        tx = Transaction(
            id=self._next_id(),
            user_id=user_id,
            kind=parsed.kind,
            item=parsed.item,
            qty=parsed.qty,
            unit_amount=parsed.unit_amount,
            total_amount=parsed.total_amount,
            occurred_on=parsed.occurred_on.isoformat(),
            occurred_at=now,
            confidence=parsed.confidence,
            raw_text=parsed.raw_text,
            created_at=now,
        )
        self._rows.append(tx)
        return tx

    async def batch_add(
        self, user_id: int, parsed: list[ParsedTransaction]
    ) -> list[Transaction]:
        return [await self.add(user_id, p) for p in parsed]

    async def get(self, user_id: int, transaction_id: int) -> Transaction | None:
        for t in self._live(user_id):
            if t.id == transaction_id:
                return t
        return None

    async def list_recent(self, user_id: int, limit: int = 20) -> list[Transaction]:
        rows = sorted(self._live(user_id), key=lambda t: (t.created_at, t.id), reverse=True)
        return rows[:limit]

    async def soft_delete_last(self, user_id: int) -> Transaction | None:
        rows = sorted(self._live(user_id), key=lambda t: (t.created_at, t.id), reverse=True)
        if not rows:
            return None
        target = rows[0]
        idx = self._rows.index(target)
        updated = target.model_copy(update={"deleted_at": int(self._clock.now().timestamp())})
        self._rows[idx] = updated
        return updated

    async def summarize_range(self, user_id: int, start_date: str, end_date: str) -> Summary:
        income = expense = count = 0
        for t in self._live(user_id):
            if start_date <= t.occurred_on <= end_date:
                count += 1
                if t.kind == "sale":
                    income += t.total_amount
                else:
                    expense += t.total_amount
        return Summary(income=income, expense=expense, profit=income - expense, count=count)

    async def daily_totals(
        self, user_id: int, start_date: str, end_date: str
    ) -> list[DayTotal]:
        totals: dict[str, list[int]] = {}
        for t in self._live(user_id):
            if start_date <= t.occurred_on <= end_date:
                bucket = totals.setdefault(t.occurred_on, [0, 0])
                if t.kind == "sale":
                    bucket[0] += t.total_amount
                else:
                    bucket[1] += t.total_amount
        return [
            DayTotal(date=day, income=inc, expense=exp, profit=inc - exp)
            for day, (inc, exp) in sorted(totals.items())
        ]

    async def top_items(self, user_id: int, kind: str, limit: int = 10) -> list[ItemTotal]:
        totals: dict[str, int] = {}
        for t in self._live(user_id):
            if t.kind == kind:
                totals[t.item] = totals.get(t.item, 0) + t.total_amount
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        return [ItemTotal(item=item, kind=kind, total=total) for item, total in ranked[:limit]]

    async def count_by_occurred_on(self, occurred_on: str) -> int:
        return sum(
            1
            for t in self._rows
            if t.occurred_on == occurred_on and t.deleted_at is None
        )

    async def count_created_since(self, since_at: int) -> int:
        return sum(1 for t in self._rows if t.created_at >= since_at and t.deleted_at is None)


class FakeInboxRepository:
    def __init__(self, clock: ClockPort, rows: dict[int, tuple[bytes, int | None]]) -> None:
        self._clock = clock
        self._rows = rows

    async def add_if_new(self, update_id: int, payload: bytes) -> bool:
        if update_id in self._rows:
            return False
        self._rows[update_id] = (payload, None)
        return True

    async def mark_processed(self, update_id: int) -> None:
        if update_id in self._rows:
            payload, _ = self._rows[update_id]
            self._rows[update_id] = (payload, int(self._clock.now().timestamp()))

    async def list_unprocessed(self) -> list[tuple[int, bytes]]:
        return [
            (update_id, payload)
            for update_id, (payload, processed_at) in self._rows.items()
            if processed_at is None
        ]

    async def count_unprocessed(self) -> int:
        return sum(1 for _, processed_at in self._rows.values() if processed_at is None)

    async def delete_processed_older_than(self, before_at: int) -> int:
        stale = [
            update_id
            for update_id, (_, processed_at) in self._rows.items()
            if processed_at is not None and processed_at < before_at
        ]
        for update_id in stale:
            del self._rows[update_id]
        return len(stale)


class FakeParseFailureRepository:
    def __init__(self, clock: ClockPort, rows: list[ParseFailure]) -> None:
        self._clock = clock
        self._rows = rows

    def _next_id(self) -> int:
        return max((f.id or 0 for f in self._rows), default=0) + 1

    async def add(self, user_id: int | None, raw_text: str, reason: str) -> ParseFailure:
        failure = ParseFailure(
            id=self._next_id(),
            user_id=user_id,
            raw_text=raw_text,
            reason=reason,
            created_at=int(self._clock.now().timestamp()),
        )
        self._rows.append(failure)
        return failure

    async def list_recent(self, limit: int = 50) -> list[ParseFailure]:
        return sorted(self._rows, key=lambda f: f.created_at, reverse=True)[:limit]

    async def count_since(self, since_at: int) -> int:
        return sum(1 for f in self._rows if f.created_at >= since_at)

    async def delete_older_than(self, before_at: int) -> int:
        stale = [f for f in self._rows if f.created_at < before_at]
        for f in stale:
            self._rows.remove(f)
        return len(stale)


class FakeUnitOfWork:
    """Every `async with` re-enters against the same shared store, so calling
    `execute()` on two different use cases sharing one `FakeUnitOfWork`
    instance sees each other's writes — just like two sessions against the
    same SQLite file.
    """

    def __init__(self, clock: ClockPort) -> None:
        self._clock = clock
        self._users: dict[int, User] = {}
        self._transactions: list[Transaction] = []
        self._inbox: dict[int, tuple[bytes, int | None]] = {}
        self._parse_failures: list[ParseFailure] = []

    async def __aenter__(self) -> Self:
        self.users = FakeUserRepository(self._clock, self._users)
        self.transactions = FakeTransactionRepository(self._clock, self._transactions)
        self.inbox = FakeInboxRepository(self._clock, self._inbox)
        self.parse_failures = FakeParseFailureRepository(self._clock, self._parse_failures)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakeRateLimiter:
    """Fixed-window counter, mirroring `SqliteRateLimiter`'s bucketing."""

    def __init__(self) -> None:
        self._counts: dict[tuple[int, str], int] = {}

    async def check_and_increment(
        self, user_id: int, bucket: str, limit: int, window_seconds: int
    ) -> bool:
        key = (user_id, bucket)
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        return count <= limit


class FakeReportRenderer:
    def __init__(self, pdf_bytes: bytes = b"%PDF-fake%") -> None:
        self._pdf_bytes = pdf_bytes
        self.calls = 0

    async def render_pdf(
        self, user_id: int, summary: Summary, day_totals: list[DayTotal]
    ) -> bytes:
        self.calls += 1
        return self._pdf_bytes
