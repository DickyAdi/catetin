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
    def __init__(self, parser: ParserPort, uow: UnitOfWork) -> None:
        self._parser = parser
        self._uow = uow

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

        return RecordResult(
            recorded=recorded, issues=issues, ambiguous=ambiguous, today_total=today_total
        )

    async def confirm(self, user_id: int, parsed: ParsedTransaction) -> Transaction:
        """Persist a single segment whose kind was ambiguous, now that the user
        has picked sale/expense via `MessagingPort.ask_choice` (US-08)."""
        async with self._uow as uow:
            tx = await uow.transactions.add(user_id, parsed)
            await uow.commit()
            return tx
