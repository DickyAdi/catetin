"""PDF renderer (M4) — `fpdf2`, core Helvetica fonts only (no TTF embedding,
per Modules M3-M4: Indonesian is Latin-1-safe and "Rp" is plain text).

`fpdf2` is synchronous and CPU-bound. `render_pdf` moves the actual build
onto a worker thread via `asyncio.to_thread`, gated by a semaphore so at
most `concurrency` renders run at once — on a 2 vCPU box the default of 1
keeps a core free for the event loop (Async & Resource Design §4/§6).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fpdf import FPDF

from catetin.domain.models import DayTotal, ItemTotal, Summary

_MAX_ITEM_NAME_LEN = 40
_MAX_PDF_BYTES = 2 * 1024 * 1024  # size guard per M4 — implausible above this
_FONT = "Helvetica"


def _rupiah(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp {abs(amount):,}".replace(",", ".")


def _truncate(text: str, limit: int = _MAX_ITEM_NAME_LEN) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _build_pdf(
    summary: Summary,
    day_totals: list[DayTotal],
    item_totals: list[ItemTotal],
    business_name: str | None,
    period_label: str,
) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font(_FONT, style="B", size=16)
    pdf.cell(0, 8, "CatetIn - Laporan Laba Rugi", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(_FONT, size=11)
    if business_name:
        pdf.cell(0, 6, business_name, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, period_label, new_x="LMARGIN", new_y="NEXT")
    generated_at = datetime.now(UTC).strftime("%d-%m-%Y %H:%M UTC")
    pdf.set_font(_FONT, style="I", size=9)
    pdf.cell(0, 5, f"Dibuat pada {generated_at}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font(_FONT, style="B", size=12)
    pdf.cell(0, 7, "Ringkasan", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT, size=11)
    for label, value in (
        ("Pemasukan", _rupiah(summary.income)),
        ("Pengeluaran", _rupiah(summary.expense)),
        ("Laba Bersih", _rupiah(summary.profit)),
        ("Jumlah Transaksi", str(summary.count)),
    ):
        pdf.cell(60, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font(_FONT, style="B", size=12)
    pdf.cell(0, 7, "Rincian Harian", new_x="LMARGIN", new_y="NEXT")
    if not day_totals:
        pdf.set_font(_FONT, size=10)
        pdf.cell(0, 6, "Belum ada transaksi di periode ini.", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font(_FONT, style="B", size=10)
        col_widths = (35, 45, 45, 45)
        for header, width in zip(
            ("Tanggal", "Pemasukan", "Pengeluaran", "Laba"), col_widths, strict=True
        ):
            pdf.cell(width, 6, header, border=1)
        pdf.ln()
        pdf.set_font(_FONT, size=10)
        for day in day_totals:
            pdf.cell(col_widths[0], 6, day.date, border=1)
            pdf.cell(col_widths[1], 6, _rupiah(day.income), border=1)
            pdf.cell(col_widths[2], 6, _rupiah(day.expense), border=1)
            pdf.cell(col_widths[3], 6, _rupiah(day.profit), border=1)
            pdf.ln()
    pdf.ln(4)

    if item_totals:
        pdf.set_font(_FONT, style="B", size=12)
        pdf.cell(0, 7, "Item Terlaris", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(_FONT, style="B", size=10)
        pdf.cell(120, 6, "Item", border=1)
        pdf.cell(55, 6, "Total", border=1)
        pdf.ln()
        pdf.set_font(_FONT, size=10)
        for item in item_totals:
            pdf.cell(120, 6, _truncate(item.item), border=1)
            pdf.cell(55, 6, _rupiah(item.total), border=1)
            pdf.ln()

    pdf.set_y(-20)
    pdf.set_font(_FONT, style="I", size=8)
    pdf.cell(0, 5, "Dibuat otomatis oleh CatetIn - bukan dokumen pajak resmi", align="C")

    data = bytes(pdf.output())
    if len(data) > _MAX_PDF_BYTES:
        raise ValueError(f"rendered PDF exceeds size guard: {len(data)} bytes")
    return data


class PdfRenderer:
    """`ReportRendererPort` adapter."""

    def __init__(self, concurrency: int = 1) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)

    async def render_pdf(
        self,
        user_id: int,
        summary: Summary,
        day_totals: list[DayTotal],
        item_totals: list[ItemTotal],
        business_name: str | None,
        period_label: str,
    ) -> bytes:
        async with self._semaphore:
            return await asyncio.to_thread(
                _build_pdf, summary, day_totals, item_totals, business_name, period_label
            )
