"""Global exception handlers -> the error envelope, per API Surface §7.

`{"error": {"code", "message", "request_id"}}` on every error response.
Domain errors map to their HTTP status; anything else is a 500 whose
traceback is logged alongside the request id.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from catetin.domain.errors import DomainValidationError, NotFound, RateLimited

from .errors import error_response
from .middleware.request_id import get_request_id

_logger = logging.getLogger("catetin.errors")

_HTTP_CODE_NAMES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainValidationError)
    async def _domain_validation(
        request: Request, exc: DomainValidationError
    ) -> ORJSONResponse:
        return error_response(422, "validation_error", str(exc))

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound) -> ORJSONResponse:
        return error_response(404, "not_found", str(exc))

    @app.exception_handler(RateLimited)
    async def _rate_limited(request: Request, exc: RateLimited) -> ORJSONResponse:
        return error_response(429, "rate_limited", str(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> ORJSONResponse:
        code = _HTTP_CODE_NAMES.get(exc.status_code, "http_error")
        response = error_response(exc.status_code, code, str(exc.detail))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> ORJSONResponse:
        _logger.exception(
            "unhandled exception", extra={"request_id": get_request_id()}
        )
        return error_response(500, "internal_error", "internal server error")
