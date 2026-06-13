# Chess Game Service

A gameplay microservice for a real-time chess web application built with a microservice architecture.

This service handles WebSocket-based gameplay, chess move validation, board state management, turn enforcement, game-over detection, player disconnect handling with reconnect timers, resignation, and publishing game result events to Redis so room-service can update room status.

---

## Badges

Main: [![CI Main](https://github.com/shyrimon2000-tech/chess-game-service/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/shyrimon2000-tech/chess-game-service/actions)

Dev: [![CI Dev](https://github.com/shyrimon2000-tech/chess-game-service/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/shyrimon2000-tech/chess-game-service/actions)

---

## Features

- Real-time WebSocket gameplay channel per game
- Chess move validation using the `chess` Python library (UCI format)
- Board state tracked as FEN string in MySQL
- Turn order enforcement
- Legal move lookup by square
- Game-over detection: checkmate, stalemate, insufficient material, seventy-five moves, fivefold repetition
- Resignation with game result publishing
- Player disconnect handling with 30-second reconnect timer
- Automatic game result on disconnect timeout
- Game abandoned event when waiting player disconnects
- Spectator WebSocket connections (read-only)
- JWT token validation via WebSocket query parameter
- Redis pub/sub: subscribes to `room_created` and `room_activated`; publishes `game_created`, `game_over`, and `game_abandoned`
- Automatic game creation triggered by Redis event from room-service
- Cross-instance WebSocket broadcasting via Redis `ws_broadcast` channel
- MySQL database persistence
- SQLAlchemy ORM
- Alembic database migrations
- Automated tests with pytest

---

## Tech Stack

- Python 3.11
- FastAPI
- Uvicorn
- WebSockets
- SQLAlchemy
- Alembic
- MySQL
- PyMySQL
- Redis
- chess (python-chess)
- python-jose
- Pydantic Settings
- tenacity
- pytest
- Docker
- Docker Compose

---

## Project Structure

```text
app/
├── routers/
│   ├── games.py
│   └── ws.py
├── services/
│   ├── game_service.py
│   └── auth_dependencies.py
├── repositories/
│   └── game_repo.py
├── events/
│   ├── publisher.py
│   ├── subscriber.py
│   └── ws_relay.py
├── config.py
├── connection_manager.py
├── database.py
├── main.py
├── models.py
└── schemas.py

alembic/
├── versions/
└── env.py

tests/
├── test_games.py
├── test_ws.py
└── test_subscriber.py
```

---

## HTTP API

### Health Check

```http
GET /health
```

Response:

```json
{ "status": "ok" }
```

---

### Get Game

```http
GET /games/{game_id}
```

Required header:

```http
Authorization: Bearer <access_token>
```

Response:

```json
{
  "id": 1,
  "room_id": 42,
  "status": "active",
  "white_player_id": 7,
  "black_player_id": 12,
  "current_turn": "white",
  "board_state": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "winner": null,
  "created_at": "2026-06-01T10:00:00",
  "updated_at": "2026-06-01T10:05:00"
}
```

---

### Join Game

```http
POST /games/{game_id}/join
```

Joins a waiting game. If the black player slot is empty, the caller is assigned as black and the game becomes active. If the slot is already taken and the caller is an existing player, the game activates. Otherwise returns 400.

Required header:

```http
Authorization: Bearer <access_token>
```

Response: game object with `status: "active"`.

---

### Make Move

```http
POST /games/{game_id}/move
```

Required header:

```http
Authorization: Bearer <access_token>
```

Request body:

```json
{ "move": "e2e4" }
```

Moves use UCI format: source square + destination square, for example `e2e4`, `g1f3`, `e1g1` (castling).

Response: updated game object. If the move ends the game, the game record is deleted — the response contains the final snapshot with `winner` set.

---

### Get Legal Moves

```http
GET /games/{game_id}/legal-moves?square=e2
```

Required header:

```http
Authorization: Bearer <access_token>
```

Response:

```json
{ "moves": ["e2e3", "e2e4"] }
```

Returns all legal moves for the piece on the given square. Returns an empty list if the square is empty or has no legal moves.

---

### Resign

```http
POST /games/{game_id}/resign
```

Required header:

```http
Authorization: Bearer <access_token>
```

Ends the game immediately. The opposing player wins. Publishes a `game_over` event to Redis.

Response: final game snapshot with `winner` set. The game record is deleted after resignation.

---

## WebSocket

```
WS /ws/games/{game_id}?token=<jwt>
```

The JWT access token is passed as a query parameter because the WebSocket protocol does not support custom headers.

Spectators can connect — they receive the current game state immediately on connect and all subsequent broadcasts, but cannot send moves.

### Client → Server Messages

Make a move:

```json
{ "type": "move", "move": "e2e4" }
```

Request legal moves for a square:

```json
{ "type": "legal_moves", "square": "e2" }
```

Resign:

```json
{ "type": "resign" }
```

### Server → Client Messages

Broadcast to all connections when the second player joins:

```json
{ "type": "game_start", "game": { ... }, "white_nickname": "alex", "black_nickname": "bob" }
```

Broadcast after each move:

```json
{ "type": "game_state", "game": { ... }, "white_nickname": "alex", "black_nickname": "bob" }
```

Broadcast when the game ends:

```json
{ "type": "game_over", "game": { ... } }
```

Sent only to the requester:

```json
{ "type": "legal_moves", "moves": ["e2e3", "e2e4"] }
```

Broadcast when a player disconnects:

```json
{ "type": "player_disconnected", "color": "white", "timeout_seconds": 30 }
```

Broadcast when a disconnected player reconnects within 30 seconds:

```json
{ "type": "player_reconnected", "color": "white" }
```

Broadcast when the waiting player abandons the game:

```json
{ "type": "game_abandoned" }
```

Sent only to the requester on a validation error:

```json
{ "type": "error", "detail": "Not your turn" }
```

---

## Redis Events

### Subscribed: `room_events` channel

```json
{ "event": "room_created",   "room_id": 42, "white_player_id": 7 }
{ "event": "room_activated", "room_id": 42, "white_player_id": 7, "black_player_id": 12 }
```

`room_created` — game-service creates a new game in `waiting` status with `white_player_id` set, then publishes `game_created` back so room-service can store the `game_id`.

`room_activated` — game-service sets `black_player_id`, changes status to `active`, and broadcasts `game_start` to all connected WebSocket clients.

### Published: `game_events` channel

```json
{ "event": "game_created",   "game_id": 1, "room_id": 42 }
{ "event": "game_over",      "game_id": 1, "room_id": 42, "winner": "white" }
{ "event": "game_abandoned", "game_id": 1, "room_id": 42 }
```

`game_created` — published immediately after game creation so room-service can store the `game_id`.

`game_over` — published on checkmate, stalemate, resignation, or 30-second disconnect timeout.

`game_abandoned` — published when the only player disconnects while the game is still in `waiting` status.

### Internal: `ws_broadcast` channel

Used internally for cross-instance WebSocket broadcasting. When `broadcast()` is called, it publishes to this channel. Each service instance runs a `ws_relay` loop that subscribes to the channel and delivers messages to locally connected WebSocket clients.

---

## Game Lifecycle

```text
waiting → active → [deleted]
```

| Status | Meaning |
|---|---|
| `waiting` | Game created by `room_created` event, waiting for second player to connect via WebSocket |
| `active` | Both players connected, moves are being played |

Games are **deleted from the database** when they end — there is no `finished` status. The final game snapshot is broadcast via WebSocket before deletion.

---

## Disconnect and Reconnect

When a player disconnects from an active game:

1. Server broadcasts `player_disconnected` to all connections
2. A 30-second key is set in Redis: `game:disconnect:{game_id}:{color}`
3. If the player reconnects within 30 seconds, the key is deleted, the reconnecting player receives the current `game_state` personally, and `player_reconnected` is broadcast to all
4. If 30 seconds pass without reconnection, the disconnected player loses, `game_over` is broadcast via WebSocket to remaining connections, and `game_over` is published to Redis

---

## Environment Variables

Create a `.env` file based on `.env.example`.

Example:

```env
# MySQL container settings
MYSQL_ROOT_PASSWORD=change-root-password
MYSQL_DATABASE=chess_game_db
MYSQL_USER=chess_user
MYSQL_PASSWORD=change-user-password

# Application database connection
DATABASE_URL=mysql+pymysql://chess_user:change-user-password@game-db:3306/chess_game_db

# JWT settings
JWT_SECRET_KEY=change-this-secret-key
JWT_ALGORITHM=HS256

# Redis settings
REDIS_URL=redis://redis:6379/0
```

Important:

- `JWT_SECRET_KEY` and `JWT_ALGORITHM` must match the values used in `chess-auth-service` and `chess-room-service`. If they differ, token validation will fail with 401.
- `DATABASE_URL` uses `game-db` as the MySQL host when running with Docker Compose.
- `.env` contains real secrets and must not be committed.
- `.env.example` is safe to commit as a template.

---

## Run with Docker Compose

Build and start the service:

```bash
docker compose up --build
```

Run in detached mode:

```bash
docker compose up -d --build
```

The API will be available at:

```text
http://127.0.0.1:8002
```

Swagger UI:

```text
http://127.0.0.1:8002/docs
```

Health check:

```text
http://127.0.0.1:8002/health
```

---

## Database Migrations

The application does not create tables automatically on startup. Schema changes are managed through Alembic migrations.

Apply migrations:

```bash
docker compose exec game-service alembic upgrade head
```

Create a new migration:

```bash
docker compose exec game-service alembic revision --autogenerate -m "migration message"
```

Check current version:

```bash
docker compose exec game-service alembic current
```

Current database tables:

```text
alembic_version
games
```

---

## Run Locally without Docker

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it.

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements-dev.txt
```

Run the service:

```bash
uvicorn app.main:app --reload
```

Notes:

- Requires a running MySQL instance and Redis instance reachable from the local machine.
- `requirements.txt` contains production dependencies only.
- `requirements-dev.txt` includes `requirements.txt` and adds `pytest` for running tests.

---

## Database

### games

| Field | Type | Description |
|---|---|---|
| `id` | Integer PK | Internal game ID |
| `room_id` | Integer, UNIQUE | Room this game belongs to — plain int, no FK to room-service |
| `status` | String(20) | `waiting` or `active` |
| `white_player_id` | Integer | Player assigned to white — plain int, no FK to auth-service |
| `black_player_id` | Integer nullable | Player assigned to black — set on `room_activated` |
| `current_turn` | String(5) nullable | `white` or `black` |
| `board_state` | Text | FEN string representing current board position |
| `winner` | String(5) nullable | `white`, `black`, or `draw` — set right before the row is deleted |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | UTC, updated on every change |

Cross-service foreign keys are intentionally avoided. `room_id`, `white_player_id`, and `black_player_id` are plain integers.

---

## Automated Tests

Run tests:

```bash
pytest tests/ -v
```

Test coverage includes:

- game creation with correct initial state
- joining a waiting game activates it
- auto-assign black player when slot is empty
- non-player join rejected when both slots are taken
- joining an already active game rejected
- move validation and turn switching
- wrong turn rejected
- illegal move rejected
- move on non-active game rejected
- checkmate finishes game and publishes `game_over`
- legal move lookup by square
- empty square returns empty move list
- resignation finishes game and publishes `game_over`
- resignation by black wins for white
- non-player resignation rejected
- resignation on non-active game rejected
- waiting game disconnect publishes `game_abandoned`
- active game disconnect sets Redis key with 30-second TTL
- reconnect deletes Redis key
- WebSocket: invalid token closes connection
- WebSocket: unknown game closes connection
- WebSocket: second player receives `game_start`
- WebSocket: spectator can connect and request legal moves
- WebSocket: move sender receives `game_state`
- WebSocket: legal moves sent only to requester
- WebSocket: wrong turn sends error only to sender
- WebSocket: resign broadcasts `game_over`
- WebSocket: reconnecting player receives current `game_state` before `player_reconnected` broadcast
- WebSocket: reconnect broadcasts `player_reconnected`
- WebSocket: spectator receives `game_state` on connect to active game
- disconnect timeout broadcasts `game_over` via WebSocket when timer fires
- disconnect timeout does nothing if player reconnected before expiry
- `room_created` Redis event creates a new game
- Redis subscriber ignores non-message events
- Redis subscriber handles invalid JSON gracefully
- Redis subscriber ignores unknown events

Current test count:

```text
51 passed
```
