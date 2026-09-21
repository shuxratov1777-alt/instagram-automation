from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app


def test_health():
    init_db()
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        ready = client.get("/ready").json()
        assert ready["auto_publish"] is False

