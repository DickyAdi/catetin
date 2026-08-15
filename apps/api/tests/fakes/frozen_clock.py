from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


class FrozenClock:
    """Test double for ClockPort — the wall clock only moves when told to."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def today_local(self, tz: str) -> date:
        return self._now.astimezone(ZoneInfo(tz)).date()

    def parse_local_date(self, text: str, tz: str) -> date | None:
        return None

    def advance(self, **kwargs: float) -> None:
        self._now += timedelta(**kwargs)
