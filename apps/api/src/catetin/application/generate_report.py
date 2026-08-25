"""GenerateReport — `/lapor`. The rate-limit check and the render call live
here, per Modules M3-M4.

FR-2 (Report V1 — review gate): before rendering, `execute()` checks for
flagged-but-not-yet-excluded transactions in the period. If any exist, it
returns a `PendingReview` instead of rendering — the caller (Telegram
handler) shows the user a review-gate message and calls `render()` once the
user has decided (optionally after `exclude_flagged()`). The rate limit is
checked once, in `execute()`, *before* the review gate — `render()` itself
never re-checks it, since a review-gate round trip is one logical `/lapor`
request, not two.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain.errors import RateLimited
from ..domain.models import DayTotal, Summary, Transaction
from ..domain.ports.observability import ObservabilityPort
from ..domain.ports.reporting import ReportRendererPort
from ..domain.ports.repositories import RateLimiterPort, UnitOfWork

PDF_BUCKET = "pdf"
RATE_LIMIT_WINDOW_SECONDS = 3600
DEFAULT_MAX_PER_HOUR = 5
TOP_ITEMS_LIMIT = 5


@dataclass(frozen=True, slots=True)
class ReportResult:
    pdf_bytes: bytes
    summary: Summary
    day_totals: list[DayTotal]


@dataclass(frozen=True, slots=True)
class PendingReview:
    """Returned instead of a `ReportResult` when the period has flagged,
    not-yet-excluded transactions — the report is held until the user
    decides to keep or exclude them (FR-2)."""

    summary: Summary
    flagged_items: list[Transaction]
    start: date
    end: date
    period_label: str


class GenerateReport:
    def __init__(
        self,
        uow: UnitOfWork,
        rate_limiter: RateLimiterPort,
        renderer: ReportRendererPort,
        max_per_user_hour: int = DEFAULT_MAX_PER_HOUR,
        observability: ObservabilityPort | None = None,
    ) -> None:
        self._uow = uow
        self._rate_limiter = rate_limiter
        self._renderer = renderer
        self._max_per_user_hour = max_per_user_hour
        # See RecordTransactions for why this is optional rather than required.
        self._obs = observability

    async def execute(
        self, user_id: int, start: date, end: date, period_label: str = "Laporan"
    ) -> ReportResult | PendingReview:
        allowed = await self._rate_limiter.check_and_increment(
            user_id, PDF_BUCKET, self._max_per_user_hour, RATE_LIMIT_WINDOW_SECONDS
        )
        if not allowed:
            raise RateLimited(
                f"user {user_id} exceeded {self._max_per_user_hour} PDF reports/hour"
            )

        async with self._uow as uow:
            flagged = await uow.transactions.list_flagged(
                user_id, start.isoformat(), end.isoformat()
            )
            if flagged:
                summary = await uow.transactions.summarize_range(
                    user_id, start.isoformat(), end.isoformat()
                )
                return PendingReview(
                    summary=summary,
                    flagged_items=flagged,
                    start=start,
                    end=end,
                    period_label=period_label,
                )

        return await self.render(user_id, start, end, period_label)

    async def exclude_flagged(self, user_id: int, start: date, end: date) -> int:
        """"Keluarkan dari laporan" (FR-2): bulk-exclude all flagged, not-yet-
        excluded transactions in the period. Returns the number excluded."""
        async with self._uow as uow:
            count = await uow.transactions.exclude_flagged(
                user_id, start.isoformat(), end.isoformat()
            )
            await uow.commit()
            return count

    async def render(
        self, user_id: int, start: date, end: date, period_label: str = "Laporan"
    ) -> ReportResult:
        """Renders unconditionally — no rate limit check, no review gate.
        Used for periods with nothing flagged, and after the user has
        resolved a review gate (whether by excluding or keeping)."""
        try:
            async with self._uow as uow:
                user = await uow.users.get_by_id(user_id)
                summary = await uow.transactions.summarize_range(
                    user_id, start.isoformat(), end.isoformat()
                )
                day_totals = await uow.transactions.daily_totals(
                    user_id, start.isoformat(), end.isoformat()
                )
                sale_item_totals = await uow.transactions.top_items(
                    user_id, "sale", limit=TOP_ITEMS_LIMIT
                )
                expense_item_totals = await uow.transactions.top_items(
                    user_id, "expense", limit=TOP_ITEMS_LIMIT
                )
                transactions = await uow.transactions.list_in_period(
                    user_id, start.isoformat(), end.isoformat()
                )

            business_name = user.business_name if user else None
            pdf_bytes = await self._renderer.render_pdf(
                user_id,
                summary,
                day_totals,
                sale_item_totals,
                expense_item_totals,
                transactions,
                business_name,
                period_label,
            )
        except Exception as exc:
            # PDF rendering is the most failure-prone thing this app does
            # (fpdf2, fonts, unbounded row counts) and the user only ever
            # sees a generic apology — so the detail has to leave here.
            if self._obs is not None:
                await self._obs.log_exception(
                    exc,
                    {
                        "use_case": "generate_report",
                        "user_id": user_id,
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "period_label": period_label,
                    },
                )
            raise

        if self._obs is not None:
            await self._obs.log_event(
                "info",
                "report_generated",
                user_id=user_id,
                period_label=period_label,
                start=start.isoformat(),
                end=end.isoformat(),
                pdf_bytes=len(pdf_bytes),
                transactions=summary.count,
            )
        return ReportResult(pdf_bytes=pdf_bytes, summary=summary, day_totals=day_totals)
