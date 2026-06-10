import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.connection_manager import manager
from app.database import SessionLocal, get_db
from app.schemas import GameResponse
from app.services import game_service

router = APIRouter()


async def _disconnect_timeout(game_id: int, color: str, disconnect_ts: int):
    await asyncio.sleep(game_service.DISCONNECT_TTL)

    db = SessionLocal()
    try:
        game = game_service.timeout_disconnect(db, game_id, color, disconnect_ts)
        if game is not None:
            await manager.broadcast(game_id, {
                "type": "game_over",
                "game": _serialize_game(game),
            })
    except Exception:
        pass
    finally:
        db.close()


def _decode_token(token: str) -> tuple[int, str] | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        sub = payload.get("sub")
        username = payload.get("username")
        if not sub or not username:
            return None
        return int(sub), username
    except (JWTError, ValueError):
        return None


def _serialize_game(game) -> dict:
    return GameResponse.model_validate(game).model_dump(mode="json")


@router.websocket("/ws/games/{game_id}")
async def game_websocket(
    websocket: WebSocket,
    game_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    token_data = _decode_token(token)
    if token_data is None:
        await websocket.close(code=4001)
        return
    user_id, username = token_data

    try:
        game = game_service.get_game(db, game_id)
    except ValueError:
        await websocket.close(code=4004)
        return

    is_player = user_id in (game.white_player_id, game.black_player_id)
    await manager.connect(game_id, websocket, user_id if is_player else None)
    if is_player:
        manager.set_nickname(game_id, user_id, username)

    if is_player and game.status == "active":
        was_disconnected = game_service.handle_reconnect(db, game_id, user_id)
        if was_disconnected:
            color = "white" if game.white_player_id == user_id else "black"
            last_move = game_service.get_last_move(game_id)
            await manager.send_personal(websocket, {
                "type": "game_state",
                "game": _serialize_game(game),
                "white_nickname": manager.get_nickname(game_id, game.white_player_id),
                "black_nickname": manager.get_nickname(game_id, game.black_player_id),
                **({"last_move": last_move} if last_move else {}),
            })
            await manager.broadcast(game_id, {
                "type": "player_reconnected",
                "color": color,
            })
        else:
            await manager.broadcast(game_id, {
                "type": "game_start",
                "game": _serialize_game(game),
                "white_nickname": manager.get_nickname(game_id, game.white_player_id),
                "black_nickname": manager.get_nickname(game_id, game.black_player_id),
            })

    if not is_player and game.status == "active":
        last_move = game_service.get_last_move(game_id)
        await manager.send_personal(websocket, {
            "type": "game_state",
            "game": _serialize_game(game),
            "white_nickname": manager.get_nickname(game_id, game.white_player_id),
            "black_nickname": manager.get_nickname(game_id, game.black_player_id),
            **({"last_move": last_move} if last_move else {}),
        })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            db.rollback()  # close any open read-only txn so next query sees latest committed data

            if msg_type == "move":
                try:
                    move = data["move"]
                    game = game_service.make_move(db, game_id, user_id, move)
                    game_service.set_last_move(game_id, move)
                    await manager.broadcast(game_id, {
                        "type": "game_over" if game.status == "finished" else "game_state",
                        "game": _serialize_game(game),
                        "last_move": move,
                    })
                except ValueError as e:
                    await manager.send_personal(websocket, {"type": "error", "detail": str(e)})

            elif msg_type == "legal_moves":
                try:
                    moves = game_service.get_legal_moves(db, game_id, data["square"])
                    await manager.send_personal(websocket, {"type": "legal_moves", "moves": moves})
                except ValueError as e:
                    await manager.send_personal(websocket, {"type": "error", "detail": str(e)})

            elif msg_type == "resign":
                try:
                    game = game_service.resign_game(db, game_id, user_id)
                    await manager.broadcast(game_id, {
                        "type": "game_over",
                        "game": _serialize_game(game),
                    })
                except ValueError as e:
                    await manager.send_personal(websocket, {"type": "error", "detail": str(e)})

    except WebSocketDisconnect:
        manager.disconnect(game_id, websocket, user_id if is_player else None)

        if is_player:
            try:
                current_game = game_service.get_game(db, game_id)

                if current_game.status == "active":
                    color = "white" if current_game.white_player_id == user_id else "black"
                    disconnect_ts = game_service.handle_disconnect(db, game_id, user_id)
                    await manager.broadcast(game_id, {
                        "type": "player_disconnected",
                        "color": color,
                        "timeout_seconds": game_service.DISCONNECT_TTL,
                    })
                    if disconnect_ts is not None:
                        asyncio.create_task(_disconnect_timeout(game_id, color, disconnect_ts))
                elif current_game.status == "waiting":
                    game_service.handle_disconnect(db, game_id, user_id)
                    await manager.broadcast(game_id, {"type": "game_abandoned"})

            except ValueError:
                pass
