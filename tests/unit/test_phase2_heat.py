from uuid import UUID

import pytest

from app.db.models import HeatAnalysisStatus
from app.integrations.fortyguard import FortyGuardError
from app.services.heat import analysis_idempotency_key, normalize_activity
from app.workers.heat_queue import RedisHeatQueue


def test_heat_idempotency_is_stable_and_zone_scoped() -> None:
    request = {"geometry": {"type": "Polygon"}, "parameters": {"season": "summer"}}
    assert analysis_idempotency_key(UUID(int=1), request) == analysis_idempotency_key(
        UUID(int=1), request
    )
    assert analysis_idempotency_key(UUID(int=1), request) != analysis_idempotency_key(
        UUID(int=2), request
    )


def test_normalizes_completed_activity() -> None:
    status, result = normalize_activity({"status": "completed", "result": {"mean_c": 37.2}})
    assert status is HeatAnalysisStatus.SUCCEEDED
    assert result == {"mean_c": 37.2}


def test_rejects_unknown_provider_status() -> None:
    with pytest.raises(FortyGuardError, match="unknown activity status"):
        normalize_activity({"status": "mystery"})


class FakeRedis:
    def __init__(self) -> None:
        self.values: list[str] = []

    async def rpush(self, key: str, value: str) -> int:
        assert key == RedisHeatQueue.key
        self.values.append(value)
        return len(self.values)

    async def blpop(self, key: str, timeout: int) -> tuple[str, str] | None:
        assert key == RedisHeatQueue.key
        assert timeout == 3
        return (key, self.values.pop(0)) if self.values else None


async def test_redis_queue_round_trip() -> None:
    queue = RedisHeatQueue(FakeRedis())  # type: ignore[arg-type]
    identifier = UUID(int=99)
    await queue.enqueue(identifier)
    assert await queue.dequeue(3) == identifier
