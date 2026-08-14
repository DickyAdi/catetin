"""Composition root.

This is the only module allowed to construct adapters (`Adapter(...)` calls
live here and nowhere else — see M6 lifespan step 4 in the design docs).
Once repositories, adapters, and routes exist, `build_app()` will wire:

- Settings (M7), loaded once and passed by dependency injection.
- Writer & reader SQLAlchemy async engines + session factories (M5),
  PRAGMA connect listener, schema revision verification against
  `EXPECTED_DB_REVISION`.
- Repository adapters implementing UserRepository, TransactionRepository,
  InboxRepository, ParseFailureRepository, and the UnitOfWork wrapping them.
- RateLimiterPort -> SqliteRateLimiter (or RedisRateLimiter if REDIS_URL is set).
- ParserPort -> RegexParser (M2).
- ClockPort -> SystemClock.
- MessagingPort -> Telegram adapter (M1); WhatsApp adapter stub in Phase 2.
- ReportRendererPort -> fpdf2-based PDF renderer (M4).
- LlmGatewayPort -> 9router HTTP adapter, only wired when LLM_ENABLED (Phase 2).
- Shared httpx.AsyncClient (20 max connections, 10 keepalive, 15s timeout).
- The PTB `Application`, handlers registered, webhook configured.
- The FastAPI app: routes, pure-ASGI middleware stack, lifespan.
- The asyncio scheduler task (M8) and its jobs.
"""

from fastapi import FastAPI


def build_app() -> FastAPI:
    raise NotImplementedError(
        "build_app() is not implemented yet. Phase 1 only lays the domain "
        "foundation (models, ports, config); repositories, adapters, and "
        "routes land in later phases before this composition root can wire "
        "a real application."
    )
