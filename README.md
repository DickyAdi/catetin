# CatetIn 📒

**Chat-based bookkeeping untuk UMKM Indonesia.** Ketik transaksi di chat Telegram pakai bahasa sehari-hari — *"jual ayam geprek 50rb"* — dan CatetIn otomatis mencatat, meringkas untung-rugi harian/mingguan, sampai bikin laporan PDF yang siap dibawa ke bank.

> **Bukan aplikasi baru untuk dipelajari. Bukan spreadsheet. Cuma chat.** 🗨️

---

## ✨ Kenapa CatetIn?

| Masalah | Solusi CatetIn |
|---|---|
| UMKM males buka Excel / app pembukuan | **Catat lewat chat** — seperti chat ke teman |
| Laporan gak diterima bank/KUR | **PDF tiered bank-ready** (ringkasan → rincian → laporan keuangan) |
| Pencatatan manual rawan lupa/salah | **Parser regex deterministik** — "nggak pernah salah baca angka" |
| Transaksi pribadi ketcampur usaha | **Flag heuristik + review gate** — bot deteksi "dapet duit di jalan" ≠ pemasukan usaha |
| Privasi & UU PDP | **`/hapusakun` self-service** + backup terenkripsi + raw_text gak ke observability |

**Stack:** Telegram Bot API (gratis, unmetered) · FastAPI · SQLite (WAL, 2-engine) · uv workspace · pure-ASGI middleware · Hexagonal (ports & adapters)

---

## 🚀 Quickstart (local dev)

