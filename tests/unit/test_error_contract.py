import httpx


async def test_unknown_route_uses_problem_details_contract(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/not-a-real-route")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str)
    assert "traceback" not in response.text.lower()
