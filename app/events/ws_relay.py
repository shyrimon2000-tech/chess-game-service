import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.config import settings
from app.connection_manager import manager, _WS_BROADCAST_CHANNEL

logger = logging.getLogger(__name__)

_RECONNECT_DELAY = 5


async def _relay_loop():
    while True:
        try:
            client = aioredis.from_url(settings.REDIS_URL)
            pubsub = client.pubsub()
            await pubsub.subscribe(_WS_BROADCAST_CHANNEL)
            logger.info("WS relay subscribed to %s", _WS_BROADCAST_CHANNEL)
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await manager.local_broadcast(data["game_id"], data["message"])
                except Exception:
                    logger.exception("WS relay failed to process message: %s", message)
        except Exception:
            logger.error("WS relay disconnected, reconnecting in %ss...", _RECONNECT_DELAY)
            await asyncio.sleep(_RECONNECT_DELAY)


async def start_ws_relay():
    asyncio.create_task(_relay_loop())
