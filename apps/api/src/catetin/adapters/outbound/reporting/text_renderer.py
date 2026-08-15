"""Text renderer — a pure function, no I/O (M4).

Renders a `Summary` as a chat text block. Everything it needs arrives as an
argument, which is what makes it directly testable and safe to call from
`/lapor` in Phase 6 ahead of the `fpdf2` PDF renderer (Phase 7).
"""

from __future__ import annotations

from catetin.domain.models import DayTotal, Summary

_DIVIDER = "─" * 25


def _rupiah(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp {abs(amount):,}".replace(",", ".")


def render_text(
    summary: Summary, business_name: str | None = None, period_label: str = "Laporan"
) -> str:
    lines = [f"📊 {period_label}"]
    if business_name:
        lines.append(business_name)
    lines.append("")
    lines.append(f"Pemasukan   : {_rupiah(summary.income)}")
    lines.append(f"Pengeluaran : {_rupiah(summary.expense)}")
    lines.append(_DIVIDER)
    marker = "✅" if summary.profit >= 0 else "⚠️"
    lines.append(f"Laba        : {_rupiah(summary.profit)}  {marker}")
    lines.append("")
    lines.append(f"{summary.count} transaksi")
    return "\n".join(lines)


def render_day_totals(day_totals: list[DayTotal]) -> str:
    if not day_totals:
        return "Belum ada transaksi di periode ini."
    lines = []
    for day in day_totals:
        marker = "✅" if day.profit >= 0 else "⚠️"
        lines.append(
            f"{day.date}: {_rupiah(day.income)} - {_rupiah(day.expense)} "
            f"= {_rupiah(day.profit)} {marker}"
        )
    return "\n".join(lines)
