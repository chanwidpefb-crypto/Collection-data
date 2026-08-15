"""Central in-memory store of the latest value for every collected tag.

Modbus/OPC UA client drivers write into it as they poll their source.
Modbus/OPC UA server drivers (and the "factor expression" evaluator) read
from it. A single process-wide instance (`tag_store`) is shared by every
driver via the DriverManager.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
from typing import Optional


@dataclasses.dataclass
class TagEntry:
    tag_name: str
    value: float | int | bool | None
    quality: str  # "good" | "bad" | "uncertain"
    timestamp: datetime.datetime
    source_connector: Optional[str] = None


class TagStore:
    def __init__(self) -> None:
        self._tags: dict[str, TagEntry] = {}
        self._lock = asyncio.Lock()

    async def set(self, tag_name: str, value, quality: str = "good",
                  source_connector: Optional[str] = None) -> None:
        async with self._lock:
            self._tags[tag_name] = TagEntry(
                tag_name=tag_name,
                value=value,
                quality=quality,
                timestamp=datetime.datetime.utcnow(),
                source_connector=source_connector,
            )

    async def get(self, tag_name: str) -> Optional[TagEntry]:
        async with self._lock:
            return self._tags.get(tag_name)

    async def get_all(self) -> dict[str, TagEntry]:
        async with self._lock:
            return dict(self._tags)

    async def snapshot_values(self) -> dict[str, float | int | bool | None]:
        """Tag name -> raw value, for feeding into expression evaluation."""
        async with self._lock:
            return {name: entry.value for name, entry in self._tags.items()
                    if entry.value is not None}

    def get_sync(self, tag_name: str) -> Optional[TagEntry]:
        """Best-effort synchronous read (no lock) for contexts that can't await,
        e.g. the pymodbus server datablock callback."""
        return self._tags.get(tag_name)

    def snapshot_values_sync(self) -> dict[str, float | int | bool | None]:
        return {name: entry.value for name, entry in self._tags.items()
                if entry.value is not None}

    def remove_by_connector(self, connector_name: str) -> None:
        stale = [name for name, entry in self._tags.items()
                 if entry.source_connector == connector_name]
        for name in stale:
            del self._tags[name]


tag_store = TagStore()
