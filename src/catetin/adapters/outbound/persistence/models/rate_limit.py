"""RateLimitRow — the `rate_limits` table (Data Model doc §8)."""

from sqlalchemy import ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RateLimitRow(Base):
    __tablename__ = "rate_limits"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    bucket: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. 'pdf'
    window_start: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = ({"sqlite_with_rowid": False},)
