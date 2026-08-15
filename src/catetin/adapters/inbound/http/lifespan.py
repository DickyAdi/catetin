"""App lifespan — startup order per Modules M5-M8 §M6 / Async & Resource Design §5:

1. Build engines/session factories.
2. Verify the schema revision (`alembic_version` vs `EXPECTED_DB_REVISION`) —
   never runs a migration; mismatch propagates and aborts startup.
3. Wire the composition root (ports -> adapters) — this also constructs the
   PTB `Application` and the Telegram sender.
4. initialize()/start() the PTB `Application`; wire the webhook dispatcher.
5. Replay unprocessed `inbox` rows from a prior crash.
6. Start the scheduler task (M8).
7. Shutdown: stop the scheduler (10 s grace, then cancel), stop/shutdown the
   PTB `Application`, dispose engines.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress

import orjson
from fastapi import FastAPI

from catetin import composition
from catetin.adapters.inbound.scheduler.loop import run_scheduler
from catetin.adapters.inbound.telegram import application as telegram_app
from catetin.adapters.outbound.persistence.version_check import check_db_revision
from catetin.application.replay_inbox import ReplayInbox
from catetin.config import Settings

from .state import AppState

_logger = logging.getLogger("catetin.lifespan")

SHUTDOWN_GRACE_SECONDS = 10


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engines = composition.create_engines(settings)
        await check_db_revision(engines.reader, settings.expected_db_revision)
        deps = composition.wire(settings, engines)

        await deps.telegram_application.initialize()
        await deps.telegram_application.start()

        async def on_webhook_update(body: bytes) -> None:
            """Durable enqueue: store the raw update, ack, only then dispatch.

            Marking the row processed happens right after the update is
            handed to PTB's `update_queue`, not after the handler actually
            finishes — PTB's queue-based dispatch has no synchronous
            "handler done" signal to wait on. A crash between enqueue and
            actual handling is the same at-least-once gap the startup
            replay below already exists to cover.

            Uses `writer_uow_factory` (a fresh session per block), not the
            shared `deps.uow` the Telegram handlers use — this closure runs
            on the HTTP request task, concurrently with PTB's fetcher task
            processing the very update just enqueued below.
            """
            payload = orjson.loads(body)
            update_id = payload.get("update_id")
            if not isinstance(update_id, int):
                return
            async with deps.writer_uow_factory() as uow:
                is_new = await uow.inbox.add_if_new(update_id, body)
                await uow.commit()
            if not is_new:
                return
            await telegram_app.feed_update(deps.telegram_application, payload)
            async with deps.writer_uow_factory() as uow:
                await uow.inbox.mark_processed(update_id)
                await uow.commit()

        app.state.catetin = AppState(
            settings=settings,
            writer_engine=engines.writer,
            reader_engine=engines.reader,
            clock=deps.clock,
            started_at=time.monotonic(),
            reader_uow_factory=deps.reader_uow_factory,
            on_webhook_update=on_webhook_update,
            telegram_update_queue=deps.telegram_application.update_queue,
        )

        async def _replay_dispatch(_update_id: int, payload: bytes) -> None:
            await telegram_app.feed_update(deps.telegram_application, orjson.loads(payload))

        replayed = await ReplayInbox(deps.writer_uow_factory()).execute(_replay_dispatch)
        if replayed:
            _logger.info("replayed %d unprocessed inbox row(s)", replayed)

        stop_event = asyncio.Event()
        scheduler_task = asyncio.create_task(
            run_scheduler(
                settings=settings,
                clock=deps.clock,
                uow=deps.writer_uow_factory(),
                messaging=deps.messaging,
                writer_engine=engines.writer,
                stop_event=stop_event,
            )
        )
        app.state.scheduler_task = scheduler_task

        try:
            yield
        finally:
            stop_event.set()
            try:
                await asyncio.wait_for(scheduler_task, timeout=SHUTDOWN_GRACE_SECONDS)
            except TimeoutError:
                scheduler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await scheduler_task

            await deps.telegram_application.stop()
            await deps.telegram_application.shutdown()

            await engines.writer.dispose()
            await engines.reader.dispose()

    return lifespan
