"""The error envelope, per API Surface §7: `{"error": {"code", "message", "request_id"}}`."""

from fastapi.responses import ORJSONResponse

from .middleware.request_id import get_request_id


def error_response(status_code: int, code: str, message: str) -> ORJSONResponse:
    return ORJSONResponse(
        {"error": {"code": code, "message": message, "request_id": get_request_id()}},
        status_code=status_code,
    )
