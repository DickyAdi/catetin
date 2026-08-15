"""Declarative persistence rows — the DDL of the Data Model doc §4-8, in SQLAlchemy.

These classes are persistence rows, not domain models. Domain models are the
pydantic `BaseModel`s in `domain/models.py`; `mappers.py` converts between the
two. Repositories return domain objects, never ORM instances or `Row`s.
"""

from sqlalchemy import (
    REAL,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Text,
    desc,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """All persistence tables. No domain logic here."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Server-generated columns (created_at, updated_at, received_at) are fetched
# back via RETURNING on insert so repositories can hand back a fully
# populated domain object without a second round trip.
_EAGER_DEFAULTS = {"eager_defaults": True}


class UserRow(Base):
    __tablename__ = "users"
    __mapper_args__ = _EAGER_DEFAULTS

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


class TransactionRow(Base):
    __tablename__ = "transactions"
    __mapper_args__ = _EAGER_DEFAULTS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    item: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'(tanpa nama)'")
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    unit_amount: Mapped[int | None] = mapped_column(Integer)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_on: Mapped[str] = mapped_column(Text, nullable=False)  # 'YYYY-MM-DD', user-local
    occurred_at: Mapped[int] = mapped_column(Integer, nullable=False)  # unix epoch, ordering
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'regex'"))
    confidence: Mapped[float] = mapped_column(REAL, nullable=False, server_default=text("1.0"))
    raw_text: Mapped[str | None] = mapped_column(Text)  # truncated to 500 chars by the use case
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )
    deleted_at: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("kind IN ('sale','expense')", name="kind_known"),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("unit_amount IS NULL OR unit_amount >= 0", name="unit_amount_nonneg"),
        CheckConstraint("total_amount > 0", name="total_amount_positive"),
        CheckConstraint("source IN ('regex','llm','manual')", name="source_known"),
        # Hot path: every summary is "one user, one date range, not deleted".
        Index(
            "idx_tx_user_date",
            "user_id",
            "occurred_on",
            sqlite_where=text("deleted_at IS NULL"),
        ),
        # /list and /batal
        Index(
            "idx_tx_user_recent",
            "user_id",
            desc("created_at"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        # top-items aggregation
        Index(
            "idx_tx_user_item",
            "user_id",
            "kind",
            "item",
            sqlite_where=text("deleted_at IS NULL"),
        ),
        {"sqlite_autoincrement": True},
    )


class InboxRow(Base):
    __tablename__ = "inbox"
    __mapper_args__ = _EAGER_DEFAULTS

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


class ParseFailureRow(Base):
    __tablename__ = "parse_failures"
    __mapper_args__ = _EAGER_DEFAULTS

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


class RateLimitRow(Base):
    __tablename__ = "rate_limits"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    bucket: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. 'pdf'
    window_start: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = ({"sqlite_with_rowid": False},)
