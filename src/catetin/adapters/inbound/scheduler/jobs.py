"""Scheduler jobs (M8): nightly digest, backup, prune, WAL checkpoint.

Each function is a plain async callable taking exactly the ports/engines it
needs — no APScheduler, no Celery, testable directly with fakes and a
frozen clock without going through `loop.py`'s sleep cycle.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine

from catetin.adapters.outbound.reporting.text_renderer import render_text
from catetin.domain.ports.clock import ClockPort
from catetin.domain.ports.messaging import MessagingPort
from catetin.domain.ports.repositories import UnitOfWork

_logger = logging.getLogger("catetin.scheduler.jobs")

PARSE_FAILURE_RETENTION_DAYS = 90
INBOX_RETENTION_DAYS = 7
DEFAULT_BACKUP_KEEP_N = 7
_SECONDS_PER_DAY = 86_400


async def run_digest(uow: UnitOfWork, clock: ClockPort, messaging: MessagingPort) -> int:
    """For opted-in, active users: yesterday's summary via `MessagingPort`."""
    sent = 0
    async with uow as u:
        users = await u.users.list_digest_enabled()
        for user in users:
            yesterday = clock.today_local(user.timezone) - timedelta(days=1)
            day = yesterday.isoformat()
            summary = await u.transactions.summarize_range(user.id, day, day)
            if summary.count == 0:
                continue
            text = render_text(summary, user.business_name, period_label="Ringkasan Kemarin")
            await messaging.send_text(user.id, text)
            sent += 1
    return sent


async def run_prune(uow: UnitOfWork, clock: ClockPort) -> tuple[int, int]:
    """Delete `parse_failures` > 90 d and processed `inbox` rows > 7 d."""
    now = int(clock.now().timestamp())
    parse_failure_cutoff = now - PARSE_FAILURE_RETENTION_DAYS * _SECONDS_PER_DAY
    inbox_cutoff = now - INBOX_RETENTION_DAYS * _SECONDS_PER_DAY
    async with uow as u:
        deleted_failures = await u.parse_failures.delete_older_than(parse_failure_cutoff)
        deleted_inbox = await u.inbox.delete_processed_older_than(inbox_cutoff)
        await u.commit()
    return deleted_failures, deleted_inbox


def _sqlite_path(database_url: str) -> str:
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if database_url.startswith(prefix):
            return database_url[len(prefix) :]
    return database_url


def _vacuum_into(db_path: str, dest: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        # `dest` is built from our own date-stamped filename, never user
        # input, so string interpolation here carries no injection risk.
        conn.execute(f"VACUUM INTO '{dest}'")
    finally:
        conn.close()


def _prune_old_backups(backup_dir: Path, keep_n: int) -> None:
    backups = sorted(backup_dir.glob("catetin-*.db"))
    for stale in backups[:-keep_n] if len(backups) > keep_n else []:
        stale.unlink(missing_ok=True)


def _do_backup(database_url: str, backup_dir: Path, today: str, keep_n: int) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"catetin-{today}.db"
    _vacuum_into(_sqlite_path(database_url), dest)
    _prune_old_backups(backup_dir, keep_n)
    return dest


async def run_backup(
    database_url: str, backup_dir: Path, today: str, keep_n: int = DEFAULT_BACKUP_KEEP_N
) -> Path:
    """`VACUUM INTO` a date-stamped file — safe against a live WAL database."""
    return await asyncio.to_thread(_do_backup, database_url, backup_dir, today, keep_n)


async def run_wal_checkpoint(writer_engine: AsyncEngine) -> None:
    async with writer_engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
