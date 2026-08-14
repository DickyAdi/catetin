"""Splits a raw message into up to 20 independently-parsed segments."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import lexicon

MAX_SEGMENTS = 20

_KEYWORD_ALTS = "|".join(sorted(lexicon.SALE_VERBS | lexicon.EXPENSE_VERBS, key=len, reverse=True))

# A bare comma is ambiguous with the Indonesian decimal separator ("12,5rb"),
# so it only splits when followed by a sale/expense keyword — otherwise
# "12,5rb" would be sliced into two unparseable halves.
_SEPARATOR_RE = re.compile(
    r"\n+|\bdan\b|\bterus\b|\babis\b|,+(?=\s*(?:" + _KEYWORD_ALTS + r")\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    segments: list[str]
    truncated: bool  # True when the message held more than MAX_SEGMENTS


def segment(text: str) -> SegmentationResult:
    parts = [p.strip() for p in _SEPARATOR_RE.split(text)]
    parts = [p for p in parts if p]
    truncated = len(parts) > MAX_SEGMENTS
    return SegmentationResult(segments=parts[:MAX_SEGMENTS], truncated=truncated)
