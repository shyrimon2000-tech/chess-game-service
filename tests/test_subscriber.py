import json
from unittest.mock import MagicMock, patch

from app.events.subscriber import _handle_message


def test_room_created_creates_game():
    message = {
        "type": "message",
        "data": json.dumps({
            "event": "room_created",
            "room_id": 42,
            "white_player_id": 7,
        }),
    }
    with patch("app.events.subscriber.game_service.create_game") as mock_create, \
         patch("app.events.subscriber.SessionLocal") as mock_session, \
         patch("app.events.subscriber.publish_game_created"):
        mock_db = MagicMock()
        mock_session.return_value = mock_db

        _handle_message(message)

        mock_create.assert_called_once_with(mock_db, room_id=42, white_player_id=7)
        mock_db.close.assert_called_once()


def test_non_message_type_is_ignored():
    message = {"type": "subscribe", "data": None}
    with patch("app.events.subscriber.game_service.create_game") as mock_create:
        _handle_message(message)
        mock_create.assert_not_called()


def test_invalid_json_is_handled_gracefully():
    message = {"type": "message", "data": "not-json"}
    with patch("app.events.subscriber.game_service.create_game") as mock_create:
        _handle_message(message)
        mock_create.assert_not_called()


def test_room_activated_activates_game():
    message = {
        "type": "message",
        "data": json.dumps({
            "event": "room_activated",
            "room_id": 42,
            "black_player_id": 12,
        }),
    }
    with patch("app.events.subscriber.game_service.activate_game") as mock_activate, \
         patch("app.events.subscriber.SessionLocal") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value = mock_db

        _handle_message(message)

        mock_activate.assert_called_once_with(mock_db, room_id=42, black_player_id=12)
        mock_db.close.assert_called_once()


def test_unknown_event_is_ignored():
    message = {
        "type": "message",
        "data": json.dumps({"event": "something_else", "room_id": 1}),
    }
    with patch("app.events.subscriber.game_service.create_game") as mock_create:
        _handle_message(message)
        mock_create.assert_not_called()
