"""M4 PDF renderer tests — real fpdf2 render, no fakes: the whole point is to
prove the bytes produced are a valid, non-trivial PDF and contain the
expected Indonesian labels across the 3 tiered zones (Report V1 FR-5).
"""

import asyncio
import io
import re

from pypdf import PdfReader

from catetin.adapters.outbound.reporting.pdf_renderer import PdfRenderer
from catetin.domain.models import DayTotal, ItemTotal, Summary, Transaction

SUMMARY = Summary(income=1_250_000, expense=480_000, profit=770_000, count=12)
DAY_TOTALS = [
    DayTotal(date="2026-08-10", income=200_000, expense=80_000, profit=120_000),
    DayTotal(date="2026-08-11", income=300_000, expense=100_000, profit=200_000),
]
SALE_ITEM_TOTALS = [
    ItemTotal(item="Ayam Geprek", kind="sale", total=900_000),
    ItemTotal(item="Es Teh", kind="sale", total=350_000),
]
EXPENSE_ITEM_TOTALS = [
    ItemTotal(item="Tepung", kind="expense", total=200_000),
    ItemTotal(item="Bensin", kind="expense", total=100_000),
]


def _tx(
    id_: int,
    kind: str,
    item: str,
    total_amount: int,
    occurred_on: str = "2026-08-10",
    deleted_at: int | None = None,
) -> Transaction:
    return Transaction(
        id=id_,
        user_id=1,
        kind=kind,  # type: ignore[arg-type]
        item=item,
        qty=1,
        unit_amount=None,
        total_amount=total_amount,
        occurred_on=occurred_on,
        occurred_at=1_755_000_000 + id_,
        raw_text=item,
        created_at=1_755_000_000 + id_,
        deleted_at=deleted_at,
    )


TRANSACTIONS = [
    _tx(1, "sale", "Ayam Geprek", 50_000),
    _tx(2, "expense", "Tepung", 20_000),
    _tx(3, "sale", "Es Teh", 10_000, deleted_at=1_755_000_100),
]


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# fpdf2 emits one `BT <x> <y> Td (<text>) Tj ET` per cell. `extract_text`
# throws the coordinates away, and they are exactly what a "does this label
# collide with its amount?" check needs, so read them off the content stream.
_TEXT_OP_RE = re.compile(r"BT ([\d.]+) ([\d.]+) Td \((.*?)\) Tj ET")


def _placed_text(pdf_bytes: bytes, page: int = 0) -> list[tuple[float, float, str]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    stream = reader.pages[page].get_contents().get_data().decode("latin-1")
    return [(float(x), float(y), text) for x, y, text in _TEXT_OP_RE.findall(stream)]


async def _render(
    day_totals: list[DayTotal] = DAY_TOTALS,
    sale_item_totals: list[ItemTotal] = SALE_ITEM_TOTALS,
    expense_item_totals: list[ItemTotal] = EXPENSE_ITEM_TOTALS,
    transactions: list[Transaction] = TRANSACTIONS,
    summary: Summary = SUMMARY,
    business_name: str | None = "Warung Bu Rina",
    period_label: str = "Laporan 7 Hari Terakhir",
) -> bytes:
    renderer = PdfRenderer()
    return await renderer.render_pdf(
        user_id=1,
        summary=summary,
        day_totals=day_totals,
        sale_item_totals=sale_item_totals,
        expense_item_totals=expense_item_totals,
        transactions=transactions,
        business_name=business_name,
        period_label=period_label,
    )


async def test_render_pdf_produces_valid_pdf_bytes() -> None:
    pdf_bytes = await _render()

    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 1000


async def test_render_pdf_has_at_least_3_pages_tiered_zones() -> None:
    pdf_bytes = await _render()
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 3


async def test_render_pdf_contains_expected_labels() -> None:
    pdf_bytes = await _render()

    text = _extract_text(pdf_bytes)
    assert "Warung Bu Rina" in text
    assert "Pemasukan" in text
    assert "Ringkasan" in text
    assert "Laba Bersih" in text
    assert "Rincian Transaksi" in text
    assert "Rp" in text
    assert "1.250.000" in text
    assert "Ayam Geprek" in text


async def test_render_pdf_summary_amounts_sit_beside_their_labels() -> None:
    """Regression: the "Pemasukan" label cell passed `new_x="LMARGIN"`, which
    returned the cursor to the left margin, so its amount was drawn on top of
    the label instead of in the value column (visible once the amount is wide,
    e.g. "Rp 2.280.500"). "Pengeluaran" never had the bug — both rows must now
    place the amount to the right of the label, on the label's own baseline.
    """
    pdf_bytes = await _render(
        summary=Summary(income=2_280_500, expense=480_000, profit=1_800_500, count=12)
    )
    placed = _placed_text(pdf_bytes)  # page 1 = Ringkasan

    for label, amount in (("Pemasukan", "Rp 2.280.500"), ("Pengeluaran", "Rp 480.000")):
        label_x, label_y, _ = next(p for p in placed if p[2] == label)
        amount_x, amount_y, _ = next(p for p in placed if p[2] == amount)
        assert amount_y == label_y, f"{label}: amount is not on the label's baseline"
        assert amount_x > label_x, f"{label}: amount overlaps the label (x={amount_x})"


async def test_render_pdf_numbers_consistent_across_tiers() -> None:
    """Page-1 hero profit figure must equal the Laba Rugi total on page 3+ —
    both come from the same `Summary`, no separate calculation (FR-5)."""
    pdf_bytes = await _render()
    text = _extract_text(pdf_bytes)

    assert text.count("770.000") >= 2


async def test_render_pdf_detail_table_shows_deleted_as_batal() -> None:
    pdf_bytes = await _render()
    text = _extract_text(pdf_bytes)

    assert "Batal" in text
    assert "Aktif" in text


async def test_render_pdf_empty_period_still_produces_pdf() -> None:
    pdf_bytes = await _render(
        day_totals=[],
        sale_item_totals=[],
        expense_item_totals=[],
        transactions=[],
        summary=Summary(income=0, expense=0, profit=0, count=0),
        business_name=None,
    )

    assert pdf_bytes[:5] == b"%PDF-"
    text = _extract_text(pdf_bytes)
    assert "Belum ada transaksi" in text
    assert "Tidak ada transaksi usaha" in text


async def test_render_pdf_multi_page_detail_table_with_many_transactions() -> None:
    many = [_tx(i, "sale", f"Item {i}", 10_000 + i) for i in range(60)]
    pdf_bytes = await _render(transactions=many)
    reader = PdfReader(io.BytesIO(pdf_bytes))

    assert len(reader.pages) > 3  # the detail table alone must overflow page 3
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "Item 59" in text


async def test_render_pdf_runs_concurrently_without_deadlock() -> None:
    """Semaphore(1) serializes renders rather than deadlocking them."""
    renderer = PdfRenderer(concurrency=1)

    results = await asyncio.gather(
        *[
            renderer.render_pdf(
                user_id=i,
                summary=SUMMARY,
                day_totals=DAY_TOTALS,
                sale_item_totals=[],
                expense_item_totals=[],
                transactions=[],
                business_name=None,
                period_label="Laporan",
            )
            for i in range(3)
        ]
    )

    assert all(r[:5] == b"%PDF-" for r in results)
