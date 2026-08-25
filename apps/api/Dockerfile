# Build context is the repo root (see ../../compose.yaml) — apps/api is a uv
# workspace member, so the workspace root's pyproject.toml/uv.lock (one repo
# above this file) must be visible to `uv sync`.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --no-dev: pytest/ruff/mypy/alembic stay off the runtime image. Migrations
# run on the host/CI (`make migrate`) before deploy, per CLAUDE.md.
#
# Manifests first so dependency layers cache across source-only changes.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-project --project apps/api

# Shared brand assets (logos, fonts). `catetin.assets` resolves these relative
# to the workspace root, so they must exist in the image at the same path.
COPY packages packages

COPY apps/api apps/api
RUN uv sync --frozen --no-dev --project apps/api

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

WORKDIR /app/apps/api
EXPOSE 8000

# Run the venv's uvicorn directly (not `uv run`) — `uv run` implicitly
# re-syncs on every start, which would pull the dev group back in and undo
# the --no-dev build above. PYTHONPATH covers the src/ layout in place of
# --app-dir (uv run's flag; plain uvicorn doesn't have one).
ENV PYTHONPATH=/app/apps/api/src
CMD ["/app/.venv/bin/uvicorn", "catetin.main:app", "--host", "0.0.0.0", "--port", "8000"]
