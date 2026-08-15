import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.historian import Historian
from app.tag_store import TagStore


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


@pytest.mark.asyncio
async def test_snapshot_writes_rows_for_numeric_and_bool_tags(session_factory):
    store = TagStore()
    await store.set("temp", 42.5, source_connector="c1")
    await store.set("running", True, source_connector="c1")
    await store.set("bad_tag", None, quality="bad", source_connector="c1")

    historian = Historian(session_factory, store, interval_ms=1000, retention_days=30)
    await historian._snapshot()

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


def test_purge_deletes_old_rows(session_factory):
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

    historian = Historian(session_factory, TagStore(), interval_ms=1000, retention_days=30)
    historian._maybe_purge()

    db = session_factory()
    try:
        remaining = db.query(models.TagHistory).all()
    finally:
        db.close()
    assert len(remaining) == 1
    assert remaining[0].value == 2.0


def test_purge_is_rate_limited(session_factory):
    historian = Historian(session_factory, TagStore(), interval_ms=1000, retention_days=30)
    historian._maybe_purge()
    first = historian._last_purge
    historian._maybe_purge()
    assert historian._last_purge == first
