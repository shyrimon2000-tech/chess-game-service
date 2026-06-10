from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.connections: dict[int, list[WebSocket]] = {}
        self.players: dict[int, dict[int, WebSocket]] = {}
        self.nicknames: dict[int, dict[int, str]] = {}

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

    def set_nickname(self, game_id: int, user_id: int, username: str) -> None:
        if game_id not in self.nicknames:
            self.nicknames[game_id] = {}
        self.nicknames[game_id][user_id] = username

    def get_nickname(self, game_id: int, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.nicknames.get(game_id, {}).get(user_id)

    def connected_player_count(self, game_id: int) -> int:
        return len(self.players.get(game_id, {}))

    async def broadcast(self, game_id: int, message: dict):
        for ws in self.connections.get(game_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def send_personal(self, websocket: WebSocket, message: dict):
        await websocket.send_json(message)


manager = ConnectionManager()
