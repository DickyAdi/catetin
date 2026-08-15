"""GET /health (liveness, no DB) and GET /health/ready (readiness), per API Surface §3-4."""

import time

from fastapi import APIRouter, Depends
from fastapi.responses import ORJSONResponse
from sqlalchemy import text

from catetin.adapters.outbound.persistence.version_check import check_db_revision

from ..state import APP_VERSION, AppState, get_state

router = APIRouter()


@router.get("/health")
async def health(state: AppState = Depends(get_state)) -> dict[str, object]:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "uptime_s": int(time.monotonic() - state.started_at),
    }


@router.get("/health/ready")
async def health_ready(state: AppState = Depends(get_state)) -> ORJSONResponse:
    checks: dict[str, str] = {}
    reason: str | None = None
    ready = True

    try:
        async with state.reader_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — any DB failure means "not ready", by design
        checks["database"] = "error"
        reason = str(exc)
        ready = False

    try:
        await check_db_revision(state.reader_engine, state.settings.expected_db_revision)
        checks["schema"] = "ok"
    except RuntimeError as exc:
        checks["schema"] = "error"
        reason = str(exc)
        ready = False

    if ready:
        return ORJSONResponse({"status": "ready", "checks": checks})
    return ORJSONResponse(
        {"status": "not_ready", "checks": checks, "reason": reason}, status_code=503
    )
