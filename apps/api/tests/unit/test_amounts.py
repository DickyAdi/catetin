import pytest

from catetin.adapters.outbound.parsing.amounts import parse_amount

VALID_CASES = [
    ("50rb", 50_000),
    ("50 rb", 50_000),
    ("50k", 50_000),
    ("50 K", 50_000),
    ("50.000", 50_000),
    ("50000", 50_000),
    ("15.500", 15_500),
    ("50.5rb", 50_500),
    ("12,5rb", 12_500),
    ("1jt", 1_000_000),
    ("1.2jt", 1_200_000),
    ("2 juta", 2_000_000),
    ("Rp 50rb", 50_000),
    ("Rp50.000", 50_000),
    ("rp.50rb", 50_000),
    ("50 ribu", 50_000),
    ("1,5 juta", 1_500_000),
    ("1.234.567", 1_234_567),
]


@pytest.mark.parametrize(("raw", "expected"), VALID_CASES)
def test_parse_amount_valid(raw: str, expected: int) -> None:
    assert parse_amount(raw) == expected


INVALID_CASES = [
    "",
    "tidak ada angka",
    "0rb",
    "0",
]


@pytest.mark.parametrize("raw", INVALID_CASES)
def test_parse_amount_invalid(raw: str) -> None:
    assert parse_amount(raw) is None


def test_parse_amount_picks_first_match_left_to_right() -> None:
    assert parse_amount("ada 3 dan 50rb") == 3
