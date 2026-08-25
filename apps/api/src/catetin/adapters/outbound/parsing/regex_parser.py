"""RegexParser — deterministic, rule-based ParserPort implementation.

No network, no model. Must stay well under the 2 ms/message budget, so it
runs inline in the event loop rather than via `asyncio.to_thread` (see
Async & Resource Design). Patterns handled, in the order components are
extracted (most specific structural signal first):

    verb-prefixed   "jual <item> <amount>" / "beli <item> <amount>"
    leading qty      "<qty> <unit> <item> <amount>"   e.g. "3 pcs ayam 50rb"
                     -> <amount> is the line total
    trailing qty     "<item> <qty> <unit> <amount>"   e.g. "ayam 5 ekor 10rb"
                     -> <amount> is the per-unit price, total = qty x amount
    slash qty        "<item> <amount>/<qty>"          e.g. "ayam 50rb/2"
                     -> <amount> is the line total, split across <qty>
    plain item+amt   "<item> <amount>"                the fallback
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from ....domain.models import FailedSegment, ParsedTransaction, ParseOutcome
from . import amounts, high_signal, lexicon, segmenter

Kind = Literal["sale", "expense"] | None

_ALL_VERBS = sorted(lexicon.SALE_VERBS | lexicon.EXPENSE_VERBS, key=len, reverse=True)
_VERB_RE = re.compile(r"^\s*(?P<verb>" + "|".join(_ALL_VERBS) + r")\b", re.IGNORECASE)

_UNIT_ALTS = "|".join(sorted(lexicon.UNITS, key=len, reverse=True))
_QTY_UNIT_RE = re.compile(
    r"\b(?P<qty>\d+)\s*(?:x\s*)?(?P<unit>" + _UNIT_ALTS + r")\b", re.IGNORECASE
)

_SLASH_QTY_RE = re.compile(r"/\s*(?P<qty>\d+)\s*$")
_WORD_RE = re.compile(r"[a-z]+")
_PUNCT_RE = re.compile(r"[/,;:@]+")
_WS_RE = re.compile(r"\s+")

_NO_NAME_ITEM = "(tanpa nama)"


class RegexParser:
    """ParserPort implementation: deterministic Indonesian free-text parsing."""

    async def parse(
        self, text: str, *, today: date, slang_enabled: bool = True
    ) -> list[ParsedTransaction]:
        return self.parse_detailed(text, today=today, slang_enabled=slang_enabled).parsed

    def parse_detailed(
        self, text: str, *, today: date, slang_enabled: bool = True
    ) -> ParseOutcome:
        seg_result = segmenter.segment(text)
        parsed: list[ParsedTransaction] = []
        failures: list[FailedSegment] = []

        if seg_result.truncated:
            failures.append(FailedSegment(raw_text=text[:500], reason="too_many_segments"))

        for raw_segment in seg_result.segments:
            outcome = _parse_segment(raw_segment, today)
            if isinstance(outcome, ParsedTransaction):
                parsed.append(outcome)
            else:
                failures.append(outcome)

        return ParseOutcome(parsed=parsed, failures=failures)


def _parse_segment(raw_segment: str, today: date) -> ParsedTransaction | FailedSegment:
    working = raw_segment.strip()
    if not working:
        return FailedSegment(raw_text=raw_segment[:500], reason="no_item")

    verb_match = _VERB_RE.match(working)
    verb = verb_match.group("verb").lower() if verb_match else None
    remainder = working[verb_match.end() :].strip() if verb_match else working

    qty = 1
    qty_match = _QTY_UNIT_RE.search(remainder)
    if qty_match:
        qty = int(qty_match.group("qty"))

    slash_match = _SLASH_QTY_RE.search(remainder)
    slash_qty = int(slash_match.group("qty")) if slash_match else None

    # Mask out the qty/unit and trailing-slash spans before hunting for the
    # amount, so a bare quantity digit (the "3" in "3 pcs") is never
    # mistaken for a second, ambiguous amount candidate.
    masked = list(remainder)
    for m in (qty_match, slash_match):
        if m is None:
            continue
        for i in range(m.start(), m.end()):
            masked[i] = " "
    search_text = "".join(masked)

    amount_matches = amounts.find_amounts(search_text)
    if not amount_matches:
        return FailedSegment(raw_text=raw_segment[:500], reason="no_amount")

    chosen = max(amount_matches, key=lambda m: m.value)
    ambiguous_amount = len(amount_matches) > 1
    total_amount = chosen.value

    # Where the quantity sits decides what the amount means:
    #
    #   "3 pcs ayam 50rb"      leading qty  -> shopping-list form, 50rb is
    #                                          already the line total
    #   "ayam 5 ekor 10rb"     trailing qty -> the amount follows a counted
    #                                          unit, so it is the per-unit
    #                                          price and the line total is
    #                                          qty x amount (5 x 10rb = 50rb)
    #
    # The slash form ("ayam 50rb/2") is explicitly "50rb split across 2" and
    # keeps its divide semantics, so it opts out.
    amount_is_per_unit = qty_match is not None and qty_match.start() > 0 and slash_qty is None
    if amount_is_per_unit and qty > 1:
        total_amount *= qty

    if total_amount > amounts.MAX_PLAUSIBLE_AMOUNT:
        return FailedSegment(raw_text=raw_segment[:500], reason="amount_too_large")

    if slash_qty:
        qty = slash_qty

    unit_amount = total_amount // qty if qty > 1 else None

    spans = [chosen.span()]
    if qty_match:
        spans.append(qty_match.span())
    if slash_match:
        spans.append(slash_match.span())

    item = _clean_item(_strip_spans(remainder, spans))
    if not item:
        item = _NO_NAME_ITEM

    kind = _classify_kind(verb, working)

    confidence = 1.0
    if kind is None:
        confidence -= 0.3
    if ambiguous_amount:
        confidence -= 0.2
    if item == _NO_NAME_ITEM:
        confidence -= 0.2
    confidence = max(0.0, min(1.0, confidence))

    return ParsedTransaction(
        kind=kind,
        item=item,
        qty=qty,
        unit_amount=unit_amount,
        total_amount=total_amount,
        occurred_on=today,
        confidence=confidence,
        raw_text=raw_segment[:500],
        flagged=high_signal.is_high_signal(raw_segment),
    )


def _classify_kind(verb: str | None, full_text: str) -> Kind:
    if verb in lexicon.SALE_VERBS:
        return "sale"
    if verb in lexicon.EXPENSE_VERBS:
        return "expense"

    words = set(_WORD_RE.findall(full_text.lower()))
    has_sale = bool(words & lexicon.SALE_VERBS)
    has_expense = bool(words & lexicon.EXPENSE_VERBS)
    if has_sale and not has_expense:
        return "sale"
    if has_expense and not has_sale:
        return "expense"
    return None


def _strip_spans(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in sorted(spans, reverse=True):
        del chars[start:end]
    return "".join(chars)


def _clean_item(text: str) -> str:
    cleaned = _PUNCT_RE.sub(" ", text)
    cleaned = _WS_RE.sub(" ", cleaned).strip(" -")
    cleaned = cleaned[:80]
    return cleaned.title() if cleaned else ""
