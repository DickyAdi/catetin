"""Thin Telegram handlers — map an Update to a use-case call, format the reply.

No business logic lives here: parsing, validation and persistence all happen
in `application/`. A handler's job is: build an `InboundCommand` via
`mapper.map_update`, call exactly one use case, hand the reply to
`MessagingPort`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from catetin.adapters.outbound.reporting.text_renderer import (
    render_day_totals,
    render_text,
)
from catetin.application.generate_report import GenerateReport, PendingReview
from catetin.application.manage_transactions import ManageTransactions
from catetin.application.onboarding import (
    MAX_BUSINESS_NAME_LEN,
    Onboarding,
    validate_business_name,
)
from catetin.application.record_transactions import RecordTransactions
from catetin.application.summarize import Summarize
from catetin.domain.errors import DomainValidationError, RateLimited
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
CHOICE_OTHER = "Bukan Usaha"
_KIND_BY_CHOICE = {CHOICE_SALE: "sale", CHOICE_EXPENSE: "expense"}

REPORT_PERIOD_LABEL = "Laporan 7 Hari Terakhir"
REVIEW_EXCLUDE_PREFIX = "review_exclude:"
REVIEW_KEEP_PREFIX = "review_keep:"
_REVIEW_SHOW_LIMIT = 20

# `/zona` buttons. The callback carries the timezone itself rather than an
# index into server-side state — unlike `choice:`, there is no pending session
# to expire, so a tap works even after a restart.
TZ_PREFIX = "tz:"
TZ_OPTIONS = (
    ("WIB", "Asia/Jakarta"),
    ("WITA", "Asia/Makassar"),
    ("WIT", "Asia/Jayapura"),
)

# `/start` setup buttons. All four share one prefix so `on_callback` can route
# on it in a single check; the payloads carry no state, the step lives in
# `TelegramDeps.onboarding_pending`.
OB_PREFIX = "ob:"
OB_SAVE = "ob:save"
OB_CANCEL = "ob:cancel"
OB_REDO = "ob:redo"
OB_SKIP_REDO = "ob:skip-redo"

ASK_NAME = "Nama usaha kamu apa? (misal: Warung Mbok Rina)"
_WELCOME = "Halo! 👋 Aku CatetIn, bot pencatatan keuangan buat usahamu.\n\n" + ASK_NAME
INVALID_NAME = (
    "Nama cuma boleh huruf, angka, spasi, - atau _ "
    f"(maks {MAX_BUSINESS_NAME_LEN} huruf). Coba lagi:"
)
ASK_TIMEZONE = "Pilih zona waktumu:"
ONBOARDING_DONE = "Siap! Coba kirim: jual ayam geprek 50rb"
REDO_PROMPT = "Kamu udah selesai setup. Mau ulangi?"
REDO_DECLINED = "Oke. Ketik /lapor buat laporan."
ONBOARDING_CANCELLED = "Oke, onboarding dibatalkan. Ketik /start kapan aja."
NOT_ONBOARDED = "Waduh, kamu belum setup nih. Ketik /start dulu ya 😊"
ONBOARDING_EXPIRED = "Sesi setup kedaluwarsa, ketik /start lagi ya."

OnboardingStep = Literal["awaiting_name", "confirming_name", "awaiting_timezone"]


@dataclass(frozen=True)
class OnboardingState:
    """Where a user is in the `/start` flow.

    `proposed_name` is set only in `confirming_name` — it is the name the user
    typed, held until they tap ✅ so nothing is written before they agree.
    """

    step: OnboardingStep
    proposed_name: str | None = None


def _rupiah(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp {abs(amount):,}".replace(",", ".")


def _short_date(occurred_on: str) -> str:
    _, month, day = occurred_on.split("-")
    return f"{day}/{month}"


@dataclass
class TelegramDeps:
    onboarding: Onboarding
    record_transactions: RecordTransactions
    manage_transactions: ManageTransactions
    summarize: Summarize
    generate_report: GenerateReport
    messaging: MessagingPort
    clock: ClockPort
    default_timezone: str
    # Ambiguous-kind segments awaiting a `Jual`/`Beli` answer, per internal
    # user id — a single in-process cache is enough for a single-instance
    # bot; lost on restart, which just means the user re-sends the message.
    pending_choices: dict[int, list[ParsedTransaction]] = field(default_factory=dict)
    # Users currently walking through `/start`, per internal user id. Same
    # single-instance, lost-on-restart trade-off as `pending_choices`: a
    # restart mid-setup just means the user types /start again, and because
    # `has_onboarded` is only flipped at the very end, an abandoned run leaves
    # their previous state untouched.
    onboarding_pending: dict[int, OnboardingState] = field(default_factory=dict)


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
    await deps.messaging.ask_choice(user.id, prompt, [CHOICE_SALE, CHOICE_EXPENSE, CHOICE_OTHER])


async def _start_onboarding(deps: TelegramDeps, user: User, *, greet: bool) -> None:
    """Step 1 — ask for the business name (overwrites any stale state)."""
    deps.onboarding_pending[user.id] = OnboardingState(step="awaiting_name")
    await deps.messaging.send_text(user.id, _WELCOME if greet else ASK_NAME)


async def _propose_business_name(deps: TelegramDeps, user: User, raw: str) -> None:
    """Step 1 continued — validate what was typed and ask to confirm it."""
    name = validate_business_name(raw)
    if name is None:
        deps.onboarding_pending[user.id] = OnboardingState(step="awaiting_name")
        await deps.messaging.send_text(user.id, INVALID_NAME)
        return
    deps.onboarding_pending[user.id] = OnboardingState(
        step="confirming_name", proposed_name=name
    )
    await deps.messaging.ask_action(
        user.id,
        f"Simpan sebagai '{name}'?",
        [("✅ Simpan", OB_SAVE), ("❌ Batal", OB_CANCEL)],
    )


async def _ask_onboarding_timezone(deps: TelegramDeps, user: User) -> None:
    """Step 2 — the same keyboard `/zona` uses; its `tz:` callback finishes."""
    deps.onboarding_pending[user.id] = OnboardingState(step="awaiting_timezone")
    await deps.messaging.ask_action(
        user.id, ASK_TIMEZONE, [(label, f"{TZ_PREFIX}{tz}") for label, tz in TZ_OPTIONS]
    )


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    if user.has_onboarded:
        # Re-running setup is opt-in, and `has_onboarded` deliberately stays
        # True for the whole redo: abandoning it halfway must not demote a
        # working account back to "belum setup".
        deps.onboarding_pending.pop(user.id, None)
        await deps.messaging.ask_action(
            user.id, REDO_PROMPT, [("✅ Ulangi", OB_REDO), ("❌ Gak usah", OB_SKIP_REDO)]
        )
        return
    await _start_onboarding(deps, user, greet=True)


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
        prefix = "🚫 " if tx.excluded_from_report else ""
        lines.append(f"{i}. {prefix}[{tx.id}] {amount} {tx.item} ({tx.occurred_on})")
    await deps.messaging.send_text(user.id, "\n".join(lines))


async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    if deps.onboarding_pending.pop(user.id, None) is not None:
        # Mid-setup, `/batal` means "get me out of this", not "undo my last
        # transaction" — the flow is what is in front of the user right now.
        await deps.messaging.send_text(user.id, ONBOARDING_CANCELLED)
        return
    removed = await deps.manage_transactions.cancel_last(user.id)
    if removed is None:
        await deps.messaging.send_text(user.id, "Belum ada transaksi buat dibatalkan.")
        return
    await deps.messaging.send_text(
        user.id, f'Dibatalkan: {removed.item} — Rp {removed.total_amount:,}'.replace(",", ".")
    )


async def on_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/lapor` — PDF report over the last 7 days, sent as a document.

    FR-2: if the period has flagged-but-undecided transactions, a review
    gate is shown first instead of the PDF (see `_send_review_gate`)."""
    deps = _deps(context)
    cmd = map_update(update)
    if cmd is None:
        return
    user = await _get_user(deps, cmd)
    if not user.has_onboarded:
        # The gate lives here, not in `GenerateReport`: onboarding is a chat
        # concern, and the use case stays usable from the scheduler and ops.
        # Only `/lapor` is gated — the quick summaries stay open so a user who
        # started recording before `/start` still sees their numbers.
        await deps.messaging.send_text(user.id, NOT_ONBOARDED)
        return
    today = deps.clock.today_local(user.timezone)
    start = today - timedelta(days=WEEK_DAYS - 1)

    try:
        result = await deps.generate_report.execute(
            user.id, start, today, period_label=REPORT_PERIOD_LABEL
        )
    except RateLimited:
        await deps.messaging.send_text(
            user.id, "Kamu sudah 5x bikin laporan hari ini, coba besok lagi ya."
        )
        return

    if isinstance(result, PendingReview):
        await _send_review_gate(deps, user, result)
        return

    filename = f"laporan-{start.isoformat()}-{today.isoformat()}.pdf"
    await deps.messaging.send_document(
        user.id, filename, result.pdf_bytes, caption=f"📊 {REPORT_PERIOD_LABEL}"
    )


