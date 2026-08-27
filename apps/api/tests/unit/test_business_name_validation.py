"""`validate_business_name` — the allowlist that guards the one free-text
field CatetIn stores.

The name is echoed straight back into chat and printed into the PDF report, so
this function is the only thing between an untrusted string and two renderers.
The tests below are therefore as much about what is *rejected* as about what a
warung is allowed to call itself.
"""

from __future__ import annotations

import pytest

from catetin.application.onboarding import MAX_BUSINESS_NAME_LEN, validate_business_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Warung Mbok Rina", "Warung Mbok Rina"),
        ("Toko-ABC_1", "Toko-ABC_1"),
        ("a", "a"),
        ("a" * MAX_BUSINESS_NAME_LEN, "a" * MAX_BUSINESS_NAME_LEN),
        ("Kedai 24 Jam", "Kedai 24 Jam"),
        ("  Warung Mbok Rina  ", "Warung Mbok Rina"),  # trimmed, not rejected
    ],
)
def test_accepted_names(raw: str, expected: str) -> None:
    assert validate_business_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "a" * (MAX_BUSINESS_NAME_LEN + 1),
        "<script>alert(1)</script>",
        "Warung <b>Rina</b>",
        "a\nb",
        "a\tb",
        "a\x00b",
        "a;DROP TABLE users",
        "a/b",
        "Warung 'Rina'",
        'Warung "Rina"',
        "Rina & Co",
        "warung@rina",
        "*bold*",
        "[link](http://x)",
        "Warung Mbok Riná",  # outside the ASCII allowlist
    ],
)
def test_rejected_names(raw: str) -> None:
    assert validate_business_name(raw) is None


def test_length_is_measured_after_trimming() -> None:
    padded = "  " + "a" * MAX_BUSINESS_NAME_LEN + "  "
    assert validate_business_name(padded) == "a" * MAX_BUSINESS_NAME_LEN
