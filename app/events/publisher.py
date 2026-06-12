import json
import logging

import redis
from tenacity import retry, stop_after_attempt, wait_fixed

from app.config import settings

logger = logging.getLogger(__name__)

_client = redis.from_url(settings.REDIS_URL)


@retry(wait=wait_fixed(2), stop=stop_after_attempt(30))
def wait_for_redis() -> None:
    _client.ping()


def publish_game_created(game_id: int, room_id: int) -> None:
    payload = json.dumps({
        "event": "game_created",
        "game_id": game_id,
        "room_id": room_id,
    })
    try:
        _client.publish("game_events", payload)
    except Exception:
        logger.exception("Failed to publish game_created for game %s", game_id)


def publish_game_over(game_id: int, room_id: int, winner: str) -> None:
    payload = json.dumps({
        "event": "game_over",
        "game_id": game_id,
        "room_id": room_id,
        "winner": winner,
    })
    try:
        _client.publish("game_events", payload)
    except Exception:
        logger.exception("Failed to publish game_over for game %s", game_id)


def publish_game_abandoned(game_id: int, room_id: int) -> None:
    payload = json.dumps({
        "event": "game_abandoned",
        "game_id": game_id,
        "room_id": room_id,
    })
    try:
        _client.publish("game_events", payload)
    except Exception:
        logger.exception("Failed to publish game_abandoned for game %s", game_id)
