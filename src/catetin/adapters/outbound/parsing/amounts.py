"""Indonesian rupiah amount grammar.

Convention: `.` is a thousands separator, `,` is a decimal separator — the
opposite of English. A trailing multiplier (`rb`/`ribu`/`k`/`jt`/`juta`)
turns whichever separator precedes it into a decimal point instead, e.g.
`50.5rb` and `12,5rb` are both 50 500 / 12 500, not 50 500 000.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MULTIPLIERS: dict[str, int] = {
    "rb": 1_000,
    "ribu": 1_000,
    "k": 1_000,
    "jt": 1_000_000,
    "juta": 1_000_000,
}

# Rejected as a likely typo rather than a real amount.
MAX_PLAUSIBLE_AMOUNT = 1_000_000_000

_MULT_ALTS = "|".join(sorted(MULTIPLIERS, key=len, reverse=True))
_NUM = r"\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?"

# Two branches, not one optional prefix: a number glued to a preceding
# letter (e.g. the "5" in "barang5") must never match, but "Rp" is itself
# letters glued to the number it prefixes ("Rp50.000") and must. A single
# `\b` before the digits cannot distinguish those two cases, so the "Rp"
# branch skips the boundary check and the bare-number branch requires it.
_TOKEN_RE = re.compile(
    r"(?:\bRp\.?\s*(?P<num>" + _NUM + r")|\b(?P<num2>" + _NUM + r"))"
    r"\s*(?P<mult>" + _MULT_ALTS + r")?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AmountMatch:
    value: int
    start: int
    end: int
    raw: str

    def span(self) -> tuple[int, int]:
        return (self.start, self.end)


def find_amounts(text: str) -> list[AmountMatch]:
    """Find every amount-looking token in `text`, left to right."""
    results: list[AmountMatch] = []
    for m in _TOKEN_RE.finditer(text):
        num = m.group("num") or m.group("num2")
        value = _to_int(num, m.group("mult"))
        if value is None:
            continue
        results.append(AmountMatch(value=value, start=m.start(), end=m.end(), raw=m.group(0)))
    return results


def parse_amount(text: str) -> int | None:
    """Parse the first amount found in `text`; None if none is valid."""
    matches = find_amounts(text)
    return matches[0].value if matches else None


def _to_int(num: str, mult: str | None) -> int | None:
    multiplier = MULTIPLIERS.get(mult.lower(), 1) if mult else 1

    if multiplier > 1:
        # A multiplier suffix turns the separator in front of it into a
        # decimal point, regardless of whether it was written as '.' or ','.
        normalized = num.replace(",", ".")
        if normalized.count(".") > 1:
            return None
        try:
            base = float(normalized)
        except ValueError:
            return None
    else:
        # No multiplier: '.' is a thousands separator (ID convention); a
        # bare ',' here has no defined meaning, so reject it.
        if "," in num:
            return None
        base = float(num.replace(".", ""))

    if base <= 0:
        return None
    return round(base * multiplier)
