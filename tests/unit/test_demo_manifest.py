from fastapi.testclient import TestClient

from app.main import create_app


def test_demo_manifest_is_safe_and_judge_facing() -> None:
    client = TestClient(create_app())
    response = client.get("/demo/manifest")
    assert response.status_code == 200
    body = response.json()
    assert [stage["stage"] for stage in body["workflow"]] == [
        "heat",
        "evidence",
        "optimize",
        "govern",
        "verify",
    ]
    assert "api_key" not in response.text.lower()
    assert "FastAPI" == body["architecture"]["api"]
