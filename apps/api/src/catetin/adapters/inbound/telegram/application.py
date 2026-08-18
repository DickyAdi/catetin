"""Builds the PTB `Application` in one of two modes.

Production (default, `polling=False`): webhook mode — `updater=None`, we feed
updates ourselves via `feed_update`. Not `run_polling`, not PTB's built-in
webserver: FastAPI owns the HTTP server, this only owns update dispatch.
Started/stopped from the HTTP lifespan (M6 steps 4 and shutdown).

Local dev (`polling=True`): PTB keeps its default `Updater` so
`scripts/dev_polling.py` can call `run_polling()` and fetch updates directly
from Telegram — no webhook, no public URL, no FastAPI. Handlers are
identical in both modes.
"""

from __future__ import annotations

from catetin.config import Settings
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from . import handlers


def build_application(settings: Settings, polling: bool = False) -> Application:
    builder = Application.builder().token(settings.telegram_bot_token.get_secret_value())
    if not polling:
        builder = builder.updater(None)  # no Updater: we feed updates ourselves
    application = builder.build()
    application.add_handler(CommandHandler("start", handlers.on_start))
    application.add_handler(CommandHandler("hariini", handlers.on_today))
    application.add_handler(CommandHandler("minggu", handlers.on_week))
    application.add_handler(CommandHandler("list", handlers.on_list))
    application.add_handler(CommandHandler("batal", handlers.on_cancel))
    application.add_handler(CommandHandler("lapor", handlers.on_report))
    application.add_handler(CommandHandler("digest", handlers.on_digest))
    application.add_handler(CommandHandler("zona", handlers.on_timezone))
    application.add_handler(CallbackQueryHandler(handlers.on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
    application.add_handler(
        MessageHandler(~filters.TEXT & ~filters.COMMAND, handlers.on_unsupported)
    )
    return application


async def feed_update(application: Application, payload: dict) -> None:
    update = Update.de_json(payload, application.bot)
    if update is None:
        return
    await application.update_queue.put(update)
