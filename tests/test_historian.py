import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.historian import HistorianService
from app.historian_backends import HistorianConfig
from app.tag_store import TagStore


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


async def _sqlite_service(session_factory, tag_store, interval_ms=1000, retention_days=30) -> HistorianService:
    service = HistorianService(session_factory, tag_store)
    await service.apply_config(HistorianConfig(backend="sqlite", interval_ms=interval_ms, retention_days=retention_days))
    return service


@pytest.mark.asyncio
async def test_snapshot_writes_rows_for_numeric_and_bool_tags(session_factory):
    store = TagStore()
    await store.set("temp", 42.5, source_connector="c1")
    await store.set("running", True, source_connector="c1")
    await store.set("bad_tag", None, quality="bad", source_connector="c1")

    service = await _sqlite_service(session_factory, store)
    await service._snapshot()

    db = session_factory()
    try:
        rows = db.query(models.TagHistory).order_by(models.TagHistory.tag_name).all()
    finally:
        db.close()

    assert {r.tag_name for r in rows} == {"temp", "running"}
    temp_row = next(r for r in rows if r.tag_name == "temp")
    assert temp_row.value == 42.5
    running_row = next(r for r in rows if r.tag_name == "running")
    assert running_row.value == 1.0


@pytest.mark.asyncio
async def test_purge_deletes_old_rows(session_factory):
    db = session_factory()
    now = datetime.datetime.utcnow()
    try:
        db.add_all([
            models.TagHistory(tag_name="t", timestamp=now - datetime.timedelta(days=40), value=1.0, quality="good"),
            models.TagHistory(tag_name="t", timestamp=now - datetime.timedelta(days=1), value=2.0, quality="good"),
        ])
        db.commit()
    finally:
        db.close()

    service = await _sqlite_service(session_factory, TagStore(), retention_days=30)
    await service._maybe_purge()

    db = session_factory()
    try:
        remaining = db.query(models.TagHistory).all()
    finally:
        db.close()
    assert len(remaining) == 1
    assert remaining[0].value == 2.0


@pytest.mark.asyncio
async def test_purge_is_rate_limited(session_factory):
    service = await _sqlite_service(session_factory, TagStore(), retention_days=30)
    await service._maybe_purge()
    first = service._last_purge
    await service._maybe_purge()
    assert service._last_purge == first


@pytest.mark.asyncio
async def test_query_and_count(session_factory):
    store = TagStore()
    service = await _sqlite_service(session_factory, store)
    now = datetime.datetime.utcnow()
    await service.backend.write_batch([
        ("temp", now - datetime.timedelta(minutes=1), 1.0, "good"),
        ("temp", now, 2.0, "good"),
        ("other", now, 9.0, "good"),
    ])

    points = await service.query("temp", now - datetime.timedelta(hours=1), now + datetime.timedelta(hours=1))
    assert [v for _, v in points] == [1.0, 2.0]
    assert await service.count() == 3


@pytest.mark.asyncio
async def test_apply_config_swaps_backend_and_stops_old_one(session_factory):
    service = await _sqlite_service(session_factory, TagStore())
    old_backend = service.backend
    await service.apply_config(HistorianConfig(backend="sqlite", interval_ms=2000, retention_days=10))
    assert service.backend is not old_backend
    assert service.config.interval_ms == 2000
    assert service.config.retention_days == 10


@pytest.mark.asyncio
async def test_load_settings_falls_back_to_sqlite_when_configured_backend_unreachable(session_factory):
    db = session_factory()
    try:
        db.add(models.HistorianSettings(
            backend=models.HistorianBackendType.TIMESCALEDB, interval_ms=1000, retention_days=30,
            ts_host="does-not-resolve.invalid", ts_port=5432, ts_database="x", ts_user="x", ts_password="x",
        ))
        db.commit()
    finally:
        db.close()

    service = HistorianService(session_factory, TagStore())
    await service.load_settings_from_db()  # must not raise even though the configured backend is unreachable

    assert service.config.backend == "sqlite"
    assert service.last_error is not None
    assert "sqlite" in service.last_error
