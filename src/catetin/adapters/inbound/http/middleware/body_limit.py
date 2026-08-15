"""BodySizeLimitMiddleware — pure ASGI, the RAM guard.

Rejects bodies over the configured limit with 413 *before* the app gets a
chance to buffer them: `Content-Length` is checked up front, and for bodies
without one (chunked) the middleware drains `receive()` itself, aborting the
instant the running total crosses the limit, so at most `max_bytes + 1`
bytes are ever held — never an unbounded buffer.
"""

from fastapi.responses import ORJSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ._headers import get_header

DEFAULT_MAX_BYTES = 256_000


def _too_large_response() -> ORJSONResponse:
    return ORJSONResponse(
        {
            "error": {
                "code": "payload_too_large",
                "message": "request body exceeds the size limit",
            }
        },
        status_code=413,
    )


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = get_header(scope, b"content-length")
        if content_length is not None and int(content_length) > self.max_bytes:
            await _too_large_response()(scope, receive, send)
            return

        buffered: list[Message] = []
        total = 0
        more_body = True

        while more_body:
            message = await receive()
            buffered.append(message)
            if message["type"] != "http.request":
                break
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await _too_large_response()(scope, receive, send)
                return
            more_body = message.get("more_body", False)

        async def replay_receive() -> Message:
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)
