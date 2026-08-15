"""UserRow — the `users` table (Data Model doc §4)."""

from sqlalchemy import CheckConstraint, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import EAGER_DEFAULTS, Base


class UserRow(Base):
    __tablename__ = "users"
    __mapper_args__ = EAGER_DEFAULTS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    platform_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    business_name: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'Asia/Jakarta'")
    )
    digest_enabled: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    blocked_at: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    __table_args__ = (
        CheckConstraint("platform IN ('telegram','whatsapp')", name="platform_known"),
        CheckConstraint("digest_enabled IN (0,1)", name="digest_bool"),
        Index("idx_users_platform_uid", "platform", "platform_user_id", unique=True),
        Index(
            "idx_users_digest",
            "digest_enabled",
            sqlite_where=text("blocked_at IS NULL"),
        ),
        {"sqlite_autoincrement": True},
    )
