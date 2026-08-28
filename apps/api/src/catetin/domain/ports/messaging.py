from typing import Protocol


class MessagingPort(Protocol):
    """Outbound messaging, shaped as intent rather than platform widgets.

    Telegram inline keyboards have no WhatsApp Cloud API equivalent, so this
    port never exposes anything shaped like `send_inline_keyboard` — only
    `ask_choice`, which each adapter renders however its platform allows.
    """

    async def send_text(self, user_id: int, text: str) -> None: ...

    async def send_document(
        self, user_id: int, filename: str, content: bytes, caption: str | None = None
    ) -> None: ...

    async def ask_choice(self, user_id: int, prompt: str, options: list[str]) -> None: ...

    async def ask_action(
        self, user_id: int, prompt: str, buttons: list[tuple[str, str]]
    ) -> None:
        """Like `ask_choice`, but each button carries its own opaque
        `callback_data` (label, data) instead of deriving it from the label —
        needed where the choice must encode state statelessly (FR-2 review
        gate: the report period, so no server-side session is kept)."""
        ...

    async def update_message(
        self,
        user_id: int,
        message_id: int,
        text: str,
        buttons: list[tuple[str, str]] | None = None,
    ) -> None:
        """Replace what an already-sent message says, in place.

        `message_id` is whatever the adapter handed out for that message — an
        opaque handle here, not a Telegram concept; a caller only ever gets one
        back from the same adapter (for Telegram, off the tap that triggered
        this call).

        `buttons` follows `ask_action`; `None` (or an empty list) leaves the
        message with no buttons at all, which is the only way to retire a
        keyboard once its question has been answered.

        Best-effort, like every other send: a message too old to edit, or one
        already carrying this exact text, is not an error the caller can act
        on. Unlike `send_text` the text cannot be split across messages, so the
        caller owns keeping it inside one — see `list_view` for `/list`'s take.
        """
        ...
