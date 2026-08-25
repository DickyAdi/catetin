"""Scheduler jobs (M8) — logic only, against fakes and a frozen clock.

No real PTB Application, no real network; `run_backup` uses a real (tiny,
tmp_path) SQLite file because `VACUUM INTO` is the thing under test.
"""

import sqlite3
from datetime import UTC, date, datetime

from catetin.adapters.inbound.scheduler import jobs, loop
from catetin.domain.models import ParsedTransaction
from tests.fakes.fake_messaging import FakeMessaging
from tests.fakes.fake_repositories import FakeUnitOfWork
from tests.fakes.frozen_clock import FrozenClock


def _parsed(total_amount: int, occurred_on: date) -> ParsedTransaction:
    return ParsedTransaction(
        kind="sale",
        item="Ayam",
        qty=1,
        unit_amount=None,
        total_amount=total_amount,
        occurred_on=occurred_on,
        confidence=1.0,
        raw_text="jual ayam 50rb",
    )


# --- is_due --------------------------------------------------------------


def test_is_due_fires_once_after_target_hour() -> None:
    today = date(2026, 8, 15)
    now = datetime(2026, 8, 15, 21, 5, tzinfo=UTC)

    assert loop.is_due(now, 21, 0, today, None) is True
    assert loop.is_due(now, 21, 0, today, today) is False  # already ran today


def test_is_due_not_yet_at_target_hour() -> None:
    today = date(2026, 8, 15)
    now = datetime(2026, 8, 15, 20, 59, tzinfo=UTC)

    assert loop.is_due(now, 21, 0, today, None) is False


def test_is_due_fires_again_on_a_new_day() -> None:
    today = date(2026, 8, 16)
    now = datetime(2026, 8, 16, 21, 0, tzinfo=UTC)

    assert loop.is_due(now, 21, 0, today, date(2026, 8, 15)) is True


# --- digest ----------------------------------------------------------------


async def test_run_digest_sends_yesterdays_summary_to_opted_in_users() -> None:
    clock = FrozenClock(datetime(2026, 8, 15, 22, 0, tzinfo=UTC))
    uow = FakeUnitOfWork(clock)
    messaging = FakeMessaging()

    async with uow as u:
        user = await u.users.create("telegram", "111", "Rina")
        # clock is 2026-08-15 22:00 UTC = 2026-08-16 05:00 Asia/Jakarta (the
        # user's default timezone), so "yesterday" there is the 15th, not UTC's.
        await u.transactions.add(user.id, _parsed(50_000, date(2026, 8, 15)))
        await u.commit()

    sent = await jobs.run_digest(uow, clock, messaging)

    assert sent == 1
    assert len(messaging.texts) == 1
    assert messaging.texts[0].user_id == user.id
    assert "50.000" in messaging.texts[0].text


async def test_run_digest_skips_users_with_no_transactions_yesterday() -> None:
    clock = FrozenClock(datetime(2026, 8, 15, 22, 0, tzinfo=UTC))
    uow = FakeUnitOfWork(clock)
    messaging = FakeMessaging()

    async with uow as u:
        await u.users.create("telegram", "222", "Dedi")
        await u.commit()

    sent = await jobs.run_digest(uow, clock, messaging)

    assert sent == 0
    assert messaging.texts == []


async def test_run_digest_skips_users_with_digest_disabled() -> None:
    clock = FrozenClock(datetime(2026, 8, 15, 22, 0, tzinfo=UTC))
    uow = FakeUnitOfWork(clock)
    messaging = FakeMessaging()

    async with uow as u:
        user = await u.users.create("telegram", "333", "Budi")
        await u.transactions.add(user.id, _parsed(50_000, date(2026, 8, 14)))
        await u.users.set_digest_enabled(user.id, False)
        await u.commit()

    sent = await jobs.run_digest(uow, clock, messaging)

    assert sent == 0
    assert messaging.texts == []


# --- prune -------------------------------------------------------------


async def test_run_prune_deletes_only_old_rows() -> None:
    clock = FrozenClock(datetime(2026, 8, 15, 2, 30, tzinfo=UTC))
    uow = FakeUnitOfWork(clock)

    clock.advance(days=-100)
    async with uow as u:
        await u.parse_failures.add(None, "old failure", "no_amount")
        await u.inbox.add_if_new(1, b"{}")
        await u.inbox.mark_processed(1)
        await u.commit()
    clock.advance(days=100)

    async with uow as u:
        await u.parse_failures.add(None, "recent failure", "no_amount")
        await u.inbox.add_if_new(2, b"{}")
        await u.inbox.mark_processed(2)
        await u.commit()

    deleted_failures, deleted_inbox = await jobs.run_prune(uow, clock)

    assert deleted_failures == 1
    assert deleted_inbox == 1
    async with uow as u:
        remaining = await u.parse_failures.list_recent()
        assert [f.raw_text for f in remaining] == ["recent failure"]