**Prerequisites:** Python 3.12+, uv, Node.js 20+, token bot Telegram dari [@BotFather](https://t.me/BotFather)

```bash
# 1. Setup
make setup                      # uv sync (apps/api) + npm ci (apps/web) + seed .env
# 2. Isi apps/api/.env — minimal:
#    CATETIN_TELEGRAM_BOT_TOKEN=<token dari BotFather>
# 3. Jalanin
make dev-bot                    # bot polling mode — test langsung dari HP Telegram
make dev-api                    # backend API (FastAPI :8000, reload)
make dev-fe                     # frontend marketing (Vite :5173)
# 4. Test & quality
make test                       # backend test suite (unit + integration + webhook)
make lint && make typecheck     # ruff + mypy
```

**Test cepat dari Telegram:**
```
/start              → onboarding 2 langkah (nama usaha → zona waktu)
jual ayam geprek 50rb  → tercatat sebagai penjualan
beli gas 20rb          → tercatat sebagai pengeluaran
/hariini            → ringkasan hari ini
/minggu             → ringkasan minggu ini
/lapor              → PDF laporan bank-ready
/hapusakun          → hapus semua data (UU PDP)
```

Run `make help` untuk daftar lengkap target.

---

## 📚 Dokumentasi (Outline — baca sebelum ngoding!)

Semua dokumen desain terpusat di **Outline** (docs.kycdia.xyz), bukan di repo. Repo cuma berisi kode.

### ⭐ Mulai dari sini (onboarding wajib)

| Doc | Isi |
|---|---|
| **[Index](https://docs.kycdia.xyz/doc/index-RnaZDQdM5y)** | Peta semua dokumen — mulai dari sini |
| **[Logic Flow Diagram](https://docs.kycdia.xyz/doc/logic-flow-diagram-Gm5de5cvhG)** | ⭐ **Flow logic per modul** — happy path + error path + trigger command. Baca ini sebelum implement fitur apa pun |
| **[Overview](https://docs.kycdia.xyz/doc/overview-kB1N5vTSfo)** | Gambaran besar produk & arsitektur |
| **[CatetIn PRD (1-Pager)](https://docs.kycdia.xyz/doc/catetin-prd-1-pager-U7hqtnPdW9)** | Product Requirements — kenapa produk ini ada |
| **[CatetIn FRD — Modules & Requirements](https://docs.kycdia.xyz/doc/catetin-frd-modules-requirements-Ucnd0n9Ztj)** | Functional Requirements per modul |

### 🏗️ Arsitektur & teknis

| Doc | Isi |
|---|---|
| [Data Model](https://docs.kycdia.xyz/doc/data-model-WQc8fKVu8L) | Skema SQLite, index, keputusan denormalisasi |
| [API Surface](https://docs.kycdia.xyz/doc/api-surface-twGMlauSMz) | Endpoint HTTP + webhook |
| [Async & Resource Design](https://docs.kycdia.xyz/doc/async-resource-design-AeyMYOxMhp) | 2-engine, pool sizing, constraint VPS 4GB |
| [Modules M1-M2](https://docs.kycdia.xyz/doc/modules-m1-m2-telegram-parser-RWvmPahFOo) · [M3-M4](https://docs.kycdia.xyz/doc/modules-m3-m4-service-report-v4ReTi8xC2) · [M5-M8](https://docs.kycdia.xyz/doc/modules-m5-m8-storage-http-config-scheduler-dnac2lS705) | Spec per modul |
| [Report Design — Bank-Ready](https://docs.kycdia.xyz/doc/report-design-bank-ready-audit-ready-tiered-wSuTvoHtic) | Tiered PDF (ringkasan/rincian/laporan keuangan) |
| [FRD — Report V1](https://docs.kycdia.xyz/doc/frd-report-v1-tiered-review-gate-data-scope-IdoVEl1ljH) | Flag heuristic + review gate + data scope |
| [Frontend Marketing Spec](https://docs.kycdia.xyz/doc/frontend-marketing-design-spec-3kRbGZOC9V) | Design system web (teal, persona Bu Rina) |

### 📈 Riset & strategi

| Doc | Isi |
|---|---|
| [Positioning — UMKM + POS](https://docs.kycdia.xyz/doc/positioning-umkm-medium-dengan-pos-SzJDSSzSXz) | "Bukan kasir. Pembukuan." — insight pasar |
| [FRD — Omzet Chat](https://docs.kycdia.xyz/doc/frd-omzet-chat-input-omzet-via-chat-HbkzzWjWZW) | Input omzet dari POS via chat (1 pesan) |
| [Competitive Analysis — Catatmak](https://docs.kycdia.xyz/doc/competitive-analysis-catatmak-vs-catetin-guwfUc07vA) | Analisis kompetitor + opex model |
| [Observability — Keputusan & Implementasi](https://docs.kycdia.xyz/doc/observability-keputusan-implementasi-9aTfZvYRLJ) | Grafana Cloud + Alloy + Tecnativa proxy |
| [Go-Launch Requirements](https://docs.kycdia.xyz/doc/go-launch-requirements-testing-launch-pF9ZOlr5H2) | Checklist live test & launch |
| [QA Test Case Library](https://docs.kycdia.xyz/doc/qa-test-case-library-dev-qoZgQkUSp1) | TC manual per modul (dev) |

---

## 🏗️ Repository layout

```
catetin/
├── Makefile            # entry point semua dev task — `make help`
├── compose.yaml         # docker compose (backend doang)
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
├── packages/assets/     # brand assets (logo SVG, font)
└── backups/             # runtime DB backup (gitignored)
```

## 🧠 Arsitektur (sekilas)

```
inbound adapters ──► application (use cases) ──► domain (models + ports) ◄── outbound adapters
(Telegram / HTTP)        (record, report,        (pure Python)                (SQLite, parser,
                         delete, onboarding)                                   sender, PDF, backup, obs)
```

- **Hexagonal** — service layer cuma kenal ports (Protocol), adapter di-inject di `composition.py` (satu-satunya tempat konstruksi)
- **Async-first** — SQLAlchemy 2.0 async + aiosqlite; sync hanya via `asyncio.to_thread`
- **SQLite 2-engine** — writer `pool_size=1` (pool = lock), reader `pool_size=3`
- **Soft delete** via `with_loader_criteria` — tapi purge `/hapusakun` pakai Core `delete()` (loader criteria gak liat row soft-deleted)
- Konvensi lengkap: [`CLAUDE.md`](./CLAUDE.md)

---

## 🛠️ Contributing

1. Baca **[Logic Flow Diagram](https://docs.kycdia.xyz/doc/logic-flow-diagram-Gm5de5cvhG)** + doc modul terkait di Outline
2. Bikin branch dari `master`: `git checkout -b feat/namafitur`
3. Implement + **tulis test** (unit/integration/webhook — target: semua hijau)
4. `make lint && make typecheck && make test`
5. Push + open PR ke `master`

**Aturan main:**
- Docs desain = Outline, bukan repo. Update doc di Outline, bukan di git.
- Gak ada em-dash (—) di copy UI — pakai ":" atau "-"
- Migrasi baru = hand-written, ikuti gaya 0001-0004, update `expected_db_revision` di config.py
- Kode observability = hexagonal (`ObservabilityPort`), jangan panggil adapter langsung

---

## 🗺️ Roadmap (sekilas)

- ✅ MVP Fase A: parser, pencatatan, ringkasan, PDF tiered, review gate
- ✅ Onboarding 2-langkah, zona keyboard, `/hapusakun` (UU PDP), backup terenkripsi, observability
- 🔜 Fase 0: live test (deploy OVH, domain catetin.dev, Grafana Cloud)
- 🔜 Fase 1: validasi 3 user real + positioning POS
- 🔜 Fase 2: omzet chat, premium V2 (laporan bank-ready sebagai revenue)

---

*Dibuat dengan 💚 di Purwokerto untuk UMKM Indonesia.*