async def _send_review_gate(
    deps: TelegramDeps, user: User, pending: PendingReview
) -> None:
    totals_line = (
        f"Total: Pemasukan {_rupiah(pending.summary.income)} "
        f"· Pengeluaran {_rupiah(pending.summary.expense)}"
    )
    lines = [
        f"📊 {pending.period_label} siap.",
        totals_line,
        "",
        f"⚠️ {len(pending.flagged_items)} transaksi terlihat bukan usaha:",
    ]
    shown = pending.flagged_items[:_REVIEW_SHOW_LIMIT]
    for tx in shown:
        marker = "+" if tx.kind == "sale" else "-"
        label = tx.raw_text or tx.item
        lines.append(f"• {_short_date(tx.occurred_on)} {label} ({marker}{_rupiah(tx.total_amount)})")
    remaining = len(pending.flagged_items) - len(shown)
    if remaining > 0:
        lines.append(f"dan {remaining} lainnya")

    start_iso = pending.start.isoformat()
    end_iso = pending.end.isoformat()
    buttons = [
        ("Keluarkan dari laporan", f"{REVIEW_EXCLUDE_PREFIX}{start_iso}:{end_iso}"),
        ("Tetap masukkan", f"{REVIEW_KEEP_PREFIX}{start_iso}:{end_iso}"),
    ]
    await deps.messaging.ask_action(user.id, "\n".join(lines), buttons)


