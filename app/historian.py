"""Time-series logging: periodically snapshots the tag store into the
configured historian storage backend (SQLite by default, or TimescaleDB --
see app/historian_backends.py and the Settings page), with a retention purge.
"""
from __future__ import annotations

import asyncio
import datetime
import logging

from app import models
from app.historian_backends import HistorianBackend, HistorianConfig, build_backend
from app.tag_store import TagStore

logger = logging.getLogger("historian")


class HistorianService:
    def __init__(self, session_factory, tag_store: TagStore):
        self.session_factory = session_factory
        self.tag_store = tag_store
        self.backend: HistorianBackend | None = None
        self.config: HistorianConfig = HistorianConfig(backend="sqlite")
        self.last_error: str | None = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._last_purge: datetime.datetime | None = None

    def stop(self) -> None:
        self._stop_event.set()

    async def load_settings_from_db(self, default_interval_ms: int = 5000, default_retention_days: int = 30) -> None:
        db = self.session_factory()
        try:
            row = db.query(models.HistorianSettings).first()
            if row is None:
                row = models.HistorianSettings(interval_ms=default_interval_ms, retention_days=default_retention_days)
                db.add(row)
                db.commit()
                db.refresh(row)
            config = HistorianConfig.from_row(row)
        finally:
            db.close()
        try:
            await self.apply_config(config)
        except Exception as exc:  # noqa: BLE001 - a saved-but-now-unreachable backend must not block app startup
            logger.error(
                "could not start the configured historian backend (%s) at startup: %s -- "
                "falling back to SQLite so the rest of the app still boots. Fix and re-save "
                "the Settings page to restore it.", config.backend, exc,
            )
            await self.apply_config(HistorianConfig(
                backend="sqlite", interval_ms=config.interval_ms, retention_days=config.retention_days,
            ))
            self.last_error = (
                f"configured backend '{config.backend}' failed to start ({exc}); "
                f"fell back to sqlite -- fix and re-save Settings to restore it"
            )

    async def apply_config(self, config: HistorianConfig) -> None:
        """Swap the active backend. Used at startup and whenever the admin
        saves new settings from the Settings page."""
        async with self._lock:
            new_backend = build_backend(config, self.session_factory)
            await new_backend.start()
            old_backend = self.backend
            self.backend = new_backend
            self.config = config
            self.last_error = None
        if old_backend is not None:
            await old_backend.stop()

    async def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._snapshot()
                await self._maybe_purge()
            except Exception as exc:  # noqa: BLE001 - keep looping even if one cycle fails
                self.last_error = str(exc)
                logger.exception("historian cycle failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.config.interval_ms / 1000)
            except asyncio.TimeoutError:
                pass

    async def _snapshot(self) -> None:
        entries = await self.tag_store.get_all()
        if not entries:
            return
        now = datetime.datetime.utcnow()
        rows = [
            (e.tag_name, now, float(e.value), e.quality)
            for e in entries.values()
            if e.value is not None and isinstance(e.value, (int, float, bool))
        ]
        if not rows:
            return
        async with self._lock:
            backend = self.backend
        if backend is not None:
            await backend.write_batch(rows)

    async def _maybe_purge(self) -> None:
        now = datetime.datetime.utcnow()
        if self._last_purge is not None and (now - self._last_purge) < datetime.timedelta(hours=1):
            return
        self._last_purge = now
        async with self._lock:
            backend = self.backend
            retention_days = self.config.retention_days
        if backend is None:
            return
        cutoff = now - datetime.timedelta(days=retention_days)
        deleted = await backend.purge_older_than(cutoff)
        if deleted:
            logger.info("purged %d historian rows older than %s", deleted, cutoff.isoformat())

    async def query(self, tag_name: str, start: datetime.datetime,
                     end: datetime.datetime) -> list[tuple[datetime.datetime, float]]:
        async with self._lock:
            backend = self.backend
        if backend is None:
            return []
        return await backend.query_range(tag_name, start, end)

    async def count(self) -> int:
        async with self._lock:
            backend = self.backend
        if backend is None:
            return 0
        return await backend.count()

    async def shutdown(self) -> None:
        self.stop()
        async with self._lock:
            if self.backend is not None:
                await self.backend.stop()
