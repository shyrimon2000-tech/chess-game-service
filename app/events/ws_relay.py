import asyncio
import json
import logging
import threading
import time

import redis

from app.config import settings
from app.connection_manager import manager, _WS_BROADCAST_CHANNEL

logger = logging.getLogger(__name__)

_RECONNECT_DELAY = 5
_loop: asyncio.AbstractEventLoop | None = None


def _relay_thread():
    while True:
        try:
            client = redis.from_url(settings.REDIS_URL)
            pubsub = client.pubsub()
            pubsub.subscribe(_WS_BROADCAST_CHANNEL)
            for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    if _loop is not None:
                        future = asyncio.run_coroutine_threadsafe(
                            manager.local_broadcast(data["game_id"], data["message"]),
                            _loop,
                        )
                        future.result(timeout=5)
                except Exception:
                    logger.exception("WS relay failed to process message: %s", message)
        except Exception:
            logger.error("WS relay disconnected, reconnecting in %ss...", _RECONNECT_DELAY)
            time.sleep(_RECONNECT_DELAY)


async def start_ws_relay():
    global _loop
    _loop = asyncio.get_running_loop()
    thread = threading.Thread(target=_relay_thread, daemon=True)
    thread.start()