async def test_run_prune_keeps_unprocessed_inbox_rows_regardless_of_age() -> None:
    clock = FrozenClock(datetime(2026, 8, 15, 2, 30, tzinfo=UTC))
    uow = FakeUnitOfWork(clock)

    clock.advance(days=-100)
    async with uow as u:
        await u.inbox.add_if_new(1, b"{}")  # never marked processed
        await u.commit()
    clock.advance(days=100)

    _, deleted_inbox = await jobs.run_prune(uow, clock)

    assert deleted_inbox == 0


# --- backup --------------------------------------------------------------


def _make_sqlite_file(path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()


async def test_run_backup_creates_timestamped_file(tmp_path) -> None:
    db_path = tmp_path / "catetin.db"
    _make_sqlite_file(db_path)
    backup_dir = tmp_path / "backups"

    dest = await jobs.run_backup(
        f"sqlite+aiosqlite:///{db_path}", backup_dir, "2026-08-15", keep_n=7
    )

    assert dest.exists()
    assert dest.name.startswith("catetin-2026-08-15-")
    assert dest.suffix == ".db"


async def test_run_backup_twice_on_the_same_day_does_not_crash(tmp_path) -> None:
    """`VACUUM INTO` refuses to write to an existing path, so the old date-only
    filename made the second backup of a day (restart, retry, a second
    instance) die with `sqlite3.OperationalError: output file already exists`.
    """
    db_path = tmp_path / "catetin.db"
    _make_sqlite_file(db_path)
    backup_dir = tmp_path / "backups"
    url = f"sqlite+aiosqlite:///{db_path}"

    first = await jobs.run_backup(url, backup_dir, "2026-08-15", keep_n=7)
    second = await jobs.run_backup(url, backup_dir, "2026-08-15", keep_n=7)

    assert first != second
    assert first.exists()
    assert second.exists()
    assert len(list(backup_dir.glob("catetin-*.db"))) == 2


def test_next_free_dest_appends_a_counter_within_the_same_second(tmp_path) -> None:
    """Two runs inside one second share an HHMMSS stamp — the counter is what
    keeps them from colliding (the timestamp alone covers every other case)."""
    assert jobs._next_free_dest(tmp_path, "2026-08-15", "163000").name == (
        "catetin-2026-08-15-163000.db"
    )

    (tmp_path / "catetin-2026-08-15-163000.db").write_bytes(b"x")
    assert jobs._next_free_dest(tmp_path, "2026-08-15", "163000").name == (
        "catetin-2026-08-15-163000-2.db"
    )

    (tmp_path / "catetin-2026-08-15-163000-2.db").write_bytes(b"x")
    assert jobs._next_free_dest(tmp_path, "2026-08-15", "163000").name == (
        "catetin-2026-08-15-163000-3.db"
    )


async def test_run_backup_prunes_same_day_reruns_too(tmp_path) -> None:
    """Retention is a file count, not a day count — repeated same-day backups
    must not be able to grow the directory past `keep_n`."""
    db_path = tmp_path / "catetin.db"
    _make_sqlite_file(db_path)
    backup_dir = tmp_path / "backups"
    url = f"sqlite+aiosqlite:///{db_path}"

    for _ in range(5):
        await jobs.run_backup(url, backup_dir, "2026-08-15", keep_n=2)

    assert len(list(backup_dir.glob("catetin-*.db"))) == 2


async def test_run_backup_keeps_only_last_n(tmp_path) -> None:
    db_path = tmp_path / "catetin.db"
    _make_sqlite_file(db_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for day in range(1, 4):
        (backup_dir / f"catetin-2026-08-0{day}.db").write_bytes(b"x")

    await jobs.run_backup(f"sqlite+aiosqlite:///{db_path}", backup_dir, "2026-08-10", keep_n=2)

    remaining = sorted(p.name for p in backup_dir.glob("catetin-*.db"))
    assert len(remaining) == 2
    assert remaining[-1].startswith("catetin-2026-08-10-")  # today's, newest
