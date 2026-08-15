"""Summarize — `/hariini` and `/minggu`. Aggregation happens in SQL via
`TransactionRepository`, never in Python.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..domain.models import DayTotal, Summary
from ..domain.ports.repositories import UnitOfWork

WEEK_DAYS = 7


class Summarize:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def today(self, user_id: int, today: date) -> Summary:
        return await self.range(user_id, today, today)

    async def range(self, user_id: int, start: date, end: date) -> Summary:
        async with self._uow as uow:
            return await uow.transactions.summarize_range(
                user_id, start.isoformat(), end.isoformat()
            )

    async def week(self, user_id: int, today: date) -> list[DayTotal]:
        start = today - timedelta(days=WEEK_DAYS - 1)
        async with self._uow as uow:
            return await uow.transactions.daily_totals(
                user_id, start.isoformat(), today.isoformat()
            )
