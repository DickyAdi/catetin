# Build context is the repo root (see ../../compose.yaml) — apps/api is a uv
# workspace member, so the workspace root's pyproject.toml/uv.lock (one repo
# above this file) must be visible to `uv sync`.
#
# Two stages: the builder owns uv and the resolver caches, the runtime image
# gets only the finished venv plus the source it needs. Nothing that is merely
# needed to *produce* the venv (uv itself, download caches, the intermediate
# --no-install-project layer) reaches the shipped image.

# --------------------------------------------------------------------------
# Stage 1 — builder
# --------------------------------------------------------------------------
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Bind the venv to this image's interpreter instead of a uv-managed
    # download: /app/.venv is copied into a runtime stage off the same base,
    # so its python symlink must point at a path that exists there too.
    UV_PYTHON=python3.13 \
    UV_PYTHON_DOWNLOADS=never \
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

# --------------------------------------------------------------------------
# Stage 2 — runtime
# --------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1

# Created before the COPYs so --chown can name it: chowning after the fact
# would rewrite every copied file into a second, full-size layer.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

# The venv is relocatable only to the same absolute path — /app/.venv here,
# /app/.venv there. `catetin` is installed editable, so apps/api/src has to
# land at the path the builder recorded as well.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/packages /app/packages
COPY --from=builder --chown=appuser:appuser /app/apps/api /app/apps/api

USER appuser

WORKDIR /app/apps/api
EXPOSE 8000

# Run the venv's uvicorn directly (not `uv run`) — uv is not installed here at
# all, and `uv run` would implicitly re-sync on every start anyway, pulling the
# dev group back in and undoing the --no-dev build above. PYTHONPATH covers the
# src/ layout in place of --app-dir (uv run's flag; plain uvicorn has none).
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/apps/api/src
CMD ["/app/.venv/bin/uvicorn", "catetin.main:app", "--host", "0.0.0.0", "--port", "8000"]
