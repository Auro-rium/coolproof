"""Durable FortyGuard polling worker entrypoint.

The container runs this module as ``python -m app.worker``.  Redis is the
transport, while poll state and the next due timestamp remain in PostgreSQL.
"""

from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis

from app.core.config import get_settings
from app.workers.heat_polling import consume_heat_queue, recover_due_heat_activities

logger = logging.getLogger("coolproof.worker")


async def run() -> None:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("COOLPROOF_REDIS_URL is required for the polling worker")

    redis: Redis[bytes] = Redis.from_url(settings.redis_url, decode_responses=False)
    try:
        while True:
            try:
                consumed = await consume_heat_queue(redis, timeout_seconds=5)
                if not consumed:
                    await recover_due_heat_activities(redis)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Keep the worker alive for transient database/provider failures;
                # the queue item has already been removed and the durable activity
                # schedule is available for a recovery scan.
                logger.exception("heat polling tick failed")
                await asyncio.sleep(1)
    finally:
        await redis.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
