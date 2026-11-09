from fastapi.testclient import TestClient

from app import __version__, db
from app.main import app

client = TestClient(app)


def test_health_db_ok(monkeypatch):
    monkeypatch.setattr(db, "check_db", lambda: True)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok", "version": __version__}
    assert client.get("/api/v1/ready").status_code == 200


def test_health_db_error(monkeypatch):
    monkeypatch.setattr(db, "check_db", lambda: False)
    r = client.get("/api/v1/health")
    assert r.status_code == 200  # liveness stays up
    assert r.json()["db"] == "error"
    assert r.json()["status"] == "degraded"
    assert client.get("/api/v1/ready").status_code == 503


def test_check_db_unreachable_returns_false(monkeypatch):
    from sqlalchemy import create_engine

    monkeypatch.setattr(
        db,
        "engine",
        create_engine(
            "postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 1}
        ),
    )
    assert db.check_db() is False
