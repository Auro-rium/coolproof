from uuid import UUID

import pytest

from app.db.models import HeatAnalysisStatus
from app.integrations.fortyguard import FortyGuardError
from app.integrations.fortyguard.client import FortyGuardClient
from app.services.heat import analysis_idempotency_key, normalize_activity
from app.workers.heat_queue import RedisHeatQueue


def test_heat_idempotency_uses_provider_query_fields() -> None:
    request = {
        "geometry": {"type": "Polygon", "coordinates": [[[1, 2], [3, 4], [1, 2]]]},
        "parameters": {
            "datetime": "2024-07-15T12:00:00Z",
            "analytic_type": "exceedance",
            "threshold": 35,
            "granularity": 100,
            "ignored": "not part of provider query",
        },
    }
    assert analysis_idempotency_key(UUID(int=1), request) == analysis_idempotency_key(
        UUID(int=1), request
    )
    # Internal zone IDs do not change a provider query and therefore must not
    # cause another credit-consuming FortyGuard activity.
    assert analysis_idempotency_key(UUID(int=1), request) == analysis_idempotency_key(
        UUID(int=2), request
    )
    changed = {**request, "parameters": {**request["parameters"], "threshold": 36}}
    assert analysis_idempotency_key(UUID(int=1), request) != analysis_idempotency_key(
        UUID(int=1), changed
    )


def test_normalizes_completed_activity() -> None:
    status, result = normalize_activity({"status": "completed", "result": {"mean_c": 37.2}})
    assert status is HeatAnalysisStatus.SUCCEEDED
    assert result == {"mean_c": 37.2}


def test_rejects_unknown_provider_status() -> None:
    with pytest.raises(FortyGuardError, match="unknown activity status"):
        normalize_activity({"status": "mystery"})


def test_translates_coolproof_heat_request_to_fortyguard_shape() -> None:
    request = FortyGuardClient._heatmap_payload(
        {
            "geometry": {"type": "Polygon", "coordinates": [[[1, 2], [3, 4], [1, 2]]]},
            "parameters": {"resolution": 100, "include_exceedance": True, "threshold": 35},
        }
    )
    assert request["polygon_aoi"]["type"] == "FeatureCollection"  # type: ignore[index]
    assert request["granularity"] == 100
    assert request["analytic_type"] == "exceedance"
    assert request["threshold"] == 35
    assert request["date_time"]["filter_type"] == 1  # type: ignore[index]


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
