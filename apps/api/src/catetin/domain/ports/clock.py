from datetime import date, datetime
from typing import Protocol


class ClockPort(Protocol):
    """The single source of "now" and user-local dates.

    Injectable so scheduler fire-times and occurred_on resolution are
    testable against a frozen clock rather than the real wall clock.
    """

    def now(self) -> datetime: ...  # tz-aware, UTC

    def today_local(self, tz: str) -> date: ...  # user-local calendar date

    def parse_local_date(self, text: str, tz: str) -> date | None: ...  # e.g. "kemarin" -> date
