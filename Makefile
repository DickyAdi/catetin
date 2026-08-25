APP_DIR := apps/api
WEB_DIR := apps/web
API_PORT := 8000
FE_PORT := 5173
INFRA_DEPLOY := infrastructure/deployment/compose.yaml
INFRA_DEV := infrastructure/development/compose.yaml
ALLOY_UI := http://127.0.0.1:12345

.DEFAULT_GOAL := help

.PHONY: help setup dev dev-api dev-fe dev-all dev-down dev-bot test lint typecheck migrate migrate-new \
	dockerized docker-up docker-down clean status deploy \
	infra-up infra-down infra-logs infra-ps infra-dev-up infra-dev-down obs-check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend (uv) and web (npm) deps; seed .env
	cd $(APP_DIR) && uv sync
	@if [ -f $(WEB_DIR)/package.json ]; then \
		cd $(WEB_DIR) && npm ci; \
	else \
		echo "note: $(WEB_DIR) has no package.json yet — web setup skipped"; \
	fi
	@if [ -f $(APP_DIR)/.env.example ] && [ ! -f $(APP_DIR)/.env ]; then \
		cp $(APP_DIR)/.env.example $(APP_DIR)/.env; \
		echo "created $(APP_DIR)/.env from .env.example — fill in real values"; \
	fi

dev: dev-api ## Alias — run the backend dev server (see dev-api/dev-fe/dev-all)

dev-api: ## Run the backend dev server with reload (needs apps/api/.env — see .env.example)
	cd $(APP_DIR) && uv run uvicorn catetin.main:app --reload --app-dir src

dev-fe: ## Run the frontend (Vite) dev server (apps/web)
	cd $(WEB_DIR) && npm run dev

dev-bot: ## Run the Telegram bot in polling mode for local testing (no webhook/tunnel needed)
	cd $(APP_DIR) && uv run python scripts/dev_polling.py

dev-all: ## Start backend + frontend dev servers in background (tracked via .dev/*.pid; stop with `make dev-down`)
	@mkdir -p .dev
	@echo "==> Starting backend (http://localhost:8000) + frontend (http://localhost:5173)"
	@cd $(APP_DIR) && nohup "$(CURDIR)/.venv/bin/uvicorn" catetin.main:app --reload --app-dir src > "$(CURDIR)/.dev/api.log" 2>&1 & echo $$! > .dev/api.pid
	@cd $(WEB_DIR) && nohup "$(CURDIR)/apps/web/node_modules/.bin/vite" > "$(CURDIR)/.dev/fe.log" 2>&1 & echo $$! > .dev/fe.pid
	@sleep 2
	@echo "    api pid: $$(cat .dev/api.pid)  fe pid: $$(cat .dev/fe.pid)"
	@echo "    logs: .dev/api.log .dev/fe.log   (stop: make dev-down)"

