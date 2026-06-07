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


async def _disconnect_timeout(game_id: int, color: str):
    await asyncio.sleep(game_service.DISCONNECT_TTL)

    db = SessionLocal()
    try:
        game = game_service.timeout_disconnect(db, game_id, color)
        if game is not None:
            await manager.broadcast(game_id, {
                "type": "game_over",
                "game": _serialize_game(game),
            })
    except Exception:
        pass
    finally:
        db.close()


def _decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        sub = payload.get("sub")
        return int(sub) if sub else None
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
    user_id = _decode_token(token)
    if user_id is None:
        await websocket.close(code=4001)
        return

    try:
        game = game_service.get_game(db, game_id)
    except ValueError:
        await websocket.close(code=4004)
        return

    is_player = (
        user_id in (game.white_player_id, game.black_player_id)
        or (game.black_player_id is None and user_id != game.white_player_id and game.status == "waiting")
    )
    await manager.connect(game_id, websocket, user_id if is_player else None)

    just_activated = False

    if is_player and game.status == "waiting":
        if manager.connected_player_count(game_id) == 2:
            try:
                game = game_service.join_game(db, game_id, user_id)
                just_activated = True
                await manager.broadcast(game_id, {
                    "type": "game_start",
                    "game": _serialize_game(game),
                })
            except ValueError as e:
                await manager.send_personal(websocket, {"type": "error", "detail": str(e)})

    if is_player and game.status == "active" and not just_activated:
        was_disconnected = game_service.handle_reconnect(db, game_id, user_id)
        if was_disconnected:
            color = "white" if game.white_player_id == user_id else "black"
            await manager.broadcast(game_id, {
                "type": "player_reconnected",
                "color": color,
            })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "move":
                try:
                    game = game_service.make_move(db, game_id, user_id, data["move"])
                    await manager.broadcast(game_id, {
                        "type": "game_over" if game.status == "finished" else "game_state",
                        "game": _serialize_game(game),
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
                    game_service.handle_disconnect(db, game_id, user_id)
                    await manager.broadcast(game_id, {
                        "type": "player_disconnected",
                        "color": color,
                        "reconnect_seconds": 30,
                    })
                    asyncio.create_task(_disconnect_timeout(game_id, color))
                elif current_game.status == "waiting":
                    game_service.handle_disconnect(db, game_id, user_id)
                    await manager.broadcast(game_id, {"type": "game_abandoned"})

            except ValueError:
                pass
