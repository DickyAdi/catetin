"""FakeParser — ParserPort double with a scripted result, no regex needed."""

from __future__ import annotations

from datetime import date

from catetin.domain.models import ParsedTransaction, ParseOutcome


class FakeParser:
    def __init__(self) -> None:
        self.next_outcome = ParseOutcome(parsed=[], failures=[])
        self.calls: list[str] = []

    async def parse(
        self, text: str, *, today: date, slang_enabled: bool = True
    ) -> list[ParsedTransaction]:
        return self.parse_detailed(text, today=today, slang_enabled=slang_enabled).parsed

    def parse_detailed(
        self, text: str, *, today: date, slang_enabled: bool = True
    ) -> ParseOutcome:
        self.calls.append(text)
        return self.next_outcome
