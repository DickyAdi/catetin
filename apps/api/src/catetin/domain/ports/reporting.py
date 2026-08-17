from typing import Protocol

from ..models import DayTotal, ItemTotal, Summary, Transaction


class ReportRendererPort(Protocol):
    """Renders a P/L report document (PDF in Phase 1) for a user."""

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
    ) -> bytes: ...
