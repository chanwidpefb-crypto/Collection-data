from __future__ import annotations

import abc
import asyncio
import logging

from app.tag_store import TagStore


class BaseDriver(abc.ABC):
    """Common lifecycle for every connector (client or server, Modbus or OPC UA)."""

    def __init__(self, connector_id: int, connector_name: str, tag_store: TagStore):
        self.connector_id = connector_id
        self.connector_name = connector_name
        self.tag_store = tag_store
        self.logger = logging.getLogger(f"driver.{connector_name}")
        self.last_error: str | None = None
        self._stop_event = asyncio.Event()

    async def run_forever(self) -> None:
        """Entry point run as an asyncio task by the DriverManager."""
        try:
            await self._run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI via status endpoint
            self.last_error = str(exc)
            self.logger.exception("driver %s crashed", self.connector_name)
            raise
        finally:
            await self._cleanup()

    def stop(self) -> None:
        self._stop_event.set()

    async def _sleep_or_stop(self, seconds: float) -> bool:
        """Sleep up to `seconds`, returning True early if stop() was called."""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    @abc.abstractmethod
    async def _run(self) -> None:
        ...

    async def _cleanup(self) -> None:
        """Optional: release sockets/clients. Overridden by subclasses."""
        return None
