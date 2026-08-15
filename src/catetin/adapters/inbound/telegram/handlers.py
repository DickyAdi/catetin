"""Thin Telegram handlers — map an Update to a use-case call, format the reply.

No business logic lives here: parsing, validation and persistence all happen
in `application/`. A handler's job is: build an `InboundCommand` via
`mapper.map_update`, call exactly one use case, hand the reply to
`MessagingPort`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from catetin.adapters.outbound.reporting.text_renderer import (
    render_day_totals,
    render_text,
)
from catetin.application.manage_transactions import ManageTransactions
from catetin.application.onboarding import Onboarding
from catetin.application.record_transactions import RecordTransactions
from catetin.application.summarize import Summarize
from catetin.domain.errors import DomainValidationError
from catetin.domain.models import ParsedTransaction, User
from catetin.domain.ports.clock import ClockPort
from catetin.domain.ports.messaging import MessagingPort
from telegram import Update
from telegram.ext import ContextTypes

from .mapper import InboundCommand, map_update

_logger = logging.getLogger("catetin.telegram.handlers")

WEEK_DAYS = 7
CHOICE_SALE = "Jual"
CHOICE_EXPENSE = "Beli"
_KIND_BY_CHOICE = {CHOICE_SALE: "sale", CHOICE_EXPENSE: "expense"}


@dataclass
class TelegramDeps:
    onboarding: Onboarding
    record_transactions: RecordTransactions
    manage_transactions: ManageTransactions
    summarize: Summarize
    messaging: MessagingPort
    clock: ClockPort
    default_timezone: str
    # Ambiguous-kind segments awaiting a `Jual`/`Beli` answer, per internal
    # user id — a single in-process cache is enough for a single-instance
    # bot; lost on restart, which just means the user re-sends the message.
    pending_choices: dict[int, list[ParsedTransaction]] = field(default_factory=dict)


def _deps(context: ContextTypes.DEFAULT_TYPE) -> TelegramDeps:
    deps: TelegramDeps = context.application.bot_data["deps"]
    return deps


async def _get_user(deps: TelegramDeps, cmd: InboundCommand) -> User:
    return await deps.onboarding.get_or_create_user(
        "telegram", cmd.platform_user_id, cmd.display_name
    )


async def _ask_next_pending(deps: TelegramDeps, user: User) -> None:
    pending = deps.pending_choices.get(user.id)
    if not pending:
        return
    next_item = pending[0]
    prompt = f'"{next_item.item}" itu pemasukan atau pengeluaran?'
    await deps.messaging.ask_choice(user.id, prompt, [CHOICE_SALE, CHOICE_EXPENSE])


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    await deps.messaging.send_text(user.id, deps.onboarding.start_message())


async def on_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    today = deps.clock.today_local(user.timezone)
    summary = await deps.summarize.today(user.id, today)
    text = render_text(summary, user.business_name, period_label="Laporan Hari Ini")
    await deps.messaging.send_text(user.id, text)


async def on_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    today = deps.clock.today_local(user.timezone)
    start = today - timedelta(days=WEEK_DAYS - 1)
    summary = await deps.summarize.range(user.id, start, today)
    day_totals = await deps.summarize.week(user.id, today)
    text = (
        render_text(summary, user.business_name, period_label="Laporan 7 Hari Terakhir")
        + "\n\n"
        + render_day_totals(day_totals)
    )
    await deps.messaging.send_text(user.id, text)


async def on_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    transactions = await deps.manage_transactions.list_recent(user.id)
    if not transactions:
        await deps.messaging.send_text(user.id, "Belum ada transaksi.")
        return
    lines = ["📋 10 Transaksi Terakhir"]
    for i, tx in enumerate(transactions, start=1):
        marker = "+" if tx.kind == "sale" else "-"
        amount = f"{marker}Rp {tx.total_amount:,}".replace(",", ".")
        lines.append(f"{i}. [{tx.id}] {amount} {tx.item} ({tx.occurred_on})")
    await deps.messaging.send_text(user.id, "\n".join(lines))


async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    removed = await deps.manage_transactions.cancel_last(user.id)
    if removed is None:
        await deps.messaging.send_text(user.id, "Belum ada transaksi buat dibatalkan.")
        return
    await deps.messaging.send_text(
        user.id, f'Dibatalkan: {removed.item} — Rp {removed.total_amount:,}'.replace(",", ".")
    )


async def on_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/lapor` — text report for now; the PDF renderer lands in Phase 7."""
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    today = deps.clock.today_local(user.timezone)
    start = today - timedelta(days=WEEK_DAYS - 1)
    summary = await deps.summarize.range(user.id, start, today)
    day_totals = await deps.summarize.week(user.id, today)
    text = (
        render_text(summary, user.business_name, period_label="Laporan Mingguan")
        + "\n\n"
        + render_day_totals(day_totals)
    )
    await deps.messaging.send_text(user.id, text)


