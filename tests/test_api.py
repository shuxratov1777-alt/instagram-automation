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


def test_admin_routes_require_api_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "test-secret")
    with TestClient(app) as client:
        assert client.get("/status").status_code == 401
        assert client.get("/status", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/status", headers={"X-API-Key": "test-secret"}).status_code == 200
