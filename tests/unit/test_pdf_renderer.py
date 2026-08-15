"""M4 PDF renderer tests — real fpdf2 render, no fakes: the whole point is to
prove the bytes produced are a valid, non-trivial PDF and contain the
expected Indonesian labels.
"""

import asyncio
import io

from pypdf import PdfReader

from catetin.adapters.outbound.reporting.pdf_renderer import PdfRenderer
from catetin.domain.models import DayTotal, ItemTotal, Summary

SUMMARY = Summary(income=1_250_000, expense=480_000, profit=770_000, count=12)
DAY_TOTALS = [
    DayTotal(date="2026-08-10", income=200_000, expense=80_000, profit=120_000),
    DayTotal(date="2026-08-11", income=300_000, expense=100_000, profit=200_000),
]
ITEM_TOTALS = [
    ItemTotal(item="Ayam Geprek", kind="sale", total=900_000),
    ItemTotal(item="Es Teh", kind="sale", total=350_000),
]


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


async def test_render_pdf_produces_valid_pdf_bytes() -> None:
    renderer = PdfRenderer()

    pdf_bytes = await renderer.render_pdf(
        user_id=1,
        summary=SUMMARY,
        day_totals=DAY_TOTALS,
        item_totals=ITEM_TOTALS,
        business_name="Warung Bu Rina",
        period_label="Laporan 7 Hari Terakhir",
    )

    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 1000


async def test_render_pdf_contains_expected_labels() -> None:
    renderer = PdfRenderer()

    pdf_bytes = await renderer.render_pdf(
        user_id=1,
        summary=SUMMARY,
        day_totals=DAY_TOTALS,
        item_totals=ITEM_TOTALS,
        business_name="Warung Bu Rina",
        period_label="Laporan 7 Hari Terakhir",
    )

    text = _extract_text(pdf_bytes)
    assert "Warung Bu Rina" in text
    assert "Pemasukan" in text
    assert "Laba Bersih" in text
    assert "Rp" in text
    assert "1.250.000" in text
    assert "Ayam Geprek" in text


async def test_render_pdf_empty_period_still_produces_pdf() -> None:
    renderer = PdfRenderer()
    empty_summary = Summary(income=0, expense=0, profit=0, count=0)

    pdf_bytes = await renderer.render_pdf(
        user_id=1,
        summary=empty_summary,
        day_totals=[],
        item_totals=[],
        business_name=None,
        period_label="Laporan 7 Hari Terakhir",
    )

    assert pdf_bytes[:5] == b"%PDF-"
    text = _extract_text(pdf_bytes)
    assert "Belum ada transaksi" in text


async def test_render_pdf_runs_concurrently_without_deadlock() -> None:
    """Semaphore(1) serializes renders rather than deadlocking them."""
    renderer = PdfRenderer(concurrency=1)

    results = await asyncio.gather(
        *[
            renderer.render_pdf(
                user_id=i,
                summary=SUMMARY,
                day_totals=DAY_TOTALS,
                item_totals=[],
                business_name=None,
                period_label="Laporan",
            )
            for i in range(3)
        ]
    )

    assert all(r[:5] == b"%PDF-" for r in results)
