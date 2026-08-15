"""InboxRow — the `inbox` table (Data Model doc §6)."""

from sqlalchemy import Index, Integer, LargeBinary, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import EAGER_DEFAULTS, Base


class InboxRow(Base):
    __tablename__ = "inbox"
    __mapper_args__ = EAGER_DEFAULTS

    update_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Telegram's own id
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # orjson-encoded
    received_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )
    processed_at: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index(
            "idx_inbox_unprocessed",
            "received_at",
            sqlite_where=text("processed_at IS NULL"),
        ),
    )
