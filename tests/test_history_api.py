from __future__ import annotations

import datetime

import app.database as database_module
from app import models

from tests.conftest import set_admin_password


def _login(client):
    set_admin_password("test-password-123")
    r = client.post("/api/auth/login", json={"username": "admin", "password": "test-password-123"})
    assert r.status_code == 200


def _insert_rows(tag_name: str, values: list[float], start: datetime.datetime, step: datetime.timedelta):
    db = database_module.SessionLocal()
    try:
        for i, v in enumerate(values):
            db.add(models.TagHistory(tag_name=tag_name, timestamp=start + step * i, value=v, quality="good"))
        db.commit()
    finally:
        db.close()


def test_history_requires_login(client):
    r = client.get("/api/history", params={"tags": "t1", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"})
    assert r.status_code == 401


def test_history_returns_points_in_range(client):
    _login(client)
    base = datetime.datetime(2026, 1, 1, 0, 0, 0)
    _insert_rows("temp1", [10.0, 20.0, 30.0], base, datetime.timedelta(minutes=5))

    r = client.get("/api/history", params={
        "tags": "temp1", "start": "2026-01-01T00:00:00Z", "end": "2026-01-01T01:00:00Z", "max_points": 100,
    })
    assert r.status_code == 200
    body = r.json()
    assert [p["v"] for p in body["temp1"]] == [10.0, 20.0, 30.0]


def test_history_excludes_out_of_range_points(client):
    _login(client)
    base = datetime.datetime(2026, 1, 1, 0, 0, 0)
    _insert_rows("temp1", [1.0, 2.0, 3.0], base, datetime.timedelta(hours=2))  # spans 4 hours

    r = client.get("/api/history", params={
        "tags": "temp1", "start": "2026-01-01T00:00:00Z", "end": "2026-01-01T02:30:00Z", "max_points": 100,
    })
    body = r.json()
    assert [p["v"] for p in body["temp1"]] == [1.0, 2.0]


def test_history_downsamples_when_over_max_points(client):
    _login(client)
    base = datetime.datetime(2026, 1, 1, 0, 0, 0)
    _insert_rows("temp1", [float(i) for i in range(1000)], base, datetime.timedelta(seconds=1))

    r = client.get("/api/history", params={
        "tags": "temp1", "start": "2026-01-01T00:00:00Z", "end": "2026-01-01T01:00:00Z", "max_points": 100,
    })
    body = r.json()
    assert len(body["temp1"]) <= 100
    # downsampling should still cover the full span, first/last close to original endpoints
    assert body["temp1"][0]["v"] == 0.0


def test_history_multiple_tags(client):
    _login(client)
    base = datetime.datetime(2026, 1, 1, 0, 0, 0)
    _insert_rows("a", [1.0, 2.0], base, datetime.timedelta(minutes=1))
    _insert_rows("b", [9.0, 8.0], base, datetime.timedelta(minutes=1))

    r = client.get("/api/history", params={
        "tags": "a,b", "start": "2026-01-01T00:00:00Z", "end": "2026-01-01T01:00:00Z", "max_points": 100,
    })
    body = r.json()
    assert set(body.keys()) == {"a", "b"}
    assert [p["v"] for p in body["a"]] == [1.0, 2.0]
    assert [p["v"] for p in body["b"]] == [9.0, 8.0]


def test_history_status(client):
    _login(client)
    base = datetime.datetime(2026, 1, 1, 0, 0, 0)
    _insert_rows("temp1", [1.0, 2.0, 3.0], base, datetime.timedelta(minutes=1))

    r = client.get("/api/history/status")
    assert r.status_code == 200
    body = r.json()
    assert body["total_points"] == 3
    assert body["interval_ms"] > 0
    assert body["retention_days"] > 0
