"""GET /ops (operator HTML page) and GET /ops/api/stats (JSON), per API Surface §6.

Both are behind Basic auth and get `X-Robots-Tag: noindex` — the payload
carries raw user text and `rss_bytes`, and the domain is crawlable now that
a public marketing site exists. `/robots.txt` disallows `/ops` for the same
reason.
"""

import hmac
import resource
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, ORJSONResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import func, select

from catetin.adapters.outbound.persistence.orm import (
    InboxRow,
    ParseFailureRow,
    TransactionRow,
    UserRow,
)

from ..state import AppState, get_state

router = APIRouter()
_basic = HTTPBasic()


def verify_ops_auth(
    credentials: HTTPBasicCredentials = Depends(_basic),
    state: AppState = Depends(get_state),
) -> None:
    valid_user = hmac.compare_digest(credentials.username, state.settings.ops_username)
    valid_pass = hmac.compare_digest(
        credentials.password, state.settings.ops_password.get_secret_value()
    )
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=401,
            detail="invalid ops credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


async def _collect_stats(state: AppState) -> dict[str, Any]:
    today = state.clock.today_local(state.settings.timezone).isoformat()
    since_24h = int((state.clock.now() - timedelta(hours=24)).timestamp())

    async with state.reader_engine.connect() as conn:
        users_total = (
            await conn.execute(select(func.count()).select_from(UserRow))
        ).scalar_one()
        transactions_today = (
            await conn.execute(
                select(func.count())
                .select_from(TransactionRow)
                .where(
                    TransactionRow.occurred_on == today,
                    TransactionRow.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        failures_24h = (
            await conn.execute(
                select(func.count())
                .select_from(ParseFailureRow)
                .where(ParseFailureRow.created_at >= since_24h)
            )
        ).scalar_one()
        successes_24h = (
            await conn.execute(
                select(func.count())
                .select_from(TransactionRow)
                .where(
                    TransactionRow.created_at >= since_24h,
                    TransactionRow.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        queue_depth = (
            await conn.execute(
                select(func.count())
                .select_from(InboxRow)
                .where(InboxRow.processed_at.is_(None))
            )
        ).scalar_one()

    attempts_24h = failures_24h + successes_24h
    parse_failure_rate_24h = failures_24h / attempts_24h if attempts_24h else 0.0

    return {
        "users_total": users_total,
        "transactions_today": transactions_today,
        "parse_failure_rate_24h": round(parse_failure_rate_24h, 4),
        "queue_depth": queue_depth,
        "rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }


@router.get("/ops/api/stats", dependencies=[Depends(verify_ops_auth)])
async def ops_stats(state: AppState = Depends(get_state)) -> ORJSONResponse:
    stats = await _collect_stats(state)
    return ORJSONResponse(stats, headers={"X-Robots-Tag": "noindex"})


@router.get("/ops", dependencies=[Depends(verify_ops_auth)])
async def ops_page(state: AppState = Depends(get_state)) -> HTMLResponse:
    stats = await _collect_stats(state)
    rows = "".join(f"<tr><th>{key}</th><td>{value}</td></tr>" for key, value in stats.items())
    html = f"""<!doctype html>
<html><head><title>CatetIn Ops</title></head>
<body>
<h1>CatetIn Ops</h1>
<table border="1">{rows}</table>
</body></html>"""
    return HTMLResponse(html, headers={"X-Robots-Tag": "noindex"})


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nDisallow: /ops\n")
