from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pymodbus.datastore import ModbusBaseSlaveContext, ModbusServerContext
from pymodbus.server import ModbusTcpServer

from app.drivers.base import BaseDriver
from app.drivers.codec import encode_value, register_count
from app.expression import ExpressionError, evaluate, referenced_names
from app.models import ModbusArea
from app.tag_store import TagStore

_FX_TO_AREA = {
    "c": ModbusArea.COIL,
    "d": ModbusArea.DISCRETE_INPUT,
    "h": ModbusArea.HOLDING_REGISTER,
    "i": ModbusArea.INPUT_REGISTER,
}


@dataclass
class ModbusServerRegisterSpec:
    name: str
    area: ModbusArea
    address: int
    data_type: str
    word_order: str
    expression: str
    enabled: bool


class ExpressionSlaveContext(ModbusBaseSlaveContext):
    """Pull-based Modbus datastore: every read re-evaluates the mapped
    expression against the current tag store, so exposed values are always
    fresh. Writes are only accepted for mappings whose expression is a bare
    tag name (a direct passthrough), in which case the write updates that
    tag in the shared tag store."""

    def __init__(self, tag_store: TagStore, registers: list[ModbusServerRegisterSpec]):
        self.tag_store = tag_store
        self.registers = [r for r in registers if r.enabled]

    def validate(self, fx, address, count=1) -> bool:
        return True

    def getValues(self, fc_as_hex: int, address: int, count: int = 1) -> list[int]:
        area = _FX_TO_AREA[self.decode(fc_as_hex)]
        values = self._build_register_map(area)
        return [values.get(a, 0) for a in range(address, address + count)]

    def setValues(self, fc_as_hex: int, address: int, values: list[int]) -> None:
        area = _FX_TO_AREA[self.decode(fc_as_hex)]
        for offset, value in enumerate(values):
            addr = address + offset
            reg = next((r for r in self.registers if r.area == area and r.address == addr), None)
            if reg is None:
                continue
            names = referenced_names(reg.expression)
            if names == {reg.expression.strip()}:
                asyncio.get_event_loop().create_task(
                    self.tag_store.set(reg.expression.strip(), bool(value) if area in
                                        (ModbusArea.COIL, ModbusArea.DISCRETE_INPUT) else value,
                                        quality="good", source_connector="modbus-write"))

    def _build_register_map(self, area: ModbusArea) -> dict[int, int]:
        tag_values = self.tag_store.snapshot_values_sync()
        result: dict[int, int] = {}
        for reg in self.registers:
            if reg.area != area:
                continue
            try:
                value = evaluate(reg.expression, tag_values)
            except ExpressionError:
                value = 0
            if area in (ModbusArea.COIL, ModbusArea.DISCRETE_INPUT):
                result[reg.address] = 1 if value else 0
            else:
                try:
                    words = encode_value(value, reg.data_type, reg.word_order)
                except (ValueError, OverflowError):
                    words = [0] * register_count(reg.data_type)
                for i, word in enumerate(words):
                    result[reg.address + i] = word
        return result


class ModbusTcpServerDriver(BaseDriver):
    def __init__(self, connector_id: int, connector_name: str, tag_store: TagStore,
                 host: str, port: int, unit_id: int, registers: list[ModbusServerRegisterSpec]):
        super().__init__(connector_id, connector_name, tag_store)
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.registers = registers
        self._server: ModbusTcpServer | None = None

    async def _run(self) -> None:
        slave_ctx = ExpressionSlaveContext(self.tag_store, self.registers)
        context = ModbusServerContext(slaves={self.unit_id: slave_ctx}, single=False)
        self._server = ModbusTcpServer(context, address=(self.host, self.port))
        serve_task = asyncio.ensure_future(self._server.serve_forever())
        await self._stop_event.wait()
        await self._server.shutdown()
        try:
            await serve_task
        except Exception:  # noqa: BLE001 - server task surfaces its own shutdown state
            pass

    async def _cleanup(self) -> None:
        if self._server is not None:
            try:
                await self._server.shutdown()
            except Exception:  # noqa: BLE001 - already shut down
                pass
