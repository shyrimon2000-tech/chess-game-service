import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import ANY, patch

from app.main import app
from app.database import get_db
from app.models import Base, INITIAL_FEN
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


def as_user(user_id: int, role: str = "user"):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user_id, role=role)


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides = {get_db: override_get_db}


# --- Helpers ---

def create_game(room_id=1, white_player_id=1, black_player_id=None):
    db = TestingSessionLocal()
    try:
        return game_service.create_game(db, room_id, white_player_id, black_player_id)
    finally:
        db.close()


def join_game(game_id: int, user_id: int):
    as_user(user_id)
    return client.post(f"/games/{game_id}/join")


def setup_active_game(room_id=1, white_id=1, black_id=2):
    create_game(room_id=room_id, white_player_id=white_id, black_player_id=black_id)
    join_game(game_id=room_id, user_id=black_id)


def make_move(game_id: int, user_id: int, move: str):
    as_user(user_id)
    return client.post(f"/games/{game_id}/move", json={"move": move})


# --- create_game ---

def test_create_game_returns_correct_fields():
    game = create_game(room_id=1, white_player_id=1)
    assert game.room_id == 1
    assert game.white_player_id == 1
    assert game.status == "waiting"
    assert game.board_state == INITIAL_FEN
    assert game.black_player_id is None
    assert game.current_turn == "white"


# --- join_game ---

def test_join_game_activates_game():
    create_game(room_id=1, white_player_id=1, black_player_id=2)
    response = join_game(game_id=1, user_id=2)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert data["current_turn"] == "white"


def test_join_game_assigns_black_when_slot_empty():
    create_game(room_id=1, white_player_id=1)
    response = join_game(game_id=1, user_id=2)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert data["black_player_id"] == 2


def test_join_game_non_player_rejected():
    create_game(room_id=1, white_player_id=1, black_player_id=2)
    response = join_game(game_id=1, user_id=3)
    assert response.status_code == 400


def test_join_already_active_game_rejected():
    create_game(room_id=1, white_player_id=1, black_player_id=2)
    join_game(game_id=1, user_id=2)
    response = join_game(game_id=1, user_id=2)
    assert response.status_code == 400


# --- make_move ---

def test_make_move_switches_turn():
    setup_active_game()
    response = make_move(game_id=1, user_id=1, move="e2e4")
    assert response.status_code == 200
    assert response.json()["current_turn"] == "black"


def test_make_move_wrong_turn_rejected():
    setup_active_game()
    response = make_move(game_id=1, user_id=2, move="e7e5")
    assert response.status_code == 400
    assert "turn" in response.json()["detail"].lower()


def test_make_move_illegal_move_rejected():
    setup_active_game()
    response = make_move(game_id=1, user_id=1, move="e2e5")
    assert response.status_code == 400


def test_make_move_on_waiting_game_rejected():
    create_game(room_id=1, white_player_id=1, black_player_id=2)
    response = make_move(game_id=1, user_id=1, move="e2e4")
    assert response.status_code == 400


@patch("app.events.publisher._client")
def test_checkmate_finishes_game(mock_client):
    setup_active_game()

    # Fool's mate: 1.f3 e5 2.g4 Qh4#
    make_move(1, 1, "f2f3")
    make_move(1, 2, "e7e5")
    make_move(1, 1, "g2g4")
    response = make_move(1, 2, "d8h4")

    data = response.json()
    assert data["status"] == "finished"
    assert data["winner"] == "black"
    mock_client.publish.assert_called_once()


# --- get_legal_moves ---

def test_legal_moves_returns_pawn_moves():
    setup_active_game()
    as_user(1)
    response = client.get("/games/1/legal-moves?square=e2")
    assert response.status_code == 200
    moves = response.json()["moves"]
    assert "e2e4" in moves
    assert "e2e3" in moves


def test_legal_moves_empty_square_returns_empty():
    setup_active_game()
    as_user(1)
    response = client.get("/games/1/legal-moves?square=e4")
    assert response.status_code == 200
    assert response.json()["moves"] == []


# --- resign ---

@patch("app.events.publisher._client")
def test_resign_game_finishes_game(mock_client):
    setup_active_game()

    as_user(1)
    response = client.post("/games/1/resign")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "finished"
    assert data["winner"] == "black"
    mock_client.publish.assert_called_once()


@patch("app.events.publisher._client")
def test_resign_game_black_wins_if_white_resigns(mock_client):
    setup_active_game()
    as_user(2)
    data = client.post("/games/1/resign").json()
    assert data["winner"] == "white"


def test_resign_game_non_player_rejected():
    setup_active_game()
    as_user(3)
    assert client.post("/games/1/resign").status_code == 400


def test_resign_game_not_active_rejected():
    create_game(room_id=1, white_player_id=1, black_player_id=2)
    as_user(1)
    assert client.post("/games/1/resign").status_code == 400


# --- disconnect / reconnect ---

@patch("app.events.publisher._client")
def test_disconnect_waiting_game_publishes_abandoned(mock_client):
    create_game(room_id=1, white_player_id=1)
    db = TestingSessionLocal()
    try:
        game_service.handle_disconnect(db, 1, 1)
    finally:
        db.close()

    payload = mock_client.publish.call_args[0][1]
    assert "game_abandoned" in payload

    as_user(1)
    assert client.get("/games/1").status_code == 404


@patch("app.services.game_service._redis")
def test_disconnect_active_game_sets_redis_key(mock_redis):
    setup_active_game()
    db = TestingSessionLocal()
    try:
        game_service.handle_disconnect(db, 1, 1)
    finally:
        db.close()

    mock_redis.set.assert_called_once_with("game:disconnect:1:white", ANY, ex=30)


@patch("app.services.game_service._redis")
def test_reconnect_deletes_redis_key(mock_redis):
    mock_redis.delete.return_value = 1

    setup_active_game()
    db = TestingSessionLocal()
    try:
        game_service.handle_reconnect(db, 1, 1)
    finally:
        db.close()

    mock_redis.delete.assert_called_once_with("game:disconnect:1:white")


@patch("app.events.publisher._client")
@patch("app.services.game_service._redis")
def test_timeout_disconnect_returns_none_if_player_reconnected(mock_redis, mock_publisher):
    mock_redis.get.return_value = None  # key deleted — player reconnected

    setup_active_game()
    db = TestingSessionLocal()
    try:
        result = game_service.timeout_disconnect(db, 1, "white", expected_ts=123)
    finally:
        db.close()

    assert result is None
    mock_redis.delete.assert_not_called()


@patch("app.events.publisher._client")
@patch("app.services.game_service._redis")
def test_timeout_disconnect_finishes_game_if_key_exists(mock_redis, mock_publisher):
    mock_redis.get.return_value = b"12345"  # key present, timestamp matches

    setup_active_game()
    db = TestingSessionLocal()
    try:
        result = game_service.timeout_disconnect(db, 1, "white", expected_ts=12345)
    finally:
        db.close()

    assert result is not None
    assert result.status == "finished"
    assert result.winner == "black"
    mock_redis.delete.assert_called_once()
