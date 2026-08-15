"""Composition root.

This is the only module allowed to construct adapters — every `Adapter(...)`
call lives here and nowhere else (see M6 lifespan step 3 in the design
docs). `http/lifespan.py` calls `create_engines()` and `wire()` in that
order so it can verify the schema revision between them; nothing else
should import the constructors this module wraps.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .adapters.outbound.parsing.regex_parser import RegexParser
from .adapters.outbound.persistence.engine import (
    create_reader_engine,
    create_writer_engine,
    session_factory,
)
from .adapters.outbound.persistence.rate_limiter import SqliteRateLimiter
from .adapters.outbound.persistence.uow import SqlAlchemyUnitOfWork
from .adapters.outbound.system_clock import SystemClock
from .application.manage_transactions import ManageTransactions
from .application.onboarding import Onboarding
from .application.record_transactions import RecordTransactions
from .application.summarize import Summarize
from .config import Settings
from .domain.ports.clock import ClockPort
from .domain.ports.parser import ParserPort
from .domain.ports.repositories import RateLimiterPort, UnitOfWork


@dataclass
class Engines:
    writer: AsyncEngine
    writer_sessions: async_sessionmaker[AsyncSession]
    reader: AsyncEngine
    reader_sessions: async_sessionmaker[AsyncSession]


@dataclass
class Dependencies:
    clock: ClockPort
    parser: ParserPort
    rate_limiter: RateLimiterPort
    uow: UnitOfWork
    reader_uow_factory: Callable[[], UnitOfWork]
    onboarding: Onboarding
    record_transactions: RecordTransactions
    manage_transactions: ManageTransactions
    summarize: Summarize


def create_engines(settings: Settings) -> Engines:
    """Lifespan step 1: writer + reader engines and their session factories."""
    writer = create_writer_engine(settings)
    reader = create_reader_engine(settings)
    return Engines(
        writer=writer,
        writer_sessions=session_factory(writer),
        reader=reader,
        reader_sessions=session_factory(reader),
    )


def wire(settings: Settings, engines: Engines) -> Dependencies:
    """Lifespan step 3: wire ports -> adapters, once the schema is verified."""
    clock = SystemClock()
    parser = RegexParser()
    rate_limiter = SqliteRateLimiter(engines.writer_sessions, clock)
    uow = cast(UnitOfWork, SqlAlchemyUnitOfWork(engines.writer_sessions, clock))

    def reader_uow_factory() -> UnitOfWork:
        # A fresh UoW per call (not a shared instance, unlike `uow` above) — ops
        # stats reads can be concurrent, and SqlAlchemyUnitOfWork stores its
        # session on `self`, so sharing one instance across concurrent callers
        # would race.
        return cast(UnitOfWork, SqlAlchemyUnitOfWork(engines.reader_sessions, clock))

    return Dependencies(
        clock=clock,
        parser=parser,
        rate_limiter=rate_limiter,
        uow=uow,
        reader_uow_factory=reader_uow_factory,
        onboarding=Onboarding(uow),
        record_transactions=RecordTransactions(parser, uow),
        manage_transactions=ManageTransactions(uow),
        summarize=Summarize(uow),
    )


def build_app() -> FastAPI:
    from .adapters.inbound.http import create_http_app

    # Settings fields are env-driven (fail-fast when unset) — mypy can't know
    # pydantic-settings supplies them from env, so construct via model_validate.
    settings = Settings.model_validate({})
    return create_http_app(settings)
