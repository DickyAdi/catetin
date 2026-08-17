"""FR-1 flag heuristic tests — pattern detection, word-boundary (EC-8),
per-segment flagging, and that flagging never changes kind/amount/parsing.
"""

from datetime import date

import pytest

from catetin.adapters.outbound.parsing import high_signal
from catetin.adapters.outbound.parsing.regex_parser import RegexParser
from catetin.domain.ports.parser import ParserPort

TODAY = date(2026, 8, 15)


@pytest.fixture
def parser() -> ParserPort:
    return RegexParser()


# --- high_signal.is_high_signal — pure pattern matching ---------------------


@pytest.mark.parametrize(
    "text",
    [
        "dapet duit 50k di jalan",
        "dapet uang di jalan",
        "ketemu uang 20rb",
        "ketemu duit di parkiran",
        "gajian 2jt",
        "gaji bulanan masuk",
        "transferan dari kakak 100rb",
        "transfer dari teman",
        "dari kakak 50rb",
        "dari ibu buat jajan",
        "dari bapak 100rb",
        "dari anak 20rb",
        "kemenangan judi 500rb",
        "menang judi tadi malam",
        "bonus kerjaan 1jt",
        "rejeki nomplok 200rb",
        "rezeki hari ini 50rb",
        "hadiah ulang tahun 100rb",
        "THR lebaran 500rb",
        "angpao imlek 200rb",
    ],
)
def test_high_signal_patterns_detected(text: str) -> None:
    assert high_signal.is_high_signal(text) is True


def test_high_signal_case_insensitive() -> None:
    assert high_signal.is_high_signal("DAPET DUIT 50K DI JALAN") is True
    assert high_signal.is_high_signal("Gajian 2Jt") is True


@pytest.mark.parametrize(
    "text",
    [
        "jual ayam geprek 50rb",
        "beli tepung 20rb",
        "bayar listrik 350rb",
        "pendapatan 50rb",  # EC-8: "dapet" must not flag inside "pendapatan"
        "pendapatan usaha bulan ini 500rb",
    ],
)
def test_high_signal_not_flagged_for_business_text(text: str) -> None:
    assert high_signal.is_high_signal(text) is False


def test_high_signal_word_boundary_does_not_match_substring() -> None:
    """EC-8: "pendapatan" contains no boundary-delimited pattern — it must
    not be treated the same as the colloquial "dapet duit"/"dapet uang"."""
    assert high_signal.is_high_signal("pendapatan") is False
    assert high_signal.is_high_signal("pendapatan duit") is False


# --- RegexParser integration — flagged is metadata, never changes parsing --


async def test_dapet_duit_parses_as_sale_and_is_flagged(parser: ParserPort) -> None:
    result = await parser.parse("dapet duit 50k di jalan", today=TODAY)

    assert len(result) == 1
    tx = result[0]
    assert tx.kind == "sale"
    assert tx.total_amount == 50_000
    assert tx.flagged is True


async def test_jual_ayam_is_not_flagged(parser: ParserPort) -> None:
    result = await parser.parse("jual ayam 50rb", today=TODAY)

    assert len(result) == 1
    assert result[0].flagged is False


async def test_pendapatan_is_not_flagged(parser: ParserPort) -> None:
    result = await parser.parse("pendapatan 50rb", today=TODAY)

    assert len(result) == 1
    assert result[0].flagged is False


async def test_multi_segment_flags_only_the_matching_segment(parser: ParserPort) -> None:
    result = await parser.parse(
        "beli tepung 20rb, dapet duit 10rb di jalan", today=TODAY
    )

    assert len(result) == 2
    by_item = {tx.item: tx for tx in result}
    assert by_item["Tepung"].flagged is False
    tepung_kind = by_item["Tepung"].kind
    duit_tx = next(tx for item, tx in by_item.items() if item != "Tepung")
    assert duit_tx.flagged is True
    assert tepung_kind == "expense"


async def test_flag_does_not_change_ambiguous_behavior(parser: ParserPort) -> None:
    """"gajian 2jt" has no sale/expense verb — kind stays ambiguous (None)
    regardless of the flag (FR-1: "Flag TIDAK mengubah perilaku ambiguous")."""
    result = await parser.parse("gajian 2jt", today=TODAY)

    assert len(result) == 1
    assert result[0].kind is None
    assert result[0].flagged is True
