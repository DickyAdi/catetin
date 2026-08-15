# CLAUDE.md — CatetIn

Chat-based bookkeeping bot for Indonesian UMKM. Users send plain chat messages to a Telegram bot ("jual ayam geprek 50rb") and get profit/loss summaries — daily, weekly, or as a PDF. No new app, no spreadsheet.

## Repository layout (monorepo)

```
catetin/
├── Makefile                # cd's into apps/api for every backend target — see `make help`
├── compose.yaml             # docker compose, root-level (build context = repo root)
├── pyproject.toml           # uv workspace root — virtual (no [project]), members = ["apps/*"]
├── uv.lock                  # THE single lockfile for the whole workspace (not duplicated per app)
├── apps/
│   ├── api/                 # backend — everything below used to be repo root pre-monorepo
│   │   ├── pyproject.toml, Dockerfile, alembic.ini
│   │   ├── alembic/, src/catetin/, tests/
│   │   └── .env.example     # copy to .env (make setup does this automatically)
│   └── web/                 # marketing site, not started yet (see "Frontend" below)
├── packages/                 # future shared code (empty for now)
├── scripts/                  # future ops scripts, e.g. scripts/deploy.sh (empty for now)
└── backups/                  # runtime DB backup output (gitignored contents)
```

`uv sync` / `uv run ...` work from **both** the repo root and `apps/api` — uv walks up to
find the workspace root at `pyproject.toml`, so both resolve to the same shared
`.venv`/`uv.lock` at the repo root. Never create a second `uv.lock` or `.venv` inside
`apps/api`. See the comment block at the top of the root `pyproject.toml` for why this
(a true uv workspace) was chosen over a "Makefile just cd's into apps/api" fallback.

## Quick commands

Prefer the `Makefile` (`make help` lists everything: `setup`, `dev`, `test`, `lint`,
`typecheck`, `migrate`, `migrate-new msg="..."`, `dockerized`, `docker-up`, `docker-down`,
`clean`, `status`, `deploy`). Equivalent raw commands, run from `apps/api/` (or from the
repo root with `-C apps/api` / `--project apps/api`):

```bash
uv sync                          # install deps (uv.lock committed, at repo root)
uv run pytest tests/ -q          # run all tests (116)
uv run pytest tests/unit -q      # unit only
uv run pytest tests/integration -q
uv run ruff check src tests      # lint
uv run mypy src/catetin           # type check
uv run alembic upgrade head      # apply migrations (dev/deploy step)
uv run alembic check             # verify ORM matches migrations (CI)
uv run alembic revision --autogenerate -m "msg"   # only for NEW revisions; initial was hand-written
```

## Architecture — Ports & Adapters (hexagonal, pragmatic)

```
inbound adapters ──► application (use cases) ──► domain (models + ports) ◄── outbound adapters
```

All paths below are relative to `apps/api/`.

- **`src/catetin/domain/`** — pure Python. Pydantic models + `typing.Protocol` ports. NO I/O, NO framework imports. Never imports adapters.
- **`src/catetin/application/`** — use cases (M3). Depend only on domain models + ports. Never import adapters directly.
- **`src/catetin/adapters/inbound/`** — HTTP shell (FastAPI + raw ASGI middleware), Telegram bot (Phase 6), scheduler (Phase 6).
- **`src/catetin/adapters/outbound/`** — parser, persistence (SQLAlchemy), Telegram sender (P6), reporting (P7), LLM gateway (P2 stub), system_clock.
- **`src/catetin/composition.py`** — THE ONLY place adapters are constructed. `build_app()` / `create_engines()` / `wire()`.
- **`src/catetin/main.py`** — ASGI entrypoint only.

Only 5 ports earn their keep (per design docs): `ParserPort`, `MessagingPort`, `LlmGatewayPort`, repository ports, `ClockPort`. Everything else is a plain module — no blanket layering ceremony.

## Fixed technical constraints (from FRD — do not violate)

| Concern | Decision |
|---|---|
| Package manager | `uv` workspace (single `uv.lock` at repo root, committed; `uv sync --frozen` in deploy) |
| Web framework | FastAPI, `ORJSONResponse` default |
| HTTP client | one shared `httpx.AsyncClient` |
| Concurrency | **async-first**; sync only for genuinely blocking work via `asyncio.to_thread` |
| JSON | `orjson` everywhere |
| Middleware | **pure ASGI** (`__call__(scope, receive, send)`) — NEVER `BaseHTTPMiddleware` unless a documented quirk forces it; contextvars must propagate |
| Database | SQLite (WAL) via SQLAlchemy 2.0 async over `aiosqlite` driver. **Two engines**: writer `pool_size=1, max_overflow=0` (the pool IS the lock — no `asyncio.Lock`), reader `pool_size=3, max_overflow=0` |
| ORM vs Core | ORM for writes & row fetches; Core `select()` for aggregations (GROUP BY in SQL, not Python). `expire_on_commit=False` |
| Migrations | Alembic, dev/deploy group. **Never imported in `main.py`** — run `alembic upgrade head` in deploy, app only VERIFIES revision at startup (`version_check`) |
| Pydantic | domain models only (`frozen=True, extra="forbid"`) — NOT the persistence layer. **No SQLModel.** ORM rows stay SQLAlchemy declarative; mappers convert |
| Background jobs | asyncio tasks in-process (no Celery/Redis) |
| Redis | NOT in MVP. `RateLimiterPort` + `REDIS_URL=None` config placeholder only |
| Host | 2 vCPU / 4 GB RAM / 2 GB swap, `vm.swappiness=10` — steady-state RSS target < 400 MB. Keep it lean |

