# CLAUDE.md — chess-game-service

This file guides Claude Code when working in this repository.

## Collaboration Style

The user is learning backend development. Apply these principles in every session:

- When introducing a new concept, pattern, or tool — briefly flag it so it registers ("здесь мы используем X потому что..."). Don't over-explain, one sentence is enough.
- Proactively offer to go deeper on anything non-obvious ("хочешь объясню почему именно так?").
- Before applying any change, explain what it does and where it takes effect — let the user decide.
- Don't make decisions silently. State what you're about to do and why, even for small things.
- The user will ask to go deeper when they want — don't over-explain by default.

## What This Service Is

`chess-game-service` is the gameplay microservice for a real-time chess web application built with a microservice architecture.

**This service is responsible for:**
- Receiving and validating chess moves
- Tracking board state in FEN notation (using the `chess` Python library)
- Managing turn order between players
- Detecting game-over conditions: checkmate, stalemate, resignation
- Publishing `game_over` and `game_abandoned` events to Redis so room-service can update room status
- Active game disconnect handling with 30-second reconnect timers

**This service is NOT responsible for:**
- Creating or closing rooms
- Matchmaking or room lifecycle
- Authenticating users (tokens are validated locally via shared JWT secret)
- Storing spectators in the database

Those responsibilities belong to `chess-room-service`.

### Service Ecosystem

| Service | Status | Role |
|---|---|---|
| `chess-auth-service` | Implemented | Issues JWT tokens, manages users |
| `chess-room-service` | Implemented | Room lifecycle and matchmaking |
| `chess-game-service` | This repo | WebSocket gameplay, move validation, game results |
| `presence-service` | Optional future split | Online user tracking (V1: may live inside game-service) |

The services are deployed as separate Docker Compose projects today and will later be deployed to Kubernetes.

---

## Architecture

This service follows a strict 4-layer pattern. Never skip or bypass layers.

```
routers → services → repositories → models
```

### Layer Responsibilities

**`app/routers/`** — HTTP/WebSocket layer only
- Parse path params and inject dependencies
- Call service functions
- Convert `ValueError` from services into `HTTPException`
- No business logic, no direct DB access

**`app/services/`** — Business logic
- Validate chess moves using the `chess` library
- Enforce turn order rules
- Detect game-over conditions and determine the winner
- Raise `ValueError` with a message when a rule is violated

**`app/repositories/`** — Database queries only
- Translate service intent into SQLAlchemy queries
- No business rules, no HTTP concerns

**`app/models.py`** — SQLAlchemy ORM models
- `Game` model maps to the `games` table

**`app/schemas.py`** — Pydantic schemas for request/response serialization

**`app/events/`** — Redis pub/sub
- `publisher.py` — publishes `game_over` and `game_abandoned` to the `game_events` channel
- `subscriber.py` — subscribes to `room_events`; handles `room_created` by creating a new game with `white_player_id` only

---

## Database Model

Single table: `games`

| Field | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `room_id` | Integer | Plain int — no FK to room-service |
| `status` | String(20) | `waiting`, `active`, `finished` |
| `white_player_id` | Integer | Plain int — no FK to auth-service |
| `black_player_id` | Integer nullable | Plain int — no FK to auth-service |
| `current_turn` | String(5) nullable | `white` or `black` |
| `board_state` | Text | FEN string representing board position |
| `winner` | String(5) nullable | `white`, `black`, or `draw` |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | UTC, updated on every change |

`room_id`, `white_player_id`, and `black_player_id` are plain integers. Cross-service foreign keys are intentionally avoided.

Initial FEN: `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1`

---

## Game Status Lifecycle

```
waiting → active → finished
```

| Status | Meaning |
|---|---|
| `waiting` | Game created, waiting for second player to connect |
| `active` | Both players connected, moves are being played |
| `finished` | Game ended — checkmate, stalemate, resignation, or disconnect timeout |

---

## Key Conventions

### Error Flow

Services raise `ValueError` with a plain message. Routers catch it and raise `HTTPException`.

```python
# service
raise ValueError("Not your turn")

# router
except ValueError as error:
    raise HTTPException(status_code=400, detail=str(error))
```

### Auth Pattern

All protected endpoints use `get_current_user`. Admin-only endpoints use `require_admin`.

JWT tokens are validated **locally** using the shared `JWT_SECRET_KEY`. Game-service never calls auth-service over HTTP to validate a token.

Token flow:
1. Frontend logs in through auth-service and receives an access token
2. Frontend sends `Authorization: Bearer <token>` to game-service
3. Game-service decodes the token locally and extracts `sub` (user id) and `role`

**Never trust `user_id` or `role` from request body or query params.** Always read them from the decoded JWT via `get_current_user`.

### Move Validation

Move validation uses the `chess` Python library. Board state is stored as a FEN string in the `board_state` column. On each move:

1. Load the FEN into a `chess.Board` object
2. Parse the move with `chess.Move.from_uci()`
3. Check the move is legal via `board.is_legal(move)`
4. Push the move and get the new FEN via `board.fen()`
5. Check for game-over conditions: `board.is_checkmate()`, `board.is_stalemate()`, etc.

