from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app import models
from app.drivers.base import BaseDriver
from app.drivers.modbus_client import ModbusClientRegisterSpec, ModbusTcpClientDriver
from app.drivers.modbus_server import ModbusServerRegisterSpec, ModbusTcpServerDriver
from app.drivers.opcua_client import OpcUaClientDriver, OpcUaClientNodeSpec
from app.drivers.opcua_server import OpcUaServerDriver, OpcUaServerNodeSpec
from app.tag_store import TagStore

logger = logging.getLogger("driver.manager")


class RunningDriver:
    def __init__(self, driver: BaseDriver, task: asyncio.Task):
        self.driver = driver
        self.task = task


def build_driver(connector: models.Connector, tag_store: TagStore) -> BaseDriver:
    if connector.type == models.ConnectorType.MODBUS_TCP_CLIENT:
        cfg = connector.modbus_client_config
        if cfg is None:
            raise ValueError("modbus tcp client connector is missing its config")
        registers = [
            ModbusClientRegisterSpec(
                tag_name=r.tag_name, area=r.area, address=r.address, data_type=r.data_type,
                word_order=r.word_order, factor=r.factor, offset=r.offset, enabled=r.enabled,
            )
            for r in connector.modbus_client_registers
        ]
        return ModbusTcpClientDriver(
            connector.id, connector.name, tag_store, cfg.host, cfg.port, cfg.unit_id,
            cfg.timeout_ms, cfg.poll_interval_ms, registers,
        )

    if connector.type == models.ConnectorType.MODBUS_TCP_SERVER:
        cfg = connector.modbus_server_config
        if cfg is None:
            raise ValueError("modbus tcp server connector is missing its config")
        registers = [
            ModbusServerRegisterSpec(
                name=r.name, area=r.area, address=r.address, data_type=r.data_type,
                word_order=r.word_order, expression=r.expression, enabled=r.enabled,
            )
            for r in connector.modbus_server_registers
        ]
        return ModbusTcpServerDriver(
            connector.id, connector.name, tag_store, cfg.host, cfg.port, cfg.unit_id, registers,
        )

    if connector.type == models.ConnectorType.OPCUA_CLIENT:
        cfg = connector.opcua_client_config
        if cfg is None:
            raise ValueError("opc ua client connector is missing its config")
        nodes = [
            OpcUaClientNodeSpec(
                tag_name=n.tag_name, node_id=n.node_id, factor=n.factor, offset=n.offset, enabled=n.enabled,
            )
            for n in connector.opcua_client_nodes
        ]
        return OpcUaClientDriver(
            connector.id, connector.name, tag_store, cfg.endpoint_url, cfg.username, cfg.password,
            cfg.poll_interval_ms, nodes,
        )

    if connector.type == models.ConnectorType.OPCUA_SERVER:
        cfg = connector.opcua_server_config
        if cfg is None:
            raise ValueError("opc ua server connector is missing its config")
        nodes = [
            OpcUaServerNodeSpec(node_name=n.node_name, expression=n.expression, enabled=n.enabled)
            for n in connector.opcua_server_nodes
        ]
        return OpcUaServerDriver(
            connector.id, connector.name, tag_store, cfg.endpoint_url, cfg.server_name,
            cfg.namespace_uri, cfg.publish_interval_ms, nodes,
        )

    raise ValueError(f"unknown connector type: {connector.type}")


class DriverManager:
    def __init__(self, session_factory, tag_store: TagStore):
        self._session_factory = session_factory
        self.tag_store = tag_store
        self._running: dict[int, RunningDriver] = {}
        self._lock = asyncio.Lock()

    async def start_all_enabled(self) -> None:
        db: Session = self._session_factory()
        try:
            connectors = db.query(models.Connector).filter(models.Connector.enabled.is_(True)).all()
            connector_ids = [c.id for c in connectors]
        finally:
            db.close()
        for connector_id in connector_ids:
            await self.start(connector_id)

    async def stop_all(self) -> None:
        async with self._lock:
            ids = list(self._running.keys())
        for connector_id in ids:
            await self.stop(connector_id)

    async def start(self, connector_id: int) -> None:
        async with self._lock:
            if connector_id in self._running:
                return
            db: Session = self._session_factory()
            try:
                connector = db.get(models.Connector, connector_id)
                if connector is None:
                    raise ValueError(f"connector {connector_id} not found")
                driver = build_driver(connector, self.tag_store)
            finally:
                db.close()
            task = asyncio.ensure_future(driver.run_forever())
            self._running[connector_id] = RunningDriver(driver, task)
            logger.info("started connector %s (%s)", connector_id, driver.connector_name)

    async def stop(self, connector_id: int) -> None:
        async with self._lock:
            running = self._running.pop(connector_id, None)
        if running is None:
            return
        running.driver.stop()
        running.task.cancel()
        try:
            await running.task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 - task may have crashed already
            pass
        self.tag_store.remove_by_connector(running.driver.connector_name)
        logger.info("stopped connector %s", connector_id)

    async def restart(self, connector_id: int) -> None:
        await self.stop(connector_id)
        await self.start(connector_id)

    def is_running(self, connector_id: int) -> bool:
        return connector_id in self._running

    def last_error(self, connector_id: int) -> str | None:
        running = self._running.get(connector_id)
        return running.driver.last_error if running else None