dev-down: ## Stop dev servers tracked in .dev/*.pid, plus any stray process left on their ports (individual `kill`s only — never a process-group kill)
	@for name in api fe; do \
		pidfile=".dev/$$name.pid"; \
		if [ -f "$$pidfile" ]; then \
			pid=$$(cat "$$pidfile"); \
			if kill -0 $$pid 2>/dev/null; then \
				kill $$pid && echo "    stopped $$name (pid $$pid)"; \
			else \
				echo "    $$name already gone (stale pid $$pid)"; \
			fi; \
			rm -f "$$pidfile"; \
		else \
			echo "    no $$name pidfile — nothing to stop"; \
		fi; \
	done
	@sleep 1
	@for portspec in "api:$(API_PORT)" "fe:$(FE_PORT)"; do \
		name=$${portspec%%:*}; port=$${portspec##*:}; \
		for pid in $$(lsof -ti tcp:$$port -sTCP:LISTEN 2>/dev/null); do \
			kill $$pid 2>/dev/null && echo "    killed stray $$name process still on port $$port (pid $$pid)"; \
		done; \
	done
	@sleep 1
	@echo "dev stacks down"

test: ## Run the backend test suite
	cd $(APP_DIR) && uv run pytest tests/ -q

lint: ## Lint the backend with ruff
	cd $(APP_DIR) && uv run ruff check src tests

typecheck: ## Type-check the backend with mypy
	cd $(APP_DIR) && uv run mypy src/catetin

migrate: ## Apply Alembic migrations to the configured database
	cd $(APP_DIR) && uv run alembic upgrade head

migrate-new: ## Generate a new Alembic revision: make migrate-new msg="add column"
	cd $(APP_DIR) && uv run alembic revision --autogenerate -m "$(msg)"

dockerized: ## Build and run the backend via Docker Compose
	docker compose up -d --build

docker-up: ## Start containers (no rebuild)
	docker compose up -d

docker-down: ## Stop and remove containers
	docker compose down

# --- Observability stack (infrastructure/) -----------------------------------
# Deployment = Alloy + socket proxy + node-exporter + api, shipping to Grafana
# Cloud. Development = the same collector topology against a local Loki, no
# credentials needed. Run one or the other; they share host ports 8000/12345.

infra-up: ## Start the production observability stack (needs infrastructure/deployment/.env)
	@if [ ! -f infrastructure/deployment/.env ]; then \
		echo "missing infrastructure/deployment/.env — copy .env.example and fill in your Grafana Cloud values"; \
		exit 1; \
	fi
	docker compose -f $(INFRA_DEPLOY) up -d
	@echo "    alloy ui: $(ALLOY_UI)  (localhost only)   logs: make infra-logs"

infra-down: ## Stop the production observability stack
	docker compose -f $(INFRA_DEPLOY) down

infra-logs: ## Follow the Alloy collector logs (production stack)
	docker compose -f $(INFRA_DEPLOY) logs -f alloy

infra-ps: ## Show container status for both observability stacks
	@echo "==> deployment"
	@docker compose -f $(INFRA_DEPLOY) ps
	@echo "==> development"
	@docker compose -f $(INFRA_DEV) ps

infra-dev-up: ## Start the local observability stack (Loki + Grafana, no cloud creds)
	docker compose -f $(INFRA_DEV) up -d --build
	@echo "    grafana: http://localhost:3001   loki: http://localhost:3100   alloy ui: $(ALLOY_UI)"

infra-dev-down: ## Stop the local observability stack
	docker compose -f $(INFRA_DEV) down

obs-check: ## Health-check the running collector (Alloy UI + OTLP receiver)
	@printf "alloy ui   %s ... " "$(ALLOY_UI)"
	@if curl -fsS -o /dev/null --max-time 3 "$(ALLOY_UI)/-/ready"; then \
		echo "ready"; \
	else \
		echo "unreachable (is a stack up? try: make infra-ps)"; \
	fi
	@printf "otlp http  http://127.0.0.1:4318 ... "
	@if curl -fsS -o /dev/null --max-time 3 -X POST -H 'Content-Type: application/json' \
		-d '{"resourceLogs":[]}' http://127.0.0.1:4318/v1/logs; then \
		echo "accepting"; \
	else \
		echo "not published (expected for the deployment stack — it keeps 4318 internal)"; \
	fi

clean: ## Remove local caches and build artifacts (keeps backups/ dir itself)
	rm -rf .venv $(APP_DIR)/.venv
	rm -rf .mypy_cache $(APP_DIR)/.mypy_cache
	rm -rf .ruff_cache $(APP_DIR)/.ruff_cache
	rm -rf .pytest_cache $(APP_DIR)/.pytest_cache
	find . -type d -name __pycache__ -not -path './.git/*' -prune -exec rm -rf {} +
	find backups -mindepth 1 -not -name '.gitkeep' -delete

status: ## Show git status and recent commits
	git status --short
	@echo "---"
	git log --oneline -5

deploy: ## Deploy (placeholder until a deploy flow is defined)
	@if [ -x scripts/deploy.sh ]; then \
		scripts/deploy.sh; \
	else \
		echo "TODO: deploy flow not defined yet — see scripts/ for a future deploy.sh"; \
	fi
