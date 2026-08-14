"""Indonesian keyword sets used to classify and extract parsed segments.

`utang`/`hutang` are deliberately excluded — debt tracking is a Phase 2
concern, not part of the MVP sale/expense vocabulary.
"""

from __future__ import annotations

from .amounts import MULTIPLIERS as AMOUNT_MULTIPLIER_ALIASES

__all__ = [
    "AMOUNT_MULTIPLIER_ALIASES",
    "EXPENSE_VERBS",
    "SALE_VERBS",
    "UNITS",
]

SALE_VERBS: frozenset[str] = frozenset(
    {
        "jual",
        "terjual",
        "laku",
        "dagang",
        "omset",
        "omzet",
        "dapet",
        "dapat",
        "masuk",
        "penjualan",
        "setor",
        "order",
        "pesan",
        "pesanan",
        "dodol",  # Javanese: jual
    }
)

EXPENSE_VERBS: frozenset[str] = frozenset(
    {
        "beli",
        "bayar",
        "sewa",
        "gaji",
        "modal",
        "belanja",
        "keluar",
        "kulakan",
        "stok",
        "biaya",
        "ongkos",
        "bensin",
        "listrik",
        "tuku",  # Javanese: beli
    }
)

UNITS: frozenset[str] = frozenset(
    {
        "lusin",
        "pcs",
        "pack",
        "kg",
        "ons",
        "bungkus",
        "gelas",
        "porsi",
        "ekor",
        "biji",
        "butir",
        "kotak",
        "dus",
        "piring",
        "botol",
        "gram",
        "liter",
        "meter",
    }
)