async def on_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    args = context.args or []
    if not args or args[0].lower() not in ("on", "off"):
        await deps.messaging.send_text(user.id, "Pakai: /digest on atau /digest off")
        return
    enabled = args[0].lower() == "on"
    await deps.onboarding.toggle_digest(user.id, enabled)
    state = "diaktifkan" if enabled else "dimatikan"
    await deps.messaging.send_text(user.id, f"Ringkasan malam hari sudah {state}.")


async def on_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    args = context.args or []
    if not args:
        await deps.messaging.send_text(user.id, "Pakai: /zona Asia/Jakarta")
        return
    try:
        await deps.onboarding.set_timezone(user.id, args[0])
    except DomainValidationError:
        await deps.messaging.send_text(user.id, f"Zona waktu tidak dikenal: {args[0]}")
        return
    await deps.messaging.send_text(user.id, f"Zona waktu diset ke {args[0]}.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    today = deps.clock.today_local(user.timezone)
    result = await deps.record_transactions.execute(user.id, cmd.text, today)

    lines: list[str] = []
    if result.recorded:
        lines.append(f"Tercatat {len(result.recorded)} transaksi:")
        for tx in result.recorded:
            marker = "+" if tx.kind == "sale" else "-"
            lines.append(f"{marker}Rp {tx.total_amount:,}".replace(",", ".") + f" {tx.item}")
        lines.append("")
        lines.append(f"Total hari ini: Rp {result.today_total.profit:,}".replace(",", "."))

    for issue in result.issues:
        if issue.reason == "no_amount":
            lines.append(
                f'Nggak ketemu nominalnya di "{issue.raw_text}" '
                '— coba tulis mis. "jual ayam 50rb".'
            )
        elif issue.reason == "too_many_segments":
            lines.append("Pesannya kepanjangan, cuma 20 transaksi pertama yang diproses.")
        else:
            lines.append(f'Nggak bisa diproses: "{issue.raw_text}" ({issue.reason}).')

    if lines:
        await deps.messaging.send_text(user.id, "\n".join(lines))

    if result.ambiguous:
        deps.pending_choices.setdefault(user.id, []).extend(result.ambiguous)
        await _ask_next_pending(deps, user)


async def on_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Non-text updates (sticker, location, voice, photo) — Phase 1 stub reply."""
    deps = _deps(context)
    if update.effective_message is None or update.effective_user is None:
        return
    tg_user = update.effective_user
    user = await deps.onboarding.get_or_create_user(
        "telegram", str(tg_user.id), tg_user.full_name or tg_user.username
    )
    await deps.messaging.send_text(user.id, "Belum bisa baca ini, kirim teks aja ya.")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()

    data = query.data or ""
    if not data.startswith("choice:"):
        return
    choice = data.removeprefix("choice:")
    kind = _KIND_BY_CHOICE.get(choice)

    user = await deps.onboarding.get_or_create_user(
        "telegram", str(update.effective_user.id), update.effective_user.full_name
    )

    pending = deps.pending_choices.get(user.id)
    if not pending:
        await deps.messaging.send_text(user.id, "Sesi kedaluwarsa, kirim ulang ya.")
        return
    parsed = pending.pop(0)
    if not pending:
        del deps.pending_choices[user.id]

    if kind is None:
        await deps.messaging.send_text(user.id, "Pilihan tidak dikenal.")
        return

    resolved = parsed.model_copy(update={"kind": kind})
    tx = await deps.record_transactions.confirm(user.id, resolved)
    marker = "+" if tx.kind == "sale" else "-"
    await deps.messaging.send_text(
        user.id, f"Dicatat: {marker}Rp {tx.total_amount:,}".replace(",", ".") + f" {tx.item}"
    )

    await _ask_next_pending(deps, user)
