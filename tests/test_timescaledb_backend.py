"""Tests against a real local PostgreSQL instance (used as a stand-in for
TimescaleDB -- the timescaledb extension itself is optional, see
TimescaleDbHistorianBackend.start(), which falls back to a plain table when
it's not installed). Skipped automatically if no Postgres is reachable."""
from __future__ import annotations

import datetime
import os
import uuid

import asyncpg
import pytest

from app.historian_backends import HistorianConfig, TimescaleDbHistorianBackend, check_timescaledb_connection

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


@pytest.fixture()
async def backend():
    if not await _postgres_available():
        pytest.skip(f"no local PostgreSQL reachable at {PG_HOST}:{PG_PORT}")
    table = f"tag_history_test_{uuid.uuid4().hex[:8]}"
    b = TimescaleDbHistorianBackend(host=PG_HOST, port=PG_PORT, database=PG_DATABASE,
                                     user=PG_USER, password=PG_PASSWORD, table=table)
    await b.start()
    yield b
    async with b._pool.acquire() as conn:
        await conn.execute(f"DROP TABLE IF EXISTS {table}")
    await b.stop()


@pytest.mark.asyncio
async def test_write_and_query_range(backend):
    now = datetime.datetime.now(datetime.timezone.utc)
    await backend.write_batch([
        ("temp1", now - datetime.timedelta(minutes=2), 10.0, "good"),
        ("temp1", now - datetime.timedelta(minutes=1), 20.0, "good"),
        ("temp2", now, 99.0, "good"),
    ])

    points = await backend.query_range("temp1", now - datetime.timedelta(hours=1), now + datetime.timedelta(hours=1))
    assert [v for _, v in points] == [10.0, 20.0]
    assert await backend.count() == 3


@pytest.mark.asyncio
async def test_purge_older_than(backend):
    now = datetime.datetime.now(datetime.timezone.utc)
    await backend.write_batch([
        ("t", now - datetime.timedelta(days=40), 1.0, "good"),
        ("t", now - datetime.timedelta(days=1), 2.0, "good"),
    ])
    deleted = await backend.purge_older_than(now - datetime.timedelta(days=30))
    assert deleted == 1
    assert await backend.count() == 1


@pytest.mark.asyncio
async def test_query_range_excludes_out_of_bounds(backend):
    now = datetime.datetime.now(datetime.timezone.utc)
    await backend.write_batch([
        ("t", now - datetime.timedelta(hours=5), 1.0, "good"),
        ("t", now, 2.0, "good"),
    ])
    points = await backend.query_range("t", now - datetime.timedelta(hours=1), now + datetime.timedelta(hours=1))
    assert [v for _, v in points] == [2.0]


@pytest.mark.asyncio
async def test_connection_helper_reports_success():
    if not await _postgres_available():
        pytest.skip(f"no local PostgreSQL reachable at {PG_HOST}:{PG_PORT}")
    ok, msg = await check_timescaledb_connection(HistorianConfig(
        backend="timescaledb", ts_host=PG_HOST, ts_port=PG_PORT, ts_database=PG_DATABASE,
        ts_user=PG_USER, ts_password=PG_PASSWORD, ts_table=f"tag_history_probe_{uuid.uuid4().hex[:8]}",
    ))
    assert ok is True


@pytest.mark.asyncio
async def test_connection_helper_reports_failure_on_bad_password():
    if not await _postgres_available():
        pytest.skip(f"no local PostgreSQL reachable at {PG_HOST}:{PG_PORT}")
    ok, msg = await check_timescaledb_connection(HistorianConfig(
        backend="timescaledb", ts_host=PG_HOST, ts_port=PG_PORT, ts_database=PG_DATABASE,
        ts_user=PG_USER, ts_password="definitely-wrong-password", ts_table="tag_history_probe_fail",
    ))
    assert ok is False
    assert msg


def test_invalid_table_name_rejected():
    with pytest.raises(ValueError):
        TimescaleDbHistorianBackend(host="x", port=5432, database="d", user="u", password="p",
                                     table="bad; drop table users;--")
