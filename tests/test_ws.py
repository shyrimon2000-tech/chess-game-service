import asyncio
import contextlib
import json

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.config import settings
from app.database import Base, get_db
from app.services import game_service
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

TOKEN1 = jwt.encode({"sub": "1", "role": "user", "username": "alice"}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
TOKEN2 = jwt.encode({"sub": "2", "role": "user", "username": "bob"}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
TOKEN_SPECTATOR = jwt.encode({"sub": "99", "role": "user", "username": "spectator"}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
INVALID_TOKEN = "invalid.token.here"


def as_user(user_id: int):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user_id, role="user")


def http_create_game(room_id=1, white_id=1, black_id=2):
    db = TestingSessionLocal()
    try:
        game_service.create_game(db, room_id, white_id, black_id)
    finally:
        db.close()


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
    # Simulates Redis for nicknames and broadcast.
    # mock_publish delivers broadcast locally so WS clients receive messages in tests.
    nickname_store: dict[str, bytes] = {}

    async def cm_set(key, value):
        nickname_store[key] = value.encode() if isinstance(value, str) else value

    async def cm_get(key):
        return nickname_store.get(key)

    async def cm_publish(channel, payload):
        from app.connection_manager import manager
        data = json.loads(payload)
        await manager.local_broadcast(data["game_id"], data["message"])

    with patch("app.services.game_service._redis") as mock_redis, \
         patch("app.routers.ws.asyncio.create_task") as mock_task, \
         patch("app.events.publisher._client"), \
         patch("app.connection_manager._redis") as mock_cm_redis, \
         patch("app.database.wait_for_db"), \
         patch("app.events.publisher.wait_for_redis"):
        mock_redis.delete.return_value = 0
        mock_redis.set.return_value = True
        mock_redis.get.return_value = None
        mock_task.side_effect = lambda coro: coro.close()

        mock_cm_redis.set = AsyncMock(side_effect=cm_set)
        mock_cm_redis.get = AsyncMock(side_effect=cm_get)
        mock_cm_redis.publish = AsyncMock(side_effect=cm_publish)

        yield mock_redis


# --- auth / routing ---

def test_ws_invalid_token_closes_connection():
    http_create_game()
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/games/1?token={INVALID_TOKEN}") as _:
            pass
    assert exc_info.value.code == 4001


def test_ws_unknown_game_closes_connection():
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/games/999?token={TOKEN1}") as _:
            pass
    assert exc_info.value.code == 4004


# --- game activation ---

def test_ws_activating_player_receives_game_start():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN2}") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "game_start"
    assert msg["game"]["status"] == "active"


def test_ws_game_start_includes_nicknames():
    # Alice connects while game is waiting (seeds her nickname), then bob connects after
    # activation — game_start broadcast includes both nicknames.
    http_create_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as _:
        http_activate_game()

        with client.websocket_connect(f"/ws/games/1?token={TOKEN2}") as ws_bob:
            msg = ws_bob.receive_json()

    assert msg["type"] == "game_start"
    assert msg["white_nickname"] == "alice"
    assert msg["black_nickname"] == "bob"


# --- spectator ---

def test_ws_spectator_can_connect_and_receive_legal_moves():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN_SPECTATOR}") as ws:
        ws.receive_json()  # game_state on connect
        ws.send_json({"type": "legal_moves", "square": "e2"})
        msg = ws.receive_json()
        assert msg["type"] == "legal_moves"
        assert "e2e4" in msg["moves"]


# --- moves ---

def test_ws_move_sender_receives_game_state():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        ws.receive_json()  # game_start on connect
        ws.send_json({"type": "move", "move": "e2e4"})
        msg = ws.receive_json()
        assert msg["type"] == "game_state"
        assert msg["game"]["current_turn"] == "black"


# --- legal moves and errors ---

def test_ws_legal_moves_sent_only_to_requester():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        ws.receive_json()  # game_start on connect
        ws.send_json({"type": "legal_moves", "square": "e2"})
        msg = ws.receive_json()
        assert msg["type"] == "legal_moves"
        assert "e2e4" in msg["moves"]
        assert "e2e3" in msg["moves"]


