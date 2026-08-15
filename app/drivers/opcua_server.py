from __future__ import annotations

from dataclasses import dataclass

from asyncua import Server, ua

from app.drivers.base import BaseDriver
from app.expression import ExpressionError, evaluate
from app.tag_store import TagStore


@dataclass
class OpcUaServerNodeSpec:
    node_name: str
    expression: str
    enabled: bool


class OpcUaServerDriver(BaseDriver):
    """Runs an OPC UA server exposing a folder of variables computed from the
    tag store's factor expressions, refreshed at `publish_interval_ms`."""

    def __init__(self, connector_id: int, connector_name: str, tag_store: TagStore,
                 endpoint_url: str, server_name: str, namespace_uri: str,
                 publish_interval_ms: int, nodes: list[OpcUaServerNodeSpec]):
        super().__init__(connector_id, connector_name, tag_store)
        self.endpoint_url = endpoint_url
        self.server_name = server_name
        self.namespace_uri = namespace_uri
        self.publish_interval_s = publish_interval_ms / 1000
        self.node_specs = [n for n in nodes if n.enabled]
        self._server: Server | None = None
        self._ua_nodes: dict[str, object] = {}

    async def _run(self) -> None:
        self._server = Server()
        await self._server.init()
        self._server.set_endpoint(self.endpoint_url)
        self._server.set_server_name(self.server_name)
        idx = await self._server.register_namespace(self.namespace_uri)

        objects = self._server.get_objects_node()
        folder = await objects.add_object(ua.NodeId(f"{self.connector_name}", idx), self.connector_name)
        for spec in self.node_specs:
            var = await folder.add_variable(ua.NodeId(f"{self.connector_name}.{spec.node_name}", idx),
                                              spec.node_name, 0.0)
            await var.set_writable(False)
            self._ua_nodes[spec.node_name] = var

        async with self._server:
            while not self._stop_event.is_set():
                await self._publish_once()
                if await self._sleep_or_stop(self.publish_interval_s):
                    break

    async def _publish_once(self) -> None:
        tag_values = await self.tag_store.snapshot_values()
        for spec in self.node_specs:
            var = self._ua_nodes[spec.node_name]
            try:
                value = evaluate(spec.expression, tag_values)
            except ExpressionError as exc:
                self.last_error = f"{spec.node_name}: {exc}"
                continue
            try:
                await var.write_value(float(value) if not isinstance(value, bool) else value)
            except Exception as exc:  # noqa: BLE001 - transient write failure
                self.last_error = f"{spec.node_name}: {exc}"

    async def _cleanup(self) -> None:
        pass  # `async with self._server` above already calls server.stop()
