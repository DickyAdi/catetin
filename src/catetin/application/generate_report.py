"""GenerateReport — `/lapor`. The rate-limit check and the render call live
here, per Modules M3-M4. The rate limit is checked *first*: no summarize or
render work starts if the user is over budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain.errors import RateLimited
from ..domain.models import DayTotal, Summary
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


class GenerateReport:
    def __init__(
        self,
        uow: UnitOfWork,
        rate_limiter: RateLimiterPort,
        renderer: ReportRendererPort,
        max_per_user_hour: int = DEFAULT_MAX_PER_HOUR,
    ) -> None:
        self._uow = uow
        self._rate_limiter = rate_limiter
        self._renderer = renderer
        self._max_per_user_hour = max_per_user_hour

    async def execute(
        self, user_id: int, start: date, end: date, period_label: str = "Laporan"
    ) -> ReportResult:
        allowed = await self._rate_limiter.check_and_increment(
            user_id, PDF_BUCKET, self._max_per_user_hour, RATE_LIMIT_WINDOW_SECONDS
        )
        if not allowed:
            raise RateLimited(
                f"user {user_id} exceeded {self._max_per_user_hour} PDF reports/hour"
            )

        async with self._uow as uow:
            user = await uow.users.get_by_id(user_id)
            summary = await uow.transactions.summarize_range(
                user_id, start.isoformat(), end.isoformat()
            )
            day_totals = await uow.transactions.daily_totals(
                user_id, start.isoformat(), end.isoformat()
            )
            item_totals = await uow.transactions.top_items(
                user_id, "sale", limit=TOP_ITEMS_LIMIT
            )

        business_name = user.business_name if user else None
        pdf_bytes = await self._renderer.render_pdf(
            user_id, summary, day_totals, item_totals, business_name, period_label
        )
        return ReportResult(pdf_bytes=pdf_bytes, summary=summary, day_totals=day_totals)
