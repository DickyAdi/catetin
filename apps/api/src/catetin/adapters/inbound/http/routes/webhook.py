"""POST /webhook/telegram/{secret}, per API Surface §5.

Secret validation happens in `WebhookAuthMiddleware` — if this handler runs
at all, the path secret already matched. This route never returns 5xx: any
failure in the (optional, Phase 6-populated) update callback is caught and
logged, and Telegram still gets its 200. A 5xx here would make Telegram
retry the same update forever.
"""

import logging

import orjson
from fastapi import APIRouter, Depends, Request
from fastapi.responses import ORJSONResponse

from ..errors import error_response
from ..state import AppState, get_state

router = APIRouter()
_logger = logging.getLogger("catetin.webhook")


@router.post("/webhook/telegram/{secret}")
async def telegram_webhook(
    secret: str, request: Request, state: AppState = Depends(get_state)
) -> ORJSONResponse:
    body = await request.body()
    try:
        payload = orjson.loads(body)
    except orjson.JSONDecodeError:
        payload = None

    if not isinstance(payload, dict):
        return error_response(400, "invalid_payload", "body must be a JSON object")

    if state.on_webhook_update is not None:
        try:
            await state.on_webhook_update(body)
        except Exception:
            _logger.exception("webhook update callback failed; acking anyway")

    return ORJSONResponse({"accepted": True})
