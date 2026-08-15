APP_DIR := apps/api

.DEFAULT_GOAL := help

.PHONY: help setup dev test lint typecheck migrate migrate-new \
	dockerized docker-up docker-down clean status deploy

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend (uv) and web (npm, once it exists) deps; seed .env
	cd $(APP_DIR) && uv sync
	@if [ -f apps/web/package.json ]; then \
		cd apps/web && npm ci; \
	else \
		echo "note: apps/web has no package.json yet — web setup skipped"; \
	fi
	@if [ -f $(APP_DIR)/.env.example ] && [ ! -f $(APP_DIR)/.env ]; then \
		cp $(APP_DIR)/.env.example $(APP_DIR)/.env; \
		echo "created $(APP_DIR)/.env from .env.example — fill in real values"; \
	fi

dev: ## Run the backend dev server with reload (needs apps/api/.env — see .env.example)
	cd $(APP_DIR) && uv run uvicorn catetin.main:app --reload --app-dir src

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
