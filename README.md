# CatetIn 📒

**Chat-based bookkeeping for Indonesian micro & small businesses (UMKM).** Type transactions in a Telegram chat using everyday language — *"jual ayam geprek 50rb"* — and CatetIn automatically records them, summarizes daily/weekly profit & loss, and generates bank-ready PDF reports.

> **No new app to learn. No spreadsheet. Just chat.** 🗨️

---

## ✨ Why CatetIn?

| Problem | CatetIn's answer |
|---|---|
| UMKM owners avoid Excel / bookkeeping apps | **Record via chat** — like texting a friend |
| Reports rejected by banks / KUR (small-business credit) | **Tiered bank-ready PDF** (summary → details → financial report) |
| Manual recording is error-prone | **Deterministic regex parser** — "never misreads a number" |
| Personal transactions mixed with business | **Heuristic flagging + review gate** — bot detects "found money on the street" ≠ business income |
| Privacy & UU PDP (Indonesian data protection) | **Self-service `/hapusakun`** + encrypted backups + raw_text never sent to observability |

**Stack:** Telegram Bot API (free, unmetered) · FastAPI · SQLite (WAL, dual-engine) · uv workspace · pure-ASGI middleware · Hexagonal (ports & adapters)

---

## 🚀 Quickstart (local development)

