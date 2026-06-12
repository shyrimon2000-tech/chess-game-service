from datetime import datetime

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (UniqueConstraint("room_id", name="uq_games_room_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    white_player_id: Mapped[int]
    black_player_id: Mapped[int | None]
    current_turn: Mapped[str | None] = mapped_column(String(5))
    board_state: Mapped[str] = mapped_column(Text, default=INITIAL_FEN)
    winner: Mapped[str | None] = mapped_column(String(5))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
