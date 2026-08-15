"""Two async SQLAlchemy engines: one writer, one reader.

The pool *is* the lock — no `asyncio.Lock` writer serialization and no
manual reader round-robin. `pool_size=1, max_overflow=0` on the writer
gives the same "writes serialize" property the hand-rolled lock used to,
with `busy_timeout` as the backstop.
"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from catetin.config import Settings

_PRAGMAS = (
    "PRAGMA journal_mode = WAL",  # persists in the database file
    "PRAGMA synchronous = NORMAL",  # WAL-safe, ~10x faster than FULL
    "PRAGMA busy_timeout = 5000",  # 5 s
    "PRAGMA foreign_keys = ON",
    "PRAGMA cache_size = -16000",  # 16 MB page cache (negative = KiB)
    "PRAGMA temp_store = MEMORY",
    "PRAGMA mmap_size = 67108864",  # 64 MB, cheap on 4 GB
)


def _register_pragmas(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        for pragma in _PRAGMAS:
            cursor.execute(pragma)
        cursor.close()


def create_writer_engine(settings: Settings) -> AsyncEngine:
    """The pool IS the lock: pool_size=1, max_overflow=0 serializes writes."""
    engine = create_async_engine(
        settings.database_url,
        pool_size=1,
        max_overflow=0,
        echo=False,
    )
    _register_pragmas(engine)
    return engine


def create_reader_engine(settings: Settings) -> AsyncEngine:
    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_reader_pool_size,
        max_overflow=0,
        echo=False,
    )
    _register_pragmas(engine)
    return engine


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """`expire_on_commit=False`: without it every post-commit attribute access
    fires a needless lazy-refresh round trip."""
    return async_sessionmaker(engine, expire_on_commit=False)
