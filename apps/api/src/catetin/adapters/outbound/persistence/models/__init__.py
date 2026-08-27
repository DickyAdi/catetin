"""Declarative persistence rows — the DDL of the Data Model doc §4-8, in SQLAlchemy.

These classes are persistence rows, not domain models. Domain models are the
pydantic `BaseModel`s in `domain/models.py`; each repository's `mappers.py`
converts between the two. Repositories return domain objects, never ORM
instances or `Row`s.
"""

from .base import Base
from .deletion_log import DeletionLogRow
from .inbox import InboxRow
from .parse_failure import ParseFailureRow
from .rate_limit import RateLimitRow
from .transaction import TransactionRow
from .user import UserRow

__all__ = [
    "Base",
    "DeletionLogRow",
    "InboxRow",
    "ParseFailureRow",
    "RateLimitRow",
    "TransactionRow",
    "UserRow",
]