## Data model (SQLite-optimal, per design docs)

- Tables: `users`, `transactions`, `inbox`, `parse_failures`, `rate_limits` (+ `alembic_version`).
- **Integer rupiah, no floats.** `total_amount` authoritative; `unit_amount` informational.
- `occurred_on` = denormalized user-local date string (`YYYY-MM-DD`) — summaries group by it directly, no per-row tz conversion.
- **Partial indexes** (`WHERE deleted_at IS NULL`) on the 3 transaction indexes; `rate_limits` is **WITHOUT ROWID** (composite PK).
- `inbox.update_id` PK → INSERT OR IGNORE gives idempotency.
- Soft delete (`deleted_at`) via `with_loader_criteria(..., lambda c: c.deleted_at.is_(None))` — structural default, not per-query discipline.
- **Repository methods take `user_id` FIRST** — cross-user isolation is enforced at the repository layer (G5/US-12).

## Key domain models

`User`, `Transaction`, `ParsedTransaction` (kind: sale/expense, validators: qty>0, total_amount>0, confidence 0..1, item ≤80 chars), `Summary`, `DayTotal`, `ItemTotal`, `ParseFailure`, `FailedSegment`/`ParseOutcome` (parser failure reasons: `no_amount`, `ambiguous_kind`, `too_many_segments`, ...).

## Parser contract

- `ParserPort.parse` (async) → `list[ParsedTransaction]`; `ParserPort.parse_detailed` (sync) → `ParseOutcome` with failure reasons (used by record_transactions).
- Amounts: `50rb`, `50k`, `50.000`, `50.5rb`→50500, `1jt`, `Rp 50rb`, `50 ribu`. Comma is a decimal separator in Indonesian — only splits segments when followed by a sale/expense keyword.
- Segment cap: 20 (`too_many_segments`).
- Ambiguous kind → reason `ambiguous_kind`, bot asks via `ask_choice` (US-08, Q8).

## Design docs (source of truth — read BEFORE implementing)

Docs live in **Outline** (NOT the repo — repo is code only). MCP server name: `outline`.
Collection id: `33ac2d97-d46f-4c62-90e8-3125912cb318` (CatetIn).

Key docs: Index, Overview, Data Model, API Surface, Async & Resource Design, Modules M1-M2, Modules M3-M4, Modules M5-M8, Frontend Marketing, Phase 2 & Open Questions.

When asked to implement a module: **fetch the relevant Outline docs first** and follow them — they are more precise than any prompt summary.

## Project status

- P1 ✅ foundation (config, domain, ports) — `4a413a9`
- P2 ✅ parser (regex, amounts, lexicon, segmenter) — `60e6e8d`
- P3 ✅ persistence (2 engines, 5 repos, alembic 0001_initial) — `da6dce7`
- P4 ✅ application use cases (record, summarize, manage, onboarding, generate_report, replay_inbox) — `0dbd824`
- P5 ✅ HTTP shell (pure-ASGI middleware, health/webhook/ops routes, composition) — `d715674`
- P6 ✅ Telegram adapter (M1) + scheduler (M8) — `48fcabf`
- P7 ✅ Report renderers (M4): text + fpdf2 PDF (`/lapor`) — `aa93dad` — **MVP feature-complete**
- Monorepo restructure (`apps/api`, `apps/web`, `packages/`, `scripts/`, Makefile, Docker) — done, this doc's layout is current

## Frontend (Phase: not started)

Marketing-only static site (no product dashboard), lives in `apps/web/` (currently just a `.gitkeep`). React Router (library mode, NOT framework mode) + shadcn + Vite, prerendered via vite-react-ssg for SEO. Build in CI only — **node/npm must never be installed on the VPS**. Hosted externally (e.g. Cloudflare Pages). Details: "Frontend Marketing" doc in Outline.

## Testing conventions

All paths below are relative to `apps/api/`.

- `tests/unit/` — parser (table-driven, largest suite), amounts, middleware, use cases (with `tests/fakes/`: FakeUnitOfWork, fake repos, fake parser/messaging, frozen_clock).
- `tests/integration/` — real temp SQLite via `conftest.py`: repositories, migrations (alembic upgrade + index/WITHOUT-ROWID assertions), webhook (ASGITransport). Path fixtures (`REPO_ROOT` in `conftest.py`/`test_migrations.py`) are `Path(__file__).resolve().parents[2]`, i.e. always `apps/api` regardless of cwd — survived the monorepo move with zero changes.
- `tests/contract/` — empty (port contract tests planned).
- Isolation tests: cross-user access attempts + structural check that every query filters `user_id`.

## Gotchas (learned — do not relearn)

- `uv` is installed **system-wide** (use plain `uv run`; do not `pip install`).
- Monorepo: `apps/api` is a `uv` workspace **member**, not a standalone project — it has no `uv.lock`/`.venv` of its own. The one lockfile lives at the repo root. Docker build context for `apps/api/Dockerfile` is deliberately the **repo root** (`compose.yaml`: `build.context: .`), not `apps/api/`, so the image build can see the workspace root files.
- Alembic `autogenerate` does NOT reliably round-trip partial indexes / WITHOUT ROWID — hand-write those parts.
- `pytest-asyncio` needs `asyncio_mode = "auto"` (already set in pyproject).
- Telegram webhook path secret: `/webhook/telegram/{secret}` — webhook_auth middleware validates it; webhook route never returns 5xx (durable inbox acceptance is the priority).
- MCP `--allowedTools` must include `mcp__outline__*` or Claude can't read the design docs in print mode.
- Long phases hit `--max-turns` — split into "implement" + "tests/verify" runs when a phase is big.
