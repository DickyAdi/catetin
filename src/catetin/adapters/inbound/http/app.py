"""Builds the FastAPI app: routes, pure-ASGI middleware, exception handlers, lifespan.

Per Modules M5-M8 §M6: `ORJSONResponse` as the default response class, no
OpenAPI UI in prod (RAM + surface), and the middleware stack is 100% pure
ASGI (no `BaseHTTPMiddleware`) so `contextvars` set in `RequestIDMiddleware`
propagate through to the endpoint and the exception handlers.
"""

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from catetin.config import Settings

from .exceptions import register_exception_handlers
from .lifespan import build_lifespan
from .middleware import (
    AccessLogMiddleware,
    BodySizeLimitMiddleware,
    RequestIDMiddleware,
    WebhookAuthMiddleware,
)
from .routes import health, ops, webhook


def create_http_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="CatetIn",
        default_response_class=ORJSONResponse,
        docs_url=None,
        redoc_url=None,
        lifespan=build_lifespan(settings),
    )

    app.include_router(health.router)
    app.include_router(webhook.router)
    app.include_router(ops.router)

    register_exception_handlers(app)

    # add_middleware wraps outside-in: the *last* one added ends up outermost,
    # so this is written innermost -> outermost to read as the §M6 stack
    # (RequestID -> AccessLog -> BodyLimit -> WebhookAuth, outermost first).
    webhook_prefix = settings.webhook_path.split("{secret}")[0]
    app.add_middleware(
        WebhookAuthMiddleware,
        webhook_prefix=webhook_prefix,
        secret=settings.telegram_webhook_secret.get_secret_value(),
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.body_max_bytes)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)

    return app
