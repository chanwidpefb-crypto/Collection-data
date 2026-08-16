from __future__ import annotations

import os

import asyncpg
import pytest

from tests.conftest import set_admin_password

PG_HOST = os.environ.get("TEST_PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("TEST_PG_PORT", "5432"))
PG_USER = os.environ.get("TEST_PG_USER", "postgres")
PG_PASSWORD = os.environ.get("TEST_PG_PASSWORD", "postgres")
PG_DATABASE = os.environ.get("TEST_PG_DATABASE", "collection_data_test")


async def _postgres_available() -> bool:
    try:
        conn = await asyncpg.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                                      password=PG_PASSWORD, database=PG_DATABASE, timeout=2)
        await conn.close()
        return True
    except Exception:
        return False


def _login_admin(client):
    set_admin_password("test-password-123")
    r = client.post("/api/auth/login", json={"username": "admin", "password": "test-password-123"})
    assert r.status_code == 200


def test_settings_requires_admin(client):
    r = client.get("/api/settings/historian")
    assert r.status_code == 401

    set_admin_password("test-password-123")
    from app import models
    import app.database as database_module
    from app.auth import hash_password
    db = database_module.SessionLocal()
    try:
        db.add(models.User(username="viewer1", password_hash=hash_password("viewer-pass-123"),
                            role=models.UserRole.VIEWER))
        db.commit()
    finally:
        db.close()
    client.post("/api/auth/login", json={"username": "viewer1", "password": "viewer-pass-123"})
    assert client.get("/api/settings/historian").status_code == 403


def test_get_defaults_to_sqlite(client):
    _login_admin(client)
    r = client.get("/api/settings/historian")
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "sqlite"
    assert body["ts_password_set"] is False


def test_switch_to_sqlite_always_succeeds(client):
    _login_admin(client)
    r = client.put("/api/settings/historian", json={"backend": "sqlite", "interval_ms": 2000, "retention_days": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["interval_ms"] == 2000
    assert body["retention_days"] == 7


def test_switch_to_timescaledb_with_bad_credentials_rejected(client):
    _login_admin(client)
    r = client.put("/api/settings/historian", json={
        "backend": "timescaledb", "ts_host": PG_HOST, "ts_port": PG_PORT, "ts_database": PG_DATABASE,
        "ts_user": PG_USER, "ts_password": "definitely-wrong-password", "ts_table": "tag_history",
    })
    assert r.status_code == 400
    # settings must not have been persisted
    r = client.get("/api/settings/historian")
    assert r.json()["backend"] == "sqlite"


@pytest.mark.asyncio
async def test_switch_to_timescaledb_with_good_credentials_succeeds(client):
    if not await _postgres_available():
        pytest.skip(f"no local PostgreSQL reachable at {PG_HOST}:{PG_PORT}")
    _login_admin(client)
    r = client.put("/api/settings/historian", json={
        "backend": "timescaledb", "ts_host": PG_HOST, "ts_port": PG_PORT, "ts_database": PG_DATABASE,
        "ts_user": PG_USER, "ts_password": PG_PASSWORD, "ts_table": "tag_history_settings_api_test",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "timescaledb"
    assert body["ts_password_set"] is True

    r = client.get("/api/settings/historian")
    assert r.json()["backend"] == "timescaledb"
    assert r.json()["ts_table"] == "tag_history_settings_api_test"

    # switch back to sqlite so other tests / the running app aren't left pointed at postgres
    client.put("/api/settings/historian", json={"backend": "sqlite"})


def test_test_connection_endpoint(client):
    _login_admin(client)
    r = client.post("/api/settings/historian/test-connection", json={
        "ts_host": PG_HOST, "ts_port": PG_PORT, "ts_database": PG_DATABASE,
        "ts_user": PG_USER, "ts_password": "wrong", "ts_table": "tag_history_probe",
    })
    assert r.status_code == 200
    assert r.json()["ok"] is False
