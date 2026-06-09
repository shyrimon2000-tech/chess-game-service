import json
import logging
import threading
import time

import redis

from app.config import settings
from app.database import SessionLocal
from app.events.publisher import publish_game_created
from app.services import game_service

logger = logging.getLogger(__name__)

_RECONNECT_DELAY = 5


def _handle_message(message):
    if message["type"] != "message":
        return

    try:
        data = json.loads(message["data"])
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse room event: %s", message)
        return

    event = data.get("event")

    if event == "room_created":
        db = SessionLocal()
        try:
            game = game_service.create_game(
                db,
                room_id=data["room_id"],
                white_player_id=data["white_player_id"],
            )
            publish_game_created(game.id, game.room_id)
        except Exception:
            logger.exception("Failed to create game for room %s", data.get("room_id"))
        finally:
            db.close()

    elif event == "room_activated":
        db = SessionLocal()
        try:
            game_service.activate_game(
                db,
                room_id=data["room_id"],
                black_player_id=data["black_player_id"],
            )
        except Exception:
            logger.exception("Failed to activate game for room %s", data.get("room_id"))
        finally:
            db.close()


def _subscriber_loop():
    while True:
        try:
            client = redis.from_url(settings.REDIS_URL)
            pubsub = client.pubsub()
            pubsub.subscribe("room_events")
            logger.info("Subscribed to room_events")
            for message in pubsub.listen():
                _handle_message(message)
        except Exception:
            logger.error("Redis subscriber disconnected, reconnecting in %ss...", _RECONNECT_DELAY)
            time.sleep(_RECONNECT_DELAY)


def start_subscriber():
    thread = threading.Thread(target=_subscriber_loop, daemon=True)
    thread.start()
