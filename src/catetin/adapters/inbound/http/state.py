"""Typed view of `app.state`, set up in `lifespan.py`.

Routes read from this instead of poking at `composition.py` directly — the
composition root stays the only place adapters are constructed.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine

from catetin.config import Settings
from catetin.domain.ports.clock import ClockPort
from catetin.domain.ports.repositories import UnitOfWork

APP_VERSION = "0.1.0"


@dataclass
class AppState:
    settings: Settings
    writer_engine: AsyncEngine
    reader_engine: AsyncEngine
    clock: ClockPort
    started_at: float
    reader_uow_factory: Callable[[], UnitOfWork]
    on_webhook_update: Callable[[bytes], Awaitable[None]] | None = None


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.catetin
    return state
