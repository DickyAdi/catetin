"""`telegram.Update` -> command DTO. The only place that reads Telegram field
names; handlers work with `InboundCommand`, never `telegram.Update` directly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from telegram import Update


class InboundCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: Literal["telegram"] = "telegram"
    platform_user_id: str
    chat_id: int
    display_name: str | None
    text: str
    sent_at: int  # unix epoch, from Update.message.date
    update_id: int


def map_update(update: Update) -> InboundCommand | None:
    """`None` for updates with no text (stickers, edits, etc.) — the caller
    decides how to respond to those; the mapper only extracts what it can."""
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None or message.text is None:
        return None

    return InboundCommand(
        platform_user_id=str(user.id),
        chat_id=message.chat_id,
        display_name=user.full_name or user.username,
        text=message.text,
        sent_at=int(message.date.timestamp()) if message.date else 0,
        update_id=update.update_id,
    )
