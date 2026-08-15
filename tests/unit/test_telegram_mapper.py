"""`Update -> InboundCommand` mapping — table-driven, no PTB Application needed."""

from telegram import Update

from catetin.adapters.inbound.telegram.mapper import map_update

_BASE_MESSAGE = {
    "message_id": 42,
    "from": {"id": 12345678, "is_bot": False, "first_name": "Rina"},
    "chat": {"id": 12345678, "type": "private"},
    "date": 1755225600,
}


def test_map_update_extracts_text_message_fields() -> None:
    update = Update.de_json(
        {
            "update_id": 918273645,
            "message": {**_BASE_MESSAGE, "text": "jual ayam geprek 50rb"},
        },
        bot=None,
    )

    cmd = map_update(update)

    assert cmd is not None
    assert cmd.platform == "telegram"
    assert cmd.platform_user_id == "12345678"
    assert cmd.chat_id == 12345678
    assert cmd.display_name == "Rina"
    assert cmd.text == "jual ayam geprek 50rb"
    assert cmd.sent_at == 1755225600
    assert cmd.update_id == 918273645


def test_map_update_extracts_command_text_verbatim() -> None:
    update = Update.de_json(
        {"update_id": 1, "message": {**_BASE_MESSAGE, "text": "/hariini"}}, bot=None
    )

    cmd = map_update(update)

    assert cmd is not None
    assert cmd.text == "/hariini"


def test_map_update_prefers_full_name_over_username() -> None:
    update = Update.de_json(
        {
            "update_id": 1,
            "message": {
                **_BASE_MESSAGE,
                "from": {
                    "id": 1,
                    "is_bot": False,
                    "first_name": "Rina",
                    "last_name": "S",
                    "username": "rina_s",
                },
                "text": "hi",
            },
        },
        bot=None,
    )

    cmd = map_update(update)

    assert cmd is not None
    assert cmd.display_name == "Rina S"


def test_map_update_returns_none_for_non_text_message() -> None:
    update = Update.de_json(
        {
            "update_id": 1,
            "message": {
                **_BASE_MESSAGE,
                "sticker": {
                    "file_id": "abc",
                    "file_unique_id": "abc-uniq",
                    "type": "regular",
                    "width": 100,
                    "height": 100,
                    "is_animated": False,
                    "is_video": False,
                },
            },
        },
        bot=None,
    )

    assert map_update(update) is None


def test_map_update_returns_none_without_update_id_message() -> None:
    update = Update.de_json({"update_id": 1}, bot=None)

    assert map_update(update) is None
