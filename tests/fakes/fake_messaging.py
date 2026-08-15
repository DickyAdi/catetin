"""FakeMessaging — MessagingPort double that records what was sent."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SentText:
    user_id: int
    text: str


@dataclass
class SentDocument:
    user_id: int
    filename: str
    content: bytes
    caption: str | None


@dataclass
class AskedChoice:
    user_id: int
    prompt: str
    options: list[str]


@dataclass
class FakeMessaging:
    texts: list[SentText] = field(default_factory=list)
    documents: list[SentDocument] = field(default_factory=list)
    choices: list[AskedChoice] = field(default_factory=list)

    async def send_text(self, user_id: int, text: str) -> None:
        self.texts.append(SentText(user_id=user_id, text=text))

    async def send_document(
        self, user_id: int, filename: str, content: bytes, caption: str | None = None
    ) -> None:
        self.documents.append(
            SentDocument(user_id=user_id, filename=filename, content=content, caption=caption)
        )

    async def ask_choice(self, user_id: int, prompt: str, options: list[str]) -> None:
        self.choices.append(AskedChoice(user_id=user_id, prompt=prompt, options=options))
