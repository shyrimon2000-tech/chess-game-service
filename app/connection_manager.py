import json
import logging

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger(__name__)

_redis = aioredis.from_url(settings.REDIS_URL)

_WS_BROADCAST_CHANNEL = "ws_broadcast"


class ConnectionManager:
    def __init__(self):
        self.connections: dict[int, list[WebSocket]] = {}
        self.players: dict[int, dict[int, WebSocket]] = {}

    async def connect(self, game_id: int, websocket: WebSocket, user_id: int | None = None):
        await websocket.accept()
        if game_id not in self.connections:
            self.connections[game_id] = []
        self.connections[game_id].append(websocket)
        if user_id is not None:
            if game_id not in self.players:
                self.players[game_id] = {}
            self.players[game_id][user_id] = websocket

    def disconnect(self, game_id: int, websocket: WebSocket, user_id: int | None = None):
        if game_id in self.connections:
            try:
                self.connections[game_id].remove(websocket)
            except ValueError:
                pass
        if user_id is not None and game_id in self.players:
            self.players[game_id].pop(user_id, None)

    async def set_nickname(self, game_id: int, user_id: int, username: str) -> None:
        try:
            await _redis.set(f"game:nickname:{game_id}:{user_id}", username)
        except Exception:
            logger.exception("Redis unavailable, nickname not saved for user %s", user_id)

    async def get_nickname(self, game_id: int, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        try:
            val = await _redis.get(f"game:nickname:{game_id}:{user_id}")
            return val.decode() if val else None
        except Exception:
            logger.exception("Redis unavailable, nickname not available for user %s", user_id)
            return None

    def connected_player_count(self, game_id: int) -> int:
        return len(self.players.get(game_id, {}))

    async def local_broadcast(self, game_id: int, message: dict):
        conns = self.connections.get(game_id, [])
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def broadcast(self, game_id: int, message: dict):
        payload = json.dumps({"game_id": game_id, "message": message})
        try:
            await _redis.publish(_WS_BROADCAST_CHANNEL, payload)
        except Exception:
            logger.exception("Redis unavailable, falling back to local broadcast for game %s", game_id)
            await self.local_broadcast(game_id, message)

    async def send_personal(self, websocket: WebSocket, message: dict):
        await websocket.send_json(message)


manager = ConnectionManager()
