from datetime import date
from typing import Protocol

from ..models import ParsedTransaction


class ParserPort(Protocol):
    """Turns raw user text into zero or more parsed transactions.

    `today` is resolved by the caller from ClockPort in the user's timezone —
    the parser never calls `date.today()` itself, which keeps date extraction
    deterministic under test.
    """

    async def parse(
        self, text: str, *, today: date, slang_enabled: bool = True
    ) -> list[ParsedTransaction]: ...
