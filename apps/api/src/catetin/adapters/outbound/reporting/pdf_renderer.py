"""PDF renderer (M4, Report V1 FR-5) — `fpdf2`, core Helvetica fonts only (no
TTF embedding, per Modules M3-M4: Indonesian is Latin-1-safe and "Rp" is
plain text).

Tiered-section layout (Report Design §5, FRD §FR-5): one PDF, 3 zones.

    PAGE 1 — RINGKASAN     everyday language, one hero number ("Untung")
    PAGE 2 — RINCIAN       still readable: daily table, top sale/expense items
    PAGE 3+ — LAPORAN      bank/audit tier: SAK terms ("Laba Bersih"), full
              KEUANGAN     transaction audit trail (incl. soft-deleted rows
                           tagged "Batal"), disclaimer notes

Numbers are identical across tiers by construction — every zone reads from
the same `Summary`/`Transaction` objects, no separate calculation.

`fpdf2` is synchronous and CPU-bound. `render_pdf` moves the actual build
onto a worker thread via `asyncio.to_thread`, gated by a semaphore so at
most `concurrency` renders run at once — on a 2 vCPU box the default of 1
keeps a core free for the event loop (Async & Resource Design §4/§6).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fpdf import FPDF

from catetin.domain.models import DayTotal, ItemTotal, Summary, Transaction

_MAX_ITEM_NAME_LEN = 40
_MAX_PDF_BYTES = 2 * 1024 * 1024  # size guard per M4 — implausible above this
_FONT = "Helvetica"

_DETAIL_COL_WIDTHS = (18, 14, 62, 18, 38, 20)  # Tgl | Jam | Keterangan | Jenis | Jumlah | Status
_DETAIL_HEADERS = ("Tgl", "Jam", "Keterangan", "Jenis", "Jumlah", "Status")

_KIND_LABEL = {"sale": "Jual", "expense": "Beli"}

_NOTES = (
    "Laporan disusun berdasarkan catatan transaksi CatetIn.",
    "Bukan laporan audit independen.",
    "Bukan dokumen pajak resmi.",
)


def _rupiah(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp {abs(amount):,}".replace(",", ".")


def _truncate(text: str, limit: int = _MAX_ITEM_NAME_LEN) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _zone(timezone: str) -> tzinfo:
    """The user's zone, or UTC if it is somehow unknown to this host.

    Timezones are validated before they are stored, so the fallback only ever
    fires on a tzdata mismatch — and a report with a slightly-off clock column
    beats no report at all.
    """
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def _short_time(occurred_at: int, zone: tzinfo) -> str:
    """`occurred_at` is a UTC epoch; the user thinks in their own wall clock,
    the same one `occurred_on` is already denormalized to."""
    return datetime.fromtimestamp(occurred_at, zone).strftime("%H:%M")


def _section_title(pdf: FPDF, title: str) -> None:
    pdf.set_font(_FONT, style="B", size=12)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")


def _item_table(pdf: FPDF, title: str, items: list[ItemTotal]) -> None:
    _section_title(pdf, title)
    if not items:
        pdf.set_font(_FONT, size=10)
        pdf.cell(0, 6, "Belum ada data.", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        return
    pdf.set_font(_FONT, style="B", size=10)
    pdf.cell(120, 6, "Item", border=1)
    pdf.cell(55, 6, "Total", border=1)
    pdf.ln()
    pdf.set_font(_FONT, size=10)
    for item in items:
        pdf.cell(120, 6, _truncate(item.item), border=1)
        pdf.cell(55, 6, _rupiah(item.total), border=1)
        pdf.ln()
    pdf.ln(4)


def _render_page1_ringkasan(
    pdf: FPDF, summary: Summary, business_name: str | None, period_label: str, zone: tzinfo
) -> None:
    pdf.add_page()
    pdf.set_font(_FONT, style="B", size=16)
    pdf.cell(0, 8, "CatetIn - Laporan Usaha", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(_FONT, size=11)
    if business_name:
        pdf.cell(0, 6, business_name, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, period_label, new_x="LMARGIN", new_y="NEXT")
    # `%Z` prints the zone's own abbreviation, which for the three Indonesian
    # zones is exactly what users call them: WIB / WITA / WIT.
    generated_at = datetime.now(zone).strftime("%d-%m-%Y %H:%M %Z")
    pdf.set_font(_FONT, style="I", size=9)
    pdf.cell(0, 5, f"Dibuat pada {generated_at}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    _section_title(pdf, "Ringkasan")

    marker = "(sehat)" if summary.profit >= 0 else "(rugi)"
    pdf.set_font(_FONT, style="B", size=14)
    pdf.cell(
        0,
        10,
        f"Untung periode ini: {_rupiah(summary.profit)} {marker}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    pdf.set_font(_FONT, size=12)
    # Label cells in a label/value row must NOT pass `new_x` — the cursor has
    # to stay at the end of the 70-wide label column so the amount lands
    # beside it. `new_x="LMARGIN"` here sends the amount back to x=15, on top
    # of the label (only visible once the amount is wide, e.g. "Rp 2.280.500").
    pdf.cell(70, 7, "Pemasukan")
    pdf.cell(0, 7, _rupiah(summary.income), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(70, 7, "Pengeluaran")
    pdf.cell(0, 7, _rupiah(summary.expense), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_font(_FONT, style="I", size=10)
    pdf.multi_cell(0, 6, "Laporan ini buat lihat untung-rugi usahamu.")


def _render_page2_rincian(
    pdf: FPDF,
    day_totals: list[DayTotal],
    sale_item_totals: list[ItemTotal],
    expense_item_totals: list[ItemTotal],
) -> None:
    pdf.add_page()
    _section_title(pdf, "Rincian")

    pdf.set_font(_FONT, style="B", size=11)
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

    _item_table(pdf, "Item Terlaris", sale_item_totals)
    _item_table(pdf, "Pengeluaran Terbesar", expense_item_totals)


def _render_page3_laporan_keuangan(
    pdf: FPDF, summary: Summary, transactions: list[Transaction], zone: tzinfo
) -> None:
    pdf.add_page()
    _section_title(pdf, "Laporan Keuangan")

    pdf.set_font(_FONT, style="B", size=11)
    pdf.cell(0, 7, "A. Laporan Laba Rugi", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT, size=11)
    for label, value in (
        ("Penghasilan Usaha", _rupiah(summary.income)),
        ("Beban Usaha", _rupiah(summary.expense)),
    ):
        pdf.cell(70, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT, style="B", size=11)
    pdf.cell(70, 6, "Laba Bersih")
    pdf.cell(0, 6, _rupiah(summary.profit), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.set_font(_FONT, style="B", size=11)
    pdf.cell(0, 7, "B. Rincian Transaksi", new_x="LMARGIN", new_y="NEXT")
    if not transactions:
        pdf.set_font(_FONT, size=10)
        pdf.cell(0, 6, "Tidak ada transaksi usaha di periode ini.", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font(_FONT, style="B", size=9)
        for header, width in zip(_DETAIL_HEADERS, _DETAIL_COL_WIDTHS, strict=True):
            pdf.cell(width, 6, header, border=1)
        pdf.ln()
        pdf.set_font(_FONT, size=9)
        for tx in transactions:
            status = "Batal" if tx.deleted_at is not None else "Aktif"
            pdf.cell(_DETAIL_COL_WIDTHS[0], 6, tx.occurred_on, border=1)
            pdf.cell(_DETAIL_COL_WIDTHS[1], 6, _short_time(tx.occurred_at, zone), border=1)
            pdf.cell(_DETAIL_COL_WIDTHS[2], 6, _truncate(tx.item, 34), border=1)
            pdf.cell(_DETAIL_COL_WIDTHS[3], 6, _KIND_LABEL[tx.kind], border=1)
            pdf.cell(_DETAIL_COL_WIDTHS[4], 6, _rupiah(tx.total_amount), border=1)
            pdf.cell(_DETAIL_COL_WIDTHS[5], 6, status, border=1)
            pdf.ln()
    pdf.ln(6)

    pdf.set_font(_FONT, style="B", size=11)
    pdf.cell(0, 7, "C. Catatan", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT, size=9)
    for note in _NOTES:
        pdf.cell(0, 5, note, new_x="LMARGIN", new_y="NEXT")


def _build_pdf(
    summary: Summary,
    day_totals: list[DayTotal],
    sale_item_totals: list[ItemTotal],
    expense_item_totals: list[ItemTotal],
    transactions: list[Transaction],
    business_name: str | None,
    period_label: str,
    timezone: str,
) -> bytes:
    zone = _zone(timezone)
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)

    _render_page1_ringkasan(pdf, summary, business_name, period_label, zone)
    _render_page2_rincian(pdf, day_totals, sale_item_totals, expense_item_totals)
    _render_page3_laporan_keuangan(pdf, summary, transactions, zone)

    pdf.set_font(_FONT, style="I", size=8)
    pdf.set_y(-20)
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
        sale_item_totals: list[ItemTotal],
        expense_item_totals: list[ItemTotal],
        transactions: list[Transaction],
        business_name: str | None,
        period_label: str,
        timezone: str,
    ) -> bytes:
        async with self._semaphore:
            return await asyncio.to_thread(
                _build_pdf,
                summary,
                day_totals,
                sale_item_totals,
                expense_item_totals,
                transactions,
                business_name,
                period_label,
                timezone,
            )
