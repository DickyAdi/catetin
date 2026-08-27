from datetime import date

import pytest

from catetin.adapters.outbound.parsing.regex_parser import RegexParser
from catetin.domain.models import ParsedTransaction
from catetin.domain.ports.parser import ParserPort

TODAY = date(2026, 8, 15)


@pytest.fixture
def parser() -> ParserPort:
    return RegexParser()


# --- US-01/US-02: sale & expense, single segment ---------------------------


async def test_sale_with_explicit_verb(parser: ParserPort) -> None:
    result = await parser.parse("jual ayam geprek 50rb", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.kind == "sale"
    assert tx.item == "Ayam Geprek"
    assert tx.qty == 1
    assert tx.unit_amount is None
    assert tx.total_amount == 50_000
    assert tx.occurred_on == TODAY
    assert tx.confidence == 1.0


async def test_expense_with_explicit_verb(parser: ParserPort) -> None:
    result = await parser.parse("beli tepung 20rb", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.kind == "expense"
    assert tx.item == "Tepung"
    assert tx.total_amount == 20_000
    assert tx.confidence == 1.0


async def test_expense_noun_without_verb(parser: ParserPort) -> None:
    result = await parser.parse("bayar listrik 350.000", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.kind == "expense"
    assert tx.total_amount == 350_000


# --- US-03: multiple transactions in one message ---------------------------


async def test_multi_line_message(parser: ParserPort) -> None:
    result = await parser.parse("jual ayam 50rb\nbeli tepung 20rb", today=TODAY)

    assert len(result) == 2
    assert result[0].kind == "sale"
    assert result[0].total_amount == 50_000
    assert result[1].kind == "expense"
    assert result[1].total_amount == 20_000


async def test_comma_separated_segments_classified_independently(parser: ParserPort) -> None:
    result = await parser.parse("jual nasi goreng 25rb, beli gas 8rb", today=TODAY)

    assert len(result) == 2
    assert result[0].item == "Nasi Goreng"
    assert result[0].total_amount == 25_000
    assert result[1].item == "Gas"
    assert result[1].total_amount == 8_000
    assert result[1].kind == "expense"


async def test_dan_separator(parser: ParserPort) -> None:
    result = await parser.parse("jual es teh 5rb dan jual es jeruk 8rb", today=TODAY)

    assert len(result) == 2
    assert result[0].total_amount == 5_000
    assert result[1].total_amount == 8_000


# --- qty + unit --------------------------------------------------------


async def test_qty_and_unit(parser: ParserPort) -> None:
    result = await parser.parse("3 pcs ayam 50rb", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.item == "Ayam"
    assert tx.qty == 3
    assert tx.total_amount == 50_000
    assert tx.unit_amount == 16_666  # round down, total stays authoritative


async def test_trailing_qty_unit_treats_the_amount_as_a_unit_price(
    parser: ParserPort,
) -> None:
    """"jual ayam 5 ekor 10rb" — the quantity trails the item name and the
    amount follows a counted unit, so 10rb is the price of one ekor and the
    line total is 5 x 10rb. Contrast `test_qty_and_unit` above, where the
    leading "3 pcs" makes 50rb the whole line's total."""
    result = await parser.parse("jual ayam 5 ekor 10rb", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.kind == "sale"
    assert tx.item == "Ayam"
    assert tx.qty == 5
    assert tx.total_amount == 50_000
    assert tx.unit_amount == 10_000


async def test_trailing_qty_unit_without_a_verb(parser: ParserPort) -> None:
    result = await parser.parse("es teh 3 gelas 5rb", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.qty == 3
    assert tx.total_amount == 15_000
    assert tx.unit_amount == 5_000


async def test_trailing_qty_of_one_leaves_the_amount_alone(parser: ParserPort) -> None:
    result = await parser.parse("jual ayam 1 ekor 20rb", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.qty == 1
    assert tx.total_amount == 20_000
    assert tx.unit_amount is None


async def test_leading_qty_unit_after_a_verb_is_still_a_line_total(
    parser: ParserPort,
) -> None:
    """Regression guard for the trailing-qty rule: stripping the verb must not
    make a leading quantity look like a trailing one."""
    result = await parser.parse("beli 2 kg tepung 30rb", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.kind == "expense"
    assert tx.qty == 2
    assert tx.total_amount == 30_000
    assert tx.unit_amount == 15_000


# --- bare qty (the unit word left out) ---------------------------------


async def test_bare_qty_without_a_unit_word(parser: ParserPort) -> None:
    """QA round 2: "jual ayam 5 10rb" must mean the same as
    "jual ayam 5 ekor 10rb" — people drop the unit word, and before the fix
    the whole thing collapsed into one 10rb transaction named "Ayam 5"."""
    result = await parser.parse("jual ayam 5 10rb", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.kind == "sale"
    assert tx.item == "Ayam"
    assert tx.qty == 5
    assert tx.total_amount == 50_000
    assert tx.unit_amount == 10_000


@pytest.mark.parametrize(
    ("text", "qty", "total"),
    [
        ("jual nasi goreng 2 15rb", 2, 30_000),
        ("jual ayam 5x 10rb", 5, 50_000),
        ("jual es teh 100 3rb", 100, 300_000),
        ("jual ayam 3 15.000", 3, 45_000),
        ("jual ayam 2 Rp15.000", 2, 30_000),
    ],
)
async def test_bare_qty_variants(
    parser: ParserPort, text: str, qty: int, total: int
) -> None:
    result = await parser.parse(text, today=TODAY)

    assert len(result) == 1
    assert result[0].qty == qty
    assert result[0].total_amount == total


@pytest.mark.parametrize(
    ("text", "item", "total"),
    [
        # Only a *price*-looking second number counts, so a bare pair stays one
        # oddly-named item rather than becoming 50 x 60.
        ("jual ayam 50 60", "Ayam 50", 60),
        # The digits must start a token: "5.000" must never split into a qty
        # "5" (or, worse, a qty "000") plus an amount.
        ("jual ayam 5.000 10rb", "Ayam 5.000", 10_000),
        # A trailing count is not a leading one.
        ("jual pulsa 10rb 5", "Pulsa 5", 10_000),
        # "5 juta" is itself an amount, not a count followed by a price.
        ("bayar utang 5 juta", "Utang", 5_000_000),
    ],
)
async def test_bare_qty_does_not_misfire(
    parser: ParserPort, text: str, item: str, total: int
) -> None:
    result = await parser.parse(text, today=TODAY)

    assert len(result) == 1
    assert result[0].item == item
    assert result[0].qty == 1
    assert result[0].total_amount == total


async def test_qty_unit_form_wins_over_the_bare_form(parser: ParserPort) -> None:
    """The bare-qty rule is only consulted when no "<qty> <unit>" pair was
    found, so the leading-qty line-total semantics are untouched."""
    result = await parser.parse("3 pcs ayam 50rb", today=TODAY)

    assert len(result) == 1
    assert result[0].qty == 3
    assert result[0].total_amount == 50_000  # a line total, not 3 x 50rb


async def test_trailing_slash_qty(parser: ParserPort) -> None:
    result = await parser.parse("ayam 50rb/2", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.item == "Ayam"
    assert tx.qty == 2
    assert tx.total_amount == 50_000
    assert tx.unit_amount == 25_000


# --- amount grammar (rb/jt/ribu, decimals) ------------------------------


@pytest.mark.parametrize(
    ("text", "expected_total"),
    [
        ("jual baju 1jt", 1_000_000),
        ("jual baju 1.2jt", 1_200_000),
        ("jual baju 50 ribu", 50_000),
        ("jual baju 50.5rb", 50_500),
        ("jual baju 12,5rb", 12_500),
    ],
)
async def test_amount_grammar_variants(
    parser: ParserPort, text: str, expected_total: int
) -> None:
    result = await parser.parse(text, today=TODAY)

    assert len(result) == 1
    assert result[0].total_amount == expected_total


# --- ambiguous kind (US-08) ---------------------------------------------


async def test_ambiguous_kind_no_keyword(parser: ParserPort) -> None:
    result = await parser.parse("ayam 50rb", today=TODAY)

    assert len(result) == 1
    assert result[0].kind is None
    assert result[0].confidence < 1.0


async def test_empty_item_lowers_confidence(parser: ParserPort) -> None:
    result = await parser.parse("masuk 200rb", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.kind == "sale"
    assert tx.item == "(tanpa nama)"
    assert tx.confidence < 1.0


# --- unparseable / no amount ---------------------------------------------


async def test_no_amount_produces_no_transaction(parser: ParserPort) -> None:
    result = await parser.parse("laris manis hari ini", today=TODAY)

    assert result == []


def test_no_amount_reason_via_parse_detailed() -> None:
    outcome = RegexParser().parse_detailed("laris manis hari ini", today=TODAY)

    assert outcome.parsed == []
    assert len(outcome.failures) == 1
    assert outcome.failures[0].reason == "no_amount"


def test_amount_too_large_is_rejected() -> None:
    outcome = RegexParser().parse_detailed("jual tanah 2000000000", today=TODAY)

    assert outcome.parsed == []
    assert outcome.failures[0].reason == "amount_too_large"


# --- segment cap (>20 segments) -------------------------------------------


def test_too_many_segments_are_capped_and_flagged() -> None:
    text = ", ".join(f"jual barang{i} {i + 1}0rb" for i in range(25))

    outcome = RegexParser().parse_detailed(text, today=TODAY)

    assert len(outcome.parsed) == 20
    assert any(f.reason == "too_many_segments" for f in outcome.failures)


async def test_parse_respects_20_segment_cap(parser: ParserPort) -> None:
    text = ", ".join(f"jual barang{i} {i + 1}0rb" for i in range(25))

    result = await parser.parse(text, today=TODAY)

    assert len(result) == 20


# --- contract sanity -------------------------------------------------------


async def test_returns_frozen_pydantic_model(parser: ParserPort) -> None:
    result = await parser.parse("jual ayam 50rb", today=TODAY)

    assert isinstance(result[0], ParsedTransaction)
    with pytest.raises(Exception):  # noqa: B017 - frozen model, mutation must fail
        result[0].total_amount = 1
