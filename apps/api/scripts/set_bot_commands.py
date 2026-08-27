"""Sync the bot's slash-command menu (the "/" list in Telegram) from code.

Telegram keeps that menu server-side; BotFather is only one way to write it.
This script writes it with a single `setMyCommands` call, so the menu lives
in version control right next to the handlers that implement it.

Deliberately NOT wired into app startup: with more than one replica every
process would fire the same API call on every boot. Run it by hand, or as a
deploy step, whenever a command is added or renamed:

    make bot-commands
    uv run python scripts/set_bot_commands.py --check   # read back what is set

`BOT_COMMANDS` must stay in sync with the `CommandHandler`s registered in
`catetin.adapters.inbound.telegram.application.build_application` —
`tests/unit/test_bot_commands.py` fails the build if the two ever drift.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pydantic import ValidationError
from telegram import Bot
from telegram.error import TelegramError

from catetin.config import Settings

BOT_COMMANDS: list[tuple[str, str]] = [
    ("start", "Mulai / ulangi onboarding"),
    ("hariini", "Ringkasan hari ini"),
    ("minggu", "Ringkasan minggu ini"),
    ("list", "Daftar transaksi terakhir"),
    ("lapor", "Buat laporan PDF"),
    ("zona", "Set zona waktu"),
    ("digest", "Aktifkan/matikan ringkasan harian"),
    ("batal", "Batalkan transaksi terakhir"),
    ("hapusakun", "Hapus semua data (UU PDP)"),
]


_MISSING_TOKEN_MESSAGE = (
    "CATETIN_TELEGRAM_BOT_TOKEN belum di-set. Isi apps/api/.env dulu "
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
                f"Konfigurasi belum lengkap. Env var berikut belum di-set: {env_names} "
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


async def _sync(token: str) -> None:
    """Push BOT_COMMANDS to Telegram (setMyCommands, default scope).

    `async with Bot(...)` runs PTB's initialize/shutdown around the call, which
    is what sets up (and tears down) the HTTPX connection pool the request
    needs. `set_my_commands` accepts plain `(command, description)` tuples, so
    no `BotCommand` wrapping is required.
    """
    async with Bot(token) as bot:
        await bot.set_my_commands(BOT_COMMANDS)
    print(f"{len(BOT_COMMANDS)} perintah ke-set ke bot.")


async def _show(token: str) -> None:
    async with Bot(token) as bot:
        current = await bot.get_my_commands()
    if not current:
        print("Bot belum punya daftar perintah sama sekali.")
        return
    print(f"{len(current)} perintah terpasang di bot saat ini:")
    for command in current:
        print(f"  /{command.command} - {command.description}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync the CatetIn bot's Telegram slash-command menu (setMyCommands)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print the command menu Telegram currently has, without changing it.",
    )
    args = parser.parse_args()

    settings = _load_settings()
    token = settings.telegram_bot_token.get_secret_value()

    try:
        asyncio.run(_show(token) if args.check else _sync(token))
    except TelegramError as exc:
        print(f"Gagal menghubungi Telegram: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