### Redis Events

Two channels are used:

**`game_events`** — published by game-service, consumed by room-service:

```json
{ "event": "game_over",     "game_id": 1, "room_id": 42, "winner": "white" }
{ "event": "game_abandoned", "game_id": 1, "room_id": 42 }
```

`game_over` fires on checkmate, stalemate, resignation, or disconnect timeout. `game_abandoned` fires when the only player disconnects while the game is still in `waiting` status.

**`room_events`** — published by room-service, consumed by game-service:

```json
{ "event": "room_created", "room_id": 42, "white_player_id": 7 }
```

Game-service creates a new game with `white_player_id` only. The second player is assigned as black automatically when they connect via WebSocket (`join_game`).

### Cross-Service Boundary

Game-service does not manage rooms. When room-service opens a new room, it publishes `room_created` to Redis — game-service creates the game in response. Room-service never calls game-service over HTTP.

---

## Commands

### Run locally (dev)

Requires a running MySQL and Redis instance and a valid `.env` file.

```bash
uvicorn app.main:app --reload
```

### Run with Docker Compose

```bash
docker compose up --build
```

Service is available at `http://localhost:8002`. The MySQL container is internal and does not expose port 3306 to the host.

### Apply Alembic migrations

When using Docker Compose, run migrations inside the service container to use Docker's internal network:

```bash
docker compose exec game-service alembic upgrade head
```

The app does **not** run migrations on startup. Migrations are a manual step during development and should be a separate job in future CI/CD and Kubernetes deployments.

### Run tests

```bash
pytest tests/
```

---

## Environment Setup

Copy `.env.example` to `.env` and fill in the values before running.

```bash
cp .env.example .env
```

### Key variables

| Variable | Notes |
|---|---|
| `DATABASE_URL` | Must use `game-db` as hostname when running via Docker Compose |
| `JWT_SECRET_KEY` | Must match the value used in `chess-auth-service` and `chess-room-service` |
| `JWT_ALGORITHM` | Must match — default `HS256` |
| `REDIS_URL` | Required — used by publisher and subscriber |
| `MYSQL_*` | Used by the Docker Compose MySQL container |

`JWT_SECRET_KEY` and `JWT_ALGORITHM` are shared across all services. If they differ, token validation will fail with 401.

---

## HTTP API

| Method | Path | Description |
|---|---|---|
| `GET` | `/games/{game_id}` | Get game state |
| `POST` | `/games/{game_id}/join` | Join a waiting game (assigns black if slot is empty) |
| `POST` | `/games/{game_id}/move` | Make a move (UCI format, e.g. `e2e4`) |
| `GET` | `/games/{game_id}/legal-moves?square=e2` | Get legal moves for a square |
| `POST` | `/games/{game_id}/resign` | Resign the game |
| `POST` | `/games/{game_id}/disconnect` | Notify server of disconnect (starts 30s timer) |
| `POST` | `/games/{game_id}/reconnect` | Cancel disconnect timer |
| `WS` | `/ws/games/{game_id}?token=<jwt>` | Real-time gameplay channel |

Games are created exclusively via the `room_created` Redis event — there is no `POST /games` endpoint.

## WebSocket Message Types

**Client → Server:**
- `{"type": "move", "move": "e2e4"}` — make a move
- `{"type": "legal_moves", "square": "e2"}` — request legal moves
- `{"type": "resign"}` — resign the game

**Server → Client:**
- `{"type": "game_start", "game": {...}}` — broadcast when second player connects
- `{"type": "game_state", "game": {...}}` — broadcast after each move
- `{"type": "game_over", "game": {...}}` — broadcast when game ends
- `{"type": "legal_moves", "moves": [...]}` — sent only to requester
- `{"type": "player_disconnected", "color": "white", "reconnect_seconds": 30}` — broadcast on disconnect
- `{"type": "player_reconnected", "color": "white"}` — broadcast on reconnect
- `{"type": "game_abandoned"}` — broadcast when waiting game is abandoned
- `{"type": "error", "detail": "..."}` — sent only to requester on validation error

---

## What To Avoid

**Layer violations**
- Do not put SQL queries in routers
- Do not put business logic in repositories
- Do not call the database from anywhere except the repository layer
- Do not validate chess moves outside of the service layer

**Auth**
- Do not trust `user_id` or `role` from request body or query params
- Do not call auth-service over HTTP to validate tokens — validate locally with the shared secret

**Cross-service boundaries**
- Do not add Foreign Keys from `games` to users, rooms, or other services
- Do not handle room lifecycle or matchmaking in game-service
- Do not store spectators in the database for V1

**Game logic**
- Do not bypass the `chess` library for move validation — always use it
- Do not modify `board_state` directly in the database without going through move validation

**Infrastructure**
- Do not run `alembic upgrade head` automatically on app startup
- Do not expose the MySQL container port to the host unnecessarily
