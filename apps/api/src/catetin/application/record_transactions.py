"""RecordTransactions — parse -> validate -> batch-commit -> confirm.

The path behind every non-command text message (US-01..03, US-08). Per the
Modules M3-M4 doc: a batch of N segments is not all-or-nothing, but the
valid subset *is* one DB transaction — the `batch_add()` below and the final
`daily_totals`/`summarize_range` read happen inside a single `async with
self._uow` block, committed once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain.models import ParsedTransaction, Summary, Transaction
from ..domain.ports.observability import ObservabilityPort
from ..domain.ports.parser import ParserPort
from ..domain.ports.repositories import UnitOfWork


@dataclass(frozen=True, slots=True)
class RecordIssue:
    """A segment that was not recorded — either unparseable or ambiguous.

    `reason` is one of the parser's failure reasons (`no_amount`,
    `too_many_segments`, `amount_too_large`, `no_item`) or `ambiguous_kind`
    for a segment whose sale/expense kind could not be inferred (US-08) and
    that needs a `MessagingPort.ask_choice` round trip before it can be
    recorded.
    """

    raw_text: str
    reason: str


@dataclass(frozen=True, slots=True)
class RecordResult:
    recorded: list[Transaction]
    issues: list[RecordIssue]
    ambiguous: list[ParsedTransaction]
    today_total: Summary


class RecordTransactions:
    def __init__(
        self,
        parser: ParserPort,
        uow: UnitOfWork,
        observability: ObservabilityPort | None = None,
    ) -> None:
        self._parser = parser
        self._uow = uow
        # Optional so callers that don't care about telemetry (most tests)
        # stay a two-argument construction. `composition.wire()` always
        # passes an adapter — the null one unless configured otherwise.
        self._obs = observability

    async def execute(
        self, user_id: int, raw_text: str, today: date, *, slang_enabled: bool = True
    ) -> RecordResult:
        outcome = self._parser.parse_detailed(raw_text, today=today, slang_enabled=slang_enabled)

        resolvable = [p for p in outcome.parsed if p.kind is not None]
        ambiguous = [p for p in outcome.parsed if p.kind is None]

        issues = [RecordIssue(raw_text=f.raw_text, reason=f.reason) for f in outcome.failures]
        issues.extend(
            RecordIssue(raw_text=p.raw_text, reason="ambiguous_kind") for p in ambiguous
        )

        today_str = today.isoformat()
        async with self._uow as uow:
            recorded = await uow.transactions.batch_add(user_id, resolvable)
            for issue in issues:
                await uow.parse_failures.add(user_id, issue.raw_text, issue.reason)
            today_total = await uow.transactions.summarize_range(user_id, today_str, today_str)
            await uow.commit()

        # Telemetry after the commit, never inside the transaction — a slow
        # collector must not hold the writer connection (pool_size=1) open.
        if self._obs is not None and issues:
            for issue in issues:
                await self._obs.log_event(
                    "warning",
                    "parse_failed",
                    user_id=user_id,
                    reason=issue.reason,
                    segment=issue.raw_text,
                )
            await self._obs.record_metric(
                "parse_failure_total", float(len(issues)), {"source": "record_transactions"}
            )

        return RecordResult(
            recorded=recorded, issues=issues, ambiguous=ambiguous, today_total=today_total
        )

    async def confirm(
        self, user_id: int, parsed: ParsedTransaction, *, excluded_from_report: bool = False
    ) -> Transaction:
        """Persist a single segment whose kind was ambiguous, now that the user
        has picked sale/expense via `MessagingPort.ask_choice` (US-08). Also used
        for "Bukan Usaha" (FR-3): `excluded_from_report=True` records the
        transaction (audit completeness) but keeps it out of reports."""
        async with self._uow as uow:
            tx = await uow.transactions.add(
                user_id, parsed, excluded_from_report=excluded_from_report
            )
            await uow.commit()
            return tx
