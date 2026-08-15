"""AccessLogMiddleware — pure ASGI, one orjson line per request.

Replaces uvicorn's own access log (`--no-access-log`, see Async & Resource
Design §2) to avoid double formatting. Skips `/health` to keep logs quiet.
"""

import logging
import time

import orjson
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .request_id import get_request_id

_logger = logging.getLogger("catetin.access")

_QUIET_PATHS = frozenset({"/health"})


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _QUIET_PATHS:
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_holder = {"status": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            line = orjson.dumps(
                {
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_holder["status"],
                    "duration_ms": round(duration_ms, 2),
                    "request_id": get_request_id(),
                }
            )
            _logger.info(line.decode())
