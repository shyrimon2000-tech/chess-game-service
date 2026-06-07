import json

import redis

from app.config import settings

_client = redis.from_url(settings.REDIS_URL)


def publish_game_over(game_id: int, room_id: int, winner: str) -> None:
    payload = json.dumps({
        "event": "game_over",
        "game_id": game_id,
        "room_id": room_id,
        "winner": winner,
    })
    _client.publish("game_events", payload)


def publish_game_abandoned(game_id: int, room_id: int) -> None:
    payload = json.dumps({
        "event": "game_abandoned",
        "game_id": game_id,
        "room_id": room_id,
    })
    _client.publish("game_events", payload)
