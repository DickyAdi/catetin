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

import orjson

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


def _payload_sender_id(payload: bytes) -> str | None:
    """Telegram user id inside a stored update, mirroring the real inbox
    repository's payload sniffing."""
    try:
        update = orjson.loads(payload)
    except orjson.JSONDecodeError:
        return None
    if not isinstance(update, dict):
        return None
    for key in ("message", "edited_message", "callback_query"):
        envelope = update.get(key)
        if isinstance(envelope, dict):
            sender = envelope.get("from")
            if isinstance(sender, dict) and sender.get("id") is not None:
                return str(sender["id"])
    return None


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

    async def set_business_name(self, user_id: int, name: str) -> User:
        updated = self._users[user_id].model_copy(update={"business_name": name})
        self._users[user_id] = updated
        return updated

    async def set_onboarded(self, user_id: int) -> User:
        updated = self._users[user_id].model_copy(update={"has_onboarded": True})
        self._users[user_id] = updated
        return updated

    async def mark_blocked(self, user_id: int) -> User:
        updated = self._users[user_id].model_copy(
            update={"blocked_at": int(self._clock.now().timestamp())}
        )
        self._users[user_id] = updated
        return updated

    async def hard_delete(self, user_id: int) -> int:
        return 1 if self._users.pop(user_id, None) is not None else 0

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

    async def add(
        self, user_id: int, parsed: ParsedTransaction, *, excluded_from_report: bool = False
    ) -> Transaction:
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
            flagged=parsed.flagged,
            excluded_from_report=excluded_from_report,
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

    def _reportable(self, user_id: int) -> list[Transaction]:
        return [t for t in self._live(user_id) if not t.excluded_from_report]

    async def summarize_range(self, user_id: int, start_date: str, end_date: str) -> Summary:
        income = expense = count = 0
        for t in self._reportable(user_id):
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
        for t in self._reportable(user_id):
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
        for t in self._reportable(user_id):
            if t.kind == kind:
                totals[t.item] = totals.get(t.item, 0) + t.total_amount
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        return [ItemTotal(item=item, kind=kind, total=total) for item, total in ranked[:limit]]

    async def list_flagged(
        self, user_id: int, start_date: str, end_date: str
    ) -> list[Transaction]:
        rows = [
            t
            for t in self._live(user_id)
            if t.flagged and not t.excluded_from_report and start_date <= t.occurred_on <= end_date
        ]
        return sorted(rows, key=lambda t: t.occurred_at)

    async def exclude_flagged(self, user_id: int, start_date: str, end_date: str) -> int:
        count = 0
        for i, t in enumerate(self._rows):
            if (
                t.user_id == user_id
                and t.deleted_at is None
                and t.flagged
                and not t.excluded_from_report
                and start_date <= t.occurred_on <= end_date
            ):
                self._rows[i] = t.model_copy(update={"excluded_from_report": True})
                count += 1
        return count

    async def list_in_period(
        self, user_id: int, start_date: str, end_date: str
    ) -> list[Transaction]:
        rows = [
            t
            for t in self._rows
            if t.user_id == user_id
            and not t.excluded_from_report
            and start_date <= t.occurred_on <= end_date
        ]
        return sorted(rows, key=lambda t: t.occurred_at)

    async def count_for_user(self, user_id: int) -> int:
        return sum(1 for t in self._rows if t.user_id == user_id)

    async def purge_user(self, user_id: int) -> int:
        # `self._rows`, not `self._live(...)` — mirrors the real repository's
        # Core delete, which erases soft-deleted rows too.
        doomed = [t for t in self._rows if t.user_id == user_id]
        for t in doomed:
            self._rows.remove(t)
        return len(doomed)

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

    async def purge_user(self, user_id: int, platform_user_id: str) -> int:
        # Same shape as the real repository: `inbox` has no `user_id` column,
        # so ownership is read out of the stored webhook payload.
        doomed = [
            update_id
            for update_id, (payload, _) in self._rows.items()
            if _payload_sender_id(payload) == platform_user_id
        ]
        for update_id in doomed:
            del self._rows[update_id]
        return len(doomed)


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

    async def purge_user(self, user_id: int) -> int:
        doomed = [f for f in self._rows if f.user_id == user_id]
        for f in doomed:
            self._rows.remove(f)
        return len(doomed)


class FakeRateLimitRepository:
    """The purge-only `rate_limits` view on the UnitOfWork (not the limiter)."""

    def __init__(self, rows: dict[tuple[int, str], int]) -> None:
        self._rows = rows

    async def purge_user(self, user_id: int) -> int:
        doomed = [key for key in self._rows if key[0] == user_id]
        for key in doomed:
            del self._rows[key]
        return len(doomed)


class FakeDeletionLogRepository:
    def __init__(self, rows: list[tuple[str, int, int]]) -> None:
        self._rows = rows

    async def add(self, platform: str, rows_deleted: int, deleted_at: int) -> None:
        self._rows.append((platform, rows_deleted, deleted_at))

    async def count_total(self) -> int:
        return len(self._rows)


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
        # (user_id, action) -> count, mirroring the real table's composite PK.
        self._rate_limits: dict[tuple[int, str], int] = {}
        # (platform, rows_deleted, deleted_at) — no user id, like the real table.
        self._deletion_log: list[tuple[str, int, int]] = []

    async def __aenter__(self) -> Self:
        self.users = FakeUserRepository(self._clock, self._users)
        self.transactions = FakeTransactionRepository(self._clock, self._transactions)
        self.inbox = FakeInboxRepository(self._clock, self._inbox)
        self.parse_failures = FakeParseFailureRepository(self._clock, self._parse_failures)
        self.rate_limits = FakeRateLimitRepository(self._rate_limits)
        self.deletion_log = FakeDeletionLogRepository(self._deletion_log)
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
        self.last_business_name: str | None = None
        self.last_period_label: str | None = None
        self.last_item_totals: list[ItemTotal] | None = None
        self.last_expense_item_totals: list[ItemTotal] | None = None
        self.last_transactions: list[Transaction] | None = None
        self.last_timezone: str | None = None

    async def render_pdf(
        self,
        user_id: int,
        summary: Summary,
        day_totals: list[DayTotal],
        sale_item_totals: list[ItemTotal],
        expense_item_totals: list[ItemTotal],
        transactions: list[Transaction],
        business_name: str | None,
        period_label: str,
        timezone: str,
    ) -> bytes:
        self.calls += 1
        self.last_business_name = business_name
        self.last_period_label = period_label
        self.last_timezone = timezone
        self.last_item_totals = sale_item_totals
        self.last_expense_item_totals = expense_item_totals
        self.last_transactions = transactions
        return self._pdf_bytes
