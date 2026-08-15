"""RequestIDMiddleware — pure ASGI, per Async & Resource Design §7.

Reads `X-Request-ID` or generates a uuid4, stashes it in a contextvar, and
echoes it on the response. Pure ASGI (not `BaseHTTPMiddleware`) so the
endpoint runs in the *same* task and the contextvar is visible there and in
the global exception handler — the whole point of this pattern.
"""

from contextvars import ContextVar
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ._headers import get_header

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = get_header(scope, b"x-request-id") or str(uuid4())
        token = request_id_ctx.set(request_id)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_ctx.reset(token)


def get_request_id() -> str | None:
    return request_id_ctx.get()
