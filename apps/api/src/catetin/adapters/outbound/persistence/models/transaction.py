"""TransactionRow — the `transactions` table (Data Model doc §5)."""

from sqlalchemy import (
    REAL,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    desc,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import EAGER_DEFAULTS, Base


class TransactionRow(Base):
    __tablename__ = "transactions"
    __mapper_args__ = EAGER_DEFAULTS

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
    # 1 = high-signal non-business pattern detected (heuristic, not a classification)
    flagged: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # 1 = user excluded this from reports (review gate / "Bukan Usaha") — stays in DB
    excluded_from_report: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        CheckConstraint("kind IN ('sale','expense')", name="kind_known"),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("unit_amount IS NULL OR unit_amount >= 0", name="unit_amount_nonneg"),
        CheckConstraint("total_amount > 0", name="total_amount_positive"),
        CheckConstraint("source IN ('regex','llm','manual')", name="source_known"),
        CheckConstraint("flagged IN (0,1)", name="flagged_bool"),
        CheckConstraint("excluded_from_report IN (0,1)", name="excluded_from_report_bool"),
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
