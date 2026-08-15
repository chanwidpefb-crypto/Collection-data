"""Time-series logging: periodically snapshots the tag store into SQLite so
the Trend page can show historical data, with a simple retention purge."""
from __future__ import annotations

import asyncio
import datetime
import logging

from app import models
from app.tag_store import TagStore

logger = logging.getLogger("historian")


class Historian:
    def __init__(self, session_factory, tag_store: TagStore,
                 interval_ms: int = 5000, retention_days: int = 30):
        self.session_factory = session_factory
        self.tag_store = tag_store
        self.interval_s = interval_ms / 1000
        self.retention_days = retention_days
        self._stop_event = asyncio.Event()
        self._last_purge: datetime.datetime | None = None

    def stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._snapshot()
                self._maybe_purge()
            except Exception:  # noqa: BLE001 - keep logging even if one cycle fails
                logger.exception("historian cycle failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                pass

    async def _snapshot(self) -> None:
        entries = await self.tag_store.get_all()
        if not entries:
            return
        now = datetime.datetime.utcnow()
        db = self.session_factory()
        try:
            rows = [
                models.TagHistory(tag_name=e.tag_name, timestamp=now,
                                   value=float(e.value), quality=e.quality)
                for e in entries.values()
                if e.value is not None and isinstance(e.value, (int, float, bool))
            ]
            if rows:
                db.add_all(rows)
                db.commit()
        finally:
            db.close()

    def _maybe_purge(self) -> None:
        now = datetime.datetime.utcnow()
        if self._last_purge is not None and (now - self._last_purge) < datetime.timedelta(hours=1):
            return
        self._last_purge = now
        cutoff = now - datetime.timedelta(days=self.retention_days)
        db = self.session_factory()
        try:
            deleted = db.query(models.TagHistory).filter(models.TagHistory.timestamp < cutoff).delete()
            db.commit()
            if deleted:
                logger.info("purged %d historian rows older than %s", deleted, cutoff.isoformat())
        finally:
            db.close()
