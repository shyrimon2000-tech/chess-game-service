from sqlalchemy.orm import Session

from app.models import Game, INITIAL_FEN


def create_game(
    db: Session,
    room_id: int,
    white_player_id: int,
    black_player_id: int | None = None,
) -> Game:
    game = Game(
        room_id=room_id,
        white_player_id=white_player_id,
        black_player_id=black_player_id,
        status="waiting",
        board_state=INITIAL_FEN,
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def get_game_by_id(db: Session, game_id: int) -> Game | None:
    return db.query(Game).filter(Game.id == game_id).first()


def get_game_by_room_id(db: Session, room_id: int) -> Game | None:
    return db.query(Game).filter(Game.room_id == room_id).first()



def save_game(db: Session, game: Game) -> Game:
    db.commit()
    db.refresh(game)
    return game
