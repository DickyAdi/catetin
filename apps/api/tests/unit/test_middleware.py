"""Middleware unit tests — each middleware wrapped around a minimal ASGI app.

No FastAPI app or database needed here; these exercise the pure-ASGI
middleware classes directly against httpx.AsyncClient + ASGITransport.
"""

import logging

import orjson
import pytest
from httpx import ASGITransport, AsyncClient
from starlette.types import Receive, Scope, Send

from catetin.adapters.inbound.http.middleware import (
    AccessLogMiddleware,
    BodySizeLimitMiddleware,
    RequestIDMiddleware,
    WebhookAuthMiddleware,
)


async def _echo_app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        return
    body = b""
    more_body = True
    while more_body:
        message = await receive()
        body += message.get("body", b"")
        more_body = message.get("more_body", False)
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": orjson.dumps({"ok": True})})


async def _client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_request_id_generated_when_absent() -> None:
    async with await _client(RequestIDMiddleware(_echo_app)) as client:
        response = await client.get("/")
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"]


async def test_request_id_echoes_incoming_header() -> None:
    async with await _client(RequestIDMiddleware(_echo_app)) as client:
        response = await client.get("/", headers={"x-request-id": "my-req-id"})
    assert response.headers["x-request-id"] == "my-req-id"


async def test_body_limit_allows_small_body() -> None:
    app = BodySizeLimitMiddleware(_echo_app, max_bytes=256_000)
    async with await _client(app) as client:
        response = await client.post("/", content=b"x" * 100)
    assert response.status_code == 200


async def test_body_limit_rejects_large_content_length() -> None:
    app = BodySizeLimitMiddleware(_echo_app, max_bytes=256_000)
    async with await _client(app) as client:
        response = await client.post("/", content=b"x" * (256_000 + 1))
    assert response.status_code == 413


async def test_body_limit_rejects_large_chunked_body(monkeypatch: pytest.MonkeyPatch) -> None:
    # httpx always sets Content-Length for bytes content, so drive the
    # middleware directly to exercise the no-Content-Length drain path.
    app = BodySizeLimitMiddleware(_echo_app, max_bytes=10)

    messages = [
        {"type": "http.request", "body": b"x" * 6, "more_body": True},
        {"type": "http.request", "body": b"x" * 6, "more_body": False},
    ]

    async def receive() -> dict:
        return messages.pop(0)

    sent = []

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/", "headers": []}
    await app(scope, receive, send)

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


async def test_webhook_auth_rejects_wrong_secret() -> None:
    app = WebhookAuthMiddleware(_echo_app, webhook_prefix="/webhook/telegram/", secret="right")
    async with await _client(app) as client:
        response = await client.post("/webhook/telegram/wrong")
    assert response.status_code == 403


async def test_webhook_auth_allows_correct_secret() -> None:
    app = WebhookAuthMiddleware(_echo_app, webhook_prefix="/webhook/telegram/", secret="right")
    async with await _client(app) as client:
        response = await client.post("/webhook/telegram/right")
    assert response.status_code == 200


async def test_webhook_auth_excludes_unrelated_paths() -> None:
    app = WebhookAuthMiddleware(_echo_app, webhook_prefix="/webhook/telegram/", secret="right")
    async with await _client(app) as client:
        response = await client.get("/health")
    assert response.status_code == 200


@pytest.fixture
def _access_logger() -> logging.Logger:
    # alembic's env.py calls logging.config.fileConfig(), which disables
    # (Logger.disabled = True) any logger not listed in alembic.ini —
    # including this one — as a side effect of running migrations in an
    # earlier test. Force it back on so this test doesn't depend on
    # suite-wide ordering.
    logger = logging.getLogger("catetin.access")
    logger.disabled = False
    return logger


async def test_access_log_does_not_crash(
    caplog: pytest.LogCaptureFixture, _access_logger: logging.Logger
) -> None:
    app = AccessLogMiddleware(_echo_app)
    with caplog.at_level(logging.INFO, logger="catetin.access"):
        async with await _client(app) as client:
            response = await client.get("/somewhere")
    assert response.status_code == 200
    assert any("somewhere" in record.getMessage() for record in caplog.records)


async def test_access_log_skips_health_path(
    caplog: pytest.LogCaptureFixture, _access_logger: logging.Logger
) -> None:
    app = AccessLogMiddleware(_echo_app)
    with caplog.at_level(logging.INFO, logger="catetin.access"):
        async with await _client(app) as client:
            response = await client.get("/health")
    assert response.status_code == 200
    assert not caplog.records
