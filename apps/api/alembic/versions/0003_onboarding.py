"""onboarding — has_onboarded flag on users

Revision ID: 0003_onboarding
Revises: 0002_report_scope
Create Date: 2026-08-26

Hand-written, same reasoning as 0001/0002: SQLite ADD COLUMN with an inline
CHECK is a raw-DDL concern autogenerate does not reliably round-trip. The
column defaults to 0, so every existing user is "not onboarded yet" and gets
the `/start` flow on their next `/start` — nobody is locked out, `/lapor` just
asks them to set up first (NFR-4).

Booleans in this schema are INTEGER + CHECK (see `digest_enabled` in 0001),
not sa.Boolean — keeping the storage type identical to the ORM's `Integer`
mapping is what keeps `alembic check` free of drift.
"""

from alembic import op

revision = "0003_onboarding"
down_revision = "0002_report_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN has_onboarded INTEGER NOT NULL "
        "DEFAULT 0 CHECK(has_onboarded IN (0,1))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN has_onboarded")
