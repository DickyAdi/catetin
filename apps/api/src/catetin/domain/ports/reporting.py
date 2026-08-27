from typing import Protocol

from ..models import DayTotal, ItemTotal, Summary, Transaction


class ReportRendererPort(Protocol):
    """Renders a P/L report document (PDF in Phase 1) for a user.

    `timezone` is the user's IANA zone. `occurred_on` reaches the renderer
    already user-local (it is denormalized that way at write time), but
    `occurred_at` is a UTC epoch, so the renderer needs the zone to print a
    clock time the user recognises.
    """

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
    ) -> bytes: ...
