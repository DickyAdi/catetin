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

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from telegram.ext import Application as TelegramApplication

from .adapters.inbound.telegram import application as telegram_app
from .adapters.inbound.telegram import handlers as telegram_handlers
from .adapters.outbound.observability import (
    GrafanaCloudObservability,
    NullObservability,
    StdoutObservability,
)
from .adapters.outbound.parsing.regex_parser import RegexParser
from .adapters.outbound.persistence.engine import (
    create_reader_engine,
    create_writer_engine,
    session_factory,
)
from .adapters.outbound.persistence.repositories.rate_limit.rate_limiter import (
    SqliteRateLimiter,
)
from .adapters.outbound.persistence.uow import SqlAlchemyUnitOfWork
from .adapters.outbound.reporting.pdf_renderer import PdfRenderer
from .adapters.outbound.system_clock import SystemClock
from .adapters.outbound.telegram.sender import TelegramSender
from .application.generate_report import GenerateReport
from .application.manage_transactions import ManageTransactions
from .application.onboarding import Onboarding
from .application.record_transactions import RecordTransactions
from .application.summarize import Summarize
from .config import Settings
from .domain.ports.clock import ClockPort
from .domain.ports.messaging import MessagingPort
from .domain.ports.observability import ObservabilityPort
from .domain.ports.parser import ParserPort
from .domain.ports.reporting import ReportRendererPort
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
    writer_uow_factory: Callable[[], UnitOfWork]
    onboarding: Onboarding
    record_transactions: RecordTransactions
    manage_transactions: ManageTransactions
    summarize: Summarize
    generate_report: GenerateReport
    messaging: MessagingPort
    telegram_application: TelegramApplication
    observability: ObservabilityPort
    # Non-None only for the grafana_cloud backend, which is the one adapter
    # that owns an httpx client. The lifespan closes it on shutdown.
    observability_client: httpx.AsyncClient | None


def build_observability(
    settings: Settings, backend: str | None = None
) -> tuple[ObservabilityPort, httpx.AsyncClient | None]:
    """Pick the ObservabilityPort adapter — the one place the backend is chosen.

    Returns the adapter plus the httpx client it owns (if any), so the caller
    can close what it created. Anything unrecognised falls back to the null
    adapter: a typo in `CATETIN_OBSERVABILITY_BACKEND` should cost telemetry,
    not startup.
    """
    choice = (backend or settings.observability_backend).lower()
    if choice == "grafana_cloud":
        client = httpx.AsyncClient()
        return GrafanaCloudObservability(client, settings.otlp_endpoint), client
    if choice == "stdout":
        return StdoutObservability(), None
    return NullObservability(), None


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


def wire(
    settings: Settings,
    engines: Engines,
    polling: bool = False,
    observability_backend: str | None = None,
) -> Dependencies:
    """Lifespan step 3: wire ports -> adapters, once the schema is verified."""
    clock = SystemClock()
    observability, observability_client = build_observability(settings, observability_backend)
    parser = RegexParser()
    rate_limiter = SqliteRateLimiter(engines.writer_sessions, clock)
    renderer = cast(ReportRendererPort, PdfRenderer(concurrency=settings.pdf_concurrency))

    def reader_uow_factory() -> UnitOfWork:
        # A fresh UoW per call (not a shared instance) — ops stats reads can be
        # concurrent, and SqlAlchemyUnitOfWork stores its session on `self`, so
        # sharing one instance across concurrent callers would race.
        return cast(UnitOfWork, SqlAlchemyUnitOfWork(engines.reader_sessions, clock))

    def writer_uow_factory() -> UnitOfWork:
        # Same reasoning as `reader_uow_factory`: every caller that can run
        # concurrently with the Telegram handler loop (the webhook route's own
        # durable-enqueue bookkeeping, inbox replay, the scheduler task) needs
        # its own session rather than sharing the `uow` instance below. The
        # writer engine's `pool_size=1` is what actually serializes concurrent
        # writers at the connection level — sharing one mutable UnitOfWork
        # object across concurrent `async with` blocks would instead race on
        # `self.session` itself (see git history for the bug this fixed).
        return cast(UnitOfWork, SqlAlchemyUnitOfWork(engines.writer_sessions, clock))

    # Shared by the Telegram use cases below only: PTB's fetcher loop processes
    # updates one at a time (no `concurrent_updates`), so sequential re-entry
    # of this single instance from within one handler invocation is safe.
    uow = writer_uow_factory()

    onboarding = Onboarding(uow)
    record_transactions = RecordTransactions(parser, uow, observability=observability)
    manage_transactions = ManageTransactions(uow)
    summarize = Summarize(uow)
    generate_report = GenerateReport(
        uow,
        rate_limiter,
        renderer,
        max_per_user_hour=settings.pdf_max_per_user_hour,
        observability=observability,
    )

    # The inbound Application and the outbound sender share one PTB Bot
    # instance (`application.bot`) — no second token, no second connection
    # pool. Handlers read their dependencies from `bot_data["deps"]`.
    application = telegram_app.build_application(settings, polling=polling)
    messaging = cast(MessagingPort, TelegramSender(application.bot, reader_uow_factory))
    application.bot_data["deps"] = telegram_handlers.TelegramDeps(
        onboarding=onboarding,
        record_transactions=record_transactions,
        manage_transactions=manage_transactions,
        summarize=summarize,
        generate_report=generate_report,
        messaging=messaging,
        clock=clock,
        default_timezone=settings.timezone,
    )

    return Dependencies(
        clock=clock,
        parser=parser,
        rate_limiter=rate_limiter,
        uow=uow,
        reader_uow_factory=reader_uow_factory,
        writer_uow_factory=writer_uow_factory,
        onboarding=onboarding,
        record_transactions=record_transactions,
        manage_transactions=manage_transactions,
        summarize=summarize,
        generate_report=generate_report,
        messaging=messaging,
        telegram_application=application,
        observability=observability,
        observability_client=observability_client,
    )


def build_app() -> FastAPI:
    from .adapters.inbound.http import create_http_app

    # Settings fields are env-driven (fail-fast when unset) — mypy can't know
    # pydantic-settings supplies them from env, so construct via model_validate.
    settings = Settings.model_validate({})
    return create_http_app(settings)
