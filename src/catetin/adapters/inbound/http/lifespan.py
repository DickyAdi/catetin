"""App lifespan — startup order per Modules M5-M8 §M6 / Async & Resource Design §5:

1. Build engines/session factories.
2. Verify the schema revision (`alembic_version` vs `EXPECTED_DB_REVISION`) —
   never runs a migration; mismatch propagates and aborts startup.
3. Wire the composition root (ports -> adapters).
4. Start the scheduler hook (Phase 6 fills this in).
5. Shutdown: dispose engines.
"""

import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from catetin import composition
from catetin.adapters.outbound.persistence.version_check import check_db_revision
from catetin.config import Settings

from .state import AppState


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engines = composition.create_engines(settings)
        await check_db_revision(engines.reader, settings.expected_db_revision)
        deps = composition.wire(settings, engines)

        app.state.catetin = AppState(
            settings=settings,
            writer_engine=engines.writer,
            reader_engine=engines.reader,
            clock=deps.clock,
            started_at=time.monotonic(),
        )
        # Phase 6 will start the asyncio scheduler task (M8) here.
        app.state.scheduler_task = None

        try:
            yield
        finally:
            await engines.writer.dispose()
            await engines.reader.dispose()

    return lifespan
