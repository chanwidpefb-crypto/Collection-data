from __future__ import annotations

import app.database as database_module
from app import models
from app.auth import hash_password

from tests.conftest import set_admin_password


def test_login_wrong_password_rejected(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_unauthenticated_request_rejected(client):
    assert client.get("/api/connectors").status_code == 401
    assert client.get("/api/values").status_code == 401


def test_full_login_flow(client):
    set_admin_password("test-password-123")

    r = client.post("/api/auth/login", json={"username": "admin", "password": "test-password-123"})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "admin"
    assert body["role"] == "admin"
    assert body["id"] == 1

    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/connectors").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_viewer_is_read_only(client):
    set_admin_password("test-password-123")
    db = database_module.SessionLocal()
    try:
        db.add(models.User(username="viewer1", password_hash=hash_password("viewer-pass-123"),
                            role=models.UserRole.VIEWER))
        db.commit()
    finally:
        db.close()

    r = client.post("/api/auth/login", json={"username": "viewer1", "password": "viewer-pass-123"})
    assert r.status_code == 200
    assert r.json()["role"] == "viewer"

    assert client.get("/api/connectors").status_code == 403
    assert client.get("/api/values").status_code == 200
    assert client.get("/api/users").status_code == 403


def test_last_admin_cannot_be_deleted_or_demoted(client):
    admin_id = set_admin_password("test-password-123")
    client.post("/api/auth/login", json={"username": "admin", "password": "test-password-123"})

    assert client.patch(f"/api/users/{admin_id}/role", json={"role": "viewer"}).status_code == 400
    assert client.delete(f"/api/users/{admin_id}").status_code == 400


def test_admin_can_manage_users(client):
    set_admin_password("test-password-123")
    client.post("/api/auth/login", json={"username": "admin", "password": "test-password-123"})

    r = client.post("/api/users", json={"username": "op1", "password": "operator-pass-1", "role": "viewer"})
    assert r.status_code == 201
    op_id = r.json()["id"]

    r = client.post("/api/users", json={"username": "op1", "password": "another-pass-1", "role": "viewer"})
    assert r.status_code == 409

    r = client.post(f"/api/users/{op_id}/reset-password", json={"new_password": "new-op-pass-1"})
    assert r.status_code == 200

    r = client.delete(f"/api/users/{op_id}")
    assert r.status_code == 204


def test_change_own_password(client):
    set_admin_password("old-password-123")
    client.post("/api/auth/login", json={"username": "admin", "password": "old-password-123"})

    r = client.patch("/api/auth/me", json={"old_password": "wrong", "new_password": "new-password-123"})
    assert r.status_code == 400

    r = client.patch("/api/auth/me", json={"old_password": "old-password-123", "new_password": "new-password-123"})
    assert r.status_code == 200

    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"username": "admin", "password": "new-password-123"})
    assert r.status_code == 200
