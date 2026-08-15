"""Pluggable historian storage backends.

`SqliteHistorianBackend` writes into the app's own SQLite database (the
`tag_history` table, via the same SQLAlchemy session as everything else) --
this is the zero-configuration default. `TimescaleDbHistorianBackend` writes
into an external PostgreSQL/TimescaleDB database over asyncpg instead, for
deployments that want a real time-series database. Both backends implement
the same interface so the historian service and the /api/history endpoints
don't need to know which one is active.
"""
from __future__ import annotations

import abc
import dataclasses
import datetime
import logging
import re

import asyncpg

from app import models

logger = logging.getLogger("historian.backend")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def validate_table_name(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(
            "table name must start with a letter/underscore and contain only "
            "letters, digits, and underscores (max 63 chars)"
        )
    return name


@dataclasses.dataclass
class HistorianConfig:
    backend: str  # "sqlite" | "timescaledb"
    interval_ms: int = 5000
    retention_days: int = 30
    ts_host: str = ""
    ts_port: int = 5432
    ts_database: str = ""
    ts_user: str = ""
    ts_password: str = ""
    ts_table: str = "tag_history"
    ts_sslmode: str = "prefer"

    @classmethod
    def from_row(cls, row: models.HistorianSettings) -> "HistorianConfig":
        return cls(
            backend=row.backend.value if hasattr(row.backend, "value") else row.backend,
            interval_ms=row.interval_ms, retention_days=row.retention_days,
            ts_host=row.ts_host, ts_port=row.ts_port, ts_database=row.ts_database,
            ts_user=row.ts_user, ts_password=row.ts_password, ts_table=row.ts_table,
            ts_sslmode=row.ts_sslmode,
        )


class HistorianBackend(abc.ABC):
    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def stop(self) -> None: ...

    @abc.abstractmethod
    async def write_batch(self, rows: list[tuple[str, datetime.datetime, float, str]]) -> None:
        """rows: list of (tag_name, timestamp, value, quality)."""

    @abc.abstractmethod
    async def purge_older_than(self, cutoff: datetime.datetime) -> int:
        """Delete samples older than cutoff; returns the number of rows deleted."""

    @abc.abstractmethod
    async def query_range(self, tag_name: str, start: datetime.datetime,
                           end: datetime.datetime) -> list[tuple[datetime.datetime, float]]:
        ...

    @abc.abstractmethod
    async def count(self) -> int: ...


class SqliteHistorianBackend(HistorianBackend):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def write_batch(self, rows: list[tuple[str, datetime.datetime, float, str]]) -> None:
        if not rows:
            return
        db = self.session_factory()
        try:
            db.add_all([models.TagHistory(tag_name=t, timestamp=ts, value=v, quality=q) for t, ts, v, q in rows])
            db.commit()
        finally:
            db.close()

    async def purge_older_than(self, cutoff: datetime.datetime) -> int:
        db = self.session_factory()
        try:
            deleted = db.query(models.TagHistory).filter(models.TagHistory.timestamp < cutoff).delete()
            db.commit()
            return deleted
        finally:
            db.close()

    async def query_range(self, tag_name: str, start: datetime.datetime,
                           end: datetime.datetime) -> list[tuple[datetime.datetime, float]]:
        db = self.session_factory()
        try:
            rows = (
                db.query(models.TagHistory)
                .filter(models.TagHistory.tag_name == tag_name,
                        models.TagHistory.timestamp >= start,
                        models.TagHistory.timestamp <= end)
                .order_by(models.TagHistory.timestamp)
                .all()
            )
            return [(r.timestamp, r.value) for r in rows]
        finally:
            db.close()

    async def count(self) -> int:
        db = self.session_factory()
        try:
            return db.query(models.TagHistory).count()
        finally:
            db.close()


class TimescaleDbHistorianBackend(HistorianBackend):
    def __init__(self, host: str, port: int, database: str, user: str, password: str,
                 table: str = "tag_history", sslmode: str = "prefer"):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table = validate_table_name(table)
        self.sslmode = sslmode
        self._pool: asyncpg.Pool | None = None

    def _dsn_kwargs(self) -> dict:
        return dict(host=self.host, port=self.port, database=self.database,
                    user=self.user, password=self.password, ssl=self._ssl_arg())

    def _ssl_arg(self):
        # asyncpg's `ssl` kwarg wants True/False/an SSLContext, not libpq's sslmode strings.
        return False if self.sslmode in ("disable", "prefer", "allow") else True

    async def start(self) -> None:
        self._pool = await asyncpg.create_pool(min_size=1, max_size=4, **self._dsn_kwargs())
        async with self._pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    id BIGSERIAL PRIMARY KEY,
                    tag_name TEXT NOT NULL,
                    ts TIMESTAMPTZ NOT NULL,
                    value DOUBLE PRECISION NOT NULL,
                    quality TEXT NOT NULL DEFAULT 'good'
                );
            """)
            await conn.execute(f"CREATE INDEX IF NOT EXISTS ix_{self.table}_tag_ts ON {self.table} (tag_name, ts);")
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
                await conn.execute(
                    f"SELECT create_hypertable('{self.table}', 'ts', if_not_exists => true, migrate_data => true);"
                )
                logger.info("TimescaleDB hypertable ready: %s", self.table)
            except Exception as exc:  # noqa: BLE001 - extension may not be installed; plain table still works
                logger.warning(
                    "could not enable TimescaleDB hypertable on '%s' (falling back to a plain "
                    "Postgres table -- install/enable the timescaledb extension for proper time-series "
                    "partitioning): %s", self.table, exc,
                )

    async def stop(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def write_batch(self, rows: list[tuple[str, datetime.datetime, float, str]]) -> None:
        if not rows:
            return
        async with self._pool.acquire() as conn:
            await conn.executemany(
                f"INSERT INTO {self.table} (tag_name, ts, value, quality) VALUES ($1, $2, $3, $4)", rows,
            )

    async def purge_older_than(self, cutoff: datetime.datetime) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(f"DELETE FROM {self.table} WHERE ts < $1", cutoff)
        # asyncpg returns a status string like "DELETE 42"
        try:
            return int(result.split()[-1])
        except (IndexError, ValueError):
            return 0

    async def query_range(self, tag_name: str, start: datetime.datetime,
                           end: datetime.datetime) -> list[tuple[datetime.datetime, float]]:
        async with self._pool.acquire() as conn:
            records = await conn.fetch(
                f"SELECT ts, value FROM {self.table} WHERE tag_name = $1 AND ts >= $2 AND ts <= $3 ORDER BY ts",
                tag_name, start, end,
            )
        return [(r["ts"], r["value"]) for r in records]

    async def count(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(f"SELECT count(*) FROM {self.table}")


def build_backend(config: HistorianConfig, session_factory) -> HistorianBackend:
    if config.backend == models.HistorianBackendType.TIMESCALEDB.value:
        return TimescaleDbHistorianBackend(
            host=config.ts_host, port=config.ts_port, database=config.ts_database,
            user=config.ts_user, password=config.ts_password, table=config.ts_table,
            sslmode=config.ts_sslmode,
        )
    return SqliteHistorianBackend(session_factory)


async def check_timescaledb_connection(config: HistorianConfig) -> tuple[bool, str]:
    """Attempt a lightweight connection to validate TimescaleDB settings
    before saving them. Returns (ok, message)."""
    backend = TimescaleDbHistorianBackend(
        host=config.ts_host, port=config.ts_port, database=config.ts_database,
        user=config.ts_user, password=config.ts_password, table=config.ts_table,
        sslmode=config.ts_sslmode,
    )
    try:
        await backend.start()
        await backend.count()
        return True, "connected"
    except Exception as exc:  # noqa: BLE001 - report any connection/auth/permission error to the caller
        return False, str(exc)
    finally:
        await backend.stop()