async def _handle_review_callback(deps: TelegramDeps, update: Update, data: str) -> None:
    if update.effective_user is None:
        return
    user = await deps.onboarding.get_or_create_user(
        "telegram", str(update.effective_user.id), update.effective_user.full_name
    )

    exclude = data.startswith(REVIEW_EXCLUDE_PREFIX)
    payload = data.removeprefix(REVIEW_EXCLUDE_PREFIX if exclude else REVIEW_KEEP_PREFIX)
    try:
        start_str, end_str = payload.split(":")
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
    except ValueError:
        await deps.messaging.send_text(user.id, "Sesi kedaluwarsa, coba /lapor lagi ya.")
        return

    if exclude:
        await deps.generate_report.exclude_flagged(user.id, start, end)

    result = await deps.generate_report.render(user.id, start, end, period_label=REPORT_PERIOD_LABEL)
    filename = f"laporan-{start.isoformat()}-{end.isoformat()}.pdf"
    await deps.messaging.send_document(
        user.id, filename, result.pdf_bytes, caption=f"📊 {REPORT_PERIOD_LABEL}"
    )


async def _handle_onboarding_callback(deps: TelegramDeps, update: Update, data: str) -> None:
    if update.effective_user is None:
        return
    user = await deps.onboarding.get_or_create_user(
        "telegram", str(update.effective_user.id), update.effective_user.full_name
    )

    # The redo answers are stateless — they are offered to an already-onboarded
    # user, so they must work even after a restart cleared `onboarding_pending`.
    if data == OB_REDO:
        await _start_onboarding(deps, user, greet=False)
        return
    if data == OB_SKIP_REDO:
        deps.onboarding_pending.pop(user.id, None)
        await deps.messaging.send_text(user.id, REDO_DECLINED)
        return

    state = deps.onboarding_pending.get(user.id)
    if state is None or state.step != "confirming_name" or state.proposed_name is None:
        # A keyboard from an abandoned run, or state lost to a restart: the
        # name it referred to is gone, so there is nothing safe to save.
        await deps.messaging.send_text(user.id, ONBOARDING_EXPIRED)
        return

    if data == OB_CANCEL:
        deps.onboarding_pending[user.id] = OnboardingState(step="awaiting_name")
        await deps.messaging.send_text(user.id, ASK_NAME)
        return
    if data != OB_SAVE:
        return

    try:
        await deps.onboarding.set_business_name(user.id, state.proposed_name)
    except DomainValidationError:
        # Unreachable through our own keyboard (the name was validated before
        # it was offered), but the use case is the authority on what is storable.
        deps.onboarding_pending[user.id] = OnboardingState(step="awaiting_name")
        await deps.messaging.send_text(user.id, INVALID_NAME)
        return
    await _ask_onboarding_timezone(deps, user)


