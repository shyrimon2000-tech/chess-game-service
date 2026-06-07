from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateGameRequest(BaseModel):
    room_id: int
    white_player_id: int


class MakeMoveRequest(BaseModel):
    move: str


class GameResponse(BaseModel):
    id: int
    room_id: int
    status: str
    white_player_id: int
    black_player_id: int | None
    current_turn: str | None
    board_state: str
    winner: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
