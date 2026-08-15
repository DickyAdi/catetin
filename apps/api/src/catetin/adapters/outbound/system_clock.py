"""SystemClock -> ClockPort, backed by the real wall clock."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def today_local(self, tz: str) -> date:
        return self.now().astimezone(ZoneInfo(tz)).date()

    def parse_local_date(self, text: str, tz: str) -> date | None:
        return None
