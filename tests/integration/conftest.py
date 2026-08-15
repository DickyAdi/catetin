from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import command
from catetin.adapters.outbound.persistence.engine import (
    create_writer_engine,
    session_factory,
)
from catetin.config import Settings
from tests.fakes.frozen_clock import FrozenClock

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'catetin.db'}"


@pytest.fixture
def migrated_settings(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("CATETIN_DATABASE_URL", database_url)
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")
    return Settings(
        telegram_bot_token="test-token",
        telegram_webhook_secret="test-secret",
        ops_username="test-ops",
        ops_password="test-ops-pass",
        database_url=database_url,
    )


@pytest.fixture
async def writer_engine(migrated_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_writer_engine(migrated_settings)
    yield engine
    await engine.dispose()


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 8, 15, 12, 0, tzinfo=UTC))


@pytest.fixture
def sessionmaker(writer_engine: AsyncEngine):
    return session_factory(writer_engine)
