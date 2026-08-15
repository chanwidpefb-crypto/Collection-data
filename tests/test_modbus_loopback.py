"""End-to-end check: a Modbus TCP Server connector exposes a value computed
from an expression on the tag store, and a Modbus TCP Client connector on the
same process reads it back correctly -- exercising the pull-based datastore,
the codec, and both driver classes together against a real TCP socket."""
import asyncio
import socket

import pytest

from app.drivers.codec import DataType, WordOrder
from app.drivers.modbus_client import ModbusClientRegisterSpec, ModbusTcpClientDriver
from app.drivers.modbus_server import ModbusServerRegisterSpec, ModbusTcpServerDriver
from app.models import ModbusArea
from app.tag_store import TagStore


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_server_to_client_roundtrip():
    port = _free_port()
    store = TagStore()
    await store.set("boiler_temp", 123.45, source_connector="seed")

    server = ModbusTcpServerDriver(
        connector_id=1, connector_name="srv", tag_store=store,
        host="127.0.0.1", port=port, unit_id=1,
        registers=[
            ModbusServerRegisterSpec(name="temp_out", area=ModbusArea.HOLDING_REGISTER, address=10,
                                      data_type=DataType.FLOAT32, word_order=WordOrder.CDAB,
                                      expression="boiler_temp * 2", enabled=True),
            ModbusServerRegisterSpec(name="running", area=ModbusArea.COIL, address=0,
                                      data_type=DataType.BOOL, word_order=WordOrder.ABCD,
                                      expression="boiler_temp", enabled=True),
        ],
    )
    server_task = asyncio.ensure_future(server.run_forever())
    await asyncio.sleep(0.3)  # let the listener come up

    client_store = TagStore()
    client = ModbusTcpClientDriver(
        connector_id=2, connector_name="cli", tag_store=client_store,
        host="127.0.0.1", port=port, unit_id=1, timeout_ms=2000, poll_interval_ms=100,
        registers=[
            ModbusClientRegisterSpec(tag_name="mirrored_temp", area=ModbusArea.HOLDING_REGISTER, address=10,
                                      data_type=DataType.FLOAT32, word_order=WordOrder.CDAB,
                                      factor=1.0, offset=0.0, enabled=True),
            ModbusClientRegisterSpec(tag_name="mirrored_running", area=ModbusArea.COIL, address=0,
                                      data_type=DataType.BOOL, word_order=WordOrder.ABCD,
                                      factor=1.0, offset=0.0, enabled=True),
        ],
    )
    client_task = asyncio.ensure_future(client.run_forever())

    try:
        for _ in range(50):
            entry = await client_store.get("mirrored_temp")
            if entry is not None and entry.quality == "good":
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("client never received a good-quality value")

        temp_entry = await client_store.get("mirrored_temp")
        assert temp_entry.value == pytest.approx(246.9, rel=1e-4)

        running_entry = await client_store.get("mirrored_running")
        assert running_entry.value is True

        # update source tag, confirm the server picks it up on next pull (no restart needed)
        await store.set("boiler_temp", 10.0, source_connector="seed")
        await asyncio.sleep(0.5)
        temp_entry = await client_store.get("mirrored_temp")
        assert temp_entry.value == pytest.approx(20.0, rel=1e-4)
    finally:
        client.stop()
        server.stop()
        for t in (client_task, server_task):
            t.cancel()
        await asyncio.gather(client_task, server_task, return_exceptions=True)
