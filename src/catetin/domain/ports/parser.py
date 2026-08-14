from datetime import datetime
from typing import Protocol

from ..models import ParsedTransaction


class ParserPort(Protocol):
    """Turns raw user text into zero or more parsed transactions."""

    def parse(self, text: str, now: datetime) -> list[ParsedTransaction]: ...
