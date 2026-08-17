"""High-signal non-business pattern detector (FRD FR-1).

Flags a segment as "mungkin bukan usaha" — heuristic metadata only. Never
rejects, never asks, never changes kind/amount. Word-boundary matching
(EC-8) so "dapet" does not flag "pendapatan".
"""

from __future__ import annotations

import re

PATTERNS: tuple[str, ...] = (
    "dapet duit",
    "dapet uang",
    "dapat duit",
    "dapat uang",
    "ketemu uang",
    "ketemu duit",
    "gajian",
    "gaji bulanan",
    "transferan",
    "transfer dari",
    "dari kakak",
    "dari ibu",
    "dari bapak",
    "dari anak",
    "kemenangan",
    "menang judi",
    "bonus",
    "rejeki",
    "rezeki",
    "hadiah",
    "thr",
    "angpao",
)

_HIGH_SIGNAL_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in PATTERNS) + r")\b", re.IGNORECASE
)


def is_high_signal(text: str) -> bool:
    """True if `text` contains a high-signal "possibly not business" pattern."""
    return _HIGH_SIGNAL_RE.search(text) is not None
