import chess
import redis as redis_lib
import time
from sqlalchemy.orm import Session

from app.config import settings
from app.events.publisher import publish_game_abandoned, publish_game_over
from app.repositories import game_repo

DISCONNECT_TTL = 30

_redis = redis_lib.from_url(settings.REDIS_URL)


def get_game(db: Session, game_id: int):
    game = game_repo.get_game_by_id(db, game_id)
    if game is None:
        raise ValueError("Game not found")
    return game


def create_game(
    db: Session,
    room_id: int,
    white_player_id: int,
    black_player_id: int | None = None,
):
    return game_repo.create_game(db, room_id, white_player_id, black_player_id)


def activate_game(db: Session, room_id: int, black_player_id: int):
    game = game_repo.get_game_by_room_id(db, room_id)
    if game is None:
        raise ValueError(f"Game not found for room {room_id}")
    game.black_player_id = black_player_id
    game.status = "active"
    game.current_turn = "white"
    return game_repo.save_game(db, game)


def join_game(db: Session, game_id: int, user_id: int):
    game = game_repo.get_game_by_id(db, game_id)
    if game is None:
        raise ValueError("Game not found")
    if game.status != "waiting":
        raise ValueError("Game is not waiting for a player")

    if game.black_player_id is None and user_id != game.white_player_id:
        game.black_player_id = user_id
    elif user_id not in (game.white_player_id, game.black_player_id):
        raise ValueError("You are not a player in this game")

    game.status = "active"
    game.current_turn = "white"
    return game_repo.save_game(db, game)


def make_move(db: Session, game_id: int, user_id: int, move_uci: str):
    game = game_repo.get_game_by_id(db, game_id)
    if game is None:
        raise ValueError("Game not found")
    if game.status != "active":
        raise ValueError("Game is not active")

    if game.current_turn == "white" and game.white_player_id != user_id:
        raise ValueError("Not your turn")
    if game.current_turn == "black" and game.black_player_id != user_id:
        raise ValueError("Not your turn")

    board = chess.Board(game.board_state)

    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        raise ValueError("Invalid move format")

    if not board.is_legal(move):
        raise ValueError("Illegal move")

    board.push(move)
    game.board_state = board.fen()

    if board.is_checkmate():
        game.status = "finished"
        game.winner = game.current_turn
        game_repo.save_game(db, game)
        publish_game_over(game.id, game.room_id, game.winner)
        return game

    if (
        board.is_stalemate()
        or board.is_insufficient_material()
        or board.is_seventyfive_moves()
        or board.is_fivefold_repetition()
    ):
        game.status = "finished"
        game.winner = "draw"
        game_repo.save_game(db, game)
        publish_game_over(game.id, game.room_id, game.winner)
        return game

    game.current_turn = "black" if game.current_turn == "white" else "white"
    return game_repo.save_game(db, game)


def get_legal_moves(db: Session, game_id: int, square: str) -> list[str]:
    game = game_repo.get_game_by_id(db, game_id)
    if game is None:
        raise ValueError("Game not found")
    if game.status != "active":
        raise ValueError("Game is not active")

    board = chess.Board(game.board_state)

    try:
        sq = chess.parse_square(square)
    except ValueError:
        raise ValueError("Invalid square")

    return [move.uci() for move in board.legal_moves if move.from_square == sq]


def resign_game(db: Session, game_id: int, user_id: int):
    game = game_repo.get_game_by_id(db, game_id)
    if game is None:
        raise ValueError("Game not found")
    if game.status != "active":
        raise ValueError("Game is not active")
    if user_id not in (game.white_player_id, game.black_player_id):
        raise ValueError("You are not a player in this game")

    game.winner = "black" if game.white_player_id == user_id else "white"
    game.status = "finished"
    game_repo.save_game(db, game)
    publish_game_over(game.id, game.room_id, game.winner)
    return game


def handle_disconnect(db: Session, game_id: int, user_id: int) -> int | None:
    """Returns disconnect timestamp (used to detect stale timeout tasks), or None for waiting games."""
    game = game_repo.get_game_by_id(db, game_id)
    if game is None:
        raise ValueError("Game not found")

    if game.status == "waiting":
        game.status = "finished"
        game_repo.save_game(db, game)
        publish_game_abandoned(game.id, game.room_id)
        return None

    if game.status != "active":
        return None

    if game.white_player_id == user_id:
        color = "white"
    elif game.black_player_id == user_id:
        color = "black"
    else:
        raise ValueError("User is not a player in this game")

    disconnect_ts = int(time.time())
    key = f"game:disconnect:{game_id}:{color}"
    _redis.set(key, str(disconnect_ts), ex=DISCONNECT_TTL)
    return disconnect_ts


def handle_reconnect(db: Session, game_id: int, user_id: int) -> bool:
    game = game_repo.get_game_by_id(db, game_id)
    if game is None:
        raise ValueError("Game not found")

    if game.white_player_id == user_id:
        color = "white"
    elif game.black_player_id == user_id:
        color = "black"
    else:
        raise ValueError("User is not a player in this game")

    key = f"game:disconnect:{game_id}:{color}"
    deleted = _redis.delete(key)
    return bool(deleted)


def timeout_disconnect(db: Session, game_id: int, color: str, expected_ts: int):
    """Called after disconnect TTL expires. Returns finished game or None if reconnected/re-disconnected."""
    key = f"game:disconnect:{game_id}:{color}"

    stored = _redis.get(key)
    if stored is None:
        return None

    # Stale task: player reconnected then disconnected again — stored ts is newer
    if int(stored) != expected_ts:
        return None

    _redis.delete(key)

    game = game_repo.get_game_by_id(db, game_id)
    if game is None or game.status != "active":
        return None

    winner = "black" if color == "white" else "white"
    game.status = "finished"
    game.winner = winner
    game_repo.save_game(db, game)
    publish_game_over(game.id, game.room_id, winner)
    return game
