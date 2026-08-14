"""ASGI entrypoint. Run with: uvicorn catetin.main:app"""

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from .composition import build_app

try:
    app = build_app()
except NotImplementedError:
    # composition.py has nothing to wire yet in Phase 1 (Foundation). This
    # placeholder keeps the app importable and startable until repositories,
    # adapters, and routes land in later phases.
    app = FastAPI(title="CatetIn", default_response_class=ORJSONResponse)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "catetin", "status": "bootstrap"}
