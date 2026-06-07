import json

import redis

from app.config import settings


def publish_game_over(game_id: int, room_id: int, winner: str) -> None:
    client = redis.from_url(settings.REDIS_URL)

    payload = json.dumps({
        "event": "game_over",
        "game_id": game_id,
        "room_id": room_id,
        "winner": winner,
    })

    client.publish("game_events", payload)


def publish_game_abandoned(game_id: int, room_id: int) -> None:
    client = redis.from_url(settings.REDIS_URL)

    payload = json.dumps({
        "event": "game_abandoned",
        "game_id": game_id,
        "room_id": room_id,
    })

    client.publish("game_events", payload)
