from __future__ import annotations

from dataclasses import dataclass

from pymodbus.client import AsyncModbusTcpClient

from app.drivers.base import BaseDriver
from app.drivers.codec import decode_registers, register_count
from app.models import ModbusArea
from app.tag_store import TagStore


@dataclass
class ModbusClientRegisterSpec:
    tag_name: str
    area: ModbusArea
    address: int
    data_type: str
    word_order: str
    factor: float
    offset: float
    enabled: bool


class ModbusTcpClientDriver(BaseDriver):
    """Polls registers from a remote Modbus TCP device and publishes them as tags."""

    def __init__(self, connector_id: int, connector_name: str, tag_store: TagStore,
                 host: str, port: int, unit_id: int, timeout_ms: int, poll_interval_ms: int,
                 registers: list[ModbusClientRegisterSpec]):
        super().__init__(connector_id, connector_name, tag_store)
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout_s = timeout_ms / 1000
        self.poll_interval_s = poll_interval_ms / 1000
        self.registers = [r for r in registers if r.enabled]
        self._client: AsyncModbusTcpClient | None = None

    async def _run(self) -> None:
        self._client = AsyncModbusTcpClient(self.host, port=self.port, timeout=self.timeout_s)
        while not self._stop_event.is_set():
            if not self._client.connected:
                await self._client.connect()
            if not self._client.connected:
                self.last_error = f"cannot connect to {self.host}:{self.port}"
                await self._mark_all_bad()
                if await self._sleep_or_stop(self.poll_interval_s):
                    break
                continue

            await self._poll_once()
            if await self._sleep_or_stop(self.poll_interval_s):
                break

    async def _poll_once(self) -> None:
        by_area: dict[ModbusArea, list[ModbusClientRegisterSpec]] = {}
        for reg in self.registers:
            by_area.setdefault(reg.area, []).append(reg)

        for area, regs in by_area.items():
            for reg in regs:
                await self._read_one(area, reg)

    async def _read_one(self, area: ModbusArea, reg: ModbusClientRegisterSpec) -> None:
        count = register_count(reg.data_type)
        try:
            if area == ModbusArea.HOLDING_REGISTER:
                rr = await self._client.read_holding_registers(reg.address, count=count, slave=self.unit_id)
            elif area == ModbusArea.INPUT_REGISTER:
                rr = await self._client.read_input_registers(reg.address, count=count, slave=self.unit_id)
            elif area == ModbusArea.COIL:
                rr = await self._client.read_coils(reg.address, count=1, slave=self.unit_id)
            elif area == ModbusArea.DISCRETE_INPUT:
                rr = await self._client.read_discrete_inputs(reg.address, count=1, slave=self.unit_id)
            else:
                raise ValueError(f"unsupported area: {area}")
        except Exception as exc:  # noqa: BLE001 - connection drops, timeouts, etc.
            self.last_error = f"{reg.tag_name}: {exc}"
            await self.tag_store.set(reg.tag_name, None, quality="bad", source_connector=self.connector_name)
            return

        if rr.isError():
            self.last_error = f"{reg.tag_name}: {rr}"
            await self.tag_store.set(reg.tag_name, None, quality="bad", source_connector=self.connector_name)
            return

        if area in (ModbusArea.COIL, ModbusArea.DISCRETE_INPUT):
            raw_value = bool(rr.bits[0])
        else:
            raw_value = decode_registers(rr.registers, reg.data_type, reg.word_order)

        value = raw_value if isinstance(raw_value, bool) else raw_value * reg.factor + reg.offset
        await self.tag_store.set(reg.tag_name, value, quality="good", source_connector=self.connector_name)

    async def _mark_all_bad(self) -> None:
        for reg in self.registers:
            await self.tag_store.set(reg.tag_name, None, quality="bad", source_connector=self.connector_name)

    async def _cleanup(self) -> None:
        if self._client is not None:
            self._client.close()
