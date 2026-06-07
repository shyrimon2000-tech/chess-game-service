import json
import logging

import redis

from app.config import settings
from app.database import SessionLocal
from app.services import game_service

logger = logging.getLogger(__name__)


def _handle_message(message):
    if message["type"] != "message":
        return

    try:
        data = json.loads(message["data"])
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse room event: %s", message)
        return

    if data.get("event") == "room_activated":
        db = SessionLocal()
        try:
            game_service.create_game(
                db,
                room_id=data["room_id"],
                white_player_id=data["white_player_id"],
                black_player_id=data["black_player_id"],
            )
        except Exception:
            logger.exception("Failed to create game for room %s", data.get("room_id"))
        finally:
            db.close()


def start_subscriber():
    client = redis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    pubsub.subscribe(**{"room_events": _handle_message})
    pubsub.run_in_thread(sleep_time=0.01, daemon=True)
