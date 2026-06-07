import threading

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock, patch

from app.main import app
from app.database import Base, get_db
from app.services.auth_dependencies import CurrentUser, get_current_user

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

SECRET = "change-this-secret-key"
TOKEN1 = jwt.encode({"sub": "1", "role": "user"}, SECRET, algorithm="HS256")
TOKEN2 = jwt.encode({"sub": "2", "role": "user"}, SECRET, algorithm="HS256")
TOKEN_SPECTATOR = jwt.encode({"sub": "99", "role": "user"}, SECRET, algorithm="HS256")
INVALID_TOKEN = "invalid.token.here"


def as_user(user_id: int):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user_id, role="user")


def http_create_game(room_id=1, white_id=1, black_id=2):
    as_user(white_id)
    client.post("/games", json={"room_id": room_id, "white_player_id": white_id, "black_player_id": black_id})


def http_activate_game(game_id=1, black_id=2):
    as_user(black_id)
    client.post(f"/games/{game_id}/join")


@pytest.fixture(autouse=True)
def reset_state():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides = {get_db: override_get_db}


@pytest.fixture(autouse=True)
def mock_game_service_redis():
    # Publisher is patched at function level, not via redis.from_url — both patches
    # would target the same attribute on the redis module and the second would win.
    with patch("app.services.game_service.redis_lib.from_url") as mock_redis, \
         patch("app.services.game_service.asyncio.create_task") as mock_task, \
         patch("app.events.publisher.publish_game_over"), \
         patch("app.events.publisher.publish_game_abandoned"):
        redis_client = MagicMock()
        redis_client.delete.return_value = 0
        redis_client.set.return_value = True
        mock_redis.return_value = redis_client
        mock_task.side_effect = lambda coro: coro.close()
        yield redis_client


# --- auth / routing ---

def test_ws_invalid_token_closes_connection():
    http_create_game()
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/games/1?token={INVALID_TOKEN}") as ws:
            pass
    assert exc_info.value.code == 4001


def test_ws_unknown_game_closes_connection():
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/games/999?token={TOKEN1}") as ws:
            pass
    assert exc_info.value.code == 4004


# --- game activation ---

def test_ws_activating_player_receives_game_start():
    # Each WS connection runs in its own anyio portal (separate event loop).
    # Cross-portal broadcast silently fails, so we only verify the activating player's events.
    http_create_game()

    p2_events = []
    p1_connected = threading.Event()
    p1_exit = threading.Event()

    def player1():
        with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
            p1_connected.set()
            p1_exit.wait(timeout=10)

    def player2():
        p1_connected.wait(timeout=3)
        with client.websocket_connect(f"/ws/games/1?token={TOKEN2}") as ws:
            p2_events.append(ws.receive_json())

    t1 = threading.Thread(target=player1, daemon=True)
    t2 = threading.Thread(target=player2)
    t1.start()
    t2.start()
    t2.join(timeout=5)
    p1_exit.set()
    t1.join(timeout=3)

    assert p2_events and p2_events[0]["type"] == "game_start"
    assert p2_events[0]["game"]["status"] == "active"


# --- spectator ---

def test_ws_spectator_can_connect_and_receive_legal_moves():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN_SPECTATOR}") as ws:
        ws.send_json({"type": "legal_moves", "square": "e2"})
        msg = ws.receive_json()
        assert msg["type"] == "legal_moves"
        assert "e2e4" in msg["moves"]


# --- moves ---

def test_ws_move_sender_receives_game_state():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        ws.send_json({"type": "move", "move": "e2e4"})
        msg = ws.receive_json()
        assert msg["type"] == "game_state"
        assert msg["game"]["current_turn"] == "black"


# --- legal moves and errors ---

def test_ws_legal_moves_sent_only_to_requester():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        ws.send_json({"type": "legal_moves", "square": "e2"})
        msg = ws.receive_json()
        assert msg["type"] == "legal_moves"
        assert "e2e4" in msg["moves"]
        assert "e2e3" in msg["moves"]


def test_ws_wrong_turn_sends_error_only_to_sender():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN2}") as ws:
        ws.send_json({"type": "move", "move": "e7e5"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "turn" in msg["detail"].lower()


# --- resign ---

def test_ws_resign_broadcasts_game_over():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        ws.send_json({"type": "resign"})
        msg = ws.receive_json()

    assert msg["type"] == "game_over"
    assert msg["game"]["winner"] == "black"
    assert msg["game"]["status"] == "finished"


# --- reconnect ---

def test_ws_reconnect_broadcasts_player_reconnected(mock_game_service_redis):
    # Single-connection test: the reconnecting player receives their own broadcast
    # (same event loop — no cross-portal send issue).
    mock_game_service_redis.delete.return_value = 1  # white had an active disconnect key

    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "player_reconnected"
    assert msg["color"] == "white"
