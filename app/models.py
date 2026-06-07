from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base

INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="waiting")
    white_player_id = Column(Integer, nullable=False)
    black_player_id = Column(Integer, nullable=True)
    current_turn = Column(String(5), nullable=True)
    board_state = Column(Text, nullable=False, default=INITIAL_FEN)
    winner = Column(String(5), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
