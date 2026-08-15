"""ORM row <-> pydantic domain model conversion.

Repositories return domain objects, never ORM instances or `Row`s — these
functions are the only place that boundary is crossed. Pydantic domain
models (`domain/models.py`) stay the single source of truth for validation.
"""

from typing import cast

from catetin.domain.errors import DomainValidationError
from catetin.domain.models import ParsedTransaction, ParseFailure, Transaction, User

from .orm import InboxRow, ParseFailureRow, TransactionRow, UserRow


def user_to_domain(row: UserRow) -> User:
    return User(
        id=row.id,
        platform=cast('str', row.platform),  # type: ignore[arg-type]
        platform_user_id=row.platform_user_id,
        display_name=row.display_name,
        business_name=row.business_name,
        timezone=row.timezone,
        digest_enabled=bool(row.digest_enabled),
        blocked_at=row.blocked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def transaction_to_domain(row: TransactionRow) -> Transaction:
    return Transaction(
        id=row.id,
        user_id=row.user_id,
        kind=cast('str', row.kind),  # type: ignore[arg-type]
        item=row.item,
        qty=row.qty,
        unit_amount=row.unit_amount,
        total_amount=row.total_amount,
        occurred_on=row.occurred_on,
        occurred_at=row.occurred_at,
        source=cast('str', row.source),  # type: ignore[arg-type]
        confidence=row.confidence,
        raw_text=row.raw_text,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )


def parse_failure_to_domain(row: ParseFailureRow) -> ParseFailure:
    return ParseFailure(
        id=row.id,
        user_id=row.user_id,
        raw_text=row.raw_text,
        reason=row.reason,
        created_at=row.created_at,
    )


def transaction_row_from_parsed(
    user_id: int, parsed: ParsedTransaction, occurred_at: int
) -> TransactionRow:
    """`parsed.kind` must already be resolved (non-None) by the caller —
    ambiguous kind is an application-layer concern, not a persistence one."""
    if parsed.kind is None:
        raise DomainValidationError("cannot persist a ParsedTransaction with an ambiguous kind")
    return TransactionRow(
        user_id=user_id,
        kind=parsed.kind,
        item=parsed.item,
        qty=parsed.qty,
        unit_amount=parsed.unit_amount,
        total_amount=parsed.total_amount,
        occurred_on=parsed.occurred_on.isoformat(),
        occurred_at=occurred_at,
        confidence=parsed.confidence,
        raw_text=parsed.raw_text,
    )


def inbox_row_from_payload(update_id: int, payload: bytes) -> InboxRow:
    return InboxRow(update_id=update_id, payload=payload)
