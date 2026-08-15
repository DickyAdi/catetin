"""ParseFailureRow — the `parse_failures` table (Data Model doc §7)."""

from sqlalchemy import ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import EAGER_DEFAULTS, Base


class ParseFailureRow(Base):
    __tablename__ = "parse_failures"
    __mapper_args__ = EAGER_DEFAULTS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # no_amount | ambiguous_kind | too_many_segments | ...
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    __table_args__ = (
        Index("idx_parse_failures_time", "created_at"),
        {"sqlite_autoincrement": True},
    )
