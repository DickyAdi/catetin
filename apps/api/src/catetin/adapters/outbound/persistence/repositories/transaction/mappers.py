"""TransactionRow <-> pydantic `Transaction` conversion.

Repositories return domain objects, never ORM instances or `Row`s — these
functions are the only place that boundary is crossed for transactions.
"""

from typing import Any, cast

from catetin.domain.errors import DomainValidationError
from catetin.domain.models import ParsedTransaction, Transaction

from ...models import TransactionRow


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
        flagged=bool(row.flagged),
        excluded_from_report=bool(row.excluded_from_report),
    )


def transaction_from_core_row(row: Any) -> Transaction:
    """Same field mapping as `transaction_to_domain`, but for a Core `Row`
    selected from `TransactionRow.__table__` directly rather than the mapped
    entity — used where the query must bypass the session-wide soft-delete
    `with_loader_criteria` (the audit-trail listing needs soft-deleted rows
    too, tagged with their own status, not silently dropped)."""
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
        flagged=bool(row.flagged),
        excluded_from_report=bool(row.excluded_from_report),
    )


def transaction_values_from_parsed(
    user_id: int,
    parsed: ParsedTransaction,
    occurred_at: int,
    *,
    excluded_from_report: bool = False,
) -> dict[str, object]:
    """Column values for a persisted transaction row — shared by the single-row
    `TransactionRow(...)` constructor and bulk `insert(TransactionRow)` executemany
    dicts alike. `parsed.kind` must already be resolved (non-None) by the caller —
    ambiguous kind is an application-layer concern, not a persistence one."""
    if parsed.kind is None:
        raise DomainValidationError("cannot persist a ParsedTransaction with an ambiguous kind")
    return {
        "user_id": user_id,
        "kind": parsed.kind,
        "item": parsed.item,
        "qty": parsed.qty,
        "unit_amount": parsed.unit_amount,
        "total_amount": parsed.total_amount,
        "occurred_on": parsed.occurred_on.isoformat(),
        "occurred_at": occurred_at,
        "confidence": parsed.confidence,
        "raw_text": parsed.raw_text,
        "flagged": int(parsed.flagged),
        "excluded_from_report": int(excluded_from_report),
    }


def transaction_row_from_parsed(
    user_id: int,
    parsed: ParsedTransaction,
    occurred_at: int,
    *,
    excluded_from_report: bool = False,
) -> TransactionRow:
    return TransactionRow(
        **transaction_values_from_parsed(
            user_id, parsed, occurred_at, excluded_from_report=excluded_from_report
        )
    )
