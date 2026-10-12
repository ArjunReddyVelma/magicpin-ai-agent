from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Magicpin AI Agent"
    assert data["status"] == "online"


def test_healthz_liveness_endpoint():
    response = client.get("/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_readiness_endpoint():
    response = client.get("/v1/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"
