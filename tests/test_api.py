from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app
from app.config import settings


def test_health():
    init_db()
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        ready = client.get("/ready").json()
        assert ready["auto_publish"] is False
        assert ready["human_approval_required"] is True


def test_public_policy_pages():
    with TestClient(app) as client:
        privacy = client.get("/privacy")
        deletion = client.get("/data-deletion")
        assert privacy.status_code == 200
        assert "Privacy Policy" in privacy.text
        assert deletion.status_code == 200
        assert "Data Deletion Instructions" in deletion.text


def test_admin_routes_require_api_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "test-secret")
    with TestClient(app) as client:
        assert client.get("/status").status_code == 401
        assert client.get("/status", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/status", headers={"X-API-Key": "test-secret"}).status_code == 200
