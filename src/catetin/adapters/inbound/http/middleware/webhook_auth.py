"""WebhookAuthMiddleware — pure ASGI.

Constant-time compare of the Telegram webhook path secret, scoped to the
webhook path prefix (per Async & Resource Design §7) — `/health` and `/ops`
never start with that prefix, so they pass through untouched without any
special-casing here.
"""

import hmac

from fastapi.responses import ORJSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def _forbidden_response() -> ORJSONResponse:
    return ORJSONResponse(
        {"error": {"code": "forbidden", "message": "invalid secret token"}},
        status_code=403,
    )


class WebhookAuthMiddleware:
    def __init__(self, app: ASGIApp, webhook_prefix: str, secret: str) -> None:
        self.app = app
        self.webhook_prefix = webhook_prefix
        self.secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.webhook_prefix):
            await self.app(scope, receive, send)
            return

        provided = scope["path"][len(self.webhook_prefix) :]
        if not hmac.compare_digest(provided, self.secret):
            await _forbidden_response()(scope, receive, send)
            return

        await self.app(scope, receive, send)