async def _handle_timezone_callback(deps: TelegramDeps, update: Update, data: str) -> None:
    if update.effective_user is None:
        return
    user = await deps.onboarding.get_or_create_user(
        "telegram", str(update.effective_user.id), update.effective_user.full_name
    )
    tz = data.removeprefix(TZ_PREFIX)
    try:
        await deps.onboarding.set_timezone(user.id, tz)
    except DomainValidationError:
        # Unreachable via the buttons we send; reachable if an old chat carries
        # a callback we no longer offer. The pending step is left in place so a
        # user mid-setup can just tap again.
        await deps.messaging.send_text(user.id, f"Zona waktu tidak dikenal: {tz}")
        return

    state = deps.onboarding_pending.get(user.id)
    if state is not None and state.step == "awaiting_timezone":
        # Step 2 of `/start`: the zone tap is the last thing setup waits for.
        del deps.onboarding_pending[user.id]
        await deps.onboarding.complete_onboarding(user.id)
        await deps.messaging.send_text(user.id, ONBOARDING_DONE)
        await deps.messaging.send_text(user.id, deps.onboarding.guide_message(tz))
        return

    await deps.messaging.send_text(user.id, f"Zona waktu diset ke {tz}.")


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
        # Bare `/zona` reports the current setting rather than only a usage
        # line — the timezone is guessed at signup, so "what is it now?" is
        # the question users actually arrive with — and offers the three
        # Indonesian zones as buttons, so nobody has to type "Asia/Makassar".
        await deps.messaging.ask_action(
            user.id,
            f"Zona waktumu sekarang: {user.timezone}.\nPilih zona waktumu:",
            [(label, f"{TZ_PREFIX}{tz}") for label, tz in TZ_OPTIONS],
        )
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

    state = deps.onboarding_pending.get(user.id)
    if state is not None:
        # Setup owns the conversation until it finishes or is cancelled, so a
        # typed message here is a business name — never a transaction. Without
        # this, "Warung Mbok Rina" would fall through to the parser and come
        # back as "nggak ketemu nominalnya".
        if state.step == "awaiting_timezone":
            await _ask_onboarding_timezone(deps, user)
        else:
            await _propose_business_name(deps, user, cmd.text)
        return

    today = deps.clock.today_local(user.timezone)
    result = await deps.record_transactions.execute(user.id, cmd.text, today)

    lines: list[str] = []
    if result.recorded:
        lines.append(f"Tercatat {len(result.recorded)} transaksi:")
        for tx in result.recorded:
            marker = "+" if tx.kind == "sale" else "-"
            suffix = " ⚠️" if tx.flagged else ""
            lines.append(
                f"{marker}Rp {tx.total_amount:,}".replace(",", ".") + f" {tx.item}{suffix}"
            )
        lines.append("")
        lines.append(f"Total hari ini: Rp {result.today_total.profit:,}".replace(",", "."))
        if any(tx.flagged for tx in result.recorded):
            # FR-1: the flag is metadata — it never rejects and never asks, so
            # this is a passive note. Without it a flagged row with an
            # unambiguous verb ("dapet duit 50k") was recorded looking exactly
            # like business income, and the flag only became visible much
            # later at `/lapor`'s review gate (FR-2).
            lines.append("")
            lines.append(
                "⚠️ Ada yang kelihatannya bukan pemasukan usaha. "
                "Pas /lapor nanti kamu bisa keluarkan dari laporan."
            )

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

    if data.startswith((REVIEW_EXCLUDE_PREFIX, REVIEW_KEEP_PREFIX)):
        await _handle_review_callback(deps, update, data)
        return

    if data.startswith(OB_PREFIX):
        await _handle_onboarding_callback(deps, update, data)
        return

    if data.startswith(TZ_PREFIX):
        await _handle_timezone_callback(deps, update, data)
        return

    if not data.startswith("choice:"):
        return
    choice = data.removeprefix("choice:")

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

    if choice == CHOICE_OTHER:
        # FR-3: "Bukan Usaha" — record with kind=default (sale, per Q3),
        # never flagged (the user has already made the call), excluded.
        resolved = parsed.model_copy(update={"kind": "sale", "flagged": False})
        await deps.record_transactions.confirm(user.id, resolved, excluded_from_report=True)
        await deps.messaging.send_text(user.id, "Oke, gak dimasukkan ke laporan usaha.")
        await _ask_next_pending(deps, user)
        return

    kind = _KIND_BY_CHOICE.get(choice)
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
