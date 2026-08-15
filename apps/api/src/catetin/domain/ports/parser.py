from datetime import date
from typing import Protocol

from ..models import ParsedTransaction, ParseOutcome


class ParserPort(Protocol):
    """Turns raw user text into zero or more parsed transactions.

    `today` is resolved by the caller from ClockPort in the user's timezone —
    the parser never calls `date.today()` itself, which keeps date extraction
    deterministic under test.
    """

    async def parse(
        self, text: str, *, today: date, slang_enabled: bool = True
    ) -> list[ParsedTransaction]: ...

    def parse_detailed(
        self, text: str, *, today: date, slang_enabled: bool = True
    ) -> ParseOutcome:
        """Like `parse`, but also reports why segments were dropped.

        Synchronous and adapter-local by nature (regex parsing is inline in
        the event loop, never a thread hop — see Async & Resource Design) but
        promoted onto the port so `application/record_transactions.py` can
        depend on the port alone rather than importing `RegexParser` directly.
        """
        ...
