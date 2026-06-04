from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "PDM Vault"
    assert "vault_mode" in data  # local or remote


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["healthy"] is True
    assert "vault_mode" in data
