from typing import Protocol

from ..models import DayTotal, Summary


class ReportRendererPort(Protocol):
    """Renders a P/L report document (PDF in Phase 1) for a user."""

    async def render_pdf(
        self, user_id: int, summary: Summary, day_totals: list[DayTotal]
    ) -> bytes: ...
