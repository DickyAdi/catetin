"""Runtime schema verification — never runs a migration.

Called from the M6 lifespan (step 2). `alembic upgrade head` runs before the
process starts, manually or in CI; this only checks that the database the
process is about to serve against matches what the binary expects.
"""

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine


async def check_db_revision(engine: AsyncEngine, expected: str) -> None:
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.first()
    except OperationalError as exc:
        raise RuntimeError(
            f"alembic_version table missing; expected revision {expected!r}. "
            "Run `alembic upgrade head` before starting the app."
        ) from exc

    if row is None:
        raise RuntimeError(
            f"alembic_version table is empty; expected revision {expected!r}"
        )

    actual = row[0]
    if actual != expected:
        raise RuntimeError(
            f"database schema revision mismatch: expected {expected!r}, got {actual!r}"
        )
