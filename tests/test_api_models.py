import pytest
from fastapi.testclient import TestClient

from main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def test_list_models(client):
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "tasks" in data
    assert "deepseek" in data["providers"]
    assert "summary" in data["tasks"]


def test_models_health(client):
    response = client.get("/api/v1/models/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "providers" in data


def test_test_model_degraded_to_local(client):
    """Without API keys, POST /models/test falls back to local adapter."""
    response = client.post("/api/v1/models/test", json={
        "task": "summary",
        "prompt": "Hello",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "local"
    assert data["text"] == ""  # local adapter returns empty text
