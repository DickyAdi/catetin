# CatetIn

Chat-based bookkeeping for Indonesian UMKM (micro/small businesses). Users text a Telegram
bot in plain language — "jual ayam geprek 50rb" — and get profit/loss summaries back:
daily, weekly, or as a PDF. No new app to learn, no spreadsheet.

## Quickstart

```bash
make setup   # uv sync (apps/api) + seed apps/api/.env from .env.example
             # fill in CATETIN_TELEGRAM_BOT_TOKEN etc. in apps/api/.env before `make dev`
make dev     # run the backend with reload (FastAPI + Telegram webhook)
make test    # run the backend test suite
```

Run `make help` for the full target list (lint, typecheck, migrate, Docker, etc.).
See [`CLAUDE.md`](./CLAUDE.md) for architecture, constraints, and conventions.

## Repository layout

```
catetin/
├── Makefile          # entry point for every dev task — see `make help`
├── compose.yaml       # docker compose (backend only, for now)
├── pyproject.toml     # uv workspace root
├── apps/
│   ├── api/            # backend — FastAPI + Telegram bot + SQLite, see apps/api/pyproject.toml
│   └── web/             # marketing site (not started yet)
├── packages/           # future shared code
└── scripts/            # future ops scripts
```

Backend is Python (`uv`, FastAPI, SQLAlchemy/SQLite, python-telegram-bot). Frontend
(`apps/web`) will be a static marketing site (React Router + Vite), built in CI only —
node/npm are never installed on the deploy host.