**Prerequisites:** Python 3.12+, uv, Node.js 20+, Telegram bot token from [@BotFather](https://t.me/BotFather)

```bash
# 1. Setup
make setup                      # uv sync (apps/api) + npm ci (apps/web) + seed .env
# 2. Fill in apps/api/.env — minimum:
#    CATETIN_TELEGRAM_BOT_TOKEN=<token from BotFather>
# 3. Run
make dev-bot                    # bot in polling mode — test directly from your phone
make dev-api                    # backend API (FastAPI :8000, hot reload)
make dev-fe                     # marketing frontend (Vite :5173)
# 4. Test & quality
make test                       # backend test suite (unit + integration + webhook)
make lint && make typecheck     # ruff + mypy
```

**Quick test from Telegram:**
```
/start              → 2-step onboarding (business name → timezone)
jual ayam geprek 50rb  → recorded as a sale
beli gas 20rb          → recorded as an expense
/hariini            → today's summary
/minggu             → this week's summary
/lapor              → bank-ready PDF report
/hapusakun          → delete all your data (UU PDP)
```

Run `make help` for the full target list.

---

## 📚 Documentation (Outline — read before coding!)

All design docs live in **Outline** (docs.kycdia.xyz), not in the repo. The repo contains code only.

### ⭐ Start here (required onboarding)

| Doc | Contents |
|---|---|
| **[Index](https://docs.kycdia.xyz/doc/index-RnaZDQdM5y)** | Map of all documents — start here |
| **[Logic Flow Diagram](https://docs.kycdia.xyz/doc/logic-flow-diagram-Gm5de5cvhG)** | ⭐ **Per-module logic flows** — happy paths + error paths + command triggers. Read this before implementing any feature |
| **[Overview](https://docs.kycdia.xyz/doc/overview-kB1N5vTSfo)** | Big picture: product & architecture |
| **[CatetIn PRD (1-Pager)](https://docs.kycdia.xyz/doc/catetin-prd-1-pager-U7hqtnPdW9)** | Product Requirements — why this product exists |
| **[CatetIn FRD — Modules & Requirements](https://docs.kycdia.xyz/doc/catetin-frd-modules-requirements-Ucnd0n9Ztj)** | Functional Requirements per module |

### 🏗️ Architecture & technical

| Doc | Contents |
|---|---|
| [Data Model](https://docs.kycdia.xyz/doc/data-model-WQc8fKVu8L) | SQLite schema, indexes, denormalization decisions |
| [API Surface](https://docs.kycdia.xyz/doc/api-surface-twGMlauSMz) | HTTP endpoints + webhook |
| [Async & Resource Design](https://docs.kycdia.xyz/doc/async-resource-design-AeyMYOxMhp) | Dual-engine, pool sizing, 4GB VPS constraints |
| [Modules M1-M2](https://docs.kycdia.xyz/doc/modules-m1-m2-telegram-parser-RWvmPahFOo) · [M3-M4](https://docs.kycdia.xyz/doc/modules-m3-m4-service-report-v4ReTi8xC2) · [M5-M8](https://docs.kycdia.xyz/doc/modules-m5-m8-storage-http-config-scheduler-dnac2lS705) | Per-module specs |
| [Report Design — Bank-Ready](https://docs.kycdia.xyz/doc/report-design-bank-ready-audit-ready-tiered-wSuTvoHtic) | Tiered PDF (summary/details/financial report) |
| [FRD — Report V1](https://docs.kycdia.xyz/doc/frd-report-v1-tiered-review-gate-data-scope-IdoVEl1ljH) | Flag heuristic + review gate + data scope |
| [Frontend Marketing Spec](https://docs.kycdia.xyz/doc/frontend-marketing-design-spec-3kRbGZOC9V) | Web design system (teal, Bu Rina persona) |

### 📈 Research & strategy

| Doc | Contents |
|---|---|
| [Positioning — UMKM + POS](https://docs.kycdia.xyz/doc/positioning-umkm-medium-dengan-pos-SzJDSSzSXz) | "Not a cashier. Bookkeeping." — market insight |
| [FRD — Omzet Chat](https://docs.kycdia.xyz/doc/frd-omzet-chat-input-omzet-via-chat-HbkzzWjWZW) | POS revenue input via chat (one message) |
| [Competitive Analysis — Catatmak](https://docs.kycdia.xyz/doc/competitive-analysis-catatmak-vs-catetin-guwfUc07vA) | Competitor analysis + opex model |
| [Observability — Decision & Implementation](https://docs.kycdia.xyz/doc/observability-keputusan-implementasi-9aTfZvYRLJ) | Grafana Cloud + Alloy + Tecnativa proxy |
| [Go-Launch Requirements](https://docs.kycdia.xyz/doc/go-launch-requirements-testing-launch-pF9ZOlr5H2) | Live-test & launch checklist |
| [QA Test Case Library](https://docs.kycdia.xyz/doc/qa-test-case-library-dev-qoZgQkUSp1) | Manual test cases per module (dev) |

---

## 🏗️ Repository layout

```
catetin/
├── Makefile            # entry point for every dev task — `make help`
├── compose.yaml         # docker compose (backend only)
├── pyproject.toml       # uv workspace root (single lockfile)
├── apps/
│   ├── api/             # backend — FastAPI + Telegram bot + SQLite
│   │   ├── src/catetin/
│   │   │   ├── domain/          # pure Python: models + ports (Protocol)
│   │   │   ├── application/     # use cases (record, summarize, report, delete_account, ...)
│   │   │   └── adapters/        # inbound (telegram, http, scheduler) + outbound (persistence, parsing, reporting, backup, observability)
│   │   ├── alembic/             # migrations 0001..0004
│   │   └── tests/               # unit, integration, webhook tests
│   └── web/              # marketing site — Vite + React 19 + Tailwind v4
├── infrastructure/      # observability: deployment/ (Grafana Cloud) + development/ (local Loki)
├── packages/assets/     # brand assets (logo SVGs, font)
└── backups/             # runtime DB backup (gitignored)
```

## 🧠 Architecture (at a glance)

```
inbound adapters ──► application (use cases) ──► domain (models + ports) ◄── outbound adapters
(Telegram / HTTP)        (record, report,        (pure Python)                (SQLite, parser,
                         delete, onboarding)                                   sender, PDF, backup, obs)
```

- **Hexagonal** — the service layer only knows ports (Protocols); adapters are injected in `composition.py` (the single construction point)
- **Async-first** — SQLAlchemy 2.0 async + aiosqlite; sync work only via `asyncio.to_thread`
- **SQLite dual-engine** — writer `pool_size=1` (the pool IS the lock), reader `pool_size=3`
- **Soft delete** via `with_loader_criteria` — but `/hapusakun` purge uses Core `delete()` (loader criteria can't see soft-deleted rows)
- Full conventions: [`CLAUDE.md`](./CLAUDE.md)

---

## 🛠️ Contributing

1. Read the **[Logic Flow Diagram](https://docs.kycdia.xyz/doc/logic-flow-diagram-Gm5de5cvhG)** + the relevant module doc in Outline
2. Branch from `master`: `git checkout -b feat/yourfeature`
3. Implement + **write tests** (unit/integration/webhook — keep the suite green)
4. `make lint && make typecheck && make test`
5. Push + open a PR to `master`

**Ground rules:**
- Design docs live in Outline, not the repo. Update docs in Outline, not in git.
- No em-dashes (—) in UI copy — use ":" or "-"
- New migrations are hand-written, follow the 0001-0004 style, and bump `expected_db_revision` in config.py
- Observability code is hexagonal (`ObservabilityPort`) — never call adapters directly

---

## 🗺️ Roadmap (snapshot)

- ✅ MVP Phase A: parser, recording, summaries, tiered PDF, review gate
- ✅ 2-step onboarding, timezone keyboard, `/hapusakun` (UU PDP), encrypted backups, observability
- 🔜 Phase 0: live test (OVH deploy, catetin.dev domain, Grafana Cloud)
- 🔜 Phase 1: validation with 3 real users + POS positioning
- 🔜 Phase 2: omzet chat, premium V2 (bank-ready reports as revenue)

---

*Built with 💚 in Purwokerto for Indonesian small businesses.*
