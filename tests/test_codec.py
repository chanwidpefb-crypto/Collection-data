import math

import pytest

from app.drivers.codec import DataType, WordOrder, decode_registers, encode_value, register_count

ALL_ORDERS = [WordOrder.ABCD, WordOrder.BADC, WordOrder.CDAB, WordOrder.DCBA]


def test_register_count():
    assert register_count(DataType.INT16) == 1
    assert register_count(DataType.UINT16) == 1
    assert register_count(DataType.INT32) == 2
    assert register_count(DataType.FLOAT32) == 2
    assert register_count(DataType.INT64) == 4
    assert register_count(DataType.FLOAT64) == 4
    assert register_count(DataType.BOOL) == 1


@pytest.mark.parametrize("order", ALL_ORDERS)
def test_int16_roundtrip(order):
    for v in (0, 1, -1, 32767, -32768, 1234):
        regs = encode_value(v, DataType.INT16, order)
        assert decode_registers(regs, DataType.INT16, order) == v


@pytest.mark.parametrize("order", ALL_ORDERS)
def test_uint32_roundtrip(order):
    for v in (0, 1, 4294967295, 305419896):  # 0x12345678
        regs = encode_value(v, DataType.UINT32, order)
        assert len(regs) == 2
        assert decode_registers(regs, DataType.UINT32, order) == v


@pytest.mark.parametrize("order", ALL_ORDERS)
def test_float32_roundtrip(order):
    for v in (0.0, 1.5, -273.15, 3.1415927):
        regs = encode_value(v, DataType.FLOAT32, order)
        decoded = decode_registers(regs, DataType.FLOAT32, order)
        assert math.isclose(decoded, v, rel_tol=1e-6)


@pytest.mark.parametrize("order", ALL_ORDERS)
def test_float64_roundtrip(order):
    for v in (0.0, 1.5, -273.15, 3.14159265358979):
        regs = encode_value(v, DataType.FLOAT64, order)
        assert len(regs) == 4
        decoded = decode_registers(regs, DataType.FLOAT64, order)
        assert math.isclose(decoded, v, rel_tol=1e-12)


@pytest.mark.parametrize("order", ALL_ORDERS)
def test_int64_roundtrip(order):
    for v in (0, -1, 1234567890123, -1234567890123):
        regs = encode_value(v, DataType.INT64, order)
        assert decode_registers(regs, DataType.INT64, order) == v


def test_bool():
    assert decode_registers([1], DataType.BOOL) is True
    assert decode_registers([0], DataType.BOOL) is False
    assert encode_value(True, DataType.BOOL) == [1]
    assert encode_value(False, DataType.BOOL) == [0]


def test_known_wire_values_abcd_uint32():
    # 0x12345678 big-endian "ABCD": hi word 0x1234, lo word 0x5678
    regs = encode_value(0x12345678, DataType.UINT32, WordOrder.ABCD)
    assert regs == [0x1234, 0x5678]


def test_known_wire_values_cdab_uint32():
    # word-swapped: lo word first
    regs = encode_value(0x12345678, DataType.UINT32, WordOrder.CDAB)
    assert regs == [0x5678, 0x1234]


def test_known_wire_values_badc_uint32():
    # byte-swapped within each word, word order unchanged
    regs = encode_value(0x12345678, DataType.UINT32, WordOrder.BADC)
    assert regs == [0x3412, 0x7856]


def test_known_wire_values_dcba_uint32():
    # fully little-endian
    regs = encode_value(0x12345678, DataType.UINT32, WordOrder.DCBA)
    assert regs == [0x7856, 0x3412]


def test_wrong_register_count_raises():
    with pytest.raises(ValueError):
        decode_registers([1], DataType.UINT32)
    with pytest.raises(ValueError):
        decode_registers([1, 2, 3], DataType.FLOAT32)


def test_out_of_range_raises():
    with pytest.raises(ValueError):
        encode_value(70000, DataType.UINT16)
    with pytest.raises(ValueError):
        encode_value(-1, DataType.UINT16)
