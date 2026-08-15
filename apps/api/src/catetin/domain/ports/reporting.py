from typing import Protocol

from ..models import DayTotal, ItemTotal, Summary


class ReportRendererPort(Protocol):
    """Renders a P/L report document (PDF in Phase 1) for a user."""

    async def render_pdf(
        self,
        user_id: int,
        summary: Summary,
        day_totals: list[DayTotal],
        item_totals: list[ItemTotal],
        business_name: str | None,
        period_label: str,
    ) -> bytes: ...
