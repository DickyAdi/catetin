"""deletion_log — proof that erasure requests were honored, with no personal data

Revision ID: 0004_deletion_log
Revises: 0003_onboarding
Create Date: 2026-08-27

Hand-written, in the style of 0001/0002. UU PDP asks a controller to be able
to show that an erasure request was carried out; it does not ask the
controller to keep identifying the person who asked. So this table records
*that* a purge happened, how big it was, and on which platform, and
deliberately carries no user id, no platform user id and no display name:
after `/hapusakun` there is nothing left in the database that points back at
the person. `sqlite_autoincrement` matches the other id-keyed tables so a
reused rowid can never make two deletions look like one.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_deletion_log"
down_revision = "0003_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deletion_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deleted_at", sa.Integer(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("rows_deleted", sa.Integer(), nullable=False),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    op.drop_table("deletion_log")
