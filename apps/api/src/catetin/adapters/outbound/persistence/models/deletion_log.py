"""DeletionLogRow — the `deletion_log` table (migration 0004).

Intentionally has no `user_id`, no `platform_user_id` and no free text: it is
the audit trail for `/hapusakun`, and an audit trail that identified the
person who asked to be forgotten would defeat the erasure it records.
"""

from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import EAGER_DEFAULTS, Base


class DeletionLogRow(Base):
    __tablename__ = "deletion_log"
    __mapper_args__ = EAGER_DEFAULTS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deleted_at: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    rows_deleted: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = ({"sqlite_autoincrement": True},)
