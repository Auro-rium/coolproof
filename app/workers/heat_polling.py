from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import FortyGuardActivity, HeatAnalysis, HeatAnalysisStatus
from app.db.session import SessionLocal
from app.integrations.fortyguard import FortyGuardClient
from app.services.heat import HeatService
from app.workers.heat_queue import RedisHeatQueue


async def poll_queued_heat_analysis(
    analysis_id: UUID,
    redis: Redis[Any] | None = None,
) -> bool:
    """Process one queue item and schedule the next non-terminal poll.

    ``next_poll_at`` is persisted before the item is re-enqueued.  Waiting until
    that timestamp prevents a fast retry loop while keeping the schedule in the
    database so a future recovery scanner can resume it after a worker restart.
    Callers that own a Redis connection should pass it; the standalone helper
    creates and closes one from ``COOLPROOF_REDIS_URL`` when configured.
    """
    settings = get_settings()
    async with SessionLocal() as session:
        analysis = await session.scalar(select(HeatAnalysis).where(HeatAnalysis.id == analysis_id))
        if analysis is None:
            return False
        client = FortyGuardClient(
            settings.fortyguard_base_url,
            settings.fortyguard_api_key.get_secret_value() if settings.fortyguard_api_key else None,
            timeout=settings.fortyguard_timeout_seconds,
            max_attempts=settings.fortyguard_max_attempts,
        )
        service = HeatService(session, client, settings.heat_cache_ttl_seconds)
        await service.poll(analysis)
        activity = await session.scalar(
            select(FortyGuardActivity).where(FortyGuardActivity.analysis_id == analysis.id)
        )
        terminal = analysis.status.value in {"succeeded", "failed"}
        if activity is None or terminal or activity.next_poll_at is None:
            return True

        owned_redis = redis is None and settings.redis_url is not None
        queue_redis = redis or (
            Redis.from_url(settings.redis_url) if settings.redis_url is not None else None
        )
        if queue_redis is None:
            # Local/test runs may not configure Redis. The durable DB schedule is
            # still retained and a deployment recovery scanner can enqueue it.
            return True
        try:
            delay = max(0.0, (activity.next_poll_at - datetime.now(UTC)).total_seconds())
            if delay:
                await asyncio.sleep(delay)
            await RedisHeatQueue(queue_redis).enqueue(analysis.id)
        finally:
            if owned_redis:
                await queue_redis.close()
        return True


async def consume_heat_queue(redis: Redis[Any], timeout_seconds: int = 1) -> bool:
    """Single queue-consumer tick used by the worker process."""
    analysis_id = await RedisHeatQueue(redis).dequeue(timeout_seconds)
    return False if analysis_id is None else await poll_queued_heat_analysis(analysis_id, redis)


async def recover_due_heat_activities(
    redis: Redis[Any], *, limit: int = 100
) -> int:
    """Re-enqueue due durable activities after a worker restart.

    Redis is only a transport.  PostgreSQL remains the source of truth for the
    schedule, so an activity whose queue item was lost while a worker was
    stopped is recovered on the next empty queue tick.
    """
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(FortyGuardActivity.analysis_id)
                .join(HeatAnalysis, HeatAnalysis.id == FortyGuardActivity.analysis_id)
                .where(
                    FortyGuardActivity.next_poll_at <= now,
                    HeatAnalysis.status.notin_((HeatAnalysisStatus.SUCCEEDED, HeatAnalysisStatus.FAILED)),
                )
                .order_by(FortyGuardActivity.next_poll_at)
                .limit(limit)
            )
        ).all()
    queue = RedisHeatQueue(redis)
    for analysis_id in rows:
        await queue.enqueue(analysis_id)
    return len(rows)
