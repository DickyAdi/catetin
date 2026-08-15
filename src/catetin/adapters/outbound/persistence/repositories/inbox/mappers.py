"""InboxRow <-> raw payload conversion.

Repositories return domain objects, never ORM instances or `Row`s — this
function is the only place that boundary is crossed for the inbox.
"""

from ...models import InboxRow


def inbox_row_from_payload(update_id: int, payload: bytes) -> InboxRow:
    return InboxRow(update_id=update_id, payload=payload)
