import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def health_client() -> TestClient:
    return TestClient(app)


def test_root_endpoint(health_client: TestClient):
    response = health_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Magicpin AI Agent"
    assert data["status"] == "online"


def test_healthz_liveness_endpoint(health_client: TestClient):
    response = health_client.get("/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_readiness_endpoint_success(monkeypatch, health_client: TestClient):
    monkeypatch.setattr("backend.app.api.v1.routes.health.check_database_connection", lambda: True)
    response = health_client.get("/v1/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"


def test_readyz_readiness_endpoint_db_failure(monkeypatch, health_client: TestClient):
    monkeypatch.setattr("backend.app.api.v1.routes.health.check_database_connection", lambda: False)
    response = health_client.get("/v1/readyz")
    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert "unavailable" in data["error"]["message"].lower()
