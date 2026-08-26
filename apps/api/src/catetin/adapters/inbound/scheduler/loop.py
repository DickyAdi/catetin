"""Scheduler loop (M8) — a single long-lived asyncio task, started in the
HTTP lifespan, that wakes every 60 s and fires any job whose window is due.
No APScheduler, no cron container, no Celery.

Each job is wrapped in try/except so one failing job never kills the loop
(per the M8 edge-case table). Fire times are recomputed from `ClockPort`
each tick rather than sleeping a fixed delta, so a wall-clock jump is
handled for free and the whole thing is testable against a frozen clock.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncEngine

from catetin.config import Settings
from catetin.domain.ports.clock import ClockPort
from catetin.domain.ports.messaging import MessagingPort
from catetin.domain.ports.repositories import UnitOfWork

from . import jobs

_logger = logging.getLogger("catetin.scheduler.loop")

CHECK_INTERVAL_SECONDS = 60
BACKUP_HOUR = 2
BACKUP_MINUTE = 0
PRUNE_HOUR = 2
PRUNE_MINUTE = 30


def is_due(
    now: datetime, target_hour: int, target_minute: int, today: date, last_run: date | None
) -> bool:
    """True once, the first tick on or after `target_hour:target_minute`
    local time, per calendar day — never twice on the same `today`."""
    if last_run == today:
        return False
    return (now.hour, now.minute) >= (target_hour, target_minute)


@dataclass
class SchedulerState:
    last_digest: date | None = None
    last_backup: date | None = None
    last_prune: date | None = None
    last_wal_checkpoint: date | None = None


async def _safe(name: str, awaitable: Coroutine[Any, Any, Any]) -> None:
    try:
        await awaitable
    except Exception:
        _logger.exception("scheduler job %s failed", name)


async def run_once(
    *,
    settings: Settings,
    clock: ClockPort,
    uow: UnitOfWork,
    messaging: MessagingPort,
    writer_engine: AsyncEngine,
    state: SchedulerState,
) -> None:
    tz = ZoneInfo(settings.timezone)
    now = clock.now().astimezone(tz)
    today = clock.today_local(settings.timezone)

    if is_due(now, settings.digest_hour_local, 0, today, state.last_digest):
        await _safe("digest", jobs.run_digest(uow, clock, messaging))
        state.last_digest = today

    if is_due(now, BACKUP_HOUR, BACKUP_MINUTE, today, state.last_backup):
        await _safe(
            "backup",
            jobs.run_backup(
                settings.database_url,
                Path(settings.backup_dir),
                today.isoformat(),
                settings.backup_keep_n,
                settings.backup_age_recipient,
            ),
        )
        state.last_backup = today
        await _safe("wal_checkpoint", jobs.run_wal_checkpoint(writer_engine))
        state.last_wal_checkpoint = today

    if is_due(now, PRUNE_HOUR, PRUNE_MINUTE, today, state.last_prune):
        await _safe("prune", jobs.run_prune(uow, clock))
        state.last_prune = today


async def run_scheduler(
    *,
    settings: Settings,
    clock: ClockPort,
    uow: UnitOfWork,
    messaging: MessagingPort,
    writer_engine: AsyncEngine,
    stop_event: asyncio.Event,
) -> None:
    state = SchedulerState()
    while not stop_event.is_set():
        await run_once(
            settings=settings,
            clock=clock,
            uow=uow,
            messaging=messaging,
            writer_engine=writer_engine,
            state=state,
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CHECK_INTERVAL_SECONDS)
        except TimeoutError:
            pass
