"""End-to-end HTTP tests against the real built app (routes + middleware +
lifespan) over a migrated tmp_path SQLite database.

`migrated_settings` / `database_url` come from `tests/integration/conftest.py`.
"""

import time
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from telegram import Bot

from catetin import composition
from catetin.adapters.inbound.http import create_http_app
from catetin.adapters.inbound.http.state import AppState
from catetin.config import Settings


def _text_update(update_id: int, user_id: int, text: str) -> dict:
    message: dict = {
        "message_id": update_id,
        "from": {"id": user_id, "is_bot": False, "first_name": "Rina"},
        "chat": {"id": user_id, "type": "private"},
        "date": int(time.time()),
        "text": text,
    }
    if text.startswith("/"):
        # Real Telegram tags slash-commands with a `bot_command` entity —
        # without it PTB's CommandHandler falls through and treats the text
        # as a plain message (see CommandHandler.check_update).
        length = len(text.split(maxsplit=1)[0])
        message["entities"] = [{"type": "bot_command", "offset": 0, "length": length}]
    return {"update_id": update_id, "message": message}


@pytest.fixture
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_http_app(migrated_settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_webhook_correct_secret_returns_accepted(client: AsyncClient) -> None:
    response = await client.post("/webhook/telegram/test-secret", json={"update_id": 1})
    assert response.status_code == 200
    assert response.json() == {"accepted": True}


async def test_webhook_wrong_secret_returns_forbidden(client: AsyncClient) -> None:
    response = await client.post("/webhook/telegram/wrong-secret", json={"update_id": 1})
    assert response.status_code == 403


async def test_webhook_text_message_is_dispatched_to_the_telegram_handler(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: durable enqueue -> PTB dispatch -> record_transactions ->
    a reply via `MessagingPort`. `Bot.send_message` is stubbed (no real
    Telegram network call, per conftest's ban on it) so the assertion is on
    what the fake captured, not on a raw HTTP call to Telegram.
    """
    sent: list[tuple[int, str]] = []

    async def fake_send_message(self: Bot, chat_id: int, text: str, **_: object) -> None:
        sent.append((chat_id, text))

    monkeypatch.setattr(Bot, "send_message", fake_send_message)

    response = await client.post(
        "/webhook/telegram/test-secret",
        json=_text_update(3001, 555444, "jual ayam geprek 50rb"),
    )
    assert response.status_code == 200
    assert response.json() == {"accepted": True}

    state = app.state.catetin
    assert state.telegram_update_queue is not None
    await state.telegram_update_queue.join()

    assert sent, "the handler should have replied via MessagingPort"
    assert "50.000" in sent[0][1]


async def test_webhook_flagged_transaction_is_marked_in_the_reply(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-1 end-to-end: "dapet duit" carries a sale verb, so it is recorded
    without an ambiguity prompt. The flag must still be visible right away —
    previously the reply was indistinguishable from real business income and
    the flag only surfaced much later at `/lapor`'s review gate.
    """
    sent: list[tuple[int, str]] = []

    async def fake_send_message(self: Bot, chat_id: int, text: str, **_: object) -> None:
        sent.append((chat_id, text))

    monkeypatch.setattr(Bot, "send_message", fake_send_message)

    response = await client.post(
        "/webhook/telegram/test-secret",
        json=_text_update(3101, 555111, "dapet duit 50rb di jalan"),
    )
    assert response.status_code == 200

    state = app.state.catetin
    await state.telegram_update_queue.join()

    assert sent, "the handler should have replied via MessagingPort"
    reply = sent[0][1]
    assert "50.000" in reply  # still recorded — the flag never rejects
    assert "⚠️" in reply
    assert "bukan pemasukan usaha" in reply


async def test_webhook_plain_sale_reply_has_no_flag_warning(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[int, str]] = []

    async def fake_send_message(self: Bot, chat_id: int, text: str, **_: object) -> None:
        sent.append((chat_id, text))

    monkeypatch.setattr(Bot, "send_message", fake_send_message)

    await client.post(
        "/webhook/telegram/test-secret",
        json=_text_update(3102, 555222, "jual ayam geprek 50rb"),
    )
    await app.state.catetin.telegram_update_queue.join()

    assert sent
    assert "⚠️" not in sent[0][1]


async def test_webhook_start_command_sends_welcome_message(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[int, str]] = []

    async def fake_send_message(self: Bot, chat_id: int, text: str, **_: object) -> None:
        sent.append((chat_id, text))

    monkeypatch.setattr(Bot, "send_message", fake_send_message)

    response = await client.post(
        "/webhook/telegram/test-secret", json=_text_update(3002, 777888, "/start")
    )
    assert response.status_code == 200

    state = app.state.catetin
    await state.telegram_update_queue.join()

    assert sent
    assert "CatetIn" in sent[0][1]


async def test_webhook_duplicate_update_id_is_not_reprocessed(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[int, str]] = []

    async def fake_send_message(self: Bot, chat_id: int, text: str, **_: object) -> None:
        sent.append((chat_id, text))

    monkeypatch.setattr(Bot, "send_message", fake_send_message)

    payload = _text_update(3003, 999000, "/start")
    state = app.state.catetin

    first = await client.post("/webhook/telegram/test-secret", json=payload)
    assert first.status_code == 200
    await state.telegram_update_queue.join()
    assert len(sent) == 1

    second = await client.post("/webhook/telegram/test-secret", json=payload)
    assert second.status_code == 200
    await state.telegram_update_queue.join()
    assert len(sent) == 1  # the duplicate update_id was not re-dispatched


async def test_webhook_lapor_command_sends_pdf_document(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[int, str]] = []
    documents: list[tuple[int, str, bytes, str | None]] = []

    async def fake_send_message(self: Bot, chat_id: int, text: str, **_: object) -> None:
        sent.append((chat_id, text))

    async def fake_send_document(
        self: Bot, chat_id: int, document: bytes, filename: str, caption: str | None = None,
        **_: object,
    ) -> None:
        documents.append((chat_id, filename, bytes(document), caption))

    monkeypatch.setattr(Bot, "send_message", fake_send_message)
    monkeypatch.setattr(Bot, "send_document", fake_send_document)

    response = await client.post(
        "/webhook/telegram/test-secret",
        json=_text_update(3004, 444555, "/lapor"),
    )
    assert response.status_code == 200

    state = app.state.catetin
    await state.telegram_update_queue.join()

    assert documents, "the /lapor handler should have sent a PDF document"
    chat_id, filename, content, caption = documents[0]
    assert chat_id == 444555
    assert filename.endswith(".pdf")
    assert content[:5] == b"%PDF-"
    assert caption is not None and "Laporan" in caption


def _callback_update(update_id: int, user_id: int, data: str) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cbq{update_id}",
            "from": {"id": user_id, "is_bot": False, "first_name": "Rina"},
            "message": {
                "message_id": update_id,
                "date": int(time.time()),
                "chat": {"id": user_id, "type": "private"},
            },
            "chat_instance": "1",
            "data": data,
        },
    }


async def test_webhook_lapor_with_flagged_shows_review_gate_then_sends_clean_pdf(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-2 end-to-end: a flagged transaction holds `/lapor` behind a review
    gate; pressing "Keluarkan dari laporan" excludes it and sends the PDF."""
    sent: list[tuple[int, str, object]] = []
    documents: list[tuple[int, str, bytes, str | None]] = []

    async def fake_send_message(self: Bot, chat_id: int, text: str, **kwargs: object) -> None:
        sent.append((chat_id, text, kwargs.get("reply_markup")))

    async def fake_send_document(
        self: Bot, chat_id: int, document: bytes, filename: str, caption: str | None = None,
        **_: object,
    ) -> None:
        documents.append((chat_id, filename, bytes(document), caption))

    async def fake_answer_callback_query(self: Bot, callback_query_id: str, **_: object) -> bool:
        return True

    monkeypatch.setattr(Bot, "send_message", fake_send_message)
    monkeypatch.setattr(Bot, "send_document", fake_send_document)
    monkeypatch.setattr(Bot, "answer_callback_query", fake_answer_callback_query)

    state = app.state.catetin
    user_id = 665544

    response = await client.post(
        "/webhook/telegram/test-secret",
        json=_text_update(4001, user_id, "dapet duit 50k di jalan"),
    )
    assert response.status_code == 200
    await state.telegram_update_queue.join()

    response = await client.post(
        "/webhook/telegram/test-secret", json=_text_update(4002, user_id, "/lapor")
    )
    assert response.status_code == 200
    await state.telegram_update_queue.join()

    assert not documents, "no PDF yet — the review gate should come first"
    review_messages = [s for s in sent if "bukan usaha" in s[1].lower()]
    assert review_messages, "expected the review-gate message"
    _, review_text, keyboard = review_messages[-1]
    assert "1 transaksi" in review_text
    assert keyboard is not None
    exclude_data = keyboard.inline_keyboard[0][0].callback_data
    assert exclude_data.startswith("review_exclude:")

    response = await client.post(
        "/webhook/telegram/test-secret", json=_callback_update(4003, user_id, exclude_data)
    )
    assert response.status_code == 200
    await state.telegram_update_queue.join()

    assert documents, "the review decision should have sent a PDF"
    assert documents[0][1].endswith(".pdf")
    assert documents[0][2][:5] == b"%PDF-"


async def test_webhook_lapor_without_flagged_sends_pdf_directly(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[int, str]] = []
    documents: list[tuple[int, str, bytes, str | None]] = []

    async def fake_send_message(self: Bot, chat_id: int, text: str, **_: object) -> None:
        sent.append((chat_id, text))

    async def fake_send_document(
        self: Bot, chat_id: int, document: bytes, filename: str, caption: str | None = None,
        **_: object,
    ) -> None:
        documents.append((chat_id, filename, bytes(document), caption))

    monkeypatch.setattr(Bot, "send_message", fake_send_message)
    monkeypatch.setattr(Bot, "send_document", fake_send_document)

    user_id = 665545
    response = await client.post(
        "/webhook/telegram/test-secret", json=_text_update(4101, user_id, "jual ayam 50rb")
    )
    assert response.status_code == 200
    state = app.state.catetin
    await state.telegram_update_queue.join()

    response = await client.post(
        "/webhook/telegram/test-secret", json=_text_update(4102, user_id, "/lapor")
    )
    assert response.status_code == 200
    await state.telegram_update_queue.join()

    assert documents, "no flagged items — the PDF should be sent directly"


async def test_webhook_ambiguous_message_offers_bukan_usaha_and_excludes(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-3 end-to-end: the ambiguous keyboard offers a 3rd "Bukan Usaha"
    button; picking it records the transaction excluded from reports."""
    sent: list[tuple[int, str, object]] = []

    async def fake_send_message(self: Bot, chat_id: int, text: str, **kwargs: object) -> None:
        sent.append((chat_id, text, kwargs.get("reply_markup")))

    async def fake_answer_callback_query(self: Bot, callback_query_id: str, **_: object) -> bool:
        return True

    monkeypatch.setattr(Bot, "send_message", fake_send_message)
    monkeypatch.setattr(Bot, "answer_callback_query", fake_answer_callback_query)

    state = app.state.catetin
    user_id = 665546

    response = await client.post(
        "/webhook/telegram/test-secret", json=_text_update(4201, user_id, "gajian 2jt")
    )
    assert response.status_code == 200
    await state.telegram_update_queue.join()

    _, _, keyboard = sent[-1]
    assert keyboard is not None
    labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert labels == ["Jual", "Beli", "Bukan Usaha"]
    other_data = next(
        btn.callback_data
        for row in keyboard.inline_keyboard
        for btn in row
        if btn.text == "Bukan Usaha"
    )

    response = await client.post(
        "/webhook/telegram/test-secret", json=_callback_update(4202, user_id, other_data)
    )
    assert response.status_code == 200
    await state.telegram_update_queue.join()

    confirmation = [s for s in sent if "gak dimasukkan ke laporan usaha" in s[1]]
    assert confirmation, "expected the 'Bukan Usaha' confirmation reply"


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_health_ready_returns_ok_with_migrated_db(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


async def test_ops_stats_with_correct_auth_returns_json(
    client: AsyncClient, migrated_settings: Settings
) -> None:
    response = await client.get(
        "/ops/api/stats",
        auth=("test-ops", "test-ops-pass"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["users_total"] == 0
    assert body["transactions_today"] == 0
    assert body["queue_depth"] == 0


async def test_ops_stats_with_wrong_auth_returns_unauthorized(client: AsyncClient) -> None:
    response = await client.get(
        "/ops/api/stats",
        auth=("test-ops", "wrong-password"),
    )
    assert response.status_code == 401


async def test_health_ready_returns_service_unavailable_without_migration(
    database_url: str,
) -> None:
    # The lifespan itself refuses to *start* against an unmigrated database
    # (see lifespan.py step 2), so this exercises the endpoint's own
    # check_db_revision call directly: build the app and wire its state by
    # hand, skipping the lifespan gate that would otherwise abort startup.
    settings = Settings(
        telegram_bot_token="test-token",
        telegram_webhook_secret="test-secret",
        ops_username="test-ops",
        ops_password="test-ops-pass",
        database_url=database_url,
    )
    application = create_http_app(settings)
    engines = composition.create_engines(settings)
    deps = composition.wire(settings, engines)
    application.state.catetin = AppState(
        settings=settings,
        writer_engine=engines.writer,
        reader_engine=engines.reader,
        clock=deps.clock,
        started_at=time.monotonic(),
        reader_uow_factory=deps.reader_uow_factory,
    )

    try:
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health/ready")
        assert response.status_code == 503
    finally:
        await engines.writer.dispose()
        await engines.reader.dispose()
