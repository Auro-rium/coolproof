import httpx


async def test_liveness_reports_healthy_service(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "healthy"}


async def test_readiness_has_stable_response_shape(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code in {200, 503}
    body = response.json()
    assert body["status"] in {"ok", "healthy", "unavailable"}
