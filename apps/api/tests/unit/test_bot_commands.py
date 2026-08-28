"""Guards for scripts/set_bot_commands.py.

The slash-command menu Telegram shows and the `CommandHandler`s that actually
answer are two separate lists in two separate files. Nothing but a test keeps
them honest, so the drift check below is the point of this module. Everything
here is offline: no token, no network.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from telegram.ext import CommandHandler

from catetin.adapters.inbound.telegram.application import build_application
from catetin.config import Settings
from scripts.set_bot_commands import BOT_COMMANDS

API_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = API_ROOT / "scripts" / "set_bot_commands.py"


def _registered_commands() -> set[str]:
    settings = Settings(
        telegram_bot_token="test-token",
        telegram_webhook_secret="test-secret",
        ops_username="test-ops",
        ops_password="test-ops-pass",
    )
    application = build_application(settings)
    return {
        command
        for group in application.handlers.values()
        for handler in group
        if isinstance(handler, CommandHandler)
        for command in handler.commands
    }


def test_menu_matches_registered_handlers() -> None:
    menu = {command for command, _ in BOT_COMMANDS}
    assert menu == _registered_commands()


def test_menu_has_no_duplicates() -> None:
    names = [command for command, _ in BOT_COMMANDS]
    assert len(names) == len(set(names))


def test_descriptions_fit_telegram_limits() -> None:
    for command, description in BOT_COMMANDS:
        # Telegram's setMyCommands contract: 1-32 chars for the name (lowercase
        # letters, digits and underscores) and 1-256 for the description.
        assert 1 <= len(command) <= 32
        assert command == command.lower()
        assert 1 <= len(description) <= 256


def test_missing_token_exits_cleanly(tmp_path: Path) -> None:
    # cwd = tmp_path so pydantic-settings finds no apps/api/.env, and the
    # CATETIN_* vars are stripped from the environment: the script must fail
    # with the friendly message instead of a traceback or an API call.
    env = {key: value for key, value in os.environ.items() if not key.startswith("CATETIN_")}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "CATETIN_TELEGRAM_BOT_TOKEN" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_blank_token_exits_cleanly(tmp_path: Path) -> None:
    # A present-but-empty token passes validation, so it needs its own guard.
    env = {key: value for key, value in os.environ.items() if not key.startswith("CATETIN_")}
    env.update(
        {
            "CATETIN_TELEGRAM_BOT_TOKEN": "   ",
            "CATETIN_TELEGRAM_WEBHOOK_SECRET": "test-secret",
            "CATETIN_OPS_USERNAME": "test-ops",
            "CATETIN_OPS_PASSWORD": "test-ops-pass",
        }
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "CATETIN_TELEGRAM_BOT_TOKEN" in result.stderr
    assert "Traceback" not in result.stderr
