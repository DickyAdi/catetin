"""UserRow <-> pydantic `User` conversion.

Repositories return domain objects, never ORM instances or `Row`s — this
function is the only place that boundary is crossed for users.
"""

from typing import cast

from catetin.domain.models import User

from ...models import UserRow


def user_to_domain(row: UserRow) -> User:
    return User(
        id=row.id,
        platform=cast('str', row.platform),  # type: ignore[arg-type]
        platform_user_id=row.platform_user_id,
        display_name=row.display_name,
        business_name=row.business_name,
        timezone=row.timezone,
        digest_enabled=bool(row.digest_enabled),
        has_onboarded=bool(row.has_onboarded),
        blocked_at=row.blocked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
