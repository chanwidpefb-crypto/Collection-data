from __future__ import annotations

from dataclasses import dataclass

from asyncua import Client

from app.drivers.base import BaseDriver
from app.tag_store import TagStore


@dataclass
class OpcUaClientNodeSpec:
    tag_name: str
    node_id: str
    factor: float
    offset: float
    enabled: bool


class OpcUaClientDriver(BaseDriver):
    """Polls nodes from a remote OPC UA server and publishes them as tags."""

    def __init__(self, connector_id: int, connector_name: str, tag_store: TagStore,
                 endpoint_url: str, username: str | None, password: str | None,
                 poll_interval_ms: int, nodes: list[OpcUaClientNodeSpec]):
        super().__init__(connector_id, connector_name, tag_store)
        self.endpoint_url = endpoint_url
        self.username = username
        self.password = password
        self.poll_interval_s = poll_interval_ms / 1000
        self.nodes = [n for n in nodes if n.enabled]
        self._client: Client | None = None
        self._connected = False

    async def _run(self) -> None:
        self._client = Client(url=self.endpoint_url)
        if self.username:
            self._client.set_user(self.username)
        if self.password:
            self._client.set_password(self.password)

        while not self._stop_event.is_set():
            if not self._connected:
                try:
                    await self._client.connect()
                    self._connected = True
                except Exception as exc:  # noqa: BLE001 - network/auth errors
                    self.last_error = f"connect failed: {exc}"
                    await self._mark_all_bad()
                    if await self._sleep_or_stop(self.poll_interval_s):
                        break
                    continue

            await self._poll_once()
            if await self._sleep_or_stop(self.poll_interval_s):
                break

    async def _poll_once(self) -> None:
        for spec in self.nodes:
            try:
                node = self._client.get_node(spec.node_id)
                raw_value = await node.read_value()
            except Exception as exc:  # noqa: BLE001 - node errors, disconnects
                self.last_error = f"{spec.tag_name}: {exc}"
                self._connected = False
                await self.tag_store.set(spec.tag_name, None, quality="bad", source_connector=self.connector_name)
                continue

            if isinstance(raw_value, bool):
                value = raw_value
            elif isinstance(raw_value, (int, float)):
                value = raw_value * spec.factor + spec.offset
            else:
                value = raw_value
            await self.tag_store.set(spec.tag_name, value, quality="good", source_connector=self.connector_name)

    async def _mark_all_bad(self) -> None:
        for spec in self.nodes:
            await self.tag_store.set(spec.tag_name, None, quality="bad", source_connector=self.connector_name)

    async def _cleanup(self) -> None:
        if self._client is not None and self._connected:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001 - best-effort on shutdown
                pass
