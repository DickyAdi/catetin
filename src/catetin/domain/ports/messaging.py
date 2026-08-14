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
