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
- Publishing `game_over` events to Redis so room-service can update room status
- Active game disconnect handling and reconnect timers (planned)

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
- `publisher.py` — publishes `game_over` events to the `game_events` channel
- `subscriber.py` — planned; will subscribe to events from room-service

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
| `finished` | Game ended — checkmate, stalemate, or resignation |

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

When a game ends, `publisher.py` publishes to the `game_events` Redis channel:

```json
{
  "event": "game_over",
  "game_id": 1,
  "room_id": 42,
  "winner": "white"
}
```

Room-service subscribes to this channel and updates the room status to `finished`.

### Cross-Service Boundary

Game-service does not manage rooms. It receives a `room_id` when a game is created (room-service calls game-service after both players join) and uses it only for event publishing.

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
| `REDIS_URL` | Required — used by publisher; subscriber not yet active |
| `MYSQL_*` | Used by the Docker Compose MySQL container |

`JWT_SECRET_KEY` and `JWT_ALGORITHM` are shared across all services. If they differ, token validation will fail with 401.

---

## In Progress / Not Yet Implemented

| Item | Status |
|---|---|
| `app/routers/games.py` | Router declared, no endpoints implemented yet |
| `app/services/game_service.py` | File exists, empty. Move logic not written yet. |
| `app/repositories/game_repo.py` | File exists, empty. DB queries not written yet. |
| `app/events/subscriber.py` | File exists, empty. Redis subscriber not implemented. |
| `tests/test_games.py` | File exists, empty. Tests not written yet. |
| WebSocket gameplay | Planned. Real-time move exchange between players. |
| Disconnect / reconnect timers | Planned. Active game disconnect handling. |

Do not document Redis subscriber as working. Do not assume WebSocket is implemented.

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
