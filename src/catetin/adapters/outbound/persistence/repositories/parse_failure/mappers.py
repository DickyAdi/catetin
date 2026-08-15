"""ParseFailureRow <-> pydantic `ParseFailure` conversion.

Repositories return domain objects, never ORM instances or `Row`s — this
function is the only place that boundary is crossed for parse failures.
"""

from catetin.domain.models import ParseFailure

from ...models import ParseFailureRow


def parse_failure_to_domain(row: ParseFailureRow) -> ParseFailure:
    return ParseFailure(
        id=row.id,
        user_id=row.user_id,
        raw_text=row.raw_text,
        reason=row.reason,
        created_at=row.created_at,
    )