def test_ws_wrong_turn_sends_error_only_to_sender():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN2}") as ws:
        ws.receive_json()  # game_start on connect
        ws.send_json({"type": "move", "move": "e7e5"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "turn" in msg["detail"].lower()


# --- resign ---

def test_ws_resign_broadcasts_game_over():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        ws.receive_json()  # game_start on connect
        ws.send_json({"type": "resign"})
        msg = ws.receive_json()

    assert msg["type"] == "game_over"
    assert msg["game"]["winner"] == "black"
    assert msg["game"]["status"] == "finished"


# --- reconnect ---

def test_ws_reconnect_sends_game_state_to_reconnecting_player(mock_game_service_redis):
    mock_game_service_redis.delete.return_value = 1  # white had an active disconnect key

    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "game_state"
    assert msg["game"]["status"] == "active"


def test_ws_reconnect_game_state_includes_nicknames(mock_game_service_redis):
    http_create_game()
    http_activate_game()

    # Bob connects first, seeds his nickname via normal WS flow
    with client.websocket_connect(f"/ws/games/1?token={TOKEN2}") as ws:
        ws.receive_json()  # consume game_start

    # Alice reconnects — set_nickname("alice") runs before get_nickname, so both are available
    mock_game_service_redis.delete.return_value = 1
    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        msg = ws.receive_json()  # game_state (personal, sent before broadcast)

    assert msg["type"] == "game_state"
    assert msg["white_nickname"] == "alice"
    assert msg["black_nickname"] == "bob"


def test_ws_reconnect_broadcasts_player_reconnected(mock_game_service_redis):
    mock_game_service_redis.delete.return_value = 1  # white had an active disconnect key

    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as ws:
        ws.receive_json()  # game_state (personal)
        msg = ws.receive_json()  # player_reconnected (broadcast)

    assert msg["type"] == "player_reconnected"
    assert msg["color"] == "white"


# --- spectator state ---

def test_ws_spectator_receives_game_state_on_connect():
    http_create_game()
    http_activate_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN_SPECTATOR}") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "game_state"
    assert msg["game"]["status"] == "active"


def test_ws_spectator_game_state_includes_nicknames():
    # Alice connects while waiting (seeds nickname), then game activates, bob connects,
    # finally spectator connects and receives game_state with both nicknames.
    http_create_game()

    with client.websocket_connect(f"/ws/games/1?token={TOKEN1}") as _:
        http_activate_game()

        with client.websocket_connect(f"/ws/games/1?token={TOKEN2}") as ws_bob:
            ws_bob.receive_json()  # consume game_start (seeds bob's nickname)

            with client.websocket_connect(f"/ws/games/1?token={TOKEN_SPECTATOR}") as ws_spec:
                msg = ws_spec.receive_json()

    assert msg["type"] == "game_state"
    assert msg["white_nickname"] == "alice"
    assert msg["black_nickname"] == "bob"


# --- _disconnect_timeout ---

def test_disconnect_timeout_broadcasts_game_over_when_timer_fires():
    from app.routers import ws as ws_module

    mock_game = MagicMock()

    async def _run():
        with patch("app.routers.ws.asyncio.sleep", new_callable=AsyncMock), \
             patch("app.routers.ws.game_service.timeout_disconnect", return_value=mock_game), \
             patch("app.routers.ws.SessionLocal"), \
             patch("app.routers.ws.manager.broadcast", new_callable=AsyncMock) as mock_broadcast, \
             patch("app.routers.ws._serialize_game", return_value={"id": 1}):
            await ws_module._disconnect_timeout(1, "white", 12345)
            mock_broadcast.assert_called_once_with(1, {"type": "game_over", "game": {"id": 1}})

    asyncio.run(_run())


def test_disconnect_timeout_skips_broadcast_when_player_reconnected():
    from app.routers import ws as ws_module

    async def _run():
        with patch("app.routers.ws.asyncio.sleep", new_callable=AsyncMock), \
             patch("app.routers.ws.game_service.timeout_disconnect", return_value=None), \
             patch("app.routers.ws.SessionLocal"), \
             patch("app.routers.ws.manager.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await ws_module._disconnect_timeout(1, "white", 12345)
            mock_broadcast.assert_not_called()

    asyncio.run(_run())


# --- Redis broadcast ---

def test_broadcast_publishes_to_redis():
    from app.connection_manager import ConnectionManager

    async def _run():
        with patch("app.connection_manager._redis") as mock_redis:
            mock_redis.publish = AsyncMock()
            cm = ConnectionManager()
            await cm.broadcast(42, {"type": "game_state"})

            mock_redis.publish.assert_called_once()
            channel, payload = mock_redis.publish.call_args[0]
            assert channel == "ws_broadcast"
            data = json.loads(payload)
            assert data["game_id"] == 42
            assert data["message"] == {"type": "game_state"}

    asyncio.run(_run())


def test_broadcast_falls_back_to_local_when_redis_down():
    from app.connection_manager import ConnectionManager

    async def _run():
        with patch("app.connection_manager._redis") as mock_redis:
            mock_redis.publish = AsyncMock(side_effect=Exception("Redis down"))
            cm = ConnectionManager()
            mock_ws = AsyncMock()
            cm.connections[42] = [mock_ws]

            await cm.broadcast(42, {"type": "game_state"})

            mock_ws.send_json.assert_called_once_with({"type": "game_state"})

    asyncio.run(_run())


def test_ws_relay_delivers_to_local_connections():
    import threading
    import app.events.ws_relay as ws_relay_module
    from app.connection_manager import manager

    async def _run():
        mock_ws = AsyncMock()
        manager.connections[99] = [mock_ws]
        ws_relay_module._loop = asyncio.get_running_loop()

        hold = threading.Event()

        def mock_listen():
            yield {"type": "subscribe", "data": None}
            yield {"type": "message", "data": json.dumps({"game_id": 99, "message": {"type": "game_over"}})}
            hold.wait()

        mock_pubsub = MagicMock()
        mock_pubsub.listen = mock_listen

        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub

        with patch("app.events.ws_relay.redis") as mock_redis:
            mock_redis.from_url.return_value = mock_client
            thread = threading.Thread(target=ws_relay_module._relay_thread, daemon=True)
            thread.start()
            await asyncio.sleep(0.1)

        manager.connections.pop(99, None)
        mock_ws.send_json.assert_called_once_with({"type": "game_over"})
        hold.set()

    asyncio.run(_run())
