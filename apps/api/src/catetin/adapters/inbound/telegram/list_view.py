"""`/list` page rendering — the text of one page and the keyboard under it.

Pure functions over a `TransactionPage`, kept out of `handlers.py` because the
length guarantee below is the interesting part of `/list` and deserves to be
testable without building an `Update`.

Why the guarantee matters here specifically: `MessagingPort.send_text` chunks
long text across several messages, but `ask_action` cannot — a keyboard belongs
to exactly one message, so the page and its buttons have to fit in one. An
oversized `sendMessage` is not truncated by Telegram, it is rejected (400), and
`TelegramSender._send` logs that and returns, so the user would tap "next" and
get silence. Hence every line is hard-capped rather than merely expected to fit.

The callback payload is the offset itself (`list:20`), not an index into
server-side state. There is deliberately no `TelegramDeps` entry for `/list`:

  - a keyboard scrolled back to next week still works, and after a restart too;
  - two `/list` messages in the same chat page independently, instead of
    fighting over one "current page" per user;
  - nothing has to be cleaned up when the user sends a new message, so no
    handler needs to know `/list` exists to avoid leaving stale state behind.

Rows that vanish under an old keyboard (a `/batal` between render and tap) are
handled by clamping in `ManageTransactions.list_page`, not by expiry.
"""

from __future__ import annotations

from catetin.application.manage_transactions import TransactionPage

# Telegram's sendMessage caps `text` at 4096 characters. We render under a
# lower ceiling so the exact per-line arithmetic never has to be right to the
# byte, and so an emoji miscount cannot walk us into a rejected message.
TELEGRAM_TEXT_LIMIT = 4096
SAFE_TEXT_LIMIT = 4000

LIST_PREFIX = "list:"
LIST_NOOP = "list:noop"  # the page indicator: a label that has to carry data
LIST_CLOSE = "list:tutup"

_ELLIPSIS = "…"


def render_page(page: TransactionPage) -> str:
    """The page body: a header, then one line per transaction.

    Line numbers are absolute (page 2 starts at 11), so the number a user reads
    out matches the position in their history, not in the current window.
    """
    first = page.offset + 1
    last = page.offset + len(page.items)
    header = f"📋 Transaksi {first}-{last} dari {page.total}"

    # Budget per line, so the whole page fits under SAFE_TEXT_LIMIT no matter
    # what is in `item` — `Transaction.item` has no length cap of its own
    # (`ParsedTransaction` caps at 80, but rows can also arrive from an import),
    # and one pathological row must not take the page down with it.
    n = len(page.items)
    budget = max(1, (SAFE_TEXT_LIMIT - len(header) - n) // n) if n else 0

    lines = [header]
    for i, tx in enumerate(page.items, start=first):
        marker = "+" if tx.kind == "sale" else "-"
        amount = f"{marker}Rp {tx.total_amount:,}".replace(",", ".")
        prefix = "🚫 " if tx.excluded_from_report else ""
        line = f"{i}. {prefix}[{tx.id}] {amount} {tx.item} ({tx.occurred_on})"
        if len(line) > budget:
            line = line[: budget - 1] + _ELLIPSIS
        lines.append(line)
    return "\n".join(lines)


def page_buttons(page: TransactionPage) -> list[tuple[str, str]]:
    """Navigation for one page, or `[]` when everything fits on a single page.

    An empty list is the signal to send the page as plain text instead of a
    keyboard — a lone "close" button under a 3-row list is noise.
    """
    if page.total <= page.page_size:
        return []

    size = page.page_size
    current = page.offset // size + 1
    pages = (page.total + size - 1) // size

    buttons: list[tuple[str, str]] = []
    if page.offset > 0:
        buttons.append(("⬅️", f"{LIST_PREFIX}{max(0, page.offset - size)}"))
    buttons.append((f"Hal {current}/{pages}", LIST_NOOP))
    if page.offset + size < page.total:
        buttons.append(("➡️", f"{LIST_PREFIX}{page.offset + size}"))
    buttons.append(("✖️ Tutup", LIST_CLOSE))
    return buttons
