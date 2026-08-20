from __future__ import annotations

from typing import Any
from uuid import UUID

from redis.asyncio import Redis


class RedisHeatQueue:
    """Durable Redis list queue; entries contain only analysis IDs."""

    key = "coolproof:heat:poll"

    def __init__(self, redis: Redis[Any]) -> None:
        self.redis = redis

    async def enqueue(self, analysis_id: UUID) -> None:
        await self.redis.rpush(self.key, str(analysis_id))

    async def dequeue(self, timeout_seconds: int = 1) -> UUID | None:
        item = await self.redis.blpop(self.key, timeout=timeout_seconds)
        if item is None:
            return None
        _, value = item
        return UUID(value.decode() if isinstance(value, bytes) else value)
