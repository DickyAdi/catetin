"""Run the CatetIn Telegram bot in polling mode, for local dev without a
public URL. No webhook, no tunnel, no FastAPI — PTB's `Updater` fetches
updates directly from Telegram. Env-driven, same as the API (`CATETIN_*` in
apps/api/.env). Run via `make dev-bot` or `uv run python scripts/dev_polling.py`.

`Application.run_polling()` is a blocking, self-contained PTB entry point —
it builds its own event loop and drives initialize/start/poll/stop/shutdown
internally (see `Application._Application__run`). It must be called directly
from sync code, not from inside an already-running `asyncio.run()` loop.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from pydantic import ValidationError
from telegram.ext import Application as TelegramApplication

from catetin import composition
from catetin.config import Settings

_logger = logging.getLogger("catetin.dev_polling")


_MISSING_TOKEN_MESSAGE = (
    "CATETIN_TELEGRAM_BOT_TOKEN belum di-set — isi apps/api/.env dulu "
    "(copy dari .env.example, isi token dari @BotFather)."
)


def _load_settings() -> Settings:
    try:
        settings = Settings.model_validate({})
    except ValidationError as exc:
        missing = [str(err["loc"][0]) for err in exc.errors() if err["type"] == "missing"]
        if "telegram_bot_token" in missing:
            print(_MISSING_TOKEN_MESSAGE, file=sys.stderr)
        elif missing:
            env_names = ", ".join(f"CATETIN_{name.upper()}" for name in missing)
            print(
                f"Konfigurasi belum lengkap — env var berikut belum di-set: {env_names} "
                "(isi apps/api/.env, lihat .env.example).",
                file=sys.stderr,
            )
        else:
            print(f"Konfigurasi tidak valid: {exc}", file=sys.stderr)
        sys.exit(1)

    if not settings.telegram_bot_token.get_secret_value().strip():
        print(_MISSING_TOKEN_MESSAGE, file=sys.stderr)
        sys.exit(1)
    return settings


async def _dispose(engines: composition.Engines) -> None:
    await engines.writer.dispose()
    await engines.reader.dispose()


async def _check(application: TelegramApplication, engines: composition.Engines) -> None:
    await application.initialize()
    await application.shutdown()
    await _dispose(engines)
    print("polling OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the CatetIn Telegram bot in polling mode (local dev only)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Build and initialize the application, verify the token works, then exit "
        "(no polling loop).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = _load_settings()
    engines = composition.create_engines(settings)
    deps = composition.wire(settings, engines, polling=True)
    application = deps.telegram_application

    if args.check:
        asyncio.run(_check(application, engines))
        return

    _logger.info("Bot polling aktif — buka Telegram dan chat ke bot kamu. Ctrl+C untuk stop.")
    try:
        application.run_polling(close_loop=True)
    finally:
        asyncio.run(_dispose(engines))


if __name__ == "__main__":
    main()
