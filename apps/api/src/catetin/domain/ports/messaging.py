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
