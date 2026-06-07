from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import CreateGameRequest, GameResponse, MakeMoveRequest
from app.services import game_service
from app.services.auth_dependencies import CurrentUser, get_current_user

router = APIRouter(
    prefix="/games",
    tags=["games"],
)


@router.post("", response_model=GameResponse, status_code=201)
def create_game(
    body: CreateGameRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return game_service.create_game(db, body.room_id, body.white_player_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{game_id}", response_model=GameResponse)
def get_game(
    game_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return game_service.get_game(db, game_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{game_id}/join", response_model=GameResponse)
def join_game(
    game_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return game_service.join_game(db, game_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{game_id}/move", response_model=GameResponse)
def make_move(
    game_id: int,
    body: MakeMoveRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return game_service.make_move(db, game_id, current_user.id, body.move)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{game_id}/legal-moves")
def get_legal_moves(
    game_id: int,
    square: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        moves = game_service.get_legal_moves(db, game_id, square)
        return {"moves": moves}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{game_id}/disconnect")
def handle_disconnect(
    game_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        game_service.handle_disconnect(db, game_id, current_user.id)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{game_id}/reconnect")
def handle_reconnect(
    game_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        game_service.handle_reconnect(db, game_id, current_user.id)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
